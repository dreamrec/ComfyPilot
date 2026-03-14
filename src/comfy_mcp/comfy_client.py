"""Async HTTP + WebSocket client for the ComfyUI API.

Handles connection pooling, auth headers, retries, and error mapping.
WebSocket methods (ws_connect, watch_execution) are implemented in Task 10.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from comfy_mcp.errors import ComfyAPIError, ComfyConnectionError, ComfyTimeoutError


class ComfyClient:
    """Async client for ComfyUI REST API and WebSocket."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        ws_reconnect_max: int = 5,
        timeout: float = 30.0,
        max_retries: int = 2,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.ws_reconnect_max = ws_reconnect_max
        self.timeout = timeout
        self.max_retries = max_retries
        self._http: httpx.AsyncClient | None = None
        self._client_id: str = str(uuid.uuid4())

    async def connect(self) -> None:
        """Initialize the HTTP client with connection pooling."""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    async def close(self) -> None:
        """Close HTTP client and release resources."""
        if self._http:
            await self._http.aclose()
            self._http = None

    def _ensure_connected(self) -> httpx.AsyncClient:
        if self._http is None:
            raise ComfyConnectionError(
                "NOT_CONNECTED",
                "Client not connected",
                "Call client.connect() first",
            )
        return self._http

    async def get(self, path: str) -> Any:
        """HTTP GET with error mapping. Returns parsed JSON (dict or list)."""
        http = self._ensure_connected()
        try:
            resp = await http.get(path)
        except httpx.ConnectError as e:
            raise ComfyConnectionError(
                "CONNECTION_REFUSED",
                f"Cannot connect to ComfyUI at {self.base_url}",
                "Check that ComfyUI is running and the URL is correct",
                retry_possible=True,
                details={"url": self.base_url, "error": str(e)},
            ) from e
        except httpx.TimeoutException as e:
            raise ComfyTimeoutError(
                "REQUEST_TIMEOUT",
                f"Request to {path} timed out",
                "Increase COMFY_TIMEOUT or check ComfyUI load",
                retry_possible=True,
            ) from e
        self._check_status(resp, path)
        return resp.json()

    async def post(self, path: str, data: Any = None) -> Any:
        """HTTP POST with error mapping."""
        http = self._ensure_connected()
        try:
            resp = await http.post(path, json=data)
        except httpx.ConnectError as e:
            raise ComfyConnectionError(
                "CONNECTION_REFUSED",
                f"Cannot connect to ComfyUI at {self.base_url}",
                "Check that ComfyUI is running and the URL is correct",
                retry_possible=True,
            ) from e
        except httpx.TimeoutException as e:
            raise ComfyTimeoutError(
                "REQUEST_TIMEOUT",
                f"POST to {path} timed out",
                "Increase COMFY_TIMEOUT or check ComfyUI load",
                retry_possible=True,
            ) from e
        self._check_status(resp, path)
        return resp.json()

    def _check_status(self, resp: httpx.Response, path: str) -> None:
        """Raise ComfyAPIError for non-2xx responses."""
        if resp.is_success:
            return
        code = resp.status_code
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text[:500]}
        raise ComfyAPIError(
            error_code=f"HTTP_{code}",
            message=f"ComfyUI returned {code} for {path}",
            suggestion=self._suggestion_for_status(code),
            retry_possible=code >= 500,
            details={"status_code": code, "path": path, "response": body},
        )

    @staticmethod
    def _suggestion_for_status(code: int) -> str:
        suggestions = {
            400: "Check request parameters and workflow format",
            401: "Check COMFY_API_KEY is correct",
            403: "Access denied — check ComfyUI auth configuration",
            404: "Endpoint not found — check ComfyUI version supports this API",
            500: "ComfyUI internal error — retry or check server logs",
            503: "ComfyUI is busy — wait and retry",
        }
        return suggestions.get(code, f"Unexpected HTTP {code}")

    # ── High-Level Methods ──

    async def get_system_stats(self) -> dict[str, Any]:
        return await self.get("/system_stats")

    async def get_queue(self) -> dict[str, Any]:
        return await self.get("/queue")

    async def get_history(self, prompt_id: str | None = None, max_items: int = 200) -> dict[str, Any]:
        if prompt_id:
            return await self.get(f"/history/{prompt_id}")
        return await self.get(f"/history?max_items={max_items}")

    async def get_object_info(self, node_type: str | None = None) -> dict[str, Any]:
        if node_type:
            return await self.get(f"/object_info/{node_type}")
        return await self.get("/object_info")

    async def get_models(self, folder: str) -> list[str]:
        result = await self.get(f"/models/{folder}")
        # ComfyUI returns a list directly for /models/{folder}
        if isinstance(result, list):
            return result
        return result.get("models", [])

    async def get_features(self) -> dict[str, Any]:
        return await self.get("/api/features")

    async def get_extensions(self) -> list[str]:
        result = await self.get("/api/extensions")
        if isinstance(result, list):
            return result
        return result.get("extensions", [])

    async def get_embeddings(self) -> list[str]:
        result = await self.get("/embeddings")
        if isinstance(result, list):
            return result
        return result.get("embeddings", [])

    async def queue_prompt(self, workflow: dict, front: bool = False) -> dict[str, Any]:
        data = {
            "prompt": workflow,
            "client_id": self._client_id,
        }
        if front:
            data["front"] = True
        return await self.post("/prompt", data)

    async def cancel_prompt(self, prompt_id: str) -> dict[str, Any]:
        return await self.post("/queue", {"delete": [prompt_id]})

    async def interrupt(self) -> dict[str, Any]:
        return await self.post("/interrupt")

    async def clear_queue(self) -> dict[str, Any]:
        return await self.post("/queue", {"clear": True})

    async def free_vram(self, unload_models: bool = False, free_memory: bool = False) -> dict[str, Any]:
        data = {}
        if unload_models:
            data["unload_models"] = True
        if free_memory:
            data["free_memory"] = True
        return await self.post("/free", data)

    async def upload_image(
        self,
        file_bytes: bytes,
        filename: str,
        subfolder: str = "",
        image_type: str = "input",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Upload an image to ComfyUI. Uses multipart form data."""
        http = self._ensure_connected()
        files = {"image": (filename, file_bytes, "image/png")}
        data = {"type": image_type, "overwrite": str(overwrite).lower()}
        if subfolder:
            data["subfolder"] = subfolder
        resp = await http.post("/upload/image", files=files, data=data)
        self._check_status(resp, "/upload/image")
        return resp.json()

    async def get_image(
        self,
        filename: str,
        subfolder: str = "",
        image_type: str = "output",
    ) -> bytes:
        """Download an image from ComfyUI. Returns raw bytes."""
        http = self._ensure_connected()
        params = {"filename": filename, "type": image_type}
        if subfolder:
            params["subfolder"] = subfolder
        resp = await http.get("/view", params=params)
        self._check_status(resp, "/view")
        return resp.content

    async def delete_history(self, prompt_id: str) -> dict[str, Any]:
        return await self.post("/history", {"delete": [prompt_id]})

    async def clear_history(self) -> dict[str, Any]:
        return await self.post("/history", {"clear": True})

"""Async HTTP + WebSocket client for the ComfyUI API.

Handles connection pooling, auth headers, retries, and error mapping.
WebSocket methods (ws_connect, watch_execution) are implemented in Task 10.
"""

from __future__ import annotations

import uuid
from urllib.parse import urlencode
from typing import Any

import httpx

from comfy_mcp.errors import ComfyAPIError, ComfyConnectionError, ComfyTimeoutError


class ComfyClient:
    """Async client for ComfyUI REST API and WebSocket."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        auth_method: str = "auto",  # "auto", "bearer", "x-api-key"
        ws_reconnect_max: int = 5,
        timeout: float = 30.0,
        max_retries: int = 2,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.auth_method = auth_method
        self.ws_reconnect_max = ws_reconnect_max
        self.timeout = timeout
        self.max_retries = max_retries
        self._http: httpx.AsyncClient | None = None
        self._client_id: str = str(uuid.uuid4())
        self.capabilities: dict = {
            "profile": "unknown",
            "version": None,
            "ws_available": True,
            "features": [],
            "auth_method": auth_method if api_key else "none",
        }

    async def connect(self) -> None:
        """Initialize the HTTP client with connection pooling."""
        headers = {}
        if self.api_key:
            method = self.auth_method
            if method == "auto":
                _CLOUD_DOMAINS = ("api.comfy", "cloud.comfy.org")
                method = "x-api-key" if any(d in self.base_url for d in _CLOUD_DOMAINS) else "bearer"
            if method == "x-api-key":
                headers["X-API-Key"] = self.api_key
            else:
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

    async def probe_capabilities(self) -> dict:
        """Probe the connected ComfyUI instance for capabilities."""
        try:
            stats = await self.get("/system_stats")
            system = stats.get("system", {})
            self.capabilities["version"] = system.get("comfyui_version")
            self.capabilities["profile"] = "local"
        except Exception:
            try:
                stats = await self.get("/api/system_stats")
                self.capabilities["profile"] = "cloud"
                self.capabilities["version"] = stats.get("system", {}).get("comfyui_version")
            except Exception:
                self.capabilities["profile"] = "unknown"

        try:
            features = await self.get_features()
            self.capabilities["features"] = features
        except Exception:
            self.capabilities["features"] = []

        self.capabilities["ws_available"] = self.capabilities["profile"] == "local"
        return self.capabilities

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

    def _route(self, local_path: str, cloud_path: str | None = None) -> str:
        """Return the correct local/cloud route for a path."""
        if self._is_cloud():
            return cloud_path or f"/api{local_path}"
        return local_path

    @staticmethod
    def _normalize_history_item(result: Any, prompt_id: str) -> dict[str, Any]:
        """Normalize a single cloud history item to the local dict shape."""
        if isinstance(result, dict):
            if prompt_id in result:
                return result
            if result.get("prompt_id") == prompt_id:
                return {prompt_id: result}
        return {}

    @staticmethod
    def _normalize_history_list(result: Any) -> dict[str, Any]:
        """Normalize cloud history list responses to the local dict shape."""
        if not isinstance(result, dict):
            return {}
        history = result.get("history")
        if not isinstance(history, list):
            return result
        normalized: dict[str, Any] = {}
        for entry in history:
            if not isinstance(entry, dict):
                continue
            prompt_id = entry.get("prompt_id")
            if prompt_id:
                normalized[str(prompt_id)] = entry
        return normalized

    def build_view_url(self, filename: str, subfolder: str = "", image_type: str = "output") -> str:
        """Build the correct local/cloud URL for viewing an image."""
        params = urlencode({"filename": filename, "type": image_type, "subfolder": subfolder})
        return f"{self.base_url}{self._route('/view')}?{params}"

    async def get_system_stats(self) -> dict[str, Any]:
        return await self.get(self._route("/system_stats"))

    async def get_queue(self) -> dict[str, Any]:
        return await self.get(self._route("/queue"))

    async def get_history(self, prompt_id: str | None = None, max_items: int = 200) -> dict[str, Any]:
        if prompt_id:
            result = await self.get(
                self._route(
                    f"/history/{prompt_id}",
                    f"/api/history_v2/{prompt_id}",
                )
            )
            if self._is_cloud():
                return self._normalize_history_item(result, prompt_id)
            return result
        result = await self.get(
            self._route(
                f"/history?max_items={max_items}",
                f"/api/history_v2?max_items={max_items}",
            )
        )
        if self._is_cloud():
            return self._normalize_history_list(result)
        return result

    async def get_object_info(self, node_type: str | None = None) -> dict[str, Any]:
        if node_type:
            return await self.get(self._route(f"/object_info/{node_type}"))
        return await self.get(self._route("/object_info"))

    async def get_models(self, folder: str) -> list[str]:
        result = await self.get(self._route(f"/models/{folder}", f"/api/experiment/models/{folder}"))
        # Local ComfyUI returns a list directly; cloud experimental models return
        # objects that include a "name" field.
        if isinstance(result, list):
            if result and isinstance(result[0], dict):
                return [item.get("name", "") for item in result if isinstance(item, dict) and item.get("name")]
            return result
        return result.get("models", [])

    def _is_cloud(self) -> bool:
        return self.capabilities.get("profile") == "cloud"

    async def get_features(self) -> Any:
        path = "/api/features" if self._is_cloud() else "/features"
        return await self.get(path)

    async def get_extensions(self) -> list[str]:
        path = "/api/extensions" if self._is_cloud() else "/extensions"
        result = await self.get(path)
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
        return await self.post(self._route("/prompt"), data)

    async def cancel_prompt(self, prompt_id: str) -> dict[str, Any]:
        return await self.post(self._route("/queue"), {"delete": [prompt_id]})

    async def interrupt(self) -> dict[str, Any]:
        return await self.post(self._route("/interrupt"), {})

    async def clear_queue(self) -> dict[str, Any]:
        return await self.post(self._route("/queue"), {"clear": True})

    async def free_vram(self, unload_models: bool = False, free_memory: bool = False) -> dict[str, Any]:
        data = {}
        if unload_models:
            data["unload_models"] = True
        if free_memory:
            data["free_memory"] = True
        return await self.post(self._route("/free"), data)

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
        upload_path = self._route("/upload/image")
        resp = await http.post(upload_path, files=files, data=data)
        self._check_status(resp, upload_path)
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
        view_path = self._route("/view")
        resp = await http.get(view_path, params=params)
        self._check_status(resp, view_path)
        return resp.content

    async def delete_history(self, prompt_id: str) -> dict[str, Any]:
        return await self.post(self._route("/history"), {"delete": [prompt_id]})

    async def clear_history(self) -> dict[str, Any]:
        return await self.post(self._route("/history"), {"clear": True})

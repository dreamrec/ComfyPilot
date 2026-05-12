"""Async HTTP + WebSocket client for the ComfyUI API.

Handles connection pooling, auth headers, retries, and error mapping.
WebSocket methods (ws_connect, watch_execution) are implemented in Task 10.
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlparse

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

    def _is_cloud(self) -> bool:
        host = (urlparse(self.base_url).hostname or "").lower()
        return host in {"cloud.comfy.org", "api.comfy.org"} or host.endswith(".cloud.comfy.org")

    def get_auth_headers(self) -> dict[str, str]:
        """Build auth headers for HTTP and WebSocket calls."""
        headers: dict[str, str] = {}
        if not self.api_key:
            return headers

        method = self.auth_method
        if method == "auto":
            method = "x-api-key" if self._is_cloud() else "bearer"

        if method == "x-api-key":
            headers["X-API-Key"] = self.api_key
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def connect(self) -> None:
        """Initialize the HTTP client with connection pooling."""
        headers = self.get_auth_headers()
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
            # Frontend version exposed since ComfyUI v0.3.46 - useful for
            # gating UI-side feature checks (subgraph editor, Nodes 2.0).
            self.capabilities["frontend_version"] = system.get("comfyui_frontend_version") or ""
            self.capabilities["profile"] = "local"
        except Exception:
            try:
                stats = await self.get("/api/system_stats")
                self.capabilities["profile"] = "cloud"
                self.capabilities["version"] = stats.get("system", {}).get("comfyui_version")
                self.capabilities["frontend_version"] = (
                    stats.get("system", {}).get("comfyui_frontend_version") or ""
                )
            except Exception:
                self.capabilities["profile"] = "unknown"
                self.capabilities["frontend_version"] = ""

        try:
            features = await self.get_features()
            # ComfyUI returns either a list (historical) or a dict of feature
            # flags (v0.17+, e.g. {"progress_text": "binary", ...}). Preserve
            # whichever shape arrived; drop only unexpected types.
            if isinstance(features, (list, dict)):
                self.capabilities["features"] = features
            else:
                self.capabilities["features"] = []
        except Exception:
            self.capabilities["features"] = []

        # CacheProvider API was added in v0.18.0 to allow external distributed
        # caching. When present, /features will surface either a "cache_provider"
        # string (or a "cache" object). Default to None when absent.
        feats = self.capabilities["features"]
        cache_provider = None
        if isinstance(feats, dict):
            raw = feats.get("cache_provider") or feats.get("cache")
            if isinstance(raw, str):
                cache_provider = raw
            elif isinstance(raw, dict):
                cache_provider = raw.get("provider") or raw.get("type")
        self.capabilities["cache_provider"] = cache_provider

        # Record the actual auth header style that will be used, not the
        # unresolved "auto" literal. Consumers of comfy://server/capabilities
        # can then introspect the final choice without re-running resolution.
        if self.api_key:
            actual = self.auth_method
            if actual == "auto":
                actual = "x-api-key" if self._is_cloud() else "bearer"
            self.capabilities["auth_method"] = actual
        else:
            self.capabilities["auth_method"] = "none"

        # Probe WebSocket reachability instead of hardcoding by profile.
        # Cloud ComfyUI (cloud.comfy.org/ws) does expose a WebSocket; the old
        # 'ws_available = profile == "local"' was overly conservative.
        self.capabilities["ws_available"] = await self._probe_ws_available()

        # Cloud tier detection (Comfy Cloud: free / standard / creator / pro).
        # Local installs have no tier - set to None. Cloud installs may
        # surface tier info via a user-info endpoint; if absent, infer from
        # behaviour (free tier returns 403 on /api/prompt).
        self.capabilities["tier"] = await self._probe_cloud_tier()

        # OpenAPI 3.1 (ComfyUI v0.20.0+). Surface the spec version so agents
        # can decide whether they can rely on schema-backed endpoint discovery.
        try:
            spec = await self.get_openapi_spec()
        except Exception:
            spec = None
        if isinstance(spec, dict):
            self.capabilities["openapi_version"] = spec.get("openapi")
        else:
            self.capabilities["openapi_version"] = None

        return self.capabilities

    async def _probe_cloud_tier(self) -> str | None:
        """Infer Comfy Cloud subscription tier when relevant.

        For local profiles, returns None (no tier concept). For cloud
        profiles, tries the user/account endpoints first; falls back to
        behavioural inference (free tier returns 403 on /api/object_info).
        """
        if self.capabilities.get("profile") != "cloud":
            return None

        # Try a few user-info endpoints. Real shape varies across forks.
        for path in ("/api/user", "/user", "/api/account", "/api/me"):
            try:
                payload = await self.get(path)
            except Exception:
                continue
            if isinstance(payload, dict):
                for key in ("tier", "plan", "subscription_tier", "subscription"):
                    val = payload.get(key)
                    if isinstance(val, str) and val:
                        return val.lower()
                    if isinstance(val, dict):
                        name = val.get("name") or val.get("tier")
                        if isinstance(name, str) and name:
                            return name.lower()

        # Fall-back: probe a paid-tier-only endpoint. /api/object_info is
        # observed to return 403 on the free tier; treat 403 (and only 403)
        # as `free`. A 404 means the endpoint isn't exposed by this fork,
        # and network errors mean the probe is inconclusive - both return
        # None so the caller doesn't false-positive on transient failures.
        try:
            await self.get("/api/object_info")
            return "paid"  # exact tier unknown but writes are unblocked
        except ComfyAPIError as e:
            if e.error_code == "HTTP_403":
                return "free"
            return None
        except Exception:
            return None

    async def _probe_ws_available(self) -> bool:
        """Attempt a short-timeout WS handshake and report success."""
        try:
            import asyncio as _asyncio

            import websockets
        except ImportError:
            return False

        base = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{base}/ws?clientId={self._client_id}"
        try:
            headers = self.get_auth_headers()
            kwargs: dict[str, object] = {}
            if headers:
                kwargs["additional_headers"] = headers
            conn = websockets.connect(ws_url, **kwargs)
            # Open & close immediately - the probe only cares about handshake
            ws = await _asyncio.wait_for(conn, timeout=3.0)
            try:
                await ws.close()
            finally:
                # websockets >=13 exposes close() on the handshake object
                pass
            return True
        except Exception:
            return False

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

    async def _get_profiled_endpoint(self, local_path: str, cloud_path: str) -> Any:
        """Fetch local/cloud endpoints with a sensible fallback order."""
        profile = self.capabilities.get("profile", "unknown")
        use_cloud_path = profile == "cloud" or (profile == "unknown" and self._is_cloud())
        primary = cloud_path if use_cloud_path else local_path
        secondary = local_path if use_cloud_path else cloud_path

        try:
            return await self.get(primary)
        except ComfyAPIError as exc:
            if exc.error_code == "HTTP_404" and secondary != primary:
                return await self.get(secondary)
            raise

    @staticmethod
    def _suggestion_for_status(code: int) -> str:
        suggestions = {
            400: "Check request parameters and workflow format",
            401: "Check COMFY_API_KEY is correct",
            403: "Access denied - check ComfyUI auth configuration",
            404: "Endpoint not found - check ComfyUI version supports this API",
            500: "ComfyUI internal error - retry or check server logs",
            503: "ComfyUI is busy - wait and retry",
        }
        return suggestions.get(code, f"Unexpected HTTP {code}")

    # High-level methods

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

    async def get_model_folders(self) -> list[str]:
        """List every model-folder name the connected ComfyUI exposes.

        ComfyUI's `GET /models` (no folder suffix) returns the live list of
        folder types it knows about. For v0.17+ this includes at least:
        checkpoints, diffusion_models, loras, vae, clip, text_encoders,
        clip_vision, controlnet, upscale_models, style_models, embeddings,
        hypernetworks, gligen, unet, diffusers. Returns [] on error so
        callers can decide whether to fall back to a static default list.
        """
        try:
            result = await self._get_profiled_endpoint("/models", "/api/models")
        except Exception:
            return []
        if isinstance(result, list):
            return [str(x) for x in result]
        if isinstance(result, dict):
            for key in ("folders", "models"):
                val = result.get(key)
                if isinstance(val, list):
                    return [str(x) for x in val]
        return []

    async def get_models(self, folder: str) -> list[str]:
        result = await self.get(f"/models/{folder}")
        # ComfyUI returns a list directly for /models/{folder}
        if isinstance(result, list):
            return result
        return result.get("models", [])

    async def get_features(self) -> dict[str, Any]:
        return await self._get_profiled_endpoint("/features", "/api/features")

    async def get_extensions(self) -> list[str]:
        result = await self._get_profiled_endpoint("/extensions", "/api/extensions")
        if isinstance(result, list):
            return result
        return result.get("extensions", [])

    async def get_embeddings(self) -> list[str]:
        result = await self.get("/embeddings")
        if isinstance(result, list):
            return result
        return result.get("embeddings", [])

    async def get_workflow_templates(self) -> dict[str, Any]:
        """Fetch workflow templates mapped by custom-node package.

        ComfyUI v0.17+ exposes /workflow_templates for frontend template discovery.
        Falls back gracefully when the endpoint isn't available.
        """
        return await self._get_profiled_endpoint("/workflow_templates", "/api/workflow_templates")

    async def get_openapi_spec(self) -> dict[str, Any] | None:
        """Fetch the OpenAPI 3.1 spec ComfyUI v0.20+ serves at /openapi.json.

        Returns the parsed spec on success, or None when the endpoint is
        unavailable (older ComfyUI builds, or a profile that disables it).
        Older versions used /openapi or /api/openapi; we try the canonical
        path first and fall back if needed.
        """
        try:
            spec = await self._get_profiled_endpoint("/openapi.json", "/api/openapi.json")
        except Exception:
            try:
                spec = await self._get_profiled_endpoint("/openapi", "/api/openapi")
            except Exception:
                return None
        return spec if isinstance(spec, dict) else None

    async def get_node_docs(self, class_type: str) -> dict[str, Any] | None:
        """Fetch embedded documentation for a node class (ComfyUI v0.3.68+).

        v0.3.68 shipped an embedded-documentation system that exposes
        markdown / structured docs per node. The exact endpoint varies
        across forks - probe a few common shapes, fall back to None.

        Falling back to object_info[class_type].description happens in the
        caller; this method strictly hits the docs endpoint.

        `class_type` is interpolated into the URL path, so we reject any
        value containing path separators or percent-encoded equivalents.
        Without this guard a hostile caller could probe arbitrary endpoints
        on the ComfyUI host (httpx normalises `..` segments before sending).
        """
        if not class_type:
            return None
        if any(c in class_type for c in ("/", "\\", "..", "%2f", "%2F", "%5c", "%5C", "?", "#")):
            return None
        for path in (
            f"/docs/{class_type}",
            f"/api/docs/{class_type}",
            f"/node_docs/{class_type}",
            f"/api/node_docs/{class_type}",
        ):
            try:
                result = await self.get(path)
            except Exception:
                continue
            if isinstance(result, dict):
                return result
            if isinstance(result, str):
                return {"description": result}
        return None

    async def get_published_subgraphs(self) -> list[dict[str, Any]]:
        """Fetch native published subgraphs from ComfyUI (v0.3.67+).

        ComfyUI v0.3.67 added an endpoint that lists subgraphs custom-node
        packages have registered. v0.3.66 made the frontend's subgraph
        widget edit-capable. We surface these alongside ComfyPilot's own
        blueprints so agents can pick from either source.

        Returns a list of {name, description?, nodes?} dicts. Returns []
        when the endpoint is absent so callers can fall back gracefully.
        """
        for path in (
            "/subgraphs",
            "/api/subgraphs",
            "/customnode/subgraphs",
            "/api/customnode/subgraphs",
        ):
            try:
                result = await self.get(path)
            except Exception:
                continue
            if isinstance(result, list):
                return [r for r in result if isinstance(r, dict)]
            if isinstance(result, dict):
                items = result.get("subgraphs") or result.get("items")
                if isinstance(items, list):
                    return [r for r in items if isinstance(r, dict)]
        return []

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

"""Async HTTP + WebSocket client for the ComfyUI API.

Handles connection pooling, auth headers, retries, and error mapping.
WebSocket methods (ws_connect, watch_execution) are implemented in Task 10.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx

from comfy_mcp import __version__
from comfy_mcp.errors import ComfyAPIError, ComfyConnectionError, ComfyTimeoutError


COMFYUI_TESTED_MIN = "0.20.0"
COMFYUI_TESTED_MAX = "0.31.1"


def _version_tuple(value: str | None) -> tuple[int, ...] | None:
    """Parse the numeric prefix of a ComfyUI version without adding a dependency."""
    if not value:
        return None
    match = re.match(r"^v?(\d+(?:\.\d+){0,3})", str(value).strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _version_at_least(value: str | None, minimum: str) -> bool:
    parsed = _version_tuple(value)
    floor = _version_tuple(minimum)
    if parsed is None or floor is None:
        return False
    width = max(len(parsed), len(floor))
    return parsed + (0,) * (width - len(parsed)) >= floor + (0,) * (width - len(floor))


def _compatibility_status(value: str | None) -> str:
    parsed = _version_tuple(value)
    minimum = _version_tuple(COMFYUI_TESTED_MIN)
    maximum = _version_tuple(COMFYUI_TESTED_MAX)
    if parsed is None or minimum is None or maximum is None:
        return "unknown"
    width = max(len(parsed), len(minimum), len(maximum))
    current = parsed + (0,) * (width - len(parsed))
    floor = minimum + (0,) * (width - len(minimum))
    ceiling = maximum + (0,) * (width - len(maximum))
    if current < floor:
        return "legacy"
    if current > ceiling:
        return "newer_than_tested"
    return "tested"


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
        # ComfyUI v0.25+ forwards this value to partner/API nodes. It gives
        # upstream providers useful provenance without changing prompt data.
        headers["Comfy-Usage-Source"] = f"comfypilot/{__version__}"
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
        stats: dict[str, Any] = {}
        try:
            stats = await self.get("/system_stats")
            system = stats.get("system", {})
            self.capabilities["version"] = system.get("comfyui_version")
            # Frontend version exposed since ComfyUI v0.3.46 - useful for
            # gating UI-side feature checks (subgraph editor, Nodes 2.0).
            self.capabilities["frontend_version"] = (
                system.get("comfyui_frontend_version")
                or system.get("comfyui_frontend_package")
                or system.get("required_frontend_version")
                or ""
            )
            self.capabilities["profile"] = "local"
        except Exception:
            try:
                stats = await self.get("/api/system_stats")
                self.capabilities["profile"] = "cloud"
                self.capabilities["version"] = stats.get("system", {}).get("comfyui_version")
                cloud_system = stats.get("system", {})
                self.capabilities["frontend_version"] = (
                    cloud_system.get("comfyui_frontend_version")
                    or cloud_system.get("comfyui_frontend_package")
                    or cloud_system.get("required_frontend_version")
                    or ""
                )
            except Exception:
                self.capabilities["profile"] = "unknown"
                self.capabilities["frontend_version"] = ""

        system = stats.get("system", {}) if isinstance(stats, dict) else {}
        devices = stats.get("devices", []) if isinstance(stats, dict) else []
        if not isinstance(system, dict):
            system = {}
        if not isinstance(devices, list):
            devices = []
        version = self.capabilities.get("version")
        self.capabilities["compatibility"] = {
            "status": _compatibility_status(version),
            "tested_min": COMFYUI_TESTED_MIN,
            "tested_max": COMFYUI_TESTED_MAX,
        }
        self.capabilities["deploy_environment"] = system.get("deploy_environment")
        package_versions = system.get("comfy_package_versions")
        self.capabilities["comfy_package_versions"] = (
            package_versions if isinstance(package_versions, (list, dict)) else []
        )
        self.capabilities["device_count"] = len(devices)
        self.capabilities["multi_gpu"] = len(devices) > 1

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

        paths = spec.get("paths", {}) if isinstance(spec, dict) else {}
        if not isinstance(paths, dict):
            paths = {}
        self.capabilities["jobs_api"] = (
            "/api/jobs" in paths or _version_at_least(version, "0.20.0")
        )
        self.capabilities["jobs_cancel_api"] = (
            "/api/jobs/{job_id}/cancel" in paths or _version_at_least(version, "0.26.0")
        )

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

    @staticmethod
    def _retry_delay(attempt: int, response: httpx.Response | None = None) -> float:
        """Return a bounded retry delay, respecting a numeric Retry-After header."""
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return min(max(float(retry_after), 0.0), 30.0)
                except ValueError:
                    pass
        return min(0.1 * (2 ** attempt), 2.0)

    async def _request_with_retries(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: Any = None,
        idempotent: bool,
    ) -> httpx.Response:
        """Issue a request and retry only when replaying it is safe.

        Prompt submission is deliberately non-idempotent: a timeout can happen
        after ComfyUI accepted the prompt, so automatically replaying it could
        queue a duplicate. Read requests and explicitly idempotent control
        operations may retry transient transport/429/5xx failures.
        """
        http = self._ensure_connected()
        retry_count = max(0, int(self.max_retries)) if idempotent else 0
        attempts = retry_count + 1
        last_transport_error: httpx.TransportError | None = None

        for attempt in range(attempts):
            try:
                if method == "GET":
                    response = (
                        await http.get(path)
                        if params is None
                        else await http.get(path, params=params)
                    )
                elif method == "POST":
                    response = await http.post(path, json=json_data)
                else:
                    response = await http.request(
                        method, path, params=params, json=json_data
                    )
            except httpx.TransportError as exc:
                last_transport_error = exc
                if attempt < retry_count:
                    await asyncio.sleep(self._retry_delay(attempt))
                    continue
                break

            if response.status_code == 429 or response.status_code >= 500:
                if attempt < retry_count:
                    await asyncio.sleep(self._retry_delay(attempt, response))
                    continue
            return response

        assert last_transport_error is not None
        if isinstance(last_transport_error, httpx.TimeoutException):
            raise ComfyTimeoutError(
                "REQUEST_TIMEOUT",
                f"{method} to {path} timed out after {attempts} attempt(s)",
                "Increase COMFY_TIMEOUT or check ComfyUI load",
                retry_possible=True,
                details={"path": path, "attempts": attempts},
            ) from last_transport_error
        raise ComfyConnectionError(
            "CONNECTION_REFUSED",
            f"Cannot connect to ComfyUI at {self.base_url}",
            "Check that ComfyUI is running and the URL is correct",
            retry_possible=True,
            details={
                "url": self.base_url,
                "path": path,
                "attempts": attempts,
                "error": str(last_transport_error),
            },
        ) from last_transport_error

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """HTTP GET with error mapping. Returns parsed JSON (dict or list)."""
        resp = await self._request_with_retries("GET", path, params=params, idempotent=True)
        self._check_status(resp, path)
        return resp.json()

    async def get_text(self, path: str) -> str:
        """HTTP GET for static text resources such as embedded Markdown docs."""
        resp = await self._request_with_retries("GET", path, idempotent=True)
        self._check_status(resp, path)
        return resp.text

    async def post(self, path: str, data: Any = None, *, idempotent: bool = False) -> Any:
        """HTTP POST with safe retry and tolerant success-body handling.

        Set ``idempotent=True`` only for operations that are safe to replay.
        Successful ComfyUI control routes commonly return an empty body; forks
        may also return plain text. JSON responses retain their parsed shape.
        """
        resp = await self._request_with_retries(
            "POST", path, json_data=data, idempotent=idempotent
        )
        self._check_status(resp, path)
        if resp.status_code == 204 or not resp.content or not resp.text.strip():
            return {}
        try:
            return resp.json()
        except (ValueError, UnicodeDecodeError):
            return resp.text

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
            retry_possible=code == 429 or code >= 500,
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
            429: "ComfyUI is rate-limiting requests - wait and retry",
            500: "ComfyUI internal error - retry or check server logs",
            503: "ComfyUI is busy - wait and retry",
        }
        return suggestions.get(code, f"Unexpected HTTP {code}")

    # High-level methods

    async def get_system_stats(self) -> dict[str, Any]:
        return await self.get("/system_stats")

    async def get_queue(self) -> dict[str, Any]:
        return await self.get("/queue")

    async def get_jobs(
        self,
        *,
        status: str | None = None,
        workflow_id: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List jobs through the canonical ComfyUI v0.20+ jobs namespace."""
        params: dict[str, Any] = {"limit": limit, "sort_order": sort_order}
        if status:
            params["status"] = status
        if workflow_id:
            params["workflow_id"] = workflow_id
        if self._is_cloud():
            aliases = {"created_at": "create_time", "execution_duration": "execution_time"}
            if sort_by:
                params["sort_by"] = aliases.get(sort_by, sort_by)
            if after:
                params["after"] = after
            else:
                params["offset"] = offset
        else:
            aliases = {"create_time": "created_at", "execution_time": "execution_duration"}
            if sort_by:
                params["sort_by"] = aliases.get(sort_by, sort_by)
            # The local API is offset-based through v0.31.1 and ignores `after`.
            params["offset"] = offset
        return await self.get("/api/jobs", params=params)

    async def get_job(self, job_id: str) -> dict[str, Any]:
        """Get a full job record, falling back to legacy history when needed."""
        try:
            result = await self.get(f"/api/jobs/{job_id}")
            return result if isinstance(result, dict) else {"job": result}
        except ComfyAPIError as exc:
            if exc.error_code != "HTTP_404":
                raise
        history = await self.get_history(prompt_id=job_id)
        if isinstance(history, dict) and job_id in history:
            return {"id": job_id, "prompt_id": job_id, **history[job_id]}
        return history if isinstance(history, dict) else {"job": history}

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
        """Fetch an OpenAPI 3.1 spec when the deployment serves one over HTTP.

        Local ComfyUI includes an OpenAPI source file but does not guarantee an
        HTTP route. Return None when unavailable and retain common fork routes.
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
        """Fetch embedded documentation for a node class.

        Official ComfyUI serves localized Markdown as static files under
        ``/docs/<class_type>/<language>.md``. Some forks expose a structured
        JSON route instead, so both contracts are supported.

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
            f"/docs/{class_type}/en.md",
            f"/api/docs/{class_type}/en.md",
            f"/docs/{class_type}.md",
        ):
            try:
                result = await self.get_text(path)
            except Exception:
                continue
            if result.strip():
                return {
                    "description": result,
                    "format": "markdown",
                    "language": "en",
                    "source": path,
                }

        for path in (
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
        """Fetch native published subgraphs from official ComfyUI and forks.

        Official ComfyUI exposes ``/global_subgraphs`` and returns an ID-keyed
        object. Older forks used list-shaped ``/subgraphs`` variants. Normalize
        every supported shape into a list and retain the official subgraph ID.

        Returns a list of {name, description?, nodes?} dicts. Returns []
        when the endpoint is absent so callers can fall back gracefully.
        """
        for path in (
            "/global_subgraphs",
            "/api/global_subgraphs",
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
                if isinstance(items, dict):
                    result = items
                # Canonical local shape: {"<sha256-id>": {name, source, info}}
                if result and all(isinstance(value, dict) for value in result.values()):
                    normalized: list[dict[str, Any]] = []
                    for subgraph_id, value in result.items():
                        entry = dict(value)
                        entry.setdefault("id", str(subgraph_id))
                        normalized.append(entry)
                    return normalized
                if not result:
                    return []
        return []

    async def queue_prompt(
        self,
        workflow: dict,
        front: bool = False,
        *,
        workflow_id: str | None = None,
        workflow_version_id: str | None = None,
        partial_execution_targets: list[str] | None = None,
        extra_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = {
            "prompt": workflow,
            "client_id": self._client_id,
        }
        if front:
            data["front"] = True
        if workflow_id:
            data["workflow_id"] = workflow_id
        if workflow_version_id:
            data["workflow_version_id"] = workflow_version_id
        if partial_execution_targets:
            data["partial_execution_targets"] = partial_execution_targets
        if extra_data:
            data["extra_data"] = extra_data
        return await self.post("/prompt", data)

    async def cancel_prompt(self, prompt_id: str) -> dict[str, Any]:
        """Cancel a running or pending job, with a pre-v0.26 fallback."""
        try:
            result = await self.post(f"/api/jobs/{prompt_id}/cancel", idempotent=True)
            if isinstance(result, dict):
                return {**result, "method": "jobs_api"}
            return {"cancelled": bool(result), "method": "jobs_api"}
        except ComfyAPIError as exc:
            if exc.error_code not in {"HTTP_404", "HTTP_405"}:
                raise
            # A v0.26+ server uses 404 for an unknown job as well as for an
            # unavailable route. Capability probing lets us avoid falsely
            # reporting that an unknown modern job was deleted by /queue.
            if exc.error_code == "HTTP_404" and self.capabilities.get("jobs_cancel_api"):
                return {"cancelled": False, "not_found": True, "method": "jobs_api"}

        # The old queue deletion endpoint only handles pending work. If this
        # ID is currently running, use the legacy interrupt route instead.
        try:
            queue = await self.get_queue()
            running = queue.get("queue_running", []) if isinstance(queue, dict) else []
            running_ids = {
                str(item[1]) for item in running
                if isinstance(item, (list, tuple)) and len(item) > 1
            }
            if prompt_id in running_ids:
                await self.interrupt()
                return {"cancelled": True, "method": "legacy_interrupt"}
        except Exception:
            pass
        result = await self.post("/queue", {"delete": [prompt_id]}, idempotent=True)
        if isinstance(result, dict):
            return {**result, "cancelled": True, "method": "legacy_queue_delete"}
        return {"cancelled": True, "method": "legacy_queue_delete"}

    async def cancel_jobs(self, job_ids: list[str]) -> dict[str, Any]:
        """Cancel multiple jobs through v0.26+, or one-by-one on older builds."""
        try:
            result = await self.post(
                "/api/jobs/cancel", {"job_ids": job_ids}, idempotent=True
            )
            return result if isinstance(result, dict) else {"cancelled": result}
        except ComfyAPIError as exc:
            if exc.error_code not in {"HTTP_404", "HTTP_405"}:
                raise
        results = {job_id: await self.cancel_prompt(job_id) for job_id in job_ids}
        return {"cancelled": job_ids, "fallback": True, "results": results}

    async def interrupt(self) -> dict[str, Any]:
        return await self.post("/interrupt", idempotent=True)

    async def clear_queue(self) -> dict[str, Any]:
        return await self.post("/queue", {"clear": True}, idempotent=True)

    async def free_vram(self, unload_models: bool = False, free_memory: bool = False) -> dict[str, Any]:
        data = {}
        if unload_models:
            data["unload_models"] = True
        if free_memory:
            data["free_memory"] = True
        return await self.post("/free", data, idempotent=True)

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
        return await self.post("/history", {"delete": [prompt_id]}, idempotent=True)

    async def clear_history(self) -> dict[str, Any]:
        return await self.post("/history", {"clear": True}, idempotent=True)

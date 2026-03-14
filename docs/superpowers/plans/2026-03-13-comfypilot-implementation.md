# ComfyPilot Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 71-tool MCP server for live AI control of ComfyUI, with typed outputs, image returns, workflow snapshots, WebSocket progress, VRAM safety, and cross-app routing.

**Architecture:** FastMCP Python server with async httpx/websockets client connecting to ComfyUI REST+WS APIs. Subsystem managers (EventManager, SnapshotManager, TechniqueStore, VRAMGuard, JobTracker) initialized via lifespan context. Tools organized in per-category modules under `tools/`, imported by a central registry.

**Tech Stack:** Python 3.10+, FastMCP (mcp>=1.0), httpx, websockets, Pydantic v2, pytest + pytest-asyncio, hatchling build

**Note on typed outputs:** Tools return `json.dumps()` strings in v1.0 for broad MCP client compatibility. The spec's `outputSchema` / Pydantic output models are a v1.1 enhancement once all tools are stable and the SDK's `structuredContent` support is widely adopted. This is a deliberate phased approach — tool logic stays identical, only the return type annotation and wrapper change.

**Spec:** `docs/superpowers/specs/2026-03-13-comfypilot-design.md`

---

## File Structure

All paths relative to `~/Desktop/ComfyPilot/`.

### Project Root
| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Package config, deps, entrypoint |
| `.mcp.json` | Default MCP server config |
| `conftest.py` | Shared pytest fixtures |

### Source (`src/comfy_mcp/`)
| File | Responsibility |
|------|---------------|
| `__init__.py` | Package marker, version |
| `errors.py` | ComfyError hierarchy (4 exception classes) |
| `comfy_client.py` | Async HTTP+WS client for ComfyUI API |
| `server.py` | FastMCP init, lifespan, CLI entrypoint |
| `tool_registry.py` | Import aggregator for all tool modules |
| `tools/__init__.py` | Package marker |
| `tools/system.py` | 6 system tools |
| `tools/models.py` | 5 model tools |
| `tools/workflow.py` | 8 workflow execution tools |
| `tools/nodes.py` | 6 node inspection tools |
| `tools/images.py` | 5 image/asset tools |
| `tools/history.py` | 5 history tools |
| `tools/snapshots.py` | 6 snapshot tools |
| `tools/memory.py` | 5 technique memory tools |
| `tools/monitoring.py` | 6 monitoring tools |
| `tools/safety.py` | 5 safety tools |
| `tools/builder.py` | 5 workflow builder tools |
| `tools/output_routing.py` | 4 output routing tools |
| `events/__init__.py` | Package marker |
| `events/event_manager.py` | WebSocket event subscription + dispatch |
| `memory/__init__.py` | Package marker |
| `memory/snapshot_manager.py` | LRU-bounded workflow snapshots |
| `memory/technique_store.py` | Reusable workflow recipe library |
| `safety/__init__.py` | Package marker |
| `safety/vram_guard.py` | VRAM monitoring + queue limits |
| `jobs/__init__.py` | Package marker |
| `jobs/job_tracker.py` | Async execution tracking |

### Tests (`tests/`)
| File | Responsibility |
|------|---------------|
| `conftest.py` | Shared fixtures (mock client, mock context) |
| `test_errors.py` | Error hierarchy tests |
| `test_comfy_client.py` | HTTP client tests (mocked transport) |
| `test_system.py` | System tool tests |
| `test_models.py` | Model tool tests |
| `test_workflow.py` | Workflow tool tests |
| `test_nodes.py` | Node tool tests |
| `test_images.py` | Image tool tests |
| `test_history.py` | History tool tests |
| `test_snapshots.py` | Snapshot subsystem + tool tests |
| `test_memory.py` | Technique store + tool tests |
| `test_monitoring.py` | Event manager + monitoring tool tests |
| `test_safety.py` | VRAM guard + safety tool tests |
| `test_builder.py` | Builder tool tests |
| `test_output_routing.py` | Output routing tool tests |
| `test_job_tracker.py` | Job tracker tests |

### Plugin (`mcp/`, `skills/`)
| File | Responsibility |
|------|---------------|
| `mcp/manifest.json` | Plugin manifest |
| `mcp/profiles/claude-desktop.json` | Claude Desktop MCP config |
| `mcp/profiles/cursor.json` | Cursor MCP config |
| `mcp/profiles/generic.json` | Generic MCP client config |
| `skills/comfypilot-core/SKILL.md` | Claude Code skill definition |

---

## Chunk 1: Foundation (Scaffold, Errors, Client, Server)

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.mcp.json`
- Create: `src/comfy_mcp/__init__.py`
- Create: `src/comfy_mcp/errors.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "comfypilot"
version = "1.0.0"
description = "MCP server for live AI control of ComfyUI"
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
authors = [{ name = "silviu" }]
keywords = ["mcp", "comfyui", "ai", "stable-diffusion", "image-generation"]

dependencies = [
    "mcp>=1.0",
    "httpx>=0.27",
    "pydantic>=2.0",
    "websockets>=12.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[project.scripts]
comfypilot = "comfy_mcp.server:main"

[project.urls]
Homepage = "https://github.com/dreamrec/ComfyPilot"
Repository = "https://github.com/dreamrec/ComfyPilot"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/comfy_mcp"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create .mcp.json**

```json
{
  "mcpServers": {
    "comfypilot": {
      "command": "uv",
      "args": ["run", "--directory", ".", "comfypilot"],
      "env": {
        "COMFY_URL": "https://desktop-3lurf0p.tail88651a.ts.net",
        "COMFY_API_KEY": ""
      }
    }
  }
}
```

- [ ] **Step 3: Create package init**

```python
# src/comfy_mcp/__init__.py
"""ComfyPilot — MCP server for live AI control of ComfyUI."""

__version__ = "1.0.0"
```

- [ ] **Step 4: Create error hierarchy**

```python
# src/comfy_mcp/errors.py
"""Structured error hierarchy for ComfyPilot.

Every error carries: error_code, message, suggestion, retry_possible, details.
Tools catch these and return structured error responses to the agent.
"""

from __future__ import annotations


class ComfyError(Exception):
    """Base error with structured fields for actionable error reporting."""

    def __init__(
        self,
        error_code: str,
        message: str,
        suggestion: str = "",
        retry_possible: bool = False,
        details: dict | None = None,
    ):
        self.error_code = error_code
        self.message = message
        self.suggestion = suggestion
        self.retry_possible = retry_possible
        self.details = details
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "suggestion": self.suggestion,
            "retry_possible": self.retry_possible,
            "details": self.details,
        }


class ComfyConnectionError(ComfyError):
    """Cannot reach the ComfyUI instance."""


class ComfyAPIError(ComfyError):
    """ComfyUI returned an HTTP 4xx/5xx error."""


class ComfyTimeoutError(ComfyError):
    """Execution or request timed out."""


class ComfyVRAMError(ComfyError):
    """VRAM exhausted or below safety threshold."""
```

- [ ] **Step 5: Create shared test fixtures**

```python
# tests/conftest.py
"""Shared pytest fixtures for ComfyPilot tests."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_client():
    """Mock ComfyClient with common method stubs."""
    client = AsyncMock()
    client.base_url = "http://localhost:8188"
    client.get = AsyncMock(return_value={})
    client.post = AsyncMock(return_value={})
    client.get_system_stats = AsyncMock(return_value={
        "system": {
            "os": "nt",
            "comfyui_version": "0.17.0",
            "python_version": "3.12.0",
            "pytorch_version": "2.5.0",
            "embedded_python": False,
        },
        "devices": [
            {
                "name": "NVIDIA GeForce RTX 5090",
                "type": "cuda",
                "index": 0,
                "vram_total": 34359738368,
                "vram_free": 30000000000,
                "torch_vram_total": 34359738368,
                "torch_vram_free": 30000000000,
            }
        ],
    })
    client.get_queue = AsyncMock(return_value={
        "queue_running": [],
        "queue_pending": [],
    })
    return client


@pytest.fixture
def mock_ctx(mock_client):
    """Mock MCP Context with lifespan_context wired to mock_client."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {
        "comfy_client": mock_client,
        "event_manager": AsyncMock(),
        "snapshot_manager": MagicMock(),
        "technique_store": MagicMock(),
        "vram_guard": MagicMock(),
        "job_tracker": AsyncMock(),
    }
    ctx.report_progress = AsyncMock()
    ctx.log_info = AsyncMock()
    ctx.log_warning = AsyncMock()
    ctx.log_error = AsyncMock()
    return ctx
```

- [ ] **Step 6: Create directory structure stubs**

```bash
mkdir -p src/comfy_mcp/tools src/comfy_mcp/events src/comfy_mcp/memory src/comfy_mcp/safety src/comfy_mcp/jobs
touch src/comfy_mcp/tools/__init__.py src/comfy_mcp/events/__init__.py src/comfy_mcp/memory/__init__.py src/comfy_mcp/safety/__init__.py src/comfy_mcp/jobs/__init__.py
```

- [ ] **Step 7: Install deps and run initial test**

```bash
cd ~/Desktop/ComfyPilot && uv sync --dev
```

- [ ] **Step 8: Commit scaffold**

```bash
git add -A && git commit -m "feat: project scaffold with pyproject, errors, test fixtures"
```

---

### Task 2: Error Hierarchy Tests

**Files:**
- Create: `tests/test_errors.py`

- [ ] **Step 1: Write error tests**

```python
# tests/test_errors.py
"""Tests for ComfyPilot error hierarchy."""

from comfy_mcp.errors import (
    ComfyAPIError,
    ComfyConnectionError,
    ComfyError,
    ComfyTimeoutError,
    ComfyVRAMError,
)


def test_comfy_error_fields():
    err = ComfyError("TEST_CODE", "test message", "try again", True, {"key": "val"})
    assert err.error_code == "TEST_CODE"
    assert err.message == "test message"
    assert err.suggestion == "try again"
    assert err.retry_possible is True
    assert err.details == {"key": "val"}
    assert str(err) == "test message"


def test_comfy_error_defaults():
    err = ComfyError("CODE", "msg")
    assert err.suggestion == ""
    assert err.retry_possible is False
    assert err.details is None


def test_comfy_error_to_dict():
    err = ComfyError("E001", "broke", "fix it", True, {"x": 1})
    d = err.to_dict()
    assert d == {
        "error_code": "E001",
        "message": "broke",
        "suggestion": "fix it",
        "retry_possible": True,
        "details": {"x": 1},
    }


def test_subclasses_inherit_fields():
    for cls in [ComfyConnectionError, ComfyAPIError, ComfyTimeoutError, ComfyVRAMError]:
        err = cls("SUB", "sub msg", "sub suggestion")
        assert isinstance(err, ComfyError)
        assert err.error_code == "SUB"
        assert err.to_dict()["error_code"] == "SUB"


def test_comfy_error_is_exception():
    err = ComfyError("E", "exception test")
    assert isinstance(err, Exception)
    try:
        raise err
    except ComfyError as caught:
        assert caught.error_code == "E"
```

- [ ] **Step 2: Run tests**

```bash
cd ~/Desktop/ComfyPilot && uv run pytest tests/test_errors.py -v
```
Expected: All 5 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_errors.py && git commit -m "test: error hierarchy tests"
```

---

### Task 3: ComfyClient — HTTP Layer

**Files:**
- Create: `src/comfy_mcp/comfy_client.py`
- Create: `tests/test_comfy_client.py`

- [ ] **Step 1: Write failing client tests**

```python
# tests/test_comfy_client.py
"""Tests for ComfyClient HTTP layer."""

from __future__ import annotations

import json

import httpx
import pytest

from comfy_mcp.comfy_client import ComfyClient
from comfy_mcp.errors import ComfyAPIError, ComfyConnectionError


def _mock_transport(responses: dict[str, tuple[int, dict]]):
    """Create httpx.MockTransport from path→(status, body) mapping."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in responses:
            status, body = responses[path]
            return httpx.Response(status, json=body)
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.fixture
def client_with_transport():
    """Factory: create ComfyClient with mock transport."""

    def _make(responses: dict[str, tuple[int, dict]], **kwargs):
        transport = _mock_transport(responses)
        c = ComfyClient("http://test:8188", **kwargs)
        c._http = httpx.AsyncClient(transport=transport, base_url="http://test:8188")
        return c

    return _make


class TestComfyClientInit:
    def test_base_url_strips_trailing_slash(self):
        c = ComfyClient("http://localhost:8188/")
        assert c.base_url == "http://localhost:8188"

    def test_defaults(self):
        c = ComfyClient("http://localhost:8188")
        assert c.api_key == ""
        assert c.ws_reconnect_max == 5

    def test_api_key_stored(self):
        c = ComfyClient("http://x:8188", api_key="secret123")
        assert c.api_key == "secret123"


class TestComfyClientGet:
    @pytest.mark.asyncio
    async def test_get_success(self, client_with_transport):
        client = client_with_transport({
            "/system_stats": (200, {"system": {"os": "nt"}}),
        })
        result = await client.get("/system_stats")
        assert result["system"]["os"] == "nt"

    @pytest.mark.asyncio
    async def test_get_404_raises_api_error(self, client_with_transport):
        client = client_with_transport({})
        with pytest.raises(ComfyAPIError) as exc_info:
            await client.get("/nonexistent")
        assert exc_info.value.error_code == "HTTP_404"

    @pytest.mark.asyncio
    async def test_get_500_raises_api_error(self, client_with_transport):
        client = client_with_transport({
            "/broken": (500, {"error": "internal"}),
        })
        with pytest.raises(ComfyAPIError) as exc_info:
            await client.get("/broken")
        assert exc_info.value.error_code == "HTTP_500"
        assert exc_info.value.retry_possible is True


class TestComfyClientPost:
    @pytest.mark.asyncio
    async def test_post_success(self, client_with_transport):
        client = client_with_transport({
            "/prompt": (200, {"prompt_id": "abc123", "number": 1}),
        })
        result = await client.post("/prompt", {"prompt": {}})
        assert result["prompt_id"] == "abc123"


class TestComfyClientHighLevel:
    @pytest.mark.asyncio
    async def test_get_system_stats(self, client_with_transport):
        client = client_with_transport({
            "/system_stats": (200, {
                "system": {"os": "nt", "comfyui_version": "0.17.0"},
                "devices": [],
            }),
        })
        result = await client.get_system_stats()
        assert result["system"]["comfyui_version"] == "0.17.0"

    @pytest.mark.asyncio
    async def test_get_queue(self, client_with_transport):
        client = client_with_transport({
            "/queue": (200, {"queue_running": [], "queue_pending": []}),
        })
        result = await client.get_queue()
        assert result["queue_running"] == []

    @pytest.mark.asyncio
    async def test_queue_prompt(self, client_with_transport):
        client = client_with_transport({
            "/prompt": (200, {"prompt_id": "p1", "number": 3}),
        })
        result = await client.queue_prompt({"1": {"class_type": "KSampler"}})
        assert result["prompt_id"] == "p1"

    @pytest.mark.asyncio
    async def test_interrupt(self, client_with_transport):
        client = client_with_transport({
            "/interrupt": (200, {}),
        })
        result = await client.interrupt()
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_image_returns_bytes(self, client_with_transport):
        # Special case: get_image returns raw bytes, not JSON
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, content=b"\x89PNG\r\n", headers={"content-type": "image/png"})
        )
        c = ComfyClient("http://test:8188")
        c._http = httpx.AsyncClient(transport=transport, base_url="http://test:8188")
        result = await c.get_image("test.png")
        assert result == b"\x89PNG\r\n"

    @pytest.mark.asyncio
    async def test_close(self, client_with_transport):
        client = client_with_transport({})
        await client.close()
        assert client._http is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/Desktop/ComfyPilot && uv run pytest tests/test_comfy_client.py -v 2>&1 | head -5
```
Expected: FAIL with ImportError (comfy_client doesn't exist yet).

- [ ] **Step 3: Implement ComfyClient**

```python
# src/comfy_mcp/comfy_client.py
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
```

- [ ] **Step 4: Run tests**

```bash
cd ~/Desktop/ComfyPilot && uv run pytest tests/test_comfy_client.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/comfy_mcp/comfy_client.py tests/test_comfy_client.py && git commit -m "feat: ComfyClient HTTP layer with tests"
```

---

### Task 4: Server + Lifespan + Tool Registry Shell

**Files:**
- Create: `src/comfy_mcp/server.py`
- Create: `src/comfy_mcp/tool_registry.py`

- [ ] **Step 1: Implement server.py**

```python
# src/comfy_mcp/server.py
"""FastMCP server for ComfyPilot.

Entry point: `comfypilot` CLI command.
Initializes the MCP server with lifespan management for persistent connections.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from comfy_mcp.comfy_client import ComfyClient


@asynccontextmanager
async def comfy_lifespan(server: FastMCP):
    """Manage ComfyClient and subsystem lifecycles."""
    url = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
    api_key = os.environ.get("COMFY_API_KEY", "")
    timeout = float(os.environ.get("COMFY_TIMEOUT", "300"))
    snapshot_limit = int(os.environ.get("COMFY_SNAPSHOT_LIMIT", "50"))

    client = ComfyClient(url, api_key=api_key, timeout=timeout)
    await client.connect()

    # Subsystem managers — imported lazily to avoid circular deps
    from comfy_mcp.events.event_manager import EventManager
    from comfy_mcp.jobs.job_tracker import JobTracker
    from comfy_mcp.memory.snapshot_manager import SnapshotManager
    from comfy_mcp.memory.technique_store import TechniqueStore
    from comfy_mcp.safety.vram_guard import VRAMGuard

    event_mgr = EventManager(client)
    snapshot_mgr = SnapshotManager(max_snapshots=snapshot_limit)
    technique_store = TechniqueStore()
    vram_guard = VRAMGuard(client)
    job_tracker = JobTracker(client, event_mgr)

    try:
        yield {
            "comfy_client": client,
            "event_manager": event_mgr,
            "snapshot_manager": snapshot_mgr,
            "technique_store": technique_store,
            "vram_guard": vram_guard,
            "job_tracker": job_tracker,
        }
    finally:
        await event_mgr.shutdown()
        await client.close()


mcp = FastMCP("comfypilot", lifespan=comfy_lifespan)


def _register_tools():
    """Import tool modules to trigger @mcp.tool() registration."""
    import comfy_mcp.tool_registry  # noqa: F401


def main():
    """CLI entry point."""
    _register_tools()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Implement tool_registry.py (empty shell)**

```python
# src/comfy_mcp/tool_registry.py
"""Central tool registration.

Imports all tools/ modules so their @mcp.tool() decorators execute at startup.
This file is imported by server._register_tools().
"""

# Tools will be imported here as they are implemented.
# Each import triggers the @mcp.tool() decorators in that module.

# from comfy_mcp.tools import system      # noqa: F401  -- Task 5
# from comfy_mcp.tools import models      # noqa: F401  -- Task 6
# from comfy_mcp.tools import workflow    # noqa: F401  -- Task 7
# from comfy_mcp.tools import nodes       # noqa: F401  -- Task 8
# from comfy_mcp.tools import images      # noqa: F401  -- Task 9
# from comfy_mcp.tools import history     # noqa: F401  -- Task 11
# from comfy_mcp.tools import monitoring  # noqa: F401  -- Task 13
# from comfy_mcp.tools import snapshots   # noqa: F401  -- Task 15
# from comfy_mcp.tools import memory      # noqa: F401  -- Task 16
# from comfy_mcp.tools import safety      # noqa: F401  -- Task 17
# from comfy_mcp.tools import builder     # noqa: F401  -- Task 18
# from comfy_mcp.tools import output_routing  # noqa: F401 -- Task 19
```

- [ ] **Step 3: Create subsystem stubs** (so server.py imports don't fail)

```python
# src/comfy_mcp/events/event_manager.py
"""WebSocket event manager — stub for Task 10."""
from __future__ import annotations
from typing import Any

class EventManager:
    def __init__(self, client: Any): self._client = client
    async def shutdown(self) -> None: pass
```

```python
# src/comfy_mcp/jobs/job_tracker.py
"""Job tracker — stub for Task 12."""
from __future__ import annotations
from typing import Any

class JobTracker:
    def __init__(self, client: Any, event_mgr: Any):
        self._client = client
        self._event_mgr = event_mgr
```

```python
# src/comfy_mcp/memory/snapshot_manager.py
"""Snapshot manager — stub for Task 14."""
from __future__ import annotations

class SnapshotManager:
    def __init__(self, max_snapshots: int = 50): self._max = max_snapshots
```

```python
# src/comfy_mcp/memory/technique_store.py
"""Technique store — stub for Task 16."""
from __future__ import annotations

class TechniqueStore:
    def __init__(self): pass
```

```python
# src/comfy_mcp/safety/vram_guard.py
"""VRAM guard — stub for Task 17."""
from __future__ import annotations
from typing import Any

class VRAMGuard:
    def __init__(self, client: Any): self._client = client
```

- [ ] **Step 4: Verify server imports work**

```bash
cd ~/Desktop/ComfyPilot && uv run python -c "from comfy_mcp.server import mcp; print('Server OK:', mcp.name)"
```
Expected: `Server OK: comfypilot`

- [ ] **Step 5: Commit**

```bash
git add src/comfy_mcp/server.py src/comfy_mcp/tool_registry.py src/comfy_mcp/events/ src/comfy_mcp/jobs/ src/comfy_mcp/memory/ src/comfy_mcp/safety/ && git commit -m "feat: server with lifespan, tool registry shell, subsystem stubs"
```

---

### Task 5: System Tools (6 tools — proves the full pattern)

**Files:**
- Create: `src/comfy_mcp/tools/system.py`
- Create: `tests/test_system.py`
- Modify: `src/comfy_mcp/tool_registry.py` (uncomment system import)

- [ ] **Step 1: Write system tool tests**

```python
# tests/test_system.py
"""Tests for system tools."""

from __future__ import annotations

import json

import pytest

from comfy_mcp.tools.system import (
    comfy_free_vram,
    comfy_get_features,
    comfy_get_gpu_info,
    comfy_get_system_stats,
    comfy_list_extensions,
)


class TestGetSystemStats:
    @pytest.mark.asyncio
    async def test_returns_system_info(self, mock_ctx, mock_client):
        result = await comfy_get_system_stats(ctx=mock_ctx)
        data = json.loads(result)
        assert data["system"]["comfyui_version"] == "0.17.0"
        mock_client.get_system_stats.assert_awaited_once()

class TestGetGpuInfo:
    @pytest.mark.asyncio
    async def test_returns_gpu_details(self, mock_ctx, mock_client):
        result = await comfy_get_gpu_info(ctx=mock_ctx)
        data = json.loads(result)
        assert len(data["devices"]) == 1
        assert "vram_total" in data["devices"][0]

class TestGetFeatures:
    @pytest.mark.asyncio
    async def test_returns_features(self, mock_ctx, mock_client):
        mock_client.get_features.return_value = {"feature1": True}
        result = await comfy_get_features(ctx=mock_ctx)
        data = json.loads(result)
        assert data["feature1"] is True

class TestListExtensions:
    @pytest.mark.asyncio
    async def test_returns_extensions(self, mock_ctx, mock_client):
        mock_client.get_extensions.return_value = ["ext1", "ext2"]
        result = await comfy_list_extensions(ctx=mock_ctx)
        data = json.loads(result)
        assert data["extensions"] == ["ext1", "ext2"]
        assert data["count"] == 2

class TestFreeVram:
    @pytest.mark.asyncio
    async def test_free_vram(self, mock_ctx, mock_client):
        mock_client.free_vram.return_value = {}
        result = await comfy_free_vram(unload_models=True, free_memory=True, ctx=mock_ctx)
        data = json.loads(result)
        assert data["status"] == "ok"
        mock_client.free_vram.assert_awaited_once_with(unload_models=True, free_memory=True)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/Desktop/ComfyPilot && uv run pytest tests/test_system.py -v 2>&1 | head -5
```
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement system tools**

```python
# src/comfy_mcp/tools/system.py
"""System tools — 6 tools for ComfyUI system info and management."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


@mcp.tool(
    annotations={
        "title": "Get System Stats",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_system_stats(ctx: Context) -> str:
    """Get ComfyUI system stats: OS, GPU, VRAM, version info."""
    result = await _client(ctx).get_system_stats()
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Get GPU Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_gpu_info(ctx: Context) -> str:
    """Get detailed GPU info: VRAM total/free/used, torch version, device names."""
    stats = await _client(ctx).get_system_stats()
    devices = stats.get("devices", [])
    gpu_info = {"devices": devices, "count": len(devices)}
    for dev in devices:
        total = dev.get("vram_total", 0)
        free = dev.get("vram_free", 0)
        dev["vram_used"] = total - free
        if total > 0:
            dev["vram_used_pct"] = round((total - free) / total * 100, 1)
    return json.dumps(gpu_info, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Features",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_features(ctx: Context) -> str:
    """List enabled ComfyUI features (v0.17+)."""
    result = await _client(ctx).get_features()
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "List Extensions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_extensions(ctx: Context) -> str:
    """List all installed ComfyUI custom nodes and extensions."""
    extensions = await _client(ctx).get_extensions()
    return json.dumps({"extensions": extensions, "count": len(extensions)}, indent=2)


@mcp.tool(
    annotations={
        "title": "Restart ComfyUI",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_restart(ctx: Context) -> str:
    """Restart the ComfyUI server. Warning: interrupts all running jobs."""
    # ComfyUI doesn't have a restart endpoint in standard API.
    # This is a placeholder that would require custom node or OS-level restart.
    return json.dumps({
        "status": "not_supported",
        "message": "ComfyUI does not expose a restart endpoint in the standard API. Use system-level restart.",
    })


@mcp.tool(
    annotations={
        "title": "Free VRAM",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_free_vram(
    unload_models: bool = False,
    free_memory: bool = False,
    ctx: Context,
) -> str:
    """Unload models and/or free VRAM memory.

    Args:
        unload_models: Unload all loaded models from VRAM
        free_memory: Free cached memory allocations
    """
    result = await _client(ctx).free_vram(
        unload_models=unload_models,
        free_memory=free_memory,
    )
    return json.dumps({"status": "ok", "unloaded_models": unload_models, "freed_memory": free_memory})
```

- [ ] **Step 4: Enable system tools in registry**

Update `src/comfy_mcp/tool_registry.py`:
```python
from comfy_mcp.tools import system  # noqa: F401
```

- [ ] **Step 5: Run tests**

```bash
cd ~/Desktop/ComfyPilot && uv run pytest tests/test_system.py -v
```
Expected: All tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
cd ~/Desktop/ComfyPilot && uv run pytest -v
```
Expected: All tests PASS (errors + client + system).

- [ ] **Step 7: Commit**

```bash
git add src/comfy_mcp/tools/system.py src/comfy_mcp/tool_registry.py tests/test_system.py && git commit -m "feat: system tools (6 tools) — first tool category complete"
```

---

### Task 6: Models Tools (5 tools)

**Files:**
- Create: `src/comfy_mcp/tools/models.py`
- Create: `tests/test_models.py`
- Modify: `src/comfy_mcp/tool_registry.py`

- [ ] **Step 1: Write model tool tests**

Follow the same pattern as Task 5. Test each tool function:
- `comfy_list_models`: mock `client.get_models("checkpoints")` → returns paginated list
- `comfy_get_model_info`: mock `client.get("/models/checkpoints")` → returns model details
- `comfy_list_model_folders`: mock `client.get_object_info()` → extract folder names
- `comfy_search_models`: mock multiple folder calls → fuzzy match
- `comfy_refresh_models`: mock `client.get_models("checkpoints")` → returns refreshed list

Key test: pagination works correctly (limit/offset/has_more/next_offset).

- [ ] **Step 2: Implement models.py**

Follow the tool pattern from Task 5. Each tool:
- Has `@mcp.tool(annotations={...})`
- Takes typed parameters + `ctx: Context`
- Returns `json.dumps(result)`
- Uses `_client(ctx)` helper

For `comfy_list_models`, implement pagination:
```python
async def comfy_list_models(folder: str, limit: int = 50, offset: int = 0, ctx: Context) -> str:
    all_models = await _client(ctx).get_models(folder)
    page = all_models[offset:offset + limit]
    return json.dumps({
        "models": page,
        "folder": folder,
        "total_count": len(all_models),
        "has_more": offset + limit < len(all_models),
        "next_offset": offset + limit if offset + limit < len(all_models) else None,
    })
```

- [ ] **Step 3: Enable in registry, run tests, commit**

```bash
# Add to tool_registry.py: from comfy_mcp.tools import models  # noqa: F401
cd ~/Desktop/ComfyPilot && uv run pytest tests/test_models.py -v
git add src/comfy_mcp/tools/models.py tests/test_models.py src/comfy_mcp/tool_registry.py && git commit -m "feat: model tools (5 tools) with pagination"
```

---

### Task 7: Workflow Execution Tools (8 tools)

**Files:**
- Create: `src/comfy_mcp/tools/workflow.py`
- Create: `tests/test_workflow.py`
- Modify: `src/comfy_mcp/tool_registry.py`

- [ ] **Step 1: Write workflow tests**

Key tools: `comfy_queue_prompt`, `comfy_get_queue`, `comfy_cancel_run`, `comfy_interrupt`, `comfy_clear_queue`, `comfy_validate_workflow`, `comfy_export_workflow`, `comfy_import_workflow`.

Test `comfy_queue_prompt` calls `ctx.report_progress()` during submission.
Test `comfy_validate_workflow` checks for required node types.

- [ ] **Step 2: Implement workflow.py**

`comfy_queue_prompt` is the most important tool — it queues a workflow and returns the prompt_id:
```python
async def comfy_queue_prompt(workflow: dict, front: bool = False, ctx: Context) -> str:
    await ctx.report_progress(0, 100)
    result = await _client(ctx).queue_prompt(workflow, front=front)
    await ctx.report_progress(100, 100)
    return json.dumps({
        "prompt_id": result.get("prompt_id"),
        "queue_position": result.get("number", 0),
    })
```

`comfy_validate_workflow` checks the workflow dict has valid structure without executing.

- [ ] **Step 3: Enable in registry, run tests, commit**

```bash
git add src/comfy_mcp/tools/workflow.py tests/test_workflow.py src/comfy_mcp/tool_registry.py && git commit -m "feat: workflow execution tools (8 tools)"
```

---

### Task 8: Node Tools (6 tools)

**Files:**
- Create: `src/comfy_mcp/tools/nodes.py`
- Create: `tests/test_nodes.py`
- Modify: `src/comfy_mcp/tool_registry.py`

- [ ] **Step 1-3: Test, implement, commit** (same pattern as Task 6)

Key tools: `comfy_list_node_types` (paginated), `comfy_get_node_info`, `comfy_search_nodes` (fuzzy match on node names), `comfy_get_categories`, `comfy_get_embeddings`, `comfy_inspect_widget`.

All are readOnly. `comfy_search_nodes` does case-insensitive substring matching on `get_object_info()` results.

```bash
git commit -m "feat: node tools (6 tools) with search and pagination"
```

---

### Task 9: Image Tools (5 tools)

**Files:**
- Create: `src/comfy_mcp/tools/images.py`
- Create: `tests/test_images.py`
- Modify: `src/comfy_mcp/tool_registry.py`

- [ ] **Step 1-3: Test, implement, commit**

Critical tool: `comfy_get_output_image` returns image content blocks:
```python
from mcp.types import TextContent, ImageContent
import base64

async def comfy_get_output_image(filename: str, subfolder: str = "", ctx: Context) -> list:
    image_bytes = await _client(ctx).get_image(filename, subfolder)
    return [
        TextContent(type="text", text=json.dumps({"filename": filename, "size_bytes": len(image_bytes)})),
        ImageContent(type="image", data=base64.b64encode(image_bytes).decode(), mimeType="image/png"),
    ]
```

`comfy_upload_image` accepts base64-encoded image data as input.
`comfy_download_batch` returns metadata only (no image bytes).

```bash
git commit -m "feat: image tools (5 tools) with image content blocks"
```

---

## Chunk 2: Subsystems (Events, Jobs, History, Monitoring)

### Task 10: EventManager (Full Implementation)

**Files:**
- Modify: `src/comfy_mcp/events/event_manager.py`
- Create: `tests/test_event_manager.py`

- [ ] **Step 1: Write EventManager tests**

Test: connect/disconnect, event buffering, subscription registration, auto-reconnect (mock WS disconnect), rate limiting, buffer drain on get_events.

- [ ] **Step 2: Implement EventManager**

```python
class EventManager:
    def __init__(self, client: ComfyClient):
        self._client = client
        self._subscriptions: dict[str, dict] = {}
        self._event_buffer: deque[dict] = deque(maxlen=1000)
        self._ws = None
        self._ws_task = None
        self._reconnect_count = 0

    async def start(self): ...       # Launch WS listener task
    async def shutdown(self): ...     # Cancel task, close WS
    async def _ws_loop(self): ...     # Connect, listen, dispatch, reconnect
    def subscribe(self, event_type, callback=None): ...
    def unsubscribe(self, event_type): ...
    def drain_events(self, event_type=None) -> list: ...
    def get_latest_progress(self, prompt_id) -> dict | None: ...
```

Auto-reconnect: exponential backoff (1, 2, 4, 8, 16s), max `client.ws_reconnect_max` attempts.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: EventManager with WS auto-reconnect and event buffering"
```

---

### Task 11: History Tools (5 tools)

**Files:**
- Create: `src/comfy_mcp/tools/history.py`
- Create: `tests/test_history.py`
- Modify: `src/comfy_mcp/tool_registry.py`

- [ ] **Step 1-3: Test, implement, commit**

`comfy_get_history` with pagination, `comfy_get_run_result`, `comfy_delete_history`, `comfy_clear_history`, `comfy_search_history`.

```bash
git commit -m "feat: history tools (5 tools)"
```

---

### Task 12: JobTracker (Full Implementation)

**Files:**
- Modify: `src/comfy_mcp/jobs/job_tracker.py`
- Create: `tests/test_job_tracker.py`

- [ ] **Step 1: Write JobTracker tests**

Test: track submission, poll progress from EventManager, wait_for_completion with timeout, recent job lookup.

- [ ] **Step 2: Implement JobTracker**

```python
class JobTracker:
    def __init__(self, client, event_mgr):
        self._client = client
        self._event_mgr = event_mgr
        self._active_jobs: dict[str, dict] = {}  # prompt_id → status
        self._completed: deque[dict] = deque(maxlen=100)

    async def track(self, prompt_id: str) -> None: ...
    def get_progress(self, prompt_id: str) -> dict | None: ...
    async def wait_for_completion(self, prompt_id: str, timeout: float = 300) -> dict: ...
    def list_active(self) -> list[dict]: ...
    def list_recent(self, limit: int = 20) -> list[dict]: ...
```

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: JobTracker with async completion wait"
```

---

### Task 13: Monitoring Tools (6 tools)

**Files:**
- Create: `src/comfy_mcp/tools/monitoring.py`
- Create: `tests/test_monitoring.py`
- Modify: `src/comfy_mcp/tool_registry.py`

- [ ] **Step 1-3: Test, implement, commit**

`comfy_watch_progress` (polls EventManager for prompt_id progress), `comfy_subscribe`, `comfy_unsubscribe`, `comfy_get_events` (drains buffer), `comfy_describe_dynamics` (blocks for N seconds, returns summary), `comfy_get_status` (one-shot queue + execution snapshot).

```bash
git commit -m "feat: monitoring tools (6 tools) — poll-based, not streaming"
```

---

## Chunk 3: Memory Layer (Snapshots, Techniques)

### Task 14: SnapshotManager (Full Implementation)

**Files:**
- Modify: `src/comfy_mcp/memory/snapshot_manager.py`
- Create: `tests/test_snapshot_manager.py`

- [ ] **Step 1: Write SnapshotManager tests**

Test: add snapshot, LRU eviction at limit, list metadata, get by id, diff two snapshots, delete.

- [ ] **Step 2: Implement SnapshotManager**

```python
class SnapshotManager:
    def __init__(self, max_snapshots=50):
        self._max = max_snapshots
        self._snapshots: dict[str, dict] = {}
        self._order: list[str] = []  # oldest first

    def add(self, workflow: dict, name: str = "") -> dict: ...  # Returns snapshot metadata
    def list(self, limit=20) -> list[dict]: ...                  # Metadata only
    def get(self, snapshot_id: str) -> dict | None: ...
    def diff(self, id_a: str, id_b: str | None = None, current: dict | None = None) -> dict: ...
    def delete(self, snapshot_id: str) -> bool: ...
    def _trim(self): ...  # LRU eviction
```

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: SnapshotManager with LRU eviction and diff"
```

---

### Task 15: Snapshot Tools (6 tools)

**Files:**
- Create: `src/comfy_mcp/tools/snapshots.py`
- Create: `tests/test_snapshots.py`
- Modify: `src/comfy_mcp/tool_registry.py`

- [ ] **Step 1-3: Test, implement, commit**

`comfy_snapshot_workflow`, `comfy_list_snapshots`, `comfy_diff_snapshots`, `comfy_restore_snapshot`, `comfy_delete_snapshot`, `comfy_auto_snapshot`.

`comfy_auto_snapshot` toggles the in-memory flag on the SnapshotManager.

```bash
git commit -m "feat: snapshot tools (6 tools)"
```

---

### Task 16: TechniqueStore + Memory Tools (5 tools)

**Files:**
- Modify: `src/comfy_mcp/memory/technique_store.py`
- Create: `src/comfy_mcp/tools/memory.py`
- Create: `tests/test_memory.py`
- Modify: `src/comfy_mcp/tool_registry.py`

- [ ] **Step 1: Write TechniqueStore tests**

Test: save, search by query, search by tags, list, replay (returns workflow dict), favorite/rate, persistence to `tmp_path`.

- [ ] **Step 2: Implement TechniqueStore**

```python
class TechniqueStore:
    def __init__(self, storage_dir: str | None = None):
        self._dir = Path(storage_dir or Path.home() / ".comfypilot" / "techniques")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._techniques: dict[str, dict] = {}
        self._load_all()

    def save(self, workflow, name, description="", tags=None) -> dict: ...
    def search(self, query="", tags=None, limit=20) -> list[dict]: ...
    def list(self, limit=50) -> list[dict]: ...
    def get(self, technique_id) -> dict | None: ...
    def favorite(self, technique_id, favorite=True, rating=-1) -> dict: ...
    def delete(self, technique_id) -> bool: ...
```

- [ ] **Step 3: Implement memory tools, enable in registry, test, commit**

```bash
git commit -m "feat: TechniqueStore + memory tools (5 tools)"
```

---

## Chunk 4: Safety, Builder, Routing, Resources, Packaging

### Task 17: VRAMGuard + Safety Tools (5 tools)

**Files:**
- Modify: `src/comfy_mcp/safety/vram_guard.py`
- Create: `src/comfy_mcp/tools/safety.py`
- Create: `tests/test_safety.py`
- Modify: `src/comfy_mcp/tool_registry.py`

- [ ] **Step 1: Implement VRAMGuard**

```python
class VRAMGuard:
    def __init__(self, client, warn_pct=80.0, block_pct=95.0):
        self._client = client
        self.warn_pct = warn_pct
        self.block_pct = block_pct
        self._limits = {"max_queue": 10, "timeout": 300}

    async def check_vram(self) -> dict: ...           # Returns usage + status (ok/warn/critical)
    async def validate_before_queue(self) -> dict: ... # Pre-flight: checks VRAM headroom
    def set_limits(self, **kwargs): ...                # Update warn/block thresholds
    async def emergency_stop(self) -> dict: ...        # interrupt + clear + free
    async def detect_instability(self) -> dict: ...    # Check for stuck jobs, error spikes, OOM patterns
```

- [ ] **Step 2: Write safety tool tests**

Test all 5 tools: `comfy_check_vram`, `comfy_set_limits`, `comfy_detect_instability`, `comfy_emergency_stop`, `comfy_validate_before_queue`.

```python
# tests/test_safety.py
async def test_check_vram_returns_status(mock_ctx):
    result = await comfy_check_vram(ctx=mock_ctx)
    data = json.loads(result)
    assert "status" in data  # ok, warn, or critical
    assert "vram_used_pct" in data

async def test_detect_instability_no_issues(mock_ctx):
    result = await comfy_detect_instability(ctx=mock_ctx)
    data = json.loads(result)
    assert data["stable"] is True

async def test_emergency_stop(mock_ctx):
    result = await comfy_emergency_stop(ctx=mock_ctx)
    data = json.loads(result)
    assert data["status"] == "stopped"
```

- [ ] **Step 3: Implement safety tools**

5 tools: `comfy_check_vram`, `comfy_set_limits`, `comfy_detect_instability`, `comfy_emergency_stop`, `comfy_validate_before_queue`. All delegate to `VRAMGuard` via `ctx.request_context.lifespan_context["vram_guard"]`.

- [ ] **Step 4: Enable in registry, run tests, commit**

```bash
# Add to tool_registry.py: from comfy_mcp.tools import safety  # noqa: F401
cd ~/Desktop/ComfyPilot && uv run pytest tests/test_safety.py -v
git add src/comfy_mcp/safety/vram_guard.py src/comfy_mcp/tools/safety.py tests/test_safety.py src/comfy_mcp/tool_registry.py && git commit -m "feat: VRAMGuard + safety tools (5 tools)"
```

---

### Task 18: Builder Tools (5 tools)

**Files:**
- Create: `src/comfy_mcp/tools/builder.py`
- Create: `tests/test_builder.py`
- Modify: `src/comfy_mcp/tool_registry.py`

- [ ] **Step 1-3: Test, implement, commit**

`comfy_build_workflow` takes template name + params, returns API-format workflow.
Templates: `txt2img`, `img2img`, `upscale`, `inpaint`, `controlnet` — each is a dict factory.

`comfy_add_node`, `comfy_connect_nodes`, `comfy_set_widget_value` operate on an in-memory workflow dict.
`comfy_apply_template` is a convenience wrapper around `build_workflow`.

```bash
git commit -m "feat: builder tools (5 tools) with template system"
```

---

### Task 19: Output Routing Tools (4 tools)

**Files:**
- Create: `src/comfy_mcp/tools/output_routing.py`
- Create: `tests/test_output_routing.py`
- Modify: `src/comfy_mcp/tool_registry.py`

- [ ] **Step 1-3: Test, implement, commit**

`comfy_send_to_disk`: downloads image from ComfyUI, saves to `COMFY_OUTPUT_DIR`.
`comfy_send_to_td`: saves to `COMFY_TD_OUTPUT_DIR`, returns suggested `td_exec_python` command.
`comfy_send_to_blender`: saves to `COMFY_BLENDER_OUTPUT_DIR`, returns suggested blender code.
`comfy_list_destinations`: checks env vars, reports configured destinations.

```bash
git commit -m "feat: output routing tools (4 tools) — agent-orchestrated cross-app"
```

---

### Task 20: MCP Resources (4 resources)

**Files:**
- Modify: `src/comfy_mcp/server.py` (add resource decorators)
- Modify: `tests/conftest.py` if needed

- [ ] **Step 1: Add resources to server.py**

Resources need access to the ComfyClient but don't receive `ctx` like tools do.
**Solution:** Store the client as a module-level reference set during lifespan startup.
Add to `server.py` before the lifespan function:

```python
# Module-level reference for resources (set during lifespan)
_shared_client: ComfyClient | None = None
```

In the lifespan `async with` block, after creating the client:
```python
global _shared_client
_shared_client = client
# ... yield ...
_shared_client = None  # cleanup
```

Then resources access it directly:

```python
@mcp.resource("comfy://system/info")
async def system_info_resource() -> str:
    """System stats, GPU info, ComfyUI version."""
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    result = await _shared_client.get_system_stats()
    return json.dumps(result, indent=2)

@mcp.resource("comfy://nodes/catalog")
async def nodes_catalog_resource() -> str:
    """Full node catalog from ComfyUI."""
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    result = await _shared_client.get_object_info()
    return json.dumps({"node_count": len(result), "nodes": list(result.keys())[:100]})

@mcp.resource("comfy://models/{folder}")
async def models_resource(folder: str) -> str:
    """List models in a specific folder (checkpoints, loras, etc)."""
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    result = await _shared_client.get_models(folder)
    return json.dumps(result, indent=2)

@mcp.resource("comfy://embeddings")
async def embeddings_resource() -> str:
    """List all available embeddings."""
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    result = await _shared_client.get_embeddings()
    return json.dumps(result, indent=2)
```

- [ ] **Step 2: Commit**

```bash
git commit -m "feat: MCP resources (4) for static data access"
```

---

### Task 21: Plugin Packaging

**Files:**
- Create: `mcp/manifest.json`
- Create: `mcp/profiles/claude-desktop.json`
- Create: `mcp/profiles/cursor.json`
- Create: `mcp/profiles/generic.json`
- Create: `skills/comfypilot-core/SKILL.md`

- [ ] **Step 1: Create manifest.json**

Use the exact JSON from spec Section 9.1.

- [ ] **Step 2: Create client profiles**

```json
// mcp/profiles/claude-desktop.json
{
  "mcpServers": {
    "comfypilot": {
      "command": "uv",
      "args": ["run", "comfypilot"],
      "env": {
        "COMFY_URL": "http://127.0.0.1:8188",
        "COMFY_API_KEY": ""
      }
    }
  }
}
```

- [ ] **Step 3: Create skill file**

```markdown
<!-- skills/comfypilot-core/SKILL.md -->
---
name: comfypilot-core
description: Core workflow for ComfyPilot — the AI assistant for ComfyUI
---

# ComfyPilot Core Skill

Use this when working with ComfyUI through MCP tools.

## Workflow
1. Check system: `comfy_get_system_stats` → verify GPU, VRAM, version
2. Check VRAM: `comfy_check_vram` → ensure headroom before loading models
3. Build workflow: `comfy_build_workflow` or construct API-format JSON
4. Validate: `comfy_validate_workflow` → catch errors before queueing
5. Queue: `comfy_queue_prompt` → submit for execution
6. Monitor: `comfy_watch_progress` → poll until complete
7. Retrieve: `comfy_get_output_image` → see the generated image
8. Route: `comfy_send_to_disk` / `comfy_send_to_td` / `comfy_send_to_blender`

## Safety
- Always `comfy_check_vram` before loading large models
- Use `comfy_snapshot_workflow` before modifications
- `comfy_emergency_stop` if anything goes wrong
```

- [ ] **Step 4: Commit**

```bash
git add mcp/ skills/ && git commit -m "feat: plugin packaging — manifest, profiles, skill"
```

---

### Task 22: Final Integration Test + README

**Files:**
- Modify: `src/comfy_mcp/tool_registry.py` (verify all imports enabled)
- Create: `README.md`

- [ ] **Step 1: Verify all tool imports are enabled in registry**

Uncomment all imports in `tool_registry.py`. Run full test suite.

```bash
cd ~/Desktop/ComfyPilot && uv run pytest -v --tb=short
```
Expected: All tests pass.

- [ ] **Step 2: Verify server starts**

```bash
cd ~/Desktop/ComfyPilot && uv run python -c "
from comfy_mcp.server import mcp, _register_tools
_register_tools()
print(f'Server: {mcp.name}')
# Use list_tools() — the public SDK API — to count registered tools
import asyncio
async def count():
    tools = await mcp.list_tools()
    print(f'Tools registered: {len(tools)}')
asyncio.run(count())
"
```
Expected: `Tools registered: 71`

- [ ] **Step 3: Create README.md**

Brief README with: what it is, quickstart (uv run comfypilot), env vars, tool categories.

- [ ] **Step 4: Final commit**

```bash
git add -A && git commit -m "feat: ComfyPilot v1.0.0 — 71 tools, complete MCP server for ComfyUI"
```

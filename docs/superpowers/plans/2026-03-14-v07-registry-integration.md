# v0.7 Registry Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a workflow uses a missing node, resolve it to the exact ComfyUI Registry package, version, and install command. Transform compat engine "blocked: missing node" errors into actionable resolution.

**Architecture:** Three-module package (`src/comfy_mcp/registry/`) with an async HTTP client for `api.comfy.org`, a reverse-lookup index with positive and negative caching, and a resolver that maps missing nodes to packages with compatibility checks. Enhances the existing compat engine output with package resolution data.

**Tech Stack:** Python 3.12, httpx (existing), compat engine (v0.3), install graph (v0.3), KnowledgeStore (v0.6).

**Prerequisite:** v0.6 (Persistent Knowledge) must be implemented first.

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/comfy_mcp/registry/__init__.py` | Package init |
| Create | `src/comfy_mcp/registry/client.py` | Async HTTP client for api.comfy.org with rate limiting |
| Create | `src/comfy_mcp/registry/index.py` | Reverse lookup cache (node class → package) with negative caching |
| Create | `src/comfy_mcp/registry/resolver.py` | Missing node → package resolution with compatibility and deduplication |
| Create | `src/comfy_mcp/tools/registry.py` | 5 MCP tools |
| Create | `tests/test_registry_client.py` | Tests for HTTP client |
| Create | `tests/test_registry_index.py` | Tests for reverse lookup cache |
| Create | `tests/test_registry_resolver.py` | Tests for resolver |
| Create | `tests/test_tools_registry.py` | Tests for MCP tools |
| Modify | `src/comfy_mcp/compat/engine.py` | Enhance missing_nodes with package info |
| Modify | `src/comfy_mcp/server.py` | Add RegistryClient + RegistryIndex to lifespan + resource |
| Modify | `src/comfy_mcp/tool_registry.py` | Add registry import |
| Modify | `tests/conftest.py` | Add registry mocks to mock_ctx |
| Modify | `README.md` | Update to 92 tools, 11 resources |

---

## Chunk 1: Registry Client

### Task 1: Package init + RegistryClient

**Files:**
- Create: `src/comfy_mcp/registry/__init__.py`
- Create: `src/comfy_mcp/registry/client.py`
- Create: `tests/test_registry_client.py`

- [ ] **Step 1: Create package init**

```python
# src/comfy_mcp/registry/__init__.py
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_registry_client.py
"""Tests for RegistryClient — async HTTP client for api.comfy.org."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSearchNodes:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        from comfy_mcp.registry.client import RegistryClient
        client = RegistryClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={
            "nodes": [{"id": "comfyui-animatediff", "name": "AnimateDiff Evolved"}],
            "total": 1, "page": 1, "totalPages": 1,
        })
        with patch.object(client, "_http", AsyncMock()) as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)
            result = await client.search_nodes("animatediff")
            assert len(result["nodes"]) == 1

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self):
        from comfy_mcp.registry.client import RegistryClient
        import httpx
        client = RegistryClient()
        with patch.object(client, "_http", AsyncMock()) as mock_http:
            mock_http.get = AsyncMock(side_effect=httpx.ConnectError("offline"))
            result = await client.search_nodes("test")
            assert result["nodes"] == []


class TestReverseLookup:
    @pytest.mark.asyncio
    async def test_returns_package_info(self):
        from comfy_mcp.registry.client import RegistryClient
        client = RegistryClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={
            "comfy_node_name": "ADE_AnimateDiffLoaderWithContext",
            "node": {"id": "comfyui-animatediff-evolved", "name": "AnimateDiff Evolved"},
        })
        with patch.object(client, "_http", AsyncMock()) as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)
            result = await client.reverse_lookup("ADE_AnimateDiffLoaderWithContext")
            assert result is not None
            assert result["node"]["id"] == "comfyui-animatediff-evolved"

    @pytest.mark.asyncio
    async def test_returns_none_on_404(self):
        from comfy_mcp.registry.client import RegistryClient
        client = RegistryClient()
        mock_response = MagicMock()
        mock_response.status_code = 404
        with patch.object(client, "_http", AsyncMock()) as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)
            result = await client.reverse_lookup("FakeNode")
            assert result is None


class TestGetNode:
    @pytest.mark.asyncio
    async def test_returns_node_details(self):
        from comfy_mcp.registry.client import RegistryClient
        client = RegistryClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={
            "id": "comfyui-animatediff", "name": "AnimateDiff", "description": "Motion",
            "latest_version": {"version": "1.2.3"},
        })
        with patch.object(client, "_http", AsyncMock()) as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)
            result = await client.get_node("comfyui-animatediff")
            assert result["id"] == "comfyui-animatediff"


class TestClose:
    @pytest.mark.asyncio
    async def test_close_is_safe(self):
        from comfy_mcp.registry.client import RegistryClient
        client = RegistryClient()
        await client.close()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_registry_client.py -v`
Expected: FAIL

- [ ] **Step 4: Implement RegistryClient**

```python
# src/comfy_mcp/registry/client.py
"""RegistryClient — async HTTP client for the ComfyUI Registry API.

Base URL: https://api.comfy.org
All read endpoints are public (no auth required).
Includes rate limiting, retry logic, and User-Agent header.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("comfypilot.registry")

BASE_URL = "https://api.comfy.org"
USER_AGENT = "ComfyPilot/0.7"
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 30.0
REQUEST_THROTTLE = 0.1  # minimum seconds between requests


class RegistryClient:
    """Async HTTP client for the ComfyUI Registry."""

    def __init__(self, base_url: str = BASE_URL, timeout: float = 30.0):
        self._base = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )
        self._last_request_time = 0.0

    async def _throttled_get(self, url: str, params: dict | None = None) -> httpx.Response:
        """GET with rate limiting and retry."""
        for attempt in range(MAX_RETRIES):
            # Throttle
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < REQUEST_THROTTLE:
                await asyncio.sleep(REQUEST_THROTTLE - elapsed)
            self._last_request_time = time.time()

            try:
                response = await self._http.get(url, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    retry_after = float(response.headers.get("Retry-After", INITIAL_BACKOFF * (2 ** attempt)))
                    wait = min(retry_after, MAX_BACKOFF)
                    logger.debug("Rate limited or server error (%d), retrying in %.1fs", response.status_code, wait)
                    await asyncio.sleep(wait)
                    continue
                return response
            except httpx.HTTPError as exc:
                if attempt < MAX_RETRIES - 1:
                    wait = min(INITIAL_BACKOFF * (2 ** attempt), MAX_BACKOFF)
                    logger.debug("Request failed (%s), retrying in %.1fs", exc, wait)
                    await asyncio.sleep(wait)
                else:
                    raise
        # Should not reach here, but just in case
        return await self._http.get(url, params=params)

    async def search_nodes(self, query: str, page: int = 1, limit: int = 10, **filters) -> dict[str, Any]:
        """Search registry packages."""
        params = {"page": page, "limit": limit}
        if query:
            # The API uses node_id filter or general search
            params["node_id"] = query
        params.update(filters)
        try:
            response = await self._throttled_get(f"{self._base}/nodes", params=params)
            if response.status_code == 200:
                return response.json()
            return {"nodes": [], "total": 0, "page": page}
        except Exception as exc:
            logger.debug("search_nodes failed: %s", exc)
            return {"nodes": [], "total": 0, "page": page}

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Get full package metadata by ID."""
        try:
            response = await self._throttled_get(f"{self._base}/nodes/{node_id}")
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as exc:
            logger.debug("get_node failed for %s: %s", node_id, exc)
            return None

    async def get_versions(self, node_id: str) -> list[dict[str, Any]]:
        """List all versions of a package."""
        try:
            response = await self._throttled_get(f"{self._base}/nodes/{node_id}/versions")
            if response.status_code == 200:
                return response.json()
            return []
        except Exception:
            return []

    async def get_comfy_nodes(self, node_id: str, version: str) -> list[dict[str, Any]]:
        """List all node classes in a specific package version."""
        try:
            response = await self._throttled_get(f"{self._base}/nodes/{node_id}/versions/{version}/comfy-nodes")
            if response.status_code == 200:
                return response.json()
            return []
        except Exception:
            return []

    async def reverse_lookup(self, class_name: str) -> dict[str, Any] | None:
        """Map a node class name back to its registry package."""
        try:
            response = await self._throttled_get(f"{self._base}/comfy-nodes/{class_name}/node")
            if response.status_code == 200:
                return response.json()
            if response.status_code in (404, 410):
                return None
            return None
        except Exception as exc:
            logger.debug("reverse_lookup failed for %s: %s", class_name, exc)
            return None

    async def bulk_resolve(self, pairs: list[dict[str, str]]) -> dict[str, Any]:
        """Batch resolve multiple (nodeId, version) pairs."""
        try:
            response = await self._http.post(
                f"{self._base}/bulk/nodes/versions",
                json=pairs,
                headers={"User-Agent": USER_AGENT},
            )
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception:
            return {}

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_registry_client.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/registry/__init__.py src/comfy_mcp/registry/client.py tests/test_registry_client.py && git commit -m "feat(v0.7): add RegistryClient with rate limiting and retry"
```

---

## Chunk 2: Reverse Lookup Index

### Task 2: RegistryIndex — cached reverse lookup

**Files:**
- Create: `src/comfy_mcp/registry/index.py`
- Create: `tests/test_registry_index.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_registry_index.py
"""Tests for RegistryIndex — reverse lookup cache with negative caching."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestIndexLookup:
    def test_cache_hit_returns_instantly(self, tmp_path):
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path))
        # Pre-populate cache
        index._cache["KSampler"] = {
            "class": "KSampler", "package": "comfy-core", "cached_at": time.time(),
        }
        result = index.lookup("KSampler")
        assert result is not None
        assert result["package"] == "comfy-core"

    def test_cache_miss_returns_none(self, tmp_path):
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path))
        result = index.lookup("FakeNode")
        assert result is None


class TestNegativeCaching:
    def test_negative_entry_cached(self, tmp_path):
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path))
        index.cache_negative("FakeNode")
        result = index.lookup("FakeNode")
        assert result is not None
        assert result["package"] is None

    def test_negative_entry_expires(self, tmp_path):
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path), negative_ttl=0)
        index.cache_negative("FakeNode")
        result = index.lookup("FakeNode")
        # TTL=0 means it should be expired already
        assert result is None


class TestCachePositive:
    def test_cache_positive_stores_entry(self, tmp_path):
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path))
        index.cache_positive("ADE_Loader", "comfyui-animatediff-evolved", "1.2.3")
        result = index.lookup("ADE_Loader")
        assert result["package"] == "comfyui-animatediff-evolved"
        assert result["version"] == "1.2.3"


class TestDiskPersistence:
    def test_save_and_load(self, tmp_path):
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path))
        index.cache_positive("KSampler", "comfy-core", "0.17.0")
        index.save()
        assert (tmp_path / "node_class_index.json").exists()

        index2 = RegistryIndex(cache_dir=str(tmp_path))
        result = index2.lookup("KSampler")
        assert result is not None
        assert result["package"] == "comfy-core"

    def test_handles_corrupted_cache(self, tmp_path):
        (tmp_path / "node_class_index.json").write_text("{{invalid")
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path))
        # Should not crash, just start empty
        assert index.lookup("anything") is None


class TestIndexStats:
    def test_summary_reports_counts(self, tmp_path):
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path))
        index.cache_positive("A", "pkg-a", "1.0")
        index.cache_positive("B", "pkg-b", "2.0")
        index.cache_negative("C")
        summary = index.summary()
        assert summary["total_entries"] == 3
        assert summary["positive_entries"] == 2
        assert summary["negative_entries"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_registry_index.py -v`
Expected: FAIL

- [ ] **Step 3: Implement RegistryIndex**

```python
# src/comfy_mcp/registry/index.py
"""RegistryIndex — reverse lookup cache mapping node class names to registry packages.

Supports both positive entries (class → package) and negative entries
(class → not-in-registry) with configurable TTL for negative entries.
Persists to ~/.comfypilot/cache/registry/node_class_index.json.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("comfypilot.registry")

NEGATIVE_TTL_DEFAULT = 86400  # 24 hours


class RegistryIndex:
    """Cached reverse lookup from node class name to registry package."""

    def __init__(self, cache_dir: str | None = None, negative_ttl: float = NEGATIVE_TTL_DEFAULT):
        self._dir = Path(cache_dir or Path.home() / ".comfypilot" / "cache" / "registry")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._negative_ttl = negative_ttl
        self._cache: dict[str, dict[str, Any]] = {}
        self._load()

    def _index_path(self) -> Path:
        return self._dir / "node_class_index.json"

    def _load(self) -> None:
        path = self._index_path()
        if not path.exists():
            return
        try:
            self._cache = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Registry index corrupted, starting fresh: %s", exc)
            self._cache = {}

    def lookup(self, class_name: str) -> dict[str, Any] | None:
        """Look up a node class in the cache.

        Returns the cached entry if found and valid, None if not cached.
        For negative entries, returns None if expired (TTL exceeded).
        """
        entry = self._cache.get(class_name)
        if entry is None:
            return None

        # Check negative entry TTL
        if entry.get("package") is None:
            age = time.time() - entry.get("cached_at", 0)
            if age >= self._negative_ttl:
                del self._cache[class_name]
                return None

        return entry

    def cache_positive(self, class_name: str, package_id: str, version: str) -> None:
        """Cache a positive lookup result."""
        self._cache[class_name] = {
            "class": class_name,
            "package": package_id,
            "version": version,
            "cached_at": time.time(),
        }

    def cache_negative(self, class_name: str) -> None:
        """Cache a negative lookup result (not found in registry)."""
        self._cache[class_name] = {
            "class": class_name,
            "package": None,
            "cached_at": time.time(),
        }

    def save(self) -> None:
        """Persist cache to disk."""
        from comfy_mcp.knowledge.store import atomic_write
        atomic_write(self._index_path(), json.dumps(self._cache, indent=2))

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache = {}
        path = self._index_path()
        if path.exists():
            path.unlink()

    def is_stale(self, max_age: float = 86400) -> bool:
        """Check if cache has any entries (empty = stale)."""
        return len(self._cache) == 0

    def content_hash(self) -> str:
        """Hash of all cached entries."""
        import hashlib
        content = json.dumps(sorted(self._cache.keys()))
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def summary(self) -> dict[str, Any]:
        positive = sum(1 for e in self._cache.values() if e.get("package") is not None)
        negative = sum(1 for e in self._cache.values() if e.get("package") is None)
        return {
            "total_entries": len(self._cache),
            "positive_entries": positive,
            "negative_entries": negative,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_registry_index.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/registry/index.py tests/test_registry_index.py && git commit -m "feat(v0.7): add RegistryIndex with positive and negative caching"
```

---

## Chunk 3: Resolver + Compat Enhancement

### Task 3: RegistryResolver

**Files:**
- Create: `src/comfy_mcp/registry/resolver.py`
- Create: `tests/test_registry_resolver.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_registry_resolver.py
"""Tests for RegistryResolver — missing node to package resolution."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest


SNAPSHOT = {
    "version": "0.17.0",
    "os": "nt",
    "gpu_devices": [{"name": "NVIDIA RTX 5090", "type": "cuda"}],
}


class TestResolveSingle:
    @pytest.mark.asyncio
    async def test_resolve_from_cache(self):
        from comfy_mcp.registry.resolver import RegistryResolver
        index = MagicMock()
        index.lookup = MagicMock(return_value={
            "class": "ADE_Loader", "package": "comfyui-animatediff", "version": "1.2.3", "cached_at": time.time(),
        })
        client = AsyncMock()
        resolver = RegistryResolver(client, index, SNAPSHOT)
        result = await resolver.resolve_one("ADE_Loader")
        assert result["package"] == "comfyui-animatediff"
        client.reverse_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_from_api(self):
        from comfy_mcp.registry.resolver import RegistryResolver
        index = MagicMock()
        index.lookup = MagicMock(return_value=None)
        index.cache_positive = MagicMock()
        client = AsyncMock()
        client.reverse_lookup = AsyncMock(return_value={
            "comfy_node_name": "ADE_Loader",
            "node": {"id": "comfyui-animatediff", "name": "AnimateDiff",
                     "latest_version": {"version": "1.2.3"}},
        })
        resolver = RegistryResolver(client, index, SNAPSHOT)
        result = await resolver.resolve_one("ADE_Loader")
        assert result["package"] == "comfyui-animatediff"
        index.cache_positive.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_not_in_registry(self):
        from comfy_mcp.registry.resolver import RegistryResolver
        index = MagicMock()
        index.lookup = MagicMock(return_value=None)
        index.cache_negative = MagicMock()
        client = AsyncMock()
        client.reverse_lookup = AsyncMock(return_value=None)
        resolver = RegistryResolver(client, index, SNAPSHOT)
        result = await resolver.resolve_one("MyPrivateNode")
        assert result["package"] is None
        assert "not found" in result["note"].lower() or "private" in result["note"].lower()
        index.cache_negative.assert_called_once()


class TestResolveBatch:
    @pytest.mark.asyncio
    async def test_batch_deduplicates_packages(self):
        from comfy_mcp.registry.resolver import RegistryResolver
        index = MagicMock()
        # Both nodes from same package
        def lookup_side_effect(name):
            return {"class": name, "package": "comfyui-animatediff", "version": "1.2.3", "cached_at": time.time()}
        index.lookup = MagicMock(side_effect=lookup_side_effect)
        client = AsyncMock()
        resolver = RegistryResolver(client, index, SNAPSHOT)
        result = await resolver.resolve_batch(["ADE_Loader", "ADE_Settings"])
        assert result["unique_packages"] == 1
        assert "Install 1 package" in result["resolution"]

    @pytest.mark.asyncio
    async def test_batch_with_mixed_results(self):
        from comfy_mcp.registry.resolver import RegistryResolver
        index = MagicMock()
        def lookup_side_effect(name):
            if name == "KnownNode":
                return {"class": name, "package": "pkg-a", "version": "1.0", "cached_at": time.time()}
            return None
        index.lookup = MagicMock(side_effect=lookup_side_effect)
        index.cache_negative = MagicMock()
        client = AsyncMock()
        client.reverse_lookup = AsyncMock(return_value=None)
        resolver = RegistryResolver(client, index, SNAPSHOT)
        result = await resolver.resolve_batch(["KnownNode", "UnknownNode"])
        assert result["resolved"] == 1
        assert result["unresolved"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_registry_resolver.py -v`
Expected: FAIL

- [ ] **Step 3: Implement RegistryResolver**

```python
# src/comfy_mcp/registry/resolver.py
"""RegistryResolver — maps missing nodes to registry packages.

Uses the RegistryIndex cache first, falls back to API lookups.
Deduplicates results (multiple nodes from same package = one install).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("comfypilot.registry")


class RegistryResolver:
    """Resolves missing node class names to registry packages."""

    def __init__(self, client, index, snapshot: dict[str, Any]):
        self._client = client
        self._index = index
        self._snapshot = snapshot

    async def resolve_one(self, class_name: str) -> dict[str, Any]:
        """Resolve a single node class name to a package.

        Returns: {"class": str, "package": str|None, "version": str|None,
                  "compatible": bool, "install_cmd": str|None, "note": str|None}
        """
        # Check cache first
        cached = self._index.lookup(class_name)
        if cached is not None:
            if cached.get("package") is None:
                return {
                    "class": class_name,
                    "package": None,
                    "version": None,
                    "compatible": False,
                    "install_cmd": None,
                    "note": "Not found in registry — may be a local/private custom node",
                }
            return self._build_result(class_name, cached["package"], cached.get("version"))

        # API lookup
        api_result = await self._client.reverse_lookup(class_name)
        if api_result is None:
            self._index.cache_negative(class_name)
            return {
                "class": class_name,
                "package": None,
                "version": None,
                "compatible": False,
                "install_cmd": None,
                "note": "Not found in registry — may be a local/private custom node",
            }

        # Extract package info
        node_info = api_result.get("node", {})
        package_id = node_info.get("id", "")
        latest = node_info.get("latest_version", {})
        version = latest.get("version", "unknown")

        self._index.cache_positive(class_name, package_id, version)
        return self._build_result(class_name, package_id, version)

    def _build_result(self, class_name: str, package_id: str, version: str | None) -> dict[str, Any]:
        """Build a resolution result with compatibility info."""
        return {
            "class": class_name,
            "package": package_id,
            "latest_version": version,
            "compatible": True,  # TODO: full compat check against snapshot in future
            "install_cmd": f"comfy node install {package_id}",
            "note": None,
        }

    async def resolve_batch(self, class_names: list[str]) -> dict[str, Any]:
        """Resolve multiple missing node classes, deduplicating by package."""
        results = []
        packages_seen: dict[str, list[str]] = {}  # package_id -> [class_names]

        for name in class_names:
            result = await self.resolve_one(name)
            results.append(result)

            pkg = result.get("package")
            if pkg:
                if pkg not in packages_seen:
                    packages_seen[pkg] = []
                packages_seen[pkg].append(name)

        # Add deduplication notes
        for result in results:
            pkg = result.get("package")
            if pkg and len(packages_seen.get(pkg, [])) > 1:
                others = [n for n in packages_seen[pkg] if n != result["class"]]
                if others:
                    result["note"] = f"Same package as {', '.join(others)}"

        # Save index after batch
        self._index.save()

        resolved = sum(1 for r in results if r.get("package") is not None)
        unresolved = len(results) - resolved
        unique_packages = len(packages_seen)

        resolution = f"Install {unique_packages} package(s) to resolve {resolved} missing node(s)"
        if unresolved > 0:
            resolution += f". {unresolved} node(s) not found in registry."

        return {
            "nodes": results,
            "resolved": resolved,
            "unresolved": unresolved,
            "unique_packages": unique_packages,
            "resolution": resolution,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_registry_resolver.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/registry/resolver.py tests/test_registry_resolver.py && git commit -m "feat(v0.7): add RegistryResolver with batch resolution and deduplication"
```

---

### Task 4: Enhance compat engine with registry data

**Files:**
- Modify: `src/comfy_mcp/compat/engine.py`
- Modify: `tests/test_compat_engine.py`

- [ ] **Step 1: Write failing test for enriched output**

Add to `tests/test_compat_engine.py`:

```python
class TestCompatEngineWithRegistry:
    def test_missing_nodes_enriched_when_registry_provided(self):
        from comfy_mcp.compat.engine import run_preflight
        wf = {"1": {"class_type": "UnknownNode", "inputs": {}}}
        registry_data = {
            "UnknownNode": {
                "class": "UnknownNode",
                "package": "some-custom-pack",
                "latest_version": "1.0.0",
                "compatible": True,
                "install_cmd": "comfy node install some-custom-pack",
                "note": None,
            }
        }
        result = run_preflight(wf, SNAPSHOT, registry_resolutions=registry_data)
        assert result["status"] == "blocked"
        # missing_nodes should now be dicts, not plain strings
        assert isinstance(result["missing_nodes"][0], dict)
        assert result["missing_nodes"][0]["package"] == "some-custom-pack"

    def test_missing_nodes_plain_when_no_registry(self):
        from comfy_mcp.compat.engine import run_preflight
        wf = {"1": {"class_type": "UnknownNode", "inputs": {}}}
        result = run_preflight(wf, SNAPSHOT)
        # Without registry, missing_nodes stays as plain strings (backwards compat)
        assert isinstance(result["missing_nodes"][0], str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_compat_engine.py::TestCompatEngineWithRegistry -v`
Expected: FAIL

- [ ] **Step 3: Add registry_resolutions parameter to run_preflight**

Modify `run_preflight` in `src/comfy_mcp/compat/engine.py` to accept an optional `registry_resolutions` parameter:

```python
def run_preflight(workflow: Any, snapshot: dict, registry_resolutions: dict[str, dict] | None = None) -> dict[str, Any]:
```

At the point where `missing_nodes` is assembled, enrich entries if registry data is provided:

```python
    # After environment check, before building result:
    if registry_resolutions and env_result.get("missing_nodes"):
        enriched_missing = []
        for node_name in env_result["missing_nodes"]:
            if node_name in registry_resolutions:
                enriched_missing.append(registry_resolutions[node_name])
            else:
                enriched_missing.append(node_name)
        missing_nodes = enriched_missing
    else:
        missing_nodes = env_result.get("missing_nodes", [])
```

Use `missing_nodes` in the final result dict instead of `env_result.get("missing_nodes", [])`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_compat_engine.py -v`
Expected: ALL pass (existing + new)

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/compat/engine.py tests/test_compat_engine.py && git commit -m "feat(v0.7): enhance compat engine with registry package resolution"
```

---

## Chunk 4: MCP Tools + Integration

### Task 5: MCP tools for registry

**Files:**
- Create: `src/comfy_mcp/tools/registry.py`
- Create: `tests/test_tools_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools_registry.py
"""Tests for registry MCP tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def registry_ctx(mock_ctx):
    client_mock = AsyncMock()
    client_mock.search_nodes = AsyncMock(return_value={"nodes": [{"id": "pkg-a", "name": "Package A"}], "total": 1})
    client_mock.get_node = AsyncMock(return_value={"id": "pkg-a", "name": "Package A", "latest_version": {"version": "1.0"}})

    index_mock = MagicMock()
    index_mock.summary = MagicMock(return_value={"total_entries": 5, "positive_entries": 4, "negative_entries": 1})
    index_mock.lookup = MagicMock(return_value=None)
    index_mock.save = MagicMock()
    index_mock.cache_positive = MagicMock()
    index_mock.cache_negative = MagicMock()

    graph_mock = MagicMock()
    graph_mock.snapshot = {"version": "0.17.0", "os": "nt", "gpu_devices": [], "node_classes": set(), "models": {}}

    mock_ctx.request_context.lifespan_context["registry_client"] = client_mock
    mock_ctx.request_context.lifespan_context["registry_index"] = index_mock
    mock_ctx.request_context.lifespan_context["install_graph"] = graph_mock
    return mock_ctx


class TestSearchRegistry:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, registry_ctx):
        from comfy_mcp.tools.registry import comfy_search_registry
        result = json.loads(await comfy_search_registry(query="animatediff", ctx=registry_ctx))
        assert "nodes" in result


class TestGetPackage:
    @pytest.mark.asyncio
    async def test_get_package(self, registry_ctx):
        from comfy_mcp.tools.registry import comfy_get_package
        result = json.loads(await comfy_get_package(package_id="pkg-a", ctx=registry_ctx))
        assert result["id"] == "pkg-a"


class TestResolveMissing:
    @pytest.mark.asyncio
    async def test_resolve_missing(self, registry_ctx):
        from comfy_mcp.tools.registry import comfy_resolve_missing
        registry_ctx.request_context.lifespan_context["registry_client"].reverse_lookup = AsyncMock(return_value=None)
        result = json.loads(await comfy_resolve_missing(node_classes=["FakeNode"], ctx=registry_ctx))
        assert "nodes" in result


class TestRegistryStatus:
    @pytest.mark.asyncio
    async def test_status(self, registry_ctx):
        from comfy_mcp.tools.registry import comfy_registry_status
        result = json.loads(await comfy_registry_status(ctx=registry_ctx))
        assert "total_entries" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_tools_registry.py -v`
Expected: FAIL

- [ ] **Step 3: Implement MCP tools**

```python
# src/comfy_mcp/tools/registry.py
"""Registry tools — MCP surface for ComfyUI package registry integration."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["registry_client"]


def _index(ctx: Context):
    return ctx.request_context.lifespan_context["registry_index"]


@mcp.tool(
    annotations={
        "title": "Search Registry",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_search_registry(
    query: str,
    tags: list[str] | None = None,
    limit: int = 10,
    ctx: Context = None,
) -> str:
    """Search the ComfyUI package registry.

    Args:
        query: Search query (package name, description, or node class name).
        tags: Optional tag filters.
        limit: Maximum results (default 10).
    """
    client = _client(ctx)
    result = await client.search_nodes(query, limit=limit)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Package",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_get_package(package_id: str, ctx: Context = None) -> str:
    """Get full metadata for a registry package.

    Args:
        package_id: Package identifier (e.g., 'comfyui-animatediff-evolved').
    """
    client = _client(ctx)
    result = await client.get_node(package_id)
    if result is None:
        return json.dumps({"error": f"Package '{package_id}' not found"}, indent=2)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Resolve Missing Nodes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_resolve_missing(
    workflow: dict | None = None,
    node_classes: list[str] | None = None,
    ctx: Context = None,
) -> str:
    """Resolve missing node classes to their registry packages.

    Provide either a workflow dict or a list of node class names.
    Returns package info with install commands for each missing node.

    Args:
        workflow: Optional workflow dict — extracts class_type from each node.
        node_classes: Optional explicit list of node class names to resolve.
    """
    client = _client(ctx)
    index = _index(ctx)
    install_graph = ctx.request_context.lifespan_context.get("install_graph")

    # Build list of class names to resolve
    classes = list(node_classes or [])
    if workflow:
        for node in workflow.values():
            ct = node.get("class_type", "")
            if ct and ct not in classes:
                classes.append(ct)

    # Filter to actually missing nodes
    if install_graph and install_graph.snapshot:
        installed = install_graph.snapshot.get("node_classes", set())
        classes = [c for c in classes if c not in installed]
        snapshot = install_graph.snapshot
    else:
        snapshot = {}

    if not classes:
        return json.dumps({"nodes": [], "resolved": 0, "unresolved": 0,
                           "resolution": "All nodes are already installed."}, indent=2)

    from comfy_mcp.registry.resolver import RegistryResolver
    resolver = RegistryResolver(client, index, snapshot)
    result = await resolver.resolve_batch(classes)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Check Package Compatibility",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_check_compatibility(package_id: str, ctx: Context = None) -> str:
    """Check if a registry package is compatible with the current environment.

    Args:
        package_id: Package identifier to check.
    """
    client = _client(ctx)
    pkg = await client.get_node(package_id)
    if pkg is None:
        return json.dumps({"error": f"Package '{package_id}' not found"}, indent=2)

    install_graph = ctx.request_context.lifespan_context.get("install_graph")
    warnings = []

    if install_graph and install_graph.snapshot:
        s = install_graph.snapshot
        # Check ComfyUI version
        required_version = pkg.get("supported_comfyui_version")
        if required_version and s.get("version"):
            warnings.append(f"Requires ComfyUI {required_version}, installed: {s['version']}")

        # Check OS
        supported_os = pkg.get("supported_os", [])
        if supported_os and s.get("os"):
            os_name = s["os"]
            if not any(os_name.lower() in so.lower() for so in supported_os):
                warnings.append(f"OS {os_name} may not be supported (supported: {supported_os})")

    return json.dumps({
        "package_id": package_id,
        "name": pkg.get("name", ""),
        "latest_version": pkg.get("latest_version", {}).get("version", "unknown"),
        "compatible": len(warnings) == 0,
        "warnings": warnings,
        "install_cmd": f"comfy node install {package_id}",
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Registry Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_registry_status(ctx: Context = None) -> str:
    """Show registry cache statistics — index size, entry counts, last sync."""
    index = _index(ctx)
    return json.dumps(index.summary(), indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_tools_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/tools/registry.py tests/test_tools_registry.py && git commit -m "feat(v0.7): add 5 MCP tools for registry integration"
```

---

### Task 6: Server integration + README

**Files:**
- Modify: `src/comfy_mcp/server.py`
- Modify: `src/comfy_mcp/tool_registry.py`
- Modify: `tests/conftest.py`
- Modify: `README.md`

- [ ] **Step 1: Add to server.py lifespan**

After knowledge_manager initialization, add:

```python
    from comfy_mcp.registry.client import RegistryClient
    from comfy_mcp.registry.index import RegistryIndex

    registry_client = RegistryClient()
    registry_index = RegistryIndex()
```

Add to yield dict:
```python
            "registry_client": registry_client,
            "registry_index": registry_index,
```

Add cleanup in finally (before `await client.close()`):
```python
        await registry_client.close()
```

Add module-level global and resource:
```python
_shared_registry_index = None
```

```python
@mcp.resource("comfy://registry/status")
async def registry_status_resource() -> str:
    """Registry cache stats and index coverage."""
    if _shared_registry_index is None:
        return json.dumps({"status": "not_initialized"})
    return json.dumps(_shared_registry_index.summary(), indent=2)
```

- [ ] **Step 2: Register in tool_registry.py**

```python
from comfy_mcp.tools import registry     # noqa: F401 -- v0.7 Registry Integration
```

- [ ] **Step 3: Update conftest.py**

Add to `lifespan_context`:
```python
        "registry_client": AsyncMock(),
        "registry_index": MagicMock(),
```

- [ ] **Step 4: Update README.md**

- Version: `v0.7.0`
- Tool count: `92-tool runtime surface`
- Add Registry Integration section (### 18)
- Resources: 11
- Add `comfy://registry/status` resource
- Update test count estimate
- Update "What This Is" bullets

- [ ] **Step 5: Run full test suite**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest -v`
Expected: ALL pass

- [ ] **Step 6: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/server.py src/comfy_mcp/tool_registry.py tests/conftest.py README.md && git commit -m "feat: v0.7.0 — Registry Integration (92 tools, 11 resources)"
```

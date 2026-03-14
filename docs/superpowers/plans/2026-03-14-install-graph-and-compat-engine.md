# Install Graph & Compatibility Engine — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a grounded Install Graph that snapshots machine state, and a multi-pass Compatibility Engine that validates whether a workflow can actually run on this machine.

**Architecture:** The Install Graph queries ComfyUI's live endpoints (`object_info`, `get_models`, `get_features`, `get_extensions`, `get_embeddings`, `system_stats`) and caches a structured snapshot. The Compatibility Engine runs 3 passes (structural, schema, environment) against this graph to produce a confidence-scored preflight report. A Model Resolver checks whether specific model references (checkpoints, LoRAs, VAEs, embeddings) can be found locally.

**Tech Stack:** Python 3.12+, httpx (via existing ComfyClient), FastMCP tools/resources, pytest + pytest-asyncio for tests.

---

## File Structure

### New files to create

| File | Responsibility |
|------|---------------|
| `src/comfy_mcp/install/__init__.py` | Package init |
| `src/comfy_mcp/install/install_graph.py` | Canonical machine state snapshot — queries client, caches result |
| `src/comfy_mcp/install/model_resolver.py` | Resolves model references against installed models |
| `src/comfy_mcp/compat/__init__.py` | Package init |
| `src/comfy_mcp/compat/engine.py` | Orchestrates passes, returns unified report |
| `src/comfy_mcp/compat/structural.py` | Pass 1: valid graph shape, links, output nodes |
| `src/comfy_mcp/compat/schema.py` | Pass 2: inputs/outputs/widgets match object_info |
| `src/comfy_mcp/compat/environment.py` | Pass 3: nodes installed, models resolvable |
| `src/comfy_mcp/tools/install.py` | MCP tools for install graph (refresh, summary, model resolution) |
| `src/comfy_mcp/tools/compat.py` | MCP tools for compatibility (preflight, explain) |
| `tests/test_install_graph.py` | Tests for InstallGraph |
| `tests/test_model_resolver.py` | Tests for ModelResolver |
| `tests/test_compat_structural.py` | Tests for Pass 1 |
| `tests/test_compat_schema.py` | Tests for Pass 2 |
| `tests/test_compat_environment.py` | Tests for Pass 3 |
| `tests/test_compat_engine.py` | Tests for orchestrator |
| `tests/test_tools_install.py` | Tests for install tools |
| `tests/test_tools_compat.py` | Tests for compat tools |

### Files to modify

| File | Change |
|------|--------|
| `src/comfy_mcp/server.py` | Add InstallGraph to lifespan context, add `comfy://install/graph` resource |
| `src/comfy_mcp/tool_registry.py` | Register new `install` and `compat` tool modules |
| `README.md` | Update tool count and feature list |

---

## Chunk 1: Install Graph

### Task 1: InstallGraph data model and snapshot

**Files:**
- Create: `src/comfy_mcp/install/__init__.py`
- Create: `src/comfy_mcp/install/install_graph.py`
- Test: `tests/test_install_graph.py`

- [ ] **Step 1: Write the failing test for InstallGraph.refresh()**

```python
# tests/test_install_graph.py
"""Tests for InstallGraph — canonical machine state snapshot."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.capabilities = {
        "profile": "local",
        "version": "0.17.0",
        "ws_available": True,
        "features": ["some-feature"],
    }
    client.get_system_stats = AsyncMock(return_value={
        "system": {
            "os": "nt",
            "comfyui_version": "0.17.0",
            "python_version": "3.12.0",
            "pytorch_version": "2.5.0",
        },
        "devices": [{"name": "RTX 5090", "type": "cuda", "vram_total": 34359738368, "vram_free": 30000000000}],
    })
    client.get_object_info = AsyncMock(return_value={
        "KSampler": {"input": {"required": {"seed": ["INT"]}}, "output": ["LATENT"], "category": "sampling"},
        "CLIPTextEncode": {"input": {"required": {"text": ["STRING"]}}, "output": ["CONDITIONING"], "category": "conditioning"},
        "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["model1.safetensors", "model2.safetensors"]]}}, "output": ["MODEL", "CLIP", "VAE"], "category": "loaders"},
    })
    client.get_models = AsyncMock(side_effect=lambda folder: {
        "checkpoints": ["model1.safetensors", "model2.safetensors"],
        "loras": ["detail.safetensors"],
        "vae": ["sdxl_vae.safetensors"],
        "controlnet": [],
        "upscale_models": ["4x_NMKD.pth"],
    }.get(folder, []))
    client.get_features = AsyncMock(return_value=["some-feature"])
    client.get_extensions = AsyncMock(return_value=["ext.core.nodes", "ext.custom.animatediff"])
    client.get_embeddings = AsyncMock(return_value=["EasyNegative", "badhandv4"])
    return client


class TestInstallGraphRefresh:
    @pytest.mark.asyncio
    async def test_refresh_populates_snapshot(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        snap = graph.snapshot
        assert snap is not None
        assert snap["version"] == "0.17.0"
        assert snap["profile"] == "local"
        assert "KSampler" in snap["node_classes"]
        assert "model1.safetensors" in snap["models"]["checkpoints"]
        assert "EasyNegative" in snap["embeddings"]
        assert "ext.custom.animatediff" in snap["extensions"]
        assert snap["refreshed_at"] > 0

    @pytest.mark.asyncio
    async def test_snapshot_is_none_before_refresh(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        assert graph.snapshot is None

    @pytest.mark.asyncio
    async def test_refresh_updates_timestamp(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        t1 = graph.snapshot["refreshed_at"]
        await graph.refresh()
        t2 = graph.snapshot["refreshed_at"]
        assert t2 >= t1

    @pytest.mark.asyncio
    async def test_node_count_and_categories(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        assert graph.snapshot["node_count"] == 3
        cats = graph.snapshot["categories"]
        assert "sampling" in cats
        assert "conditioning" in cats

    @pytest.mark.asyncio
    async def test_gpu_info_included(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        assert len(graph.snapshot["gpu_devices"]) == 1
        assert graph.snapshot["gpu_devices"][0]["name"] == "RTX 5090"

    @pytest.mark.asyncio
    async def test_model_folder_error_handled(self, mock_client):
        """If a model folder errors, it's skipped gracefully."""
        original = mock_client.get_models.side_effect
        async def flaky(folder):
            if folder == "controlnet":
                raise Exception("folder not found")
            return (await original(folder)) if callable(original) else original(folder)
        # Re-mock with side_effect that raises for controlnet
        mock_client.get_models = AsyncMock(side_effect=lambda folder: {
            "checkpoints": ["model1.safetensors", "model2.safetensors"],
            "loras": ["detail.safetensors"],
            "vae": ["sdxl_vae.safetensors"],
            "upscale_models": ["4x_NMKD.pth"],
        }.get(folder, (_ for _ in ()).throw(Exception("folder not found"))))
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        # Should not raise
        await graph.refresh()
        assert "checkpoints" in graph.snapshot["models"]


class TestInstallGraphSummary:
    @pytest.mark.asyncio
    async def test_summary_returns_counts(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        summary = graph.summary()
        assert summary["node_count"] == 3
        assert summary["extension_count"] == 2
        assert summary["embedding_count"] == 2
        assert "checkpoints" in summary["model_counts"]
        assert summary["model_counts"]["checkpoints"] == 2


class TestInstallGraphHasNode:
    @pytest.mark.asyncio
    async def test_has_node_true(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        assert graph.has_node("KSampler") is True

    @pytest.mark.asyncio
    async def test_has_node_false(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        assert graph.has_node("NonExistentNode") is False

    @pytest.mark.asyncio
    async def test_has_node_before_refresh_returns_false(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        assert graph.has_node("KSampler") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest tests/test_install_graph.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'comfy_mcp.install'`

- [ ] **Step 3: Write the InstallGraph implementation**

```python
# src/comfy_mcp/install/__init__.py
# (empty)
```

```python
# src/comfy_mcp/install/install_graph.py
"""InstallGraph — canonical snapshot of the connected ComfyUI machine state.

Queries object_info, models, features, extensions, embeddings, and system stats,
then caches a structured snapshot for use by the Compatibility Engine and tools.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("comfypilot.install")

MODEL_FOLDERS = ("checkpoints", "loras", "vae", "controlnet", "upscale_models", "clip", "diffusers", "hypernetworks")


class InstallGraph:
    """Canonical machine state snapshot."""

    def __init__(self, client):
        self._client = client
        self._snapshot: dict[str, Any] | None = None

    @property
    def snapshot(self) -> dict[str, Any] | None:
        return self._snapshot

    async def refresh(self) -> dict[str, Any]:
        """Query ComfyUI and rebuild the snapshot."""
        client = self._client

        # System info
        stats = await client.get_system_stats()
        system = stats.get("system", {})
        devices = stats.get("devices", [])

        # Node catalog
        object_info = await client.get_object_info()
        node_classes = set(object_info.keys())
        categories = set()
        for info in object_info.values():
            cat = info.get("category", "")
            if cat:
                categories.add(cat)

        # Models per folder
        models: dict[str, list[str]] = {}
        for folder in MODEL_FOLDERS:
            try:
                models[folder] = await client.get_models(folder)
            except Exception:
                logger.debug("Skipping model folder %s (not available)", folder)

        # Features, extensions, embeddings
        try:
            features = await client.get_features()
        except Exception:
            features = []

        try:
            extensions = await client.get_extensions()
        except Exception:
            extensions = []

        try:
            embeddings = await client.get_embeddings()
        except Exception:
            embeddings = []

        self._snapshot = {
            "version": system.get("comfyui_version") or client.capabilities.get("version"),
            "profile": client.capabilities.get("profile", "unknown"),
            "python_version": system.get("python_version"),
            "pytorch_version": system.get("pytorch_version"),
            "os": system.get("os"),
            "gpu_devices": devices,
            "node_classes": sorted(node_classes),
            "node_count": len(node_classes),
            "categories": sorted(categories),
            "object_info": object_info,
            "models": models,
            "features": features if isinstance(features, list) else [],
            "extensions": extensions,
            "embeddings": embeddings,
            "refreshed_at": time.time(),
        }
        logger.info("Install graph refreshed: %d nodes, %d extensions, %d embeddings",
                     len(node_classes), len(extensions), len(embeddings))
        return self._snapshot

    def summary(self) -> dict[str, Any]:
        """Return a compact summary of the install graph."""
        if not self._snapshot:
            return {"status": "not_refreshed"}
        s = self._snapshot
        return {
            "version": s["version"],
            "profile": s["profile"],
            "node_count": s["node_count"],
            "category_count": len(s["categories"]),
            "extension_count": len(s["extensions"]),
            "embedding_count": len(s["embeddings"]),
            "model_counts": {folder: len(files) for folder, files in s["models"].items()},
            "gpu_count": len(s["gpu_devices"]),
            "refreshed_at": s["refreshed_at"],
        }

    def has_node(self, node_type: str) -> bool:
        """Check if a node type is installed."""
        if not self._snapshot:
            return False
        return node_type in self._snapshot["node_classes"]

    def get_node_schema(self, node_type: str) -> dict | None:
        """Get the object_info schema for a specific node type."""
        if not self._snapshot:
            return None
        return self._snapshot["object_info"].get(node_type)

    def find_models(self, query: str, folder: str | None = None) -> dict[str, list[str]]:
        """Search installed models by substring match."""
        if not self._snapshot:
            return {}
        q = query.lower()
        results = {}
        folders = [folder] if folder else self._snapshot["models"].keys()
        for f in folders:
            files = self._snapshot["models"].get(f, [])
            matches = [m for m in files if q in m.lower()]
            if matches:
                results[f] = matches
        return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest tests/test_install_graph.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/comfy_mcp/install/ tests/test_install_graph.py
git commit -m "feat(install): add InstallGraph machine state snapshot"
```

---

### Task 2: Model Resolver

**Files:**
- Create: `src/comfy_mcp/install/model_resolver.py`
- Test: `tests/test_model_resolver.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_model_resolver.py
"""Tests for ModelResolver — resolves model references against installed models."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


def _make_graph_snapshot():
    """Create a minimal install graph snapshot for testing."""
    return {
        "models": {
            "checkpoints": ["sd_xl_base_1.0.safetensors", "dreamshaper_8.safetensors", "v1-5-pruned.safetensors"],
            "loras": ["detail_tweaker.safetensors", "add_detail.safetensors"],
            "vae": ["sdxl_vae.safetensors"],
            "controlnet": ["control_v11p_sd15_openpose.pth"],
            "upscale_models": [],
        },
        "embeddings": ["EasyNegative", "badhandv4", "verybadimagenegative_v1.3"],
    }


class TestModelResolver:
    def test_resolve_exact_match(self):
        from comfy_mcp.install.model_resolver import ModelResolver
        resolver = ModelResolver(_make_graph_snapshot())
        result = resolver.resolve("sd_xl_base_1.0.safetensors", "checkpoints")
        assert result["found"] is True
        assert result["exact"] is True
        assert result["match"] == "sd_xl_base_1.0.safetensors"

    def test_resolve_not_found(self):
        from comfy_mcp.install.model_resolver import ModelResolver
        resolver = ModelResolver(_make_graph_snapshot())
        result = resolver.resolve("nonexistent_model.safetensors", "checkpoints")
        assert result["found"] is False

    def test_resolve_partial_match(self):
        from comfy_mcp.install.model_resolver import ModelResolver
        resolver = ModelResolver(_make_graph_snapshot())
        result = resolver.resolve("dreamshaper", "checkpoints")
        assert result["found"] is True
        assert result["exact"] is False
        assert "dreamshaper_8.safetensors" in result["candidates"]

    def test_resolve_embedding(self):
        from comfy_mcp.install.model_resolver import ModelResolver
        resolver = ModelResolver(_make_graph_snapshot())
        result = resolver.resolve_embedding("EasyNegative")
        assert result["found"] is True

    def test_resolve_embedding_not_found(self):
        from comfy_mcp.install.model_resolver import ModelResolver
        resolver = ModelResolver(_make_graph_snapshot())
        result = resolver.resolve_embedding("UnknownEmbed")
        assert result["found"] is False

    def test_resolve_all_from_workflow(self):
        from comfy_mcp.install.model_resolver import ModelResolver
        resolver = ModelResolver(_make_graph_snapshot())
        refs = [
            {"name": "sd_xl_base_1.0.safetensors", "folder": "checkpoints"},
            {"name": "missing_lora.safetensors", "folder": "loras"},
            {"name": "detail_tweaker.safetensors", "folder": "loras"},
        ]
        report = resolver.resolve_all(refs)
        assert report["resolved"] == 2
        assert report["missing"] == 1
        assert report["missing_refs"][0]["name"] == "missing_lora.safetensors"

    def test_resolve_across_all_folders(self):
        from comfy_mcp.install.model_resolver import ModelResolver
        resolver = ModelResolver(_make_graph_snapshot())
        result = resolver.resolve("detail_tweaker.safetensors")
        assert result["found"] is True
        assert result["folder"] == "loras"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest tests/test_model_resolver.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the ModelResolver implementation**

```python
# src/comfy_mcp/install/model_resolver.py
"""ModelResolver — resolves model references against the install graph snapshot."""

from __future__ import annotations

from typing import Any


class ModelResolver:
    """Resolves model file references against installed models."""

    def __init__(self, snapshot: dict[str, Any]):
        self._models = snapshot.get("models", {})
        self._embeddings = snapshot.get("embeddings", [])

    def resolve(self, name: str, folder: str | None = None) -> dict[str, Any]:
        """Resolve a model reference.

        Args:
            name: Model filename or partial name to find
            folder: Specific folder to search. If None, searches all.

        Returns:
            Dict with found, exact, match/candidates, folder
        """
        folders = [folder] if folder else list(self._models.keys())
        name_lower = name.lower()

        for f in folders:
            files = self._models.get(f, [])
            # Exact match
            if name in files:
                return {"found": True, "exact": True, "match": name, "folder": f}
            # Substring match
            candidates = [m for m in files if name_lower in m.lower()]
            if candidates:
                return {"found": True, "exact": False, "candidates": candidates, "folder": f}

        return {"found": False, "name": name, "folder": folder}

    def resolve_embedding(self, name: str) -> dict[str, Any]:
        """Resolve an embedding reference."""
        if name in self._embeddings:
            return {"found": True, "exact": True, "match": name}
        candidates = [e for e in self._embeddings if name.lower() in e.lower()]
        if candidates:
            return {"found": True, "exact": False, "candidates": candidates}
        return {"found": False, "name": name}

    def resolve_all(self, refs: list[dict[str, str]]) -> dict[str, Any]:
        """Resolve a batch of model references.

        Args:
            refs: List of {"name": "...", "folder": "..."} dicts.

        Returns:
            Report with resolved/missing counts and details.
        """
        resolved_refs = []
        missing_refs = []
        for ref in refs:
            result = self.resolve(ref["name"], ref.get("folder"))
            if result["found"]:
                resolved_refs.append({**ref, **result})
            else:
                missing_refs.append(ref)
        return {
            "resolved": len(resolved_refs),
            "missing": len(missing_refs),
            "total": len(refs),
            "resolved_refs": resolved_refs,
            "missing_refs": missing_refs,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest tests/test_model_resolver.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/comfy_mcp/install/model_resolver.py tests/test_model_resolver.py
git commit -m "feat(install): add ModelResolver for model reference resolution"
```

---

### Task 3: Wire InstallGraph into server lifespan + tools + resource

**Files:**
- Modify: `src/comfy_mcp/server.py`
- Modify: `src/comfy_mcp/tool_registry.py`
- Create: `src/comfy_mcp/tools/install.py`
- Test: `tests/test_tools_install.py`

- [ ] **Step 1: Write the failing test for install tools**

```python
# tests/test_tools_install.py
"""Tests for install tools — MCP surface for InstallGraph."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def graph_mock():
    """Mock InstallGraph with a populated snapshot."""
    graph = MagicMock()
    graph.snapshot = {
        "version": "0.17.0",
        "profile": "local",
        "node_classes": ["KSampler", "CLIPTextEncode"],
        "node_count": 2,
        "categories": ["sampling", "conditioning"],
        "models": {"checkpoints": ["model.safetensors"], "loras": ["detail.safetensors"]},
        "extensions": ["ext.core"],
        "embeddings": ["EasyNeg"],
        "features": [],
        "gpu_devices": [{"name": "RTX 5090"}],
        "refreshed_at": 1710000000.0,
        "object_info": {},
    }
    graph.summary = MagicMock(return_value={
        "version": "0.17.0",
        "profile": "local",
        "node_count": 2,
        "category_count": 2,
        "extension_count": 1,
        "embedding_count": 1,
        "model_counts": {"checkpoints": 1, "loras": 1},
        "gpu_count": 1,
        "refreshed_at": 1710000000.0,
    })
    graph.refresh = AsyncMock(return_value=graph.snapshot)
    graph.has_node = MagicMock(side_effect=lambda n: n in ["KSampler", "CLIPTextEncode"])
    graph.find_models = MagicMock(return_value={"checkpoints": ["model.safetensors"]})
    return graph


@pytest.fixture
def install_ctx(mock_ctx, graph_mock):
    mock_ctx.request_context.lifespan_context["install_graph"] = graph_mock
    return mock_ctx


class TestRefreshInstallGraph:
    @pytest.mark.asyncio
    async def test_refresh_returns_summary(self, install_ctx, graph_mock):
        from comfy_mcp.tools.install import comfy_refresh_install_graph
        result = json.loads(await comfy_refresh_install_graph(ctx=install_ctx))
        graph_mock.refresh.assert_called_once()
        assert result["status"] == "ok"
        assert result["summary"]["node_count"] == 2


class TestGetInstallSummary:
    @pytest.mark.asyncio
    async def test_returns_summary(self, install_ctx, graph_mock):
        from comfy_mcp.tools.install import comfy_get_install_summary
        result = json.loads(await comfy_get_install_summary(ctx=install_ctx))
        assert result["node_count"] == 2
        assert result["version"] == "0.17.0"


class TestCheckModelResolution:
    @pytest.mark.asyncio
    async def test_resolves_model(self, install_ctx, graph_mock):
        from comfy_mcp.tools.install import comfy_check_model
        result = json.loads(await comfy_check_model(name="model", folder="checkpoints", ctx=install_ctx))
        assert result["found"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest tests/test_tools_install.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create install tools module**

```python
# src/comfy_mcp/tools/install.py
"""Install tools — MCP surface for InstallGraph and ModelResolver."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _graph(ctx: Context):
    return ctx.request_context.lifespan_context["install_graph"]


@mcp.tool(
    annotations={
        "title": "Refresh Install Graph",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_refresh_install_graph(ctx: Context = None) -> str:
    """Re-scan the connected ComfyUI instance and rebuild the install graph.

    Queries object_info, models, features, extensions, embeddings, and system stats.
    Call this after installing custom nodes, adding models, or updating ComfyUI.
    """
    graph = _graph(ctx)
    await graph.refresh()
    return json.dumps({"status": "ok", "summary": graph.summary()}, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Install Summary",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_install_summary(ctx: Context = None) -> str:
    """Get a compact summary of the machine's ComfyUI installation.

    Returns counts of installed nodes, models, extensions, embeddings, GPU info.
    """
    graph = _graph(ctx)
    if not graph.snapshot:
        await graph.refresh()
    return json.dumps(graph.summary(), indent=2)


@mcp.tool(
    annotations={
        "title": "Check Model",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_check_model(
    name: str,
    folder: str | None = None,
    ctx: Context = None,
) -> str:
    """Check if a model is installed and resolvable.

    Args:
        name: Model filename or partial name
        folder: Specific folder (checkpoints, loras, vae, etc). If omitted, searches all.
    """
    graph = _graph(ctx)
    if not graph.snapshot:
        await graph.refresh()
    from comfy_mcp.install.model_resolver import ModelResolver
    resolver = ModelResolver(graph.snapshot)
    result = resolver.resolve(name, folder)
    return json.dumps(result, indent=2)
```

- [ ] **Step 4: Wire into server.py and tool_registry.py**

In `src/comfy_mcp/server.py`, add to the lifespan:

```python
# After existing imports inside comfy_lifespan:
from comfy_mcp.install.install_graph import InstallGraph

# After job_tracker creation:
install_graph = InstallGraph(client)
await install_graph.refresh()

# Add to yield dict:
"install_graph": install_graph,
```

Add the `comfy://install/graph` resource after the existing resources:

```python
@mcp.resource("comfy://install/graph")
async def install_graph_resource() -> str:
    """Full install graph snapshot."""
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    # Access via module-level ref — InstallGraph is set during lifespan
    from comfy_mcp.install.install_graph import InstallGraph
    # We need a module-level ref like _shared_client
    return json.dumps(_shared_install_graph.summary() if _shared_install_graph else {"error": "Not initialized"})
```

In `src/comfy_mcp/tool_registry.py`, add:

```python
from comfy_mcp.tools import install      # noqa: F401
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest tests/test_tools_install.py tests/test_install_graph.py tests/test_model_resolver.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/comfy_mcp/server.py src/comfy_mcp/tool_registry.py src/comfy_mcp/tools/install.py tests/test_tools_install.py
git commit -m "feat(install): wire InstallGraph into server, add install tools and resource"
```

---

## Chunk 2: Compatibility Engine

### Task 4: Structural validation (Pass 1)

**Files:**
- Create: `src/comfy_mcp/compat/__init__.py`
- Create: `src/comfy_mcp/compat/structural.py`
- Test: `tests/test_compat_structural.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_compat_structural.py
"""Tests for compatibility Pass 1: structural validation."""

from __future__ import annotations

import pytest


# Minimal valid API-format workflow
VALID_WORKFLOW = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
    "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": 42}},
    "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0]}},
}


class TestStructuralPass:
    def test_valid_workflow_passes(self):
        from comfy_mcp.compat.structural import check_structural
        result = check_structural(VALID_WORKFLOW)
        assert result["pass"] is True
        assert result["errors"] == []

    def test_empty_workflow_fails(self):
        from comfy_mcp.compat.structural import check_structural
        result = check_structural({})
        assert result["pass"] is False
        assert any("empty" in e.lower() for e in result["errors"])

    def test_not_dict_fails(self):
        from comfy_mcp.compat.structural import check_structural
        result = check_structural("not a dict")
        assert result["pass"] is False

    def test_missing_class_type_fails(self):
        from comfy_mcp.compat.structural import check_structural
        wf = {"1": {"inputs": {"seed": 42}}}
        result = check_structural(wf)
        assert result["pass"] is False
        assert any("class_type" in e for e in result["errors"])

    def test_broken_link_detected(self):
        from comfy_mcp.compat.structural import check_structural
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"model": ["999", 0]}},
        }
        result = check_structural(wf)
        assert result["pass"] is False
        assert any("999" in e for e in result["errors"])

    def test_valid_link_format(self):
        from comfy_mcp.compat.structural import check_structural
        wf = {
            "1": {"class_type": "LoadModel", "inputs": {}},
            "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}},
        }
        result = check_structural(wf)
        assert result["pass"] is True

    def test_no_output_node_warning(self):
        from comfy_mcp.compat.structural import check_structural
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 42}},
        }
        result = check_structural(wf)
        # Should pass structurally but warn about no output node
        assert any("output" in w.lower() for w in result["warnings"])

    def test_node_count_reported(self):
        from comfy_mcp.compat.structural import check_structural
        result = check_structural(VALID_WORKFLOW)
        assert result["node_count"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest tests/test_compat_structural.py -v`
Expected: FAIL

- [ ] **Step 3: Write structural validation**

```python
# src/comfy_mcp/compat/__init__.py
# (empty)
```

```python
# src/comfy_mcp/compat/structural.py
"""Compatibility Pass 1: Structural validation.

Checks that a workflow is a valid API-format graph:
- Is a non-empty dict
- Every node has class_type
- All link references point to existing nodes
- At least one likely output node exists (warning, not error)
"""

from __future__ import annotations

from typing import Any

OUTPUT_NODE_HINTS = {"SaveImage", "PreviewImage", "SaveAnimatedWEBP", "SaveAnimatedPNG",
                     "VHS_VideoCombine", "SaveVideo", "SaveAudio"}


def check_structural(workflow: Any) -> dict[str, Any]:
    """Run structural validation on an API-format workflow."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(workflow, dict):
        return {"pass": False, "errors": ["Workflow must be a dict, got " + type(workflow).__name__],
                "warnings": [], "node_count": 0}

    if len(workflow) == 0:
        return {"pass": False, "errors": ["Workflow is empty (no nodes)"],
                "warnings": [], "node_count": 0}

    node_ids = set(workflow.keys())
    has_output = False

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            errors.append(f"Node {node_id}: value is not a dict")
            continue

        class_type = node.get("class_type")
        if not class_type:
            errors.append(f"Node {node_id}: missing class_type")
            continue

        if class_type in OUTPUT_NODE_HINTS:
            has_output = True

        # Check link references in inputs
        inputs = node.get("inputs", {})
        for input_name, value in inputs.items():
            if isinstance(value, list) and len(value) == 2:
                ref_id = str(value[0])
                if ref_id not in node_ids:
                    errors.append(f"Node {node_id}.{input_name}: broken link to node {ref_id}")

    if not has_output and not errors:
        warnings.append("No recognized output node found (SaveImage, PreviewImage, etc)")

    return {
        "pass": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "node_count": len(workflow),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest tests/test_compat_structural.py -v`
Expected: All 8 PASS

- [ ] **Step 5: Commit**

```bash
git add src/comfy_mcp/compat/ tests/test_compat_structural.py
git commit -m "feat(compat): add Pass 1 structural validation"
```

---

### Task 5: Schema validation (Pass 2)

**Files:**
- Create: `src/comfy_mcp/compat/schema.py`
- Test: `tests/test_compat_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_compat_schema.py
"""Tests for compatibility Pass 2: schema validation against object_info."""

from __future__ import annotations

import pytest


OBJECT_INFO = {
    "KSampler": {
        "input": {
            "required": {
                "model": ["MODEL"],
                "seed": ["INT", {"default": 0, "min": 0, "max": 2**32}],
                "steps": ["INT", {"default": 20, "min": 1, "max": 10000}],
                "cfg": ["FLOAT", {"default": 7.0}],
                "sampler_name": [["euler", "euler_ancestral", "dpmpp_2m"]],
                "scheduler": [["normal", "karras"]],
                "positive": ["CONDITIONING"],
                "negative": ["CONDITIONING"],
                "latent_image": ["LATENT"],
            },
        },
        "output": ["LATENT"],
        "category": "sampling",
    },
    "CheckpointLoaderSimple": {
        "input": {
            "required": {
                "ckpt_name": [["model1.safetensors", "model2.safetensors"]],
            },
        },
        "output": ["MODEL", "CLIP", "VAE"],
        "category": "loaders",
    },
    "SaveImage": {
        "input": {
            "required": {
                "images": ["IMAGE"],
            },
        },
        "output": [],
        "output_node": True,
        "category": "image",
    },
}


class TestSchemaPass:
    def test_valid_inputs_pass(self):
        from comfy_mcp.compat.schema import check_schema
        wf = {
            "1": {"class_type": "KSampler", "inputs": {
                "model": ["0", 0], "seed": 42, "steps": 20, "cfg": 7.0,
                "sampler_name": "euler", "scheduler": "normal",
                "positive": ["0", 1], "negative": ["0", 2], "latent_image": ["0", 3],
            }},
        }
        result = check_schema(wf, OBJECT_INFO)
        assert result["pass"] is True

    def test_unknown_node_type_flagged(self):
        from comfy_mcp.compat.schema import check_schema
        wf = {"1": {"class_type": "NonExistentNode", "inputs": {}}}
        result = check_schema(wf, OBJECT_INFO)
        assert result["pass"] is False
        assert any("NonExistentNode" in e for e in result["errors"])

    def test_missing_required_input_flagged(self):
        from comfy_mcp.compat.schema import check_schema
        wf = {"1": {"class_type": "KSampler", "inputs": {"seed": 42}}}
        result = check_schema(wf, OBJECT_INFO)
        assert result["pass"] is False
        assert any("model" in e for e in result["errors"])

    def test_invalid_enum_value_flagged(self):
        from comfy_mcp.compat.schema import check_schema
        wf = {"1": {"class_type": "KSampler", "inputs": {
            "model": ["0", 0], "seed": 42, "steps": 20, "cfg": 7.0,
            "sampler_name": "invalid_sampler", "scheduler": "normal",
            "positive": ["0", 1], "negative": ["0", 2], "latent_image": ["0", 3],
        }}}
        result = check_schema(wf, OBJECT_INFO)
        assert any("invalid_sampler" in w or "sampler_name" in w for w in result["warnings"])

    def test_link_inputs_not_validated_as_missing(self):
        """Inputs provided via links should not be flagged as missing."""
        from comfy_mcp.compat.schema import check_schema
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model1.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0], "seed": 42, "steps": 20, "cfg": 7.0,
                "sampler_name": "euler", "scheduler": "normal",
                "positive": ["1", 1], "negative": ["1", 2], "latent_image": ["1", 3],
            }},
        }
        result = check_schema(wf, OBJECT_INFO)
        assert result["pass"] is True

    def test_schema_reports_checked_count(self):
        from comfy_mcp.compat.schema import check_schema
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model1.safetensors"}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        result = check_schema(wf, OBJECT_INFO)
        assert result["nodes_checked"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest tests/test_compat_schema.py -v`
Expected: FAIL

- [ ] **Step 3: Write schema validation**

```python
# src/comfy_mcp/compat/schema.py
"""Compatibility Pass 2: Schema validation against object_info.

Checks that workflow nodes match their live definitions:
- Node type exists in object_info
- Required inputs are present (or linked)
- Enum values are valid
"""

from __future__ import annotations

from typing import Any


def check_schema(workflow: dict, object_info: dict) -> dict[str, Any]:
    """Validate workflow nodes against object_info schemas."""
    errors: list[str] = []
    warnings: list[str] = []
    nodes_checked = 0

    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        if not class_type:
            continue

        schema = object_info.get(class_type)
        if schema is None:
            errors.append(f"Node {node_id}: unknown node type '{class_type}'")
            continue

        nodes_checked += 1
        inputs = node.get("inputs", {})
        required = schema.get("input", {}).get("required", {})

        for input_name, input_spec in required.items():
            value = inputs.get(input_name)

            # Missing required input
            if value is None:
                errors.append(f"Node {node_id} ({class_type}): missing required input '{input_name}'")
                continue

            # Linked inputs are valid by definition (type checking is structural)
            if isinstance(value, list) and len(value) == 2 and isinstance(value[1], int):
                continue

            # Check enum (COMBO) values
            if isinstance(input_spec, list) and len(input_spec) >= 1:
                if isinstance(input_spec[0], list):
                    # This is a COMBO: [["option1", "option2", ...]]
                    allowed = input_spec[0]
                    if value not in allowed:
                        warnings.append(
                            f"Node {node_id} ({class_type}): input '{input_name}' "
                            f"value '{value}' not in allowed values"
                        )

    return {
        "pass": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "nodes_checked": nodes_checked,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest tests/test_compat_schema.py -v`
Expected: All 6 PASS

- [ ] **Step 5: Commit**

```bash
git add src/comfy_mcp/compat/schema.py tests/test_compat_schema.py
git commit -m "feat(compat): add Pass 2 schema validation"
```

---

### Task 6: Environment validation (Pass 3)

**Files:**
- Create: `src/comfy_mcp/compat/environment.py`
- Test: `tests/test_compat_environment.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_compat_environment.py
"""Tests for compatibility Pass 3: environment validation."""

from __future__ import annotations

import pytest


SNAPSHOT = {
    "node_classes": ["KSampler", "CheckpointLoaderSimple", "CLIPTextEncode", "VAEDecode", "SaveImage"],
    "models": {
        "checkpoints": ["sd_xl_base_1.0.safetensors", "dreamshaper_8.safetensors"],
        "loras": ["detail.safetensors"],
        "vae": [],
        "controlnet": [],
    },
    "embeddings": ["EasyNegative"],
    "object_info": {
        "CheckpointLoaderSimple": {
            "input": {"required": {"ckpt_name": [["sd_xl_base_1.0.safetensors", "dreamshaper_8.safetensors"]]}},
        },
    },
}


class TestEnvironmentPass:
    def test_all_nodes_installed(self):
        from comfy_mcp.compat.environment import check_environment
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}},
        }
        result = check_environment(wf, SNAPSHOT)
        assert result["pass"] is True
        assert result["missing_nodes"] == []

    def test_missing_node_detected(self):
        from comfy_mcp.compat.environment import check_environment
        wf = {
            "1": {"class_type": "IPAdapterAdvanced", "inputs": {}},
        }
        result = check_environment(wf, SNAPSHOT)
        assert result["pass"] is False
        assert "IPAdapterAdvanced" in result["missing_nodes"]

    def test_model_reference_resolved(self):
        from comfy_mcp.compat.environment import check_environment
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
        }
        result = check_environment(wf, SNAPSHOT)
        assert result["missing_models"] == []

    def test_missing_model_detected(self):
        from comfy_mcp.compat.environment import check_environment
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "nonexistent.safetensors"}},
        }
        result = check_environment(wf, SNAPSHOT)
        assert len(result["missing_models"]) == 1
        assert result["missing_models"][0]["name"] == "nonexistent.safetensors"

    def test_mixed_installed_and_missing(self):
        from comfy_mcp.compat.environment import check_environment
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
            "2": {"class_type": "IPAdapterAdvanced", "inputs": {}},
            "3": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}},
        }
        result = check_environment(wf, SNAPSHOT)
        assert result["pass"] is False
        assert "IPAdapterAdvanced" in result["missing_nodes"]
        assert result["installed_nodes"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest tests/test_compat_environment.py -v`
Expected: FAIL

- [ ] **Step 3: Write environment validation**

```python
# src/comfy_mcp/compat/environment.py
"""Compatibility Pass 3: Environment validation.

Checks that everything the workflow references is actually available:
- All node types are installed
- All model references can be resolved
"""

from __future__ import annotations

from typing import Any

# Known input names that reference models by folder
MODEL_INPUT_HINTS = {
    "ckpt_name": "checkpoints",
    "lora_name": "loras",
    "vae_name": "vae",
    "control_net_name": "controlnet",
    "upscale_model": "upscale_models",
    "clip_name": "clip",
}


def check_environment(workflow: dict, snapshot: dict) -> dict[str, Any]:
    """Validate that workflow requirements exist on this machine."""
    errors: list[str] = []
    warnings: list[str] = []
    missing_nodes: list[str] = []
    missing_models: list[dict] = []
    installed_nodes = 0

    node_classes = set(snapshot.get("node_classes", []))
    models = snapshot.get("models", {})

    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        if not class_type:
            continue

        if class_type in node_classes:
            installed_nodes += 1
        else:
            missing_nodes.append(class_type)
            errors.append(f"Node {node_id}: '{class_type}' is not installed")

        # Check model references in inputs
        inputs = node.get("inputs", {})
        for input_name, value in inputs.items():
            if isinstance(value, (list, dict)):
                continue  # link or complex input
            folder = MODEL_INPUT_HINTS.get(input_name)
            if folder and isinstance(value, str):
                folder_models = models.get(folder, [])
                if value not in folder_models:
                    missing_models.append({"name": value, "folder": folder, "node_id": node_id})

    if missing_nodes:
        errors.append(f"Missing {len(missing_nodes)} node type(s): {', '.join(sorted(set(missing_nodes)))}")

    return {
        "pass": len(missing_nodes) == 0 and len(missing_models) == 0,
        "errors": errors,
        "warnings": warnings,
        "missing_nodes": sorted(set(missing_nodes)),
        "missing_models": missing_models,
        "installed_nodes": installed_nodes,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest tests/test_compat_environment.py -v`
Expected: All 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/comfy_mcp/compat/environment.py tests/test_compat_environment.py
git commit -m "feat(compat): add Pass 3 environment validation"
```

---

### Task 7: Compatibility Engine orchestrator + tools

**Files:**
- Create: `src/comfy_mcp/compat/engine.py`
- Create: `src/comfy_mcp/tools/compat.py`
- Test: `tests/test_compat_engine.py`
- Test: `tests/test_tools_compat.py`
- Modify: `src/comfy_mcp/tool_registry.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_compat_engine.py
"""Tests for the Compatibility Engine orchestrator."""

from __future__ import annotations

import pytest


OBJECT_INFO = {
    "KSampler": {
        "input": {"required": {
            "model": ["MODEL"], "seed": ["INT"], "steps": ["INT"],
            "cfg": ["FLOAT"], "sampler_name": [["euler"]], "scheduler": [["normal"]],
            "positive": ["CONDITIONING"], "negative": ["CONDITIONING"],
            "latent_image": ["LATENT"],
        }},
        "output": ["LATENT"],
        "category": "sampling",
    },
    "CheckpointLoaderSimple": {
        "input": {"required": {"ckpt_name": [["model.safetensors"]]}},
        "output": ["MODEL", "CLIP", "VAE"],
        "category": "loaders",
    },
    "SaveImage": {
        "input": {"required": {"images": ["IMAGE"]}},
        "output": [],
        "output_node": True,
        "category": "image",
    },
}

SNAPSHOT = {
    "node_classes": ["KSampler", "CheckpointLoaderSimple", "SaveImage"],
    "models": {"checkpoints": ["model.safetensors"]},
    "embeddings": [],
    "object_info": OBJECT_INFO,
}


class TestCompatEngine:
    def test_valid_workflow_verified(self):
        from comfy_mcp.compat.engine import run_preflight
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0], "seed": 42, "steps": 20, "cfg": 7.0,
                "sampler_name": "euler", "scheduler": "normal",
                "positive": ["1", 1], "negative": ["1", 2], "latent_image": ["1", 3],
            }},
            "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0]}},
        }
        result = run_preflight(wf, SNAPSHOT)
        assert result["status"] == "verified"
        assert result["confidence"] >= 0.9

    def test_missing_node_blocks(self):
        from comfy_mcp.compat.engine import run_preflight
        wf = {
            "1": {"class_type": "UnknownNode", "inputs": {}},
        }
        result = run_preflight(wf, SNAPSHOT)
        assert result["status"] == "blocked"
        assert "UnknownNode" in str(result["errors"])

    def test_schema_warning_reduces_confidence(self):
        from comfy_mcp.compat.engine import run_preflight
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0], "seed": 42, "steps": 20, "cfg": 7.0,
                "sampler_name": "bad_sampler", "scheduler": "normal",
                "positive": ["1", 1], "negative": ["1", 2], "latent_image": ["1", 3],
            }},
        }
        result = run_preflight(wf, SNAPSHOT)
        assert result["status"] in ("likely", "risky")
        assert len(result["warnings"]) > 0

    def test_empty_workflow_blocked(self):
        from comfy_mcp.compat.engine import run_preflight
        result = run_preflight({}, SNAPSHOT)
        assert result["status"] == "blocked"

    def test_result_includes_all_sections(self):
        from comfy_mcp.compat.engine import run_preflight
        wf = {"1": {"class_type": "KSampler", "inputs": {"seed": 42}}}
        result = run_preflight(wf, SNAPSHOT)
        assert "status" in result
        assert "errors" in result
        assert "warnings" in result
        assert "missing_nodes" in result
        assert "missing_models" in result
        assert "confidence" in result
```

```python
# tests/test_tools_compat.py
"""Tests for compatibility MCP tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def compat_ctx(mock_ctx):
    graph = MagicMock()
    graph.snapshot = {
        "node_classes": ["KSampler", "SaveImage"],
        "models": {"checkpoints": ["model.safetensors"]},
        "embeddings": [],
        "object_info": {
            "KSampler": {
                "input": {"required": {"seed": ["INT"]}},
                "output": ["LATENT"],
            },
            "SaveImage": {
                "input": {"required": {"images": ["IMAGE"]}},
                "output": [],
                "output_node": True,
            },
        },
    }
    graph.refresh = AsyncMock(return_value=graph.snapshot)
    mock_ctx.request_context.lifespan_context["install_graph"] = graph
    return mock_ctx


class TestPreflightWorkflow:
    @pytest.mark.asyncio
    async def test_preflight_returns_report(self, compat_ctx):
        from comfy_mcp.tools.compat import comfy_preflight_workflow
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 42}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        result = json.loads(await comfy_preflight_workflow(workflow=wf, ctx=compat_ctx))
        assert "status" in result
        assert "confidence" in result

    @pytest.mark.asyncio
    async def test_preflight_missing_node(self, compat_ctx):
        from comfy_mcp.tools.compat import comfy_preflight_workflow
        wf = {"1": {"class_type": "FakeNode", "inputs": {}}}
        result = json.loads(await comfy_preflight_workflow(workflow=wf, ctx=compat_ctx))
        assert result["status"] == "blocked"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest tests/test_compat_engine.py tests/test_tools_compat.py -v`
Expected: FAIL

- [ ] **Step 3: Write the engine orchestrator**

```python
# src/comfy_mcp/compat/engine.py
"""Compatibility Engine — orchestrates multi-pass workflow preflight.

Runs structural, schema, and environment passes to produce a unified report.
"""

from __future__ import annotations

from typing import Any

from comfy_mcp.compat.structural import check_structural
from comfy_mcp.compat.schema import check_schema
from comfy_mcp.compat.environment import check_environment


def run_preflight(workflow: Any, snapshot: dict) -> dict[str, Any]:
    """Run all compatibility passes and produce a unified preflight report.

    Args:
        workflow: API-format workflow dict
        snapshot: InstallGraph snapshot

    Returns:
        Unified report with status, errors, warnings, missing_nodes,
        missing_models, and confidence score.
    """
    all_errors: list[str] = []
    all_warnings: list[str] = []
    missing_nodes: list[str] = []
    missing_models: list[dict] = []

    # Pass 1: Structural
    p1 = check_structural(workflow)
    all_errors.extend(p1["errors"])
    all_warnings.extend(p1["warnings"])

    if not p1["pass"]:
        return _build_report("blocked", all_errors, all_warnings, missing_nodes, missing_models)

    # Pass 2: Schema
    object_info = snapshot.get("object_info", {})
    p2 = check_schema(workflow, object_info)
    all_errors.extend(p2["errors"])
    all_warnings.extend(p2["warnings"])

    # Pass 3: Environment
    p3 = check_environment(workflow, snapshot)
    all_errors.extend(p3["errors"])
    all_warnings.extend(p3["warnings"])
    missing_nodes = p3.get("missing_nodes", [])
    missing_models = p3.get("missing_models", [])

    # Determine status
    has_errors = len(all_errors) > 0
    has_warnings = len(all_warnings) > 0

    if missing_nodes or missing_models:
        status = "blocked"
    elif has_errors:
        status = "blocked"
    elif has_warnings:
        status = "likely"
    else:
        status = "verified"

    return _build_report(status, all_errors, all_warnings, missing_nodes, missing_models)


def _build_report(
    status: str,
    errors: list[str],
    warnings: list[str],
    missing_nodes: list[str],
    missing_models: list[dict],
) -> dict[str, Any]:
    """Build the unified preflight report with confidence score."""
    # Confidence heuristic
    if status == "verified":
        confidence = 0.95
    elif status == "likely":
        confidence = max(0.5, 0.9 - 0.1 * len(warnings))
    elif status == "risky":
        confidence = max(0.2, 0.5 - 0.1 * len(warnings))
    else:  # blocked
        confidence = 0.0

    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "missing_nodes": missing_nodes,
        "missing_models": missing_models,
        "confidence": round(confidence, 2),
    }
```

- [ ] **Step 4: Write the compat tools**

```python
# src/comfy_mcp/tools/compat.py
"""Compatibility tools — MCP surface for the Compatibility Engine."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _graph(ctx: Context):
    return ctx.request_context.lifespan_context["install_graph"]


@mcp.tool(
    annotations={
        "title": "Preflight Workflow",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_preflight_workflow(workflow: dict, ctx: Context = None) -> str:
    """Run a multi-pass compatibility check on a workflow before execution.

    Validates structural integrity, schema correctness, and environment
    compatibility (installed nodes, resolvable models).

    Args:
        workflow: API-format workflow dict

    Returns:
        JSON preflight report with status (verified/likely/blocked),
        errors, warnings, missing_nodes, missing_models, and confidence score.
    """
    graph = _graph(ctx)
    if not graph.snapshot:
        await graph.refresh()
    from comfy_mcp.compat.engine import run_preflight
    report = run_preflight(workflow, graph.snapshot)
    return json.dumps(report, indent=2)


@mcp.tool(
    annotations={
        "title": "Explain Incompatibilities",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_explain_incompatibilities(workflow: dict, ctx: Context = None) -> str:
    """Explain why a workflow may not run on this machine.

    Runs preflight and returns a human-readable explanation with
    actionable suggestions for each issue found.

    Args:
        workflow: API-format workflow dict
    """
    graph = _graph(ctx)
    if not graph.snapshot:
        await graph.refresh()
    from comfy_mcp.compat.engine import run_preflight
    report = run_preflight(workflow, graph.snapshot)

    explanations = []
    for node in report.get("missing_nodes", []):
        explanations.append(f"- Node '{node}' is not installed. Install the custom node pack that provides it.")
    for model in report.get("missing_models", []):
        explanations.append(
            f"- Model '{model['name']}' not found in {model['folder']}. "
            f"Download it or change the workflow to use an installed model."
        )
    for err in report.get("errors", []):
        if not any(err.startswith(f"Node") for _ in []):
            explanations.append(f"- {err}")

    result = {
        "status": report["status"],
        "confidence": report["confidence"],
        "explanation": "\n".join(explanations) if explanations else "No issues found.",
        "raw_report": report,
    }
    return json.dumps(result, indent=2)
```

- [ ] **Step 5: Register compat tools**

In `src/comfy_mcp/tool_registry.py`, add:

```python
from comfy_mcp.tools import compat       # noqa: F401
```

- [ ] **Step 6: Run all tests to verify they pass**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest tests/test_compat_engine.py tests/test_tools_compat.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/comfy_mcp/compat/engine.py src/comfy_mcp/tools/compat.py src/comfy_mcp/tool_registry.py tests/test_compat_engine.py tests/test_tools_compat.py
git commit -m "feat(compat): add engine orchestrator and preflight/explain tools"
```

---

### Task 8: Full integration — run entire suite, update README, push

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run the full test suite**

Run: `cd "C:/Users/dr5090/AppData/Local/Temp/ComfyPilot" && python -m pytest --tb=short`
Expected: All pass (previous 334 + new ~40 = ~374)

- [ ] **Step 2: Update README**

Update the test count and add the new tools/resource to the feature list.
Add a "Compatibility Engine" section to the README feature list.

- [ ] **Step 3: Final commit and push**

```bash
git add README.md
git commit -m "docs: update README with install graph and compat engine"
git push origin master
```

---

## Summary

| Task | What it builds | New tests |
|------|---------------|-----------|
| 1 | InstallGraph — machine state snapshot | ~10 |
| 2 | ModelResolver — model reference resolution | ~7 |
| 3 | Install tools + resource + server wiring | ~3 |
| 4 | Compat Pass 1: structural validation | ~8 |
| 5 | Compat Pass 2: schema validation | ~6 |
| 6 | Compat Pass 3: environment validation | ~5 |
| 7 | Engine orchestrator + compat tools | ~7 |
| 8 | Integration, README, push | 0 |

**Total: ~46 new tests, 18 new files, 3 modified files.**

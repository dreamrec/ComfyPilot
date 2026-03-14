# v0.5 Template Engine Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded workflow templates with a discover/score/instantiate pipeline that uses official ComfyUI templates, custom node examples, and the user's installed models.

**Architecture:** Four-module package (`src/comfy_mcp/templates/`) with discovery for fetching template sources, index for unified metadata, scorer for relevance ranking, and instantiator for model substitution + validation. Tools access the subsystem via lifespan context.

**Tech Stack:** Python 3.12, httpx (existing), ModelResolver (v0.3), compat engine (v0.3).

**Prerequisite:** v0.4 (Docs Engine) must be implemented first. The template engine uses the install graph and compat engine from v0.3 but does NOT depend on v0.4 at runtime — the docs-based tag expansion noted in the spec is deferred to a future version.

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/comfy_mcp/templates/__init__.py` | Package init |
| Create | `src/comfy_mcp/templates/discovery.py` | Fetch official + custom node + builtin template sources |
| Create | `src/comfy_mcp/templates/index.py` | Unified index builder with metadata extraction |
| Create | `src/comfy_mcp/templates/scorer.py` | Relevance ranking given query + installed environment |
| Create | `src/comfy_mcp/templates/instantiator.py` | Model substitution + compat validation + ready workflow output |
| Create | `src/comfy_mcp/tools/templates.py` | 6 MCP tools |
| Create | `tests/test_template_discovery.py` | Tests for discovery |
| Create | `tests/test_template_scorer.py` | Tests for scoring |
| Create | `tests/test_template_instantiator.py` | Tests for instantiation |
| Create | `tests/test_tools_templates.py` | Tests for MCP tools |
| Modify | `src/comfy_mcp/server.py` | Add TemplateIndex to lifespan + resource |
| Modify | `src/comfy_mcp/tool_registry.py` | Add templates import |
| Modify | `tests/conftest.py` | Add template_index to mock_ctx |
| Modify | `README.md` | Update to 82 tools, 9 resources |

---

## Chunk 1: Discovery + Index

### Task 1: Package init + TemplateDiscovery

**Files:**
- Create: `src/comfy_mcp/templates/__init__.py`
- Create: `src/comfy_mcp/templates/discovery.py`
- Create: `tests/test_template_discovery.py`

- [ ] **Step 1: Create package init**

```python
# src/comfy_mcp/templates/__init__.py
```

- [ ] **Step 2: Write failing tests for discovery**

```python
# tests/test_template_discovery.py
"""Tests for TemplateDiscovery — fetching template sources."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_comfy_client():
    client = AsyncMock()
    client.base_url = "http://localhost:8188"
    # Official templates endpoint
    client.get = AsyncMock()
    return client


class TestDiscoverOfficial:
    @pytest.mark.asyncio
    async def test_discovers_official_templates(self, mock_comfy_client):
        from comfy_mcp.templates.discovery import TemplateDiscovery
        index_data = [
            {"name": "txt2img_basic", "category": "text-to-image", "description": "Basic txt2img", "file": "txt2img_basic.json"},
            {"name": "img2img_simple", "category": "image-to-image", "description": "Simple img2img", "file": "img2img_simple.json"},
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=index_data)
        mock_comfy_client.get = AsyncMock(return_value=mock_response)

        discovery = TemplateDiscovery(mock_comfy_client)
        templates = await discovery.discover_official()
        assert len(templates) == 2
        assert templates[0]["name"] == "txt2img_basic"
        assert templates[0]["source"] == "official"

    @pytest.mark.asyncio
    async def test_returns_empty_on_failure(self, mock_comfy_client):
        from comfy_mcp.templates.discovery import TemplateDiscovery
        mock_comfy_client.get = AsyncMock(side_effect=Exception("offline"))
        discovery = TemplateDiscovery(mock_comfy_client)
        templates = await discovery.discover_official()
        assert templates == []


class TestDiscoverCustomNode:
    @pytest.mark.asyncio
    async def test_discovers_custom_node_templates(self, mock_comfy_client):
        from comfy_mcp.templates.discovery import TemplateDiscovery
        wf_data = [
            {"name": "animatediff_example", "node_pack": "comfyui-animatediff", "file": "example.json"},
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=wf_data)
        mock_comfy_client.get = AsyncMock(return_value=mock_response)

        discovery = TemplateDiscovery(mock_comfy_client)
        templates = await discovery.discover_custom_node()
        assert len(templates) == 1
        assert templates[0]["source"] == "custom_node"


class TestDiscoverBuiltin:
    def test_builtin_templates_always_available(self):
        from comfy_mcp.templates.discovery import TemplateDiscovery
        discovery = TemplateDiscovery(None)
        templates = discovery.discover_builtin()
        assert len(templates) >= 5  # txt2img, img2img, upscale, inpaint, controlnet
        for t in templates:
            assert t["source"] == "builtin"
            assert "name" in t
            assert "category" in t
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_template_discovery.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement TemplateDiscovery**

```python
# src/comfy_mcp/templates/discovery.py
"""TemplateDiscovery — fetches templates from official, custom node, and builtin sources."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("comfypilot.templates")

# Builtin template definitions (minimal API-format skeletons)
BUILTIN_TEMPLATES = [
    {"name": "txt2img_basic", "category": "text-to-image", "description": "Basic text-to-image generation", "tags": ["txt2img", "basic", "generation"],
     "required_nodes": ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler", "EmptyLatentImage", "VAEDecode", "SaveImage"],
     "required_models": {"checkpoints": 1}},
    {"name": "img2img_basic", "category": "image-to-image", "description": "Image-to-image with denoise control", "tags": ["img2img", "denoise", "generation"],
     "required_nodes": ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler", "VAEEncode", "VAEDecode", "LoadImage", "SaveImage"],
     "required_models": {"checkpoints": 1}},
    {"name": "upscale_basic", "category": "upscale", "description": "Upscale with model", "tags": ["upscale", "super-resolution"],
     "required_nodes": ["UpscaleModelLoader", "ImageUpscaleWithModel", "LoadImage", "SaveImage"],
     "required_models": {"upscale_models": 1}},
    {"name": "inpaint_basic", "category": "inpaint", "description": "Inpainting with mask", "tags": ["inpaint", "mask", "editing"],
     "required_nodes": ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler", "VAEDecode", "LoadImage", "SaveImage"],
     "required_models": {"checkpoints": 1}},
    {"name": "controlnet_basic", "category": "controlnet", "description": "ControlNet guided generation", "tags": ["controlnet", "guided", "generation"],
     "required_nodes": ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler", "ControlNetLoader", "ControlNetApply", "VAEDecode", "SaveImage"],
     "required_models": {"checkpoints": 1, "controlnet": 1}},
]


class TemplateDiscovery:
    """Discovers templates from multiple sources."""

    def __init__(self, comfy_client):
        self._client = comfy_client

    async def discover_official(self) -> list[dict[str, Any]]:
        """Fetch official templates from ComfyUI server."""
        if self._client is None:
            return []
        try:
            response = await self._client.get("/templates/index.json")
            if response.status_code != 200:
                logger.debug("Official templates returned %d", response.status_code)
                return []
            data = response.json()
            templates = []
            for item in data:
                item["source"] = "official"
                if "tags" not in item:
                    item["tags"] = []
                templates.append(item)
            return templates
        except Exception as exc:
            logger.debug("Official template discovery failed: %s", exc)
            return []

    async def discover_custom_node(self) -> list[dict[str, Any]]:
        """Fetch custom node example workflows from ComfyUI server."""
        if self._client is None:
            return []
        try:
            response = await self._client.get("/workflow_templates")
            if response.status_code != 200:
                logger.debug("Custom node templates returned %d", response.status_code)
                return []
            data = response.json()
            templates = []
            for item in data:
                item["source"] = "custom_node"
                if "tags" not in item:
                    item["tags"] = []
                templates.append(item)
            return templates
        except Exception as exc:
            logger.debug("Custom node template discovery failed: %s", exc)
            return []

    def discover_builtin(self) -> list[dict[str, Any]]:
        """Return built-in template definitions."""
        import copy
        templates = []
        for t in BUILTIN_TEMPLATES:
            entry = copy.deepcopy(t)
            entry["source"] = "builtin"
            templates.append(entry)
        return templates

    async def discover_all(self) -> list[dict[str, Any]]:
        """Discover templates from all sources."""
        official = await self.discover_official()
        custom = await self.discover_custom_node()
        builtin = self.discover_builtin()
        return official + custom + builtin
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_template_discovery.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/templates/__init__.py src/comfy_mcp/templates/discovery.py tests/test_template_discovery.py && git commit -m "feat(v0.5): add TemplateDiscovery for official, custom node, and builtin sources"
```

---

### Task 2: TemplateIndex — unified index with disk cache

**Files:**
- Create: `src/comfy_mcp/templates/index.py`

- [ ] **Step 1: Implement TemplateIndex**

```python
# src/comfy_mcp/templates/index.py
"""TemplateIndex — unified template index with disk cache.

Maintains a merged index of all template sources at ~/.comfypilot/templates/.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class TemplateIndex:
    """Unified template index across all sources."""

    def __init__(self, storage_dir: str | None = None):
        self._dir = Path(storage_dir or Path.home() / ".comfypilot" / "templates")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._templates: list[dict[str, Any]] = []
        self._manifest: dict[str, Any] = {}
        self._load()

    def _index_path(self) -> Path:
        return self._dir / "index.json"

    def _manifest_path(self) -> Path:
        return self._dir / "manifest.json"

    def _load(self) -> None:
        idx_path = self._index_path()
        if idx_path.exists():
            try:
                self._templates = json.loads(idx_path.read_text())
            except (json.JSONDecodeError, OSError):
                self._templates = []
        mfst_path = self._manifest_path()
        if mfst_path.exists():
            try:
                self._manifest = json.loads(mfst_path.read_text())
            except (json.JSONDecodeError, OSError):
                self._manifest = {}

    def rebuild(self, templates: list[dict[str, Any]]) -> None:
        """Replace the index with a new list of templates."""
        # Assign stable IDs based on source + name
        for t in templates:
            if "id" not in t:
                t["id"] = f"{t.get('source', 'unknown')}_{t.get('name', 'unnamed')}"
        self._templates = templates
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path().write_text(json.dumps(templates, indent=2))
        self._manifest = {
            "last_updated": time.time(),
            "template_count": len(templates),
            "content_hash": _content_hash(json.dumps(templates, sort_keys=True)),
            "source_counts": self._count_sources(templates),
        }
        self._manifest_path().write_text(json.dumps(self._manifest, indent=2))

    def _count_sources(self, templates: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in templates:
            src = t.get("source", "unknown")
            counts[src] = counts.get(src, 0) + 1
        return counts

    def get(self, template_id: str) -> dict | None:
        """Get a template by ID."""
        for t in self._templates:
            if t.get("id") == template_id:
                return t
        return None

    def list_all(self) -> list[dict]:
        """Return all templates (metadata only, no workflow bodies)."""
        return [
            {k: v for k, v in t.items() if k != "workflow"}
            for t in self._templates
        ]

    def categories(self) -> list[str]:
        """Return all unique categories."""
        cats = set()
        for t in self._templates:
            cat = t.get("category", "")
            if cat:
                cats.add(cat)
        return sorted(cats)

    def is_stale(self, max_age: float = 300) -> bool:
        last = self._manifest.get("last_updated")
        if last is None:
            return True
        return (time.time() - last) >= max_age

    def content_hash(self) -> str:
        return self._manifest.get("content_hash", "")

    def summary(self) -> dict:
        return {
            "template_count": len(self._templates),
            "categories": self.categories(),
            "source_counts": self._manifest.get("source_counts", {}),
            "stale": self.is_stale(),
            "last_updated": self._manifest.get("last_updated"),
            "content_hash": self.content_hash(),
        }
```

- [ ] **Step 2: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/templates/index.py && git commit -m "feat(v0.5): add TemplateIndex with unified disk cache"
```

---

## Chunk 2: Scorer + Instantiator

### Task 3: TemplateScorer

**Files:**
- Create: `src/comfy_mcp/templates/scorer.py`
- Create: `tests/test_template_scorer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_template_scorer.py
"""Tests for TemplateScorer — relevance ranking."""

from __future__ import annotations

import pytest


INSTALLED_NODES = {"KSampler", "CheckpointLoaderSimple", "CLIPTextEncode", "VAEDecode", "SaveImage", "EmptyLatentImage"}
INSTALLED_MODELS = {"checkpoints": ["dreamshaper_8.safetensors"], "loras": [], "controlnet": []}

TEMPLATES = [
    {"id": "official_txt2img", "name": "txt2img_basic", "category": "text-to-image", "source": "official",
     "tags": ["txt2img", "basic"], "required_nodes": ["CheckpointLoaderSimple", "KSampler", "VAEDecode", "SaveImage"],
     "required_models": {"checkpoints": 1}},
    {"id": "official_controlnet", "name": "controlnet_basic", "category": "controlnet", "source": "official",
     "tags": ["controlnet", "guided"], "required_nodes": ["ControlNetLoader", "ControlNetApply"],
     "required_models": {"controlnet": 1}},
    {"id": "builtin_txt2img", "name": "txt2img_basic", "category": "text-to-image", "source": "builtin",
     "tags": ["txt2img", "basic"], "required_nodes": ["CheckpointLoaderSimple", "KSampler"],
     "required_models": {"checkpoints": 1}},
]


class TestScorerRanking:
    def test_matching_tags_ranked_higher(self):
        from comfy_mcp.templates.scorer import TemplateScorer
        scorer = TemplateScorer(INSTALLED_NODES, INSTALLED_MODELS)
        results = scorer.score("txt2img basic", TEMPLATES)
        assert results[0]["id"] in ("official_txt2img", "builtin_txt2img")

    def test_missing_nodes_penalized(self):
        from comfy_mcp.templates.scorer import TemplateScorer
        scorer = TemplateScorer(INSTALLED_NODES, INSTALLED_MODELS)
        results = scorer.score("controlnet", TEMPLATES)
        controlnet = next(r for r in results if r["id"] == "official_controlnet")
        assert controlnet["score"] < 1.0
        assert len(controlnet.get("warnings", [])) > 0

    def test_source_precedence_tiebreaker(self):
        from comfy_mcp.templates.scorer import TemplateScorer
        scorer = TemplateScorer(INSTALLED_NODES, INSTALLED_MODELS)
        results = scorer.score("txt2img basic", TEMPLATES)
        # Both txt2img templates match, but official should rank first
        txt2img_results = [r for r in results if "txt2img" in r["id"]]
        assert txt2img_results[0]["id"] == "official_txt2img"

    def test_empty_query_returns_all(self):
        from comfy_mcp.templates.scorer import TemplateScorer
        scorer = TemplateScorer(INSTALLED_NODES, INSTALLED_MODELS)
        results = scorer.score("", TEMPLATES)
        assert len(results) == len(TEMPLATES)

    def test_limit_respected(self):
        from comfy_mcp.templates.scorer import TemplateScorer
        scorer = TemplateScorer(INSTALLED_NODES, INSTALLED_MODELS)
        results = scorer.score("", TEMPLATES, limit=1)
        assert len(results) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_template_scorer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TemplateScorer**

```python
# src/comfy_mcp/templates/scorer.py
"""TemplateScorer — relevance ranking for template search.

Scores templates based on tag match, category match, model compatibility,
and node compatibility. Uses source precedence as tiebreaker.
"""

from __future__ import annotations

from typing import Any

# Scoring weights (hardcoded defaults, defined as constants for tuning)
TAG_WEIGHT = 0.3
CATEGORY_WEIGHT = 0.2
MODEL_WEIGHT = 0.3
NODE_WEIGHT = 0.2

# Source precedence for tiebreaking (lower = higher priority)
SOURCE_PRECEDENCE = {"official": 0, "custom_node": 1, "builtin": 2}


class TemplateScorer:
    """Ranks templates by relevance to a query and installed environment."""

    def __init__(self, installed_nodes: set[str], installed_models: dict[str, list[str]]):
        self._nodes = installed_nodes
        self._models = installed_models

    def score(
        self,
        query: str,
        templates: list[dict[str, Any]],
        tags: list[str] | None = None,
        category: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Score and rank templates. Returns scored results with warnings."""
        query_tokens = set(query.lower().split()) if query else set()
        filter_tags = set(t.lower() for t in tags) if tags else set()

        scored = []
        for t in templates:
            template_tags = set(tag.lower() for tag in t.get("tags", []))
            template_cat = t.get("category", "").lower()

            # Tag overlap
            if query_tokens:
                tag_overlap = len(query_tokens & template_tags) / max(len(query_tokens), 1)
                # Also check name and description
                name_match = any(tok in t.get("name", "").lower() for tok in query_tokens)
                desc_match = any(tok in t.get("description", "").lower() for tok in query_tokens)
                if name_match or desc_match:
                    tag_overlap = max(tag_overlap, 0.5)
            else:
                tag_overlap = 1.0  # no query = everything matches

            # Filter tag match
            if filter_tags and not (filter_tags & template_tags):
                continue

            # Category match
            cat_match = 1.0 if (category and category.lower() == template_cat) else (0.5 if not category else 0.0)

            # Node compatibility
            required_nodes = t.get("required_nodes", [])
            warnings = []
            if required_nodes:
                available = sum(1 for n in required_nodes if n in self._nodes)
                node_ratio = available / len(required_nodes)
                missing = [n for n in required_nodes if n not in self._nodes]
                if missing:
                    warnings.append(f"Missing nodes: {', '.join(missing)}")
            else:
                node_ratio = 1.0

            # Model compatibility
            required_models = t.get("required_models", {})
            if required_models:
                model_available = 0
                model_total = 0
                for folder, count in required_models.items():
                    model_total += count
                    if len(self._models.get(folder, [])) >= count:
                        model_available += count
                    else:
                        warnings.append(f"Need {count} {folder} model(s), have {len(self._models.get(folder, []))}")
                model_ratio = model_available / max(model_total, 1)
            else:
                model_ratio = 1.0

            # Compute score
            total = (TAG_WEIGHT * tag_overlap
                     + CATEGORY_WEIGHT * cat_match
                     + MODEL_WEIGHT * model_ratio
                     + NODE_WEIGHT * node_ratio)

            scored.append({
                "id": t.get("id", t.get("name", "")),
                "name": t.get("name", ""),
                "category": t.get("category", ""),
                "source": t.get("source", "unknown"),
                "description": t.get("description", ""),
                "score": round(total, 3),
                "warnings": warnings,
            })

        # Sort by score desc, then source precedence asc
        scored.sort(key=lambda x: (-x["score"], SOURCE_PRECEDENCE.get(x["source"], 9)))
        return scored[:limit]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_template_scorer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/templates/scorer.py tests/test_template_scorer.py && git commit -m "feat(v0.5): add TemplateScorer with weighted ranking and source precedence"
```

---

### Task 4: TemplateInstantiator

**Files:**
- Create: `src/comfy_mcp/templates/instantiator.py`
- Create: `tests/test_template_instantiator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_template_instantiator.py
"""Tests for TemplateInstantiator — model substitution and workflow output."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


SNAPSHOT = {
    "node_classes": {"KSampler", "CheckpointLoaderSimple", "CLIPTextEncode", "VAEDecode", "SaveImage", "EmptyLatentImage"},
    "models": {"checkpoints": ["dreamshaper_8.safetensors"], "loras": [], "controlnet": []},
    "embeddings": [],
    "object_info": {
        "KSampler": {"input": {"required": {"seed": ["INT"]}}, "output": ["LATENT"]},
        "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["dreamshaper_8.safetensors"]]}}, "output": ["MODEL", "CLIP", "VAE"]},
        "SaveImage": {"input": {"required": {"images": ["IMAGE"]}}, "output": [], "output_node": True},
    },
}


TEMPLATE_WITH_WORKFLOW = {
    "id": "builtin_txt2img",
    "name": "txt2img_basic",
    "workflow": {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
        "2": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20, "cfg": 7.0,
              "sampler_name": "euler", "scheduler": "normal",
              "model": ["1", 0], "positive": ["1", 1], "negative": ["1", 2], "latent_image": ["3", 0]}},
        "3": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "4": {"class_type": "VAEDecode", "inputs": {"samples": ["2", 0], "vae": ["1", 2]}},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["4", 0]}},
    },
}


class TestInstantiation:
    def test_substitutes_checkpoint(self):
        from comfy_mcp.templates.instantiator import TemplateInstantiator
        inst = TemplateInstantiator(SNAPSHOT)
        result = inst.instantiate(TEMPLATE_WITH_WORKFLOW)
        wf = result["workflow"]
        assert wf["1"]["inputs"]["ckpt_name"] == "dreamshaper_8.safetensors"

    def test_applies_overrides(self):
        from comfy_mcp.templates.instantiator import TemplateInstantiator
        inst = TemplateInstantiator(SNAPSHOT)
        result = inst.instantiate(TEMPLATE_WITH_WORKFLOW, overrides={"width": 768, "height": 768})
        wf = result["workflow"]
        assert wf["3"]["inputs"]["width"] == 768

    def test_unknown_override_produces_warning(self):
        from comfy_mcp.templates.instantiator import TemplateInstantiator
        inst = TemplateInstantiator(SNAPSHOT)
        result = inst.instantiate(TEMPLATE_WITH_WORKFLOW, overrides={"nonexistent_param": 42})
        assert len(result.get("warnings", [])) > 0

    def test_returns_ready_status_for_valid_workflow(self):
        from comfy_mcp.templates.instantiator import TemplateInstantiator
        inst = TemplateInstantiator(SNAPSHOT)
        result = inst.instantiate(TEMPLATE_WITH_WORKFLOW)
        assert result["status"] in ("ready", "warnings")

    def test_missing_model_produces_warning(self):
        from comfy_mcp.templates.instantiator import TemplateInstantiator
        snapshot = dict(SNAPSHOT)
        snapshot["models"] = {"checkpoints": [], "loras": [], "controlnet": []}
        inst = TemplateInstantiator(snapshot)
        result = inst.instantiate(TEMPLATE_WITH_WORKFLOW)
        assert any("model" in w.lower() or "checkpoint" in w.lower() for w in result.get("warnings", []))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_template_instantiator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TemplateInstantiator**

```python
# src/comfy_mcp/templates/instantiator.py
"""TemplateInstantiator — model substitution and workflow preparation.

Takes a template, substitutes model references with installed models,
applies user overrides, and returns a ready-to-queue workflow.
"""

from __future__ import annotations

import copy
from typing import Any

# Input names that reference models, mapped to model folder
MODEL_INPUT_HINTS = {
    "ckpt_name": "checkpoints",
    "lora_name": "loras",
    "vae_name": "vae",
    "control_net_name": "controlnet",
    "unet_name": "checkpoints",
    "clip_name": "clip",
    "upscale_model": "upscale_models",
}

# Input names that are common override targets
OVERRIDE_TARGETS = {
    "width", "height", "batch_size", "seed", "steps", "cfg",
    "sampler_name", "scheduler", "denoise",
    "positive_prompt", "negative_prompt",
    "ckpt_name", "lora_name", "vae_name",
}


class TemplateInstantiator:
    """Substitutes model references and applies overrides to template workflows."""

    def __init__(self, snapshot: dict[str, Any]):
        self._models = snapshot.get("models", {})
        self._nodes = snapshot.get("node_classes", set())

    def instantiate(
        self,
        template: dict[str, Any],
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Instantiate a template into a ready-to-queue workflow.

        Returns: {"status": "ready"|"warnings", "workflow": {...}, "warnings": [...]}
        """
        if "workflow" not in template:
            return {"status": "error", "workflow": {}, "warnings": ["Template has no workflow body"]}

        workflow = copy.deepcopy(template["workflow"])
        warnings: list[str] = []

        # Phase 1: Model substitution
        for node_id, node in workflow.items():
            inputs = node.get("inputs", {})
            for input_name, value in list(inputs.items()):
                if input_name in MODEL_INPUT_HINTS and isinstance(value, str):
                    folder = MODEL_INPUT_HINTS[input_name]
                    installed = self._models.get(folder, [])
                    if value not in installed:
                        if installed:
                            # Pick first alphabetically (deterministic default)
                            replacement = sorted(installed)[0]
                            inputs[input_name] = replacement
                            warnings.append(f"Substituted {input_name}: '{value}' -> '{replacement}' (first available {folder})")
                        else:
                            warnings.append(f"No {folder} models installed for {input_name} (template needs '{value}')")

        # Phase 2: Apply overrides
        if overrides:
            applied = set()
            for node_id, node in workflow.items():
                inputs = node.get("inputs", {})
                for key, new_value in overrides.items():
                    if key in inputs:
                        inputs[key] = new_value
                        applied.add(key)

            unapplied = set(overrides.keys()) - applied
            for key in unapplied:
                warnings.append(f"Override '{key}' did not match any workflow input (ignored)")

        status = "ready" if not warnings else "warnings"
        return {
            "status": status,
            "workflow": workflow,
            "warnings": warnings,
            "template_id": template.get("id", ""),
            "template_name": template.get("name", ""),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_template_instantiator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/templates/instantiator.py tests/test_template_instantiator.py && git commit -m "feat(v0.5): add TemplateInstantiator with model substitution and overrides"
```

---

## Chunk 3: MCP Tools + Integration

### Task 5: MCP tools for templates

**Files:**
- Create: `src/comfy_mcp/tools/templates.py`
- Create: `tests/test_tools_templates.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools_templates.py
"""Tests for template MCP tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def template_ctx(mock_ctx):
    """Mock context with template_index in lifespan."""
    index_mock = MagicMock()
    index_mock.list_all = MagicMock(return_value=[
        {"id": "official_txt2img", "name": "txt2img_basic", "category": "text-to-image", "source": "official"},
    ])
    index_mock.categories = MagicMock(return_value=["text-to-image", "controlnet"])
    index_mock.get = MagicMock(return_value={
        "id": "official_txt2img", "name": "txt2img_basic", "category": "text-to-image",
        "source": "official", "workflow": {"1": {"class_type": "KSampler", "inputs": {}}},
    })
    index_mock.summary = MagicMock(return_value={"template_count": 1, "stale": False})
    index_mock.rebuild = MagicMock()

    discovery_mock = AsyncMock()
    discovery_mock.discover_all = AsyncMock(return_value=[
        {"name": "txt2img_basic", "category": "text-to-image", "source": "official", "tags": ["txt2img"]},
    ])

    mock_ctx.request_context.lifespan_context["template_index"] = index_mock
    mock_ctx.request_context.lifespan_context["template_discovery"] = discovery_mock

    # Ensure install_graph has snapshot for instantiator
    graph_mock = MagicMock()
    graph_mock.snapshot = {
        "node_classes": {"KSampler"},
        "models": {"checkpoints": ["model.safetensors"]},
        "embeddings": [],
        "object_info": {},
    }
    mock_ctx.request_context.lifespan_context["install_graph"] = graph_mock
    return mock_ctx


class TestDiscoverTemplates:
    @pytest.mark.asyncio
    async def test_discover_rebuilds_index(self, template_ctx):
        from comfy_mcp.tools.templates import comfy_discover_templates
        result = json.loads(await comfy_discover_templates(ctx=template_ctx))
        assert result["status"] == "ok"


class TestSearchTemplates:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, template_ctx):
        from comfy_mcp.tools.templates import comfy_search_templates
        result = json.loads(await comfy_search_templates(query="txt2img", ctx=template_ctx))
        assert "results" in result


class TestGetTemplate:
    @pytest.mark.asyncio
    async def test_get_returns_template(self, template_ctx):
        from comfy_mcp.tools.templates import comfy_get_template
        result = json.loads(await comfy_get_template(template_id="official_txt2img", ctx=template_ctx))
        assert result["name"] == "txt2img_basic"


class TestListCategories:
    @pytest.mark.asyncio
    async def test_list_categories(self, template_ctx):
        from comfy_mcp.tools.templates import comfy_list_template_categories
        result = json.loads(await comfy_list_template_categories(ctx=template_ctx))
        assert "categories" in result


class TestTemplateStatus:
    @pytest.mark.asyncio
    async def test_status_returns_summary(self, template_ctx):
        from comfy_mcp.tools.templates import comfy_template_status
        result = json.loads(await comfy_template_status(ctx=template_ctx))
        assert "template_count" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_tools_templates.py -v`
Expected: FAIL

- [ ] **Step 3: Implement MCP tools**

```python
# src/comfy_mcp/tools/templates.py
"""Template tools — MCP surface for the template engine."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _index(ctx: Context):
    return ctx.request_context.lifespan_context["template_index"]


def _discovery(ctx: Context):
    return ctx.request_context.lifespan_context["template_discovery"]


@mcp.tool(
    annotations={
        "title": "Discover Templates",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_discover_templates(ctx: Context = None) -> str:
    """Scan all template sources and rebuild the unified template index.

    Fetches from official ComfyUI templates, custom node examples, and built-in templates.
    """
    discovery = _discovery(ctx)
    index = _index(ctx)
    templates = await discovery.discover_all()
    index.rebuild(templates)
    return json.dumps({"status": "ok", "summary": index.summary()}, indent=2)


@mcp.tool(
    annotations={
        "title": "Search Templates",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_search_templates(
    query: str,
    tags: list[str] | None = None,
    category: str | None = None,
    limit: int = 10,
    ctx: Context = None,
) -> str:
    """Search templates by query, tags, and/or category.

    Returns scored results ranked by relevance and compatibility.

    Args:
        query: Natural language search query.
        tags: Optional tag filters.
        category: Optional category filter.
        limit: Maximum results (default 10).
    """
    index = _index(ctx)
    install_graph = ctx.request_context.lifespan_context.get("install_graph")
    if install_graph and install_graph.snapshot:
        nodes = install_graph.snapshot.get("node_classes", set())
        models = install_graph.snapshot.get("models", {})
    else:
        nodes = set()
        models = {}

    from comfy_mcp.templates.scorer import TemplateScorer
    scorer = TemplateScorer(nodes, models)
    results = scorer.score(query, index.list_all(), tags=tags, category=category, limit=limit)
    return json.dumps({"query": query, "count": len(results), "results": results}, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Template",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_template(template_id: str, ctx: Context = None) -> str:
    """Get full template details including metadata and model requirements.

    Args:
        template_id: Template ID from search results.
    """
    index = _index(ctx)
    template = index.get(template_id)
    if template is None:
        return json.dumps({"error": f"Template '{template_id}' not found"}, indent=2)
    return json.dumps(template, indent=2)


@mcp.tool(
    annotations={
        "title": "Instantiate Template",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_instantiate_template(
    template_id: str,
    overrides: dict | None = None,
    ctx: Context = None,
) -> str:
    """Instantiate a template with model substitution.

    Substitutes model references with installed models, applies overrides,
    and returns a ready-to-queue workflow.

    Args:
        template_id: Template ID to instantiate.
        overrides: Optional dict of parameter overrides (e.g., {"width": 768}).
    """
    index = _index(ctx)
    template = index.get(template_id)
    if template is None:
        return json.dumps({"error": f"Template '{template_id}' not found"}, indent=2)

    install_graph = ctx.request_context.lifespan_context.get("install_graph")
    if not install_graph or not install_graph.snapshot:
        return json.dumps({"error": "Install graph not available. Run comfy_refresh_install_graph first."}, indent=2)

    from comfy_mcp.templates.instantiator import TemplateInstantiator
    instantiator = TemplateInstantiator(install_graph.snapshot)
    result = instantiator.instantiate(template, overrides=overrides)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "List Template Categories",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_template_categories(ctx: Context = None) -> str:
    """List all available template categories."""
    index = _index(ctx)
    return json.dumps({"categories": index.categories()}, indent=2)


@mcp.tool(
    annotations={
        "title": "Template Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_template_status(ctx: Context = None) -> str:
    """Show template index status — counts, categories, cache freshness."""
    index = _index(ctx)
    return json.dumps(index.summary(), indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_tools_templates.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/tools/templates.py tests/test_tools_templates.py && git commit -m "feat(v0.5): add 6 MCP tools for template engine"
```

---

### Task 6: Server integration + README

**Files:**
- Modify: `src/comfy_mcp/server.py`
- Modify: `src/comfy_mcp/tool_registry.py`
- Modify: `tests/conftest.py`
- Modify: `README.md`

- [ ] **Step 1: Add to server.py lifespan**

After docs_store/docs_fetcher initialization, add:

```python
    from comfy_mcp.templates.discovery import TemplateDiscovery
    from comfy_mcp.templates.index import TemplateIndex

    template_discovery = TemplateDiscovery(client)
    template_index = TemplateIndex()
```

Add to yield dict:
```python
            "template_discovery": template_discovery,
            "template_index": template_index,
```

Add module-level global and resource:
```python
_shared_template_index = None
```

Set in lifespan: `_shared_template_index = template_index`
Clear in finally: `_shared_template_index = None`

```python
@mcp.resource("comfy://templates/index")
async def templates_index_resource() -> str:
    """Template index summary — counts, categories, sources."""
    if _shared_template_index is None:
        return json.dumps({"status": "not_initialized"})
    return json.dumps(_shared_template_index.summary(), indent=2)
```

- [ ] **Step 2: Register in tool_registry.py**

```python
from comfy_mcp.tools import templates     # noqa: F401 -- v0.5 Template Engine
```

- [ ] **Step 3: Update conftest.py**

Add to `lifespan_context`:
```python
        "template_index": MagicMock(),
        "template_discovery": AsyncMock(),
```

- [ ] **Step 4: Update README.md**

- Version: `v0.5.0`
- Tool count: `82-tool runtime surface`
- Add Template Engine section (### 16)
- Resources count: 9
- Add `comfy://templates/index` resource

- [ ] **Step 5: Run full test suite**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest -v`
Expected: ALL pass

- [ ] **Step 6: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/server.py src/comfy_mcp/tool_registry.py tests/conftest.py README.md && git commit -m "feat: v0.5.0 — Template Engine (82 tools, 9 resources)"
```

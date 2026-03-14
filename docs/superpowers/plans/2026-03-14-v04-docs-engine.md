# v0.4 Docs Engine Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a documentation engine that fetches, caches, and serves official ComfyUI documentation so the agent can answer "how does node X work?" without hallucinating.

**Architecture:** Three-module package (`src/comfy_mcp/docs/`) with a fetcher for HTTP retrieval, a store for disk caching at `~/.comfypilot/docs/`, and an index for search/lookup. Tools access the store via lifespan context. Falls back to object_info-only when docs are unavailable.

**Tech Stack:** Python 3.12, httpx (already a dependency), pathlib for disk I/O, hashlib for cache hashes.

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/comfy_mcp/docs/__init__.py` | Package init |
| Create | `src/comfy_mcp/docs/fetcher.py` | HTTP fetch from embedded-docs + llms-full.txt with graceful degradation |
| Create | `src/comfy_mcp/docs/store.py` | Disk cache at `~/.comfypilot/docs/`, hash-based staleness, filename sanitization, section indexing |
| Create | `src/comfy_mcp/docs/index.py` | Lookup by class name, full-text search, section-based guide lookup |
| Create | `src/comfy_mcp/tools/docs.py` | 5 MCP tools: get_node_docs, search_docs, get_guide, refresh_docs, docs_status |
| Create | `tests/test_docs_store.py` | Tests for store: cache, staleness, sanitization, sections |
| Create | `tests/test_docs_fetcher.py` | Tests for fetcher: HTTP mock, degradation |
| Create | `tests/test_docs_index.py` | Tests for index: lookup, search, guide |
| Create | `tests/test_tools_docs.py` | Tests for MCP tools: end-to-end via mock_ctx |
| Modify | `src/comfy_mcp/server.py` | Add DocsStore to lifespan context + `comfy://docs/status` resource |
| Modify | `src/comfy_mcp/tool_registry.py` | Add `from comfy_mcp.tools import docs` import |
| Modify | `tests/conftest.py` | Add `"docs_store"` to mock_ctx lifespan_context |
| Modify | `README.md` | Update tool count to 76, resource count to 8, add Docs Engine section |

---

## Chunk 1: DocsStore (disk cache layer)

### Task 1: Package init + DocsStore skeleton

**Files:**
- Create: `src/comfy_mcp/docs/__init__.py`
- Create: `src/comfy_mcp/docs/store.py`
- Create: `tests/test_docs_store.py`

- [ ] **Step 1: Create the package init**

```python
# src/comfy_mcp/docs/__init__.py
```

Empty file. Just establishes the package.

- [ ] **Step 2: Write the first failing test — store initialization creates directory**

```python
# tests/test_docs_store.py
"""Tests for DocsStore — disk cache for ComfyUI documentation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestDocsStoreInit:
    def test_creates_storage_directory(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store_dir = tmp_path / "docs"
        store = DocsStore(storage_dir=str(store_dir))
        assert store_dir.exists()
        assert (store_dir / "embedded").exists()

    def test_defaults_to_home_comfypilot(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        # Also patch Path.home() for Windows
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore()
        assert (tmp_path / ".comfypilot" / "docs").exists()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_docs_store.py::TestDocsStoreInit -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 4: Write minimal DocsStore**

```python
# src/comfy_mcp/docs/store.py
"""DocsStore — disk cache for ComfyUI documentation.

Caches embedded-docs markdown files and llms-full.txt to ~/.comfypilot/docs/.
Provides hash-based staleness checks and filename sanitization for node class names.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def _content_hash(text: str) -> str:
    """SHA-256 prefix for change detection."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class DocsStore:
    """Manages on-disk documentation cache at ~/.comfypilot/docs/."""

    def __init__(self, storage_dir: str | None = None):
        self._dir = Path(storage_dir or Path.home() / ".comfypilot" / "docs")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._embedded_dir = self._dir / "embedded"
        self._embedded_dir.mkdir(exist_ok=True)
        self._manifest = self._load_manifest()

    def _manifest_path(self) -> Path:
        return self._dir / "manifest.json"

    def _load_manifest(self) -> dict[str, Any]:
        path = self._manifest_path()
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_manifest(self) -> None:
        path = self._manifest_path()
        path.write_text(json.dumps(self._manifest, indent=2))
```

Note: `_sanitize_filename` is intentionally NOT included here. Task 1 stores files using the raw `class_name` directly. Sanitization is added in Task 2 following TDD (tests first, then implementation).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_docs_store.py::TestDocsStoreInit -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/docs/__init__.py src/comfy_mcp/docs/store.py tests/test_docs_store.py && git commit -m "feat(v0.4): add DocsStore skeleton with directory creation"
```

---

### Task 2: Filename sanitization

**Files:**
- Modify: `src/comfy_mcp/docs/store.py`
- Modify: `tests/test_docs_store.py`

- [ ] **Step 1: Write failing tests for sanitization**

Add to `tests/test_docs_store.py`:

```python
class TestFilenameSanitization:
    def test_simple_name_unchanged(self):
        from comfy_mcp.docs.store import _sanitize_filename
        assert _sanitize_filename("KSampler") == "KSampler"

    def test_plus_sign_replaced(self):
        from comfy_mcp.docs.store import _sanitize_filename
        assert _sanitize_filename("Node+Plus") == "Node_Plus"

    def test_parentheses_replaced(self):
        from comfy_mcp.docs.store import _sanitize_filename
        assert _sanitize_filename("Node(v2)") == "Node_v2_"

    def test_spaces_replaced(self):
        from comfy_mcp.docs.store import _sanitize_filename
        assert _sanitize_filename("My Custom Node") == "My_Custom_Node"

    def test_already_safe_with_dots(self):
        from comfy_mcp.docs.store import _sanitize_filename
        assert _sanitize_filename("ADE_AnimateDiff.v2") == "ADE_AnimateDiff.v2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_docs_store.py::TestFilenameSanitization -v`
Expected: FAIL with `ImportError` — `_sanitize_filename` does not exist yet.

- [ ] **Step 3: Implement `_sanitize_filename` in store.py**

Add to `src/comfy_mcp/docs/store.py`, above the `_content_hash` function:

```python
import re

def _sanitize_filename(class_name: str) -> str:
    """Convert a node class name to a filesystem-safe filename."""
    return re.sub(r'[^\w\-.]', '_', class_name)
```

Also add `import re` to the imports at the top of the file.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_docs_store.py::TestFilenameSanitization -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/docs/store.py tests/test_docs_store.py && git commit -m "feat(v0.4): add filename sanitization with TDD (tests first, then implementation)"
```

---

### Task 3: Embedded doc save/load/staleness

**Files:**
- Modify: `src/comfy_mcp/docs/store.py`
- Modify: `tests/test_docs_store.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_docs_store.py`:

```python
class TestEmbeddedDocCache:
    def test_save_and_get_embedded_doc(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_embedded("KSampler", "# KSampler\nSamples latents.")
        doc = store.get_embedded("KSampler")
        assert doc == "# KSampler\nSamples latents."

    def test_get_embedded_returns_none_for_missing(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        assert store.get_embedded("FakeNode") is None

    def test_save_embedded_updates_manifest(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_embedded("KSampler", "# KSampler\nSamples latents.")
        assert "KSampler" in store._manifest.get("embedded", {})

    def test_is_stale_returns_true_when_empty(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        assert store.is_stale() is True

    def test_is_stale_returns_false_when_fresh(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_embedded("KSampler", "doc")
        assert store.is_stale(max_age=300) is False

    def test_content_hash_changes_on_update(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_embedded("KSampler", "v1")
        hash1 = store.content_hash()
        store.save_embedded("KSampler", "v2")
        hash2 = store.content_hash()
        assert hash1 != hash2

    def test_unsafe_classname_stored_safely(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_embedded("Node(v2+)", "doc content")
        doc = store.get_embedded("Node(v2+)")
        assert doc == "doc content"
        # Verify no file with unsafe characters was created
        files = list((tmp_path / "docs" / "embedded").glob("*"))
        for f in files:
            assert "(" not in f.name
            assert "+" not in f.name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_docs_store.py::TestEmbeddedDocCache -v`
Expected: FAIL with `AttributeError: 'DocsStore' object has no attribute 'save_embedded'`

- [ ] **Step 3: Implement save_embedded, get_embedded, is_stale, content_hash**

Add to `DocsStore` class in `src/comfy_mcp/docs/store.py`:

```python
    # Add these instance variables in __init__:
    #   self._name_to_file: dict[str, str] = {}  # class_name -> sanitized filename
    #   self._rebuild_name_map()

    def _rebuild_name_map(self) -> None:
        """Build class_name -> sanitized_filename map from manifest."""
        self._name_to_file = {}
        for class_name, info in self._manifest.get("embedded", {}).items():
            self._name_to_file[class_name] = info.get("filename", _sanitize_filename(class_name))

    def save_embedded(self, class_name: str, content: str) -> None:
        """Save an embedded doc markdown file for a node class."""
        safe_name = _sanitize_filename(class_name)
        path = self._embedded_dir / f"{safe_name}.md"
        path.write_text(content)

        if "embedded" not in self._manifest:
            self._manifest["embedded"] = {}
        self._manifest["embedded"][class_name] = {
            "filename": safe_name,
            "hash": _content_hash(content),
            "cached_at": time.time(),
        }
        self._manifest["last_updated"] = time.time()
        self._name_to_file[class_name] = safe_name
        self._save_manifest()

    def get_embedded(self, class_name: str) -> str | None:
        """Get cached embedded doc for a node class. Returns None if not cached."""
        safe_name = self._name_to_file.get(class_name, _sanitize_filename(class_name))
        path = self._embedded_dir / f"{safe_name}.md"
        if path.exists():
            return path.read_text()
        return None

    def is_stale(self, max_age: float = 300) -> bool:
        """Check if the cache is empty or older than max_age seconds."""
        last = self._manifest.get("last_updated")
        if last is None:
            return True
        return (time.time() - last) >= max_age

    def content_hash(self) -> str:
        """Combined hash of all cached content for change detection."""
        hashes = sorted(
            info.get("hash", "")
            for info in self._manifest.get("embedded", {}).values()
        )
        combined = "|".join(hashes)
        return _content_hash(combined)

    def clear(self) -> None:
        """Remove all cached documentation."""
        for path in self._embedded_dir.glob("*.md"):
            path.unlink()
        llms_path = self._dir / "llms-full.txt"
        if llms_path.exists():
            llms_path.unlink()
        sections_path = self._dir / "sections.json"
        if sections_path.exists():
            sections_path.unlink()
        self._manifest = {}
        self._name_to_file = {}
        self._save_manifest()

    def list_embedded_classes(self) -> list[str]:
        """Return the list of class names that have cached embedded docs."""
        return list(self._manifest.get("embedded", {}).keys())

    def summary(self) -> dict:
        """Return cache status summary."""
        embedded_count = len(self._manifest.get("embedded", {}))
        has_llms = (self._dir / "llms-full.txt").exists()
        has_sections = (self._dir / "sections.json").exists()
        return {
            "embedded_docs": embedded_count,
            "llms_full_cached": has_llms,
            "sections_indexed": has_sections,
            "stale": self.is_stale(),
            "last_updated": self._manifest.get("last_updated"),
            "content_hash": self.content_hash() if embedded_count > 0 else None,
        }
```

Also update `__init__` to add:
```python
        self._name_to_file: dict[str, str] = {}
        self._rebuild_name_map()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_docs_store.py::TestEmbeddedDocCache -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/docs/store.py tests/test_docs_store.py && git commit -m "feat(v0.4): add embedded doc save/load with staleness and hashing"
```

---

### Task 4: Section indexing for llms-full.txt

**Files:**
- Modify: `src/comfy_mcp/docs/store.py`
- Modify: `tests/test_docs_store.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_docs_store.py`:

```python
class TestSectionIndexing:
    SAMPLE_LLMS = """# Getting Started
This is the intro section.

## Installation
Install ComfyUI from source.

## First Workflow
Create your first txt2img workflow.

# Advanced Topics
Deep dive into advanced features.

## Custom Nodes
How to write custom nodes.
"""

    def test_save_llms_creates_sections_index(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_llms(self.SAMPLE_LLMS)
        sections_path = tmp_path / "docs" / "sections.json"
        assert sections_path.exists()
        sections = json.loads(sections_path.read_text())
        assert len(sections) > 0

    def test_sections_have_correct_fields(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_llms(self.SAMPLE_LLMS)
        sections = json.loads((tmp_path / "docs" / "sections.json").read_text())
        for s in sections:
            assert "title" in s
            assert "start_line" in s
            assert "end_line" in s
            assert "level" in s

    def test_get_llms_section_by_topic(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_llms(self.SAMPLE_LLMS)
        result = store.get_section("installation")
        assert result is not None
        assert "Install ComfyUI" in result["content"]

    def test_get_llms_section_returns_none_for_unknown(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_llms(self.SAMPLE_LLMS)
        result = store.get_section("quantum_computing")
        assert result is None

    def test_llms_stored_on_disk(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_llms(self.SAMPLE_LLMS)
        assert (tmp_path / "docs" / "llms-full.txt").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_docs_store.py::TestSectionIndexing -v`
Expected: FAIL with `AttributeError: 'DocsStore' object has no attribute 'save_llms'`

- [ ] **Step 3: Implement save_llms and get_section**

Add to `DocsStore` class in `src/comfy_mcp/docs/store.py`:

```python
    def save_llms(self, content: str) -> None:
        """Save llms-full.txt and build section index."""
        llms_path = self._dir / "llms-full.txt"
        llms_path.write_text(content)
        self._manifest["llms_hash"] = _content_hash(content)
        self._manifest["llms_cached_at"] = time.time()
        self._manifest["last_updated"] = time.time()
        self._save_manifest()
        self._build_section_index(content)

    def _build_section_index(self, content: str) -> None:
        """Parse markdown headings into a section index."""
        lines = content.split("\n")
        sections = []
        current: dict | None = None

        for i, line in enumerate(lines):
            if line.startswith("#"):
                # Close previous section
                if current is not None:
                    current["end_line"] = i - 1
                    sections.append(current)
                # Count heading level
                level = len(line) - len(line.lstrip("#"))
                title = line.lstrip("#").strip()
                current = {
                    "title": title,
                    "start_line": i,
                    "end_line": len(lines) - 1,  # default to end
                    "level": level,
                }

        # Close last section
        if current is not None:
            current["end_line"] = len(lines) - 1
            sections.append(current)

        sections_path = self._dir / "sections.json"
        sections_path.write_text(json.dumps(sections, indent=2))

    def get_section(self, topic: str) -> dict | None:
        """Find a section by topic (case-insensitive substring match)."""
        sections_path = self._dir / "sections.json"
        if not sections_path.exists():
            return None
        llms_path = self._dir / "llms-full.txt"
        if not llms_path.exists():
            return None

        sections = json.loads(sections_path.read_text())
        topic_lower = topic.lower()

        # Find best match (prefer exact title match, then substring)
        best = None
        for s in sections:
            if topic_lower == s["title"].lower():
                best = s
                break
            if topic_lower in s["title"].lower() and best is None:
                best = s

        if best is None:
            return None

        lines = llms_path.read_text().split("\n")
        content = "\n".join(lines[best["start_line"]:best["end_line"] + 1])
        return {
            "title": best["title"],
            "level": best["level"],
            "content": content,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_docs_store.py::TestSectionIndexing -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/docs/store.py tests/test_docs_store.py && git commit -m "feat(v0.4): add llms-full.txt section indexing and topic lookup"
```

---

## Chunk 2: Fetcher (HTTP layer)

### Task 5: DocsFetcher with HTTP fetch + graceful degradation

**Files:**
- Create: `src/comfy_mcp/docs/fetcher.py`
- Create: `tests/test_docs_fetcher.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_docs_fetcher.py
"""Tests for DocsFetcher — HTTP fetch with graceful degradation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestFetchEmbeddedDoc:
    @pytest.mark.asyncio
    async def test_fetch_returns_content_on_success(self):
        from comfy_mcp.docs.fetcher import DocsFetcher
        fetcher = DocsFetcher()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# KSampler\nSamples latents."
        with patch.object(fetcher, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            result = await fetcher.fetch_embedded_doc("KSampler")
            assert result == "# KSampler\nSamples latents."

    @pytest.mark.asyncio
    async def test_fetch_returns_none_on_404(self):
        from comfy_mcp.docs.fetcher import DocsFetcher
        fetcher = DocsFetcher()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        with patch.object(fetcher, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            result = await fetcher.fetch_embedded_doc("FakeNode")
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_returns_none_on_network_error(self):
        from comfy_mcp.docs.fetcher import DocsFetcher
        import httpx
        fetcher = DocsFetcher()
        with patch.object(fetcher, "_client") as mock_client:
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("offline"))
            result = await fetcher.fetch_embedded_doc("KSampler")
            assert result is None


class TestFetchLlmsFull:
    @pytest.mark.asyncio
    async def test_fetch_llms_returns_content(self):
        from comfy_mcp.docs.fetcher import DocsFetcher
        fetcher = DocsFetcher()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# Full Docs\nContent here."
        with patch.object(fetcher, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            result = await fetcher.fetch_llms_full()
            assert result == "# Full Docs\nContent here."

    @pytest.mark.asyncio
    async def test_fetch_llms_returns_none_on_error(self):
        from comfy_mcp.docs.fetcher import DocsFetcher
        import httpx
        fetcher = DocsFetcher()
        with patch.object(fetcher, "_client") as mock_client:
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("offline"))
            result = await fetcher.fetch_llms_full()
            assert result is None


class TestFetcherClose:
    @pytest.mark.asyncio
    async def test_close_is_safe_to_call(self):
        from comfy_mcp.docs.fetcher import DocsFetcher
        fetcher = DocsFetcher()
        await fetcher.close()  # should not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_docs_fetcher.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement DocsFetcher**

```python
# src/comfy_mcp/docs/fetcher.py
"""DocsFetcher — HTTP fetch for ComfyUI documentation sources.

Fetches embedded-docs markdown files and llms-full.txt with graceful
degradation on network errors. Never raises on fetch failure — returns None.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("comfypilot.docs")

# Default URLs — configurable via constructor for testability
DEFAULT_EMBEDDED_BASE = "https://raw.githubusercontent.com/Comfy-Org/embedded-docs/main/docs"
DEFAULT_LLMS_URL = "https://docs.comfy.org/llms-full.txt"


class DocsFetcher:
    """Fetches documentation from remote sources with graceful degradation."""

    def __init__(
        self,
        embedded_base_url: str = DEFAULT_EMBEDDED_BASE,
        llms_url: str = DEFAULT_LLMS_URL,
        timeout: float = 30.0,
    ):
        self._embedded_base = embedded_base_url.rstrip("/")
        self._llms_url = llms_url
        self._client = httpx.AsyncClient(timeout=timeout)

    async def fetch_embedded_doc(self, class_name: str) -> str | None:
        """Fetch a single node's embedded doc. Returns None on any failure."""
        url = f"{self._embedded_base}/{class_name}.md"
        try:
            response = await self._client.get(url)
            if response.status_code == 200:
                return response.text
            logger.debug("Embedded doc fetch %s returned %d", class_name, response.status_code)
            return None
        except Exception as exc:
            logger.debug("Embedded doc fetch failed for %s: %s", class_name, exc)
            return None

    async def fetch_llms_full(self) -> str | None:
        """Fetch the complete llms-full.txt. Returns None on any failure."""
        try:
            response = await self._client.get(self._llms_url)
            if response.status_code == 200:
                return response.text
            logger.debug("llms-full.txt fetch returned %d", response.status_code)
            return None
        except Exception as exc:
            logger.debug("llms-full.txt fetch failed: %s", exc)
            return None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_docs_fetcher.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/docs/fetcher.py tests/test_docs_fetcher.py && git commit -m "feat(v0.4): add DocsFetcher with HTTP fetch and graceful degradation"
```

---

## Chunk 3: DocsIndex (search + lookup)

### Task 6: DocsIndex — lookup and search

**Files:**
- Create: `src/comfy_mcp/docs/index.py`
- Create: `tests/test_docs_index.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_docs_index.py
"""Tests for DocsIndex — documentation lookup and search."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def populated_store(tmp_path):
    """DocsStore with some cached docs."""
    from comfy_mcp.docs.store import DocsStore
    store = DocsStore(storage_dir=str(tmp_path / "docs"))
    store.save_embedded("KSampler", "# KSampler\nSamples latent noise using various methods.\nUses model, seed, steps, cfg, sampler_name.")
    store.save_embedded("SaveImage", "# SaveImage\nSaves generated images to the output directory.")
    store.save_embedded("CheckpointLoaderSimple", "# CheckpointLoaderSimple\nLoads a diffusion model checkpoint.\nOutputs MODEL, CLIP, VAE.")
    store.save_llms("# Getting Started\nIntro guide.\n\n## Sampling\nHow sampling works in ComfyUI.\n\n## Models\nAbout model loading.")
    return store


class TestDocsIndexLookup:
    def test_get_node_doc_returns_cached(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        index = DocsIndex(populated_store)
        result = index.get_node_doc("KSampler")
        assert result is not None
        assert "Samples latent noise" in result["description"]

    def test_get_node_doc_returns_none_for_missing(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        index = DocsIndex(populated_store)
        result = index.get_node_doc("FakeNode")
        assert result is None

    def test_get_node_doc_merges_object_info(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        object_info = {
            "KSampler": {
                "input": {"required": {"seed": ["INT"], "steps": ["INT"]}},
                "output": ["LATENT"],
            }
        }
        index = DocsIndex(populated_store, object_info=object_info)
        result = index.get_node_doc("KSampler")
        assert "schema" in result
        assert result["schema"]["output"] == ["LATENT"]


class TestDocsIndexSearch:
    def test_search_finds_by_keyword(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        index = DocsIndex(populated_store)
        results = index.search("sampl")
        assert len(results) >= 1
        assert any("KSampler" in r["class_name"] for r in results)

    def test_search_returns_empty_for_no_match(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        index = DocsIndex(populated_store)
        results = index.search("quantum_physics")
        assert results == []

    def test_search_respects_limit(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        index = DocsIndex(populated_store)
        results = index.search("", limit=1)
        assert len(results) <= 1


class TestDocsIndexGuide:
    def test_get_guide_finds_section(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        index = DocsIndex(populated_store)
        result = index.get_guide("sampling")
        assert result is not None
        assert "How sampling works" in result["content"]

    def test_get_guide_returns_none_for_unknown(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        index = DocsIndex(populated_store)
        result = index.get_guide("quantum_computing")
        assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_docs_index.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement DocsIndex**

```python
# src/comfy_mcp/docs/index.py
"""DocsIndex — documentation lookup and search.

Provides node doc lookup (embedded + object_info merge), full-text search,
and section-based guide retrieval from llms-full.txt.
"""

from __future__ import annotations

from typing import Any

from comfy_mcp.docs.store import DocsStore


class DocsIndex:
    """Search and lookup interface for cached documentation."""

    def __init__(self, store: DocsStore, object_info: dict[str, Any] | None = None):
        self._store = store
        self._object_info = object_info or {}

    def get_node_doc(self, class_name: str) -> dict | None:
        """Get documentation for a node class.

        Merges embedded doc (description) with object_info (schema).
        Returns None if neither source has data for this class.
        """
        embedded = self._store.get_embedded(class_name)
        schema = self._object_info.get(class_name)

        if embedded is None and schema is None:
            return None

        result: dict[str, Any] = {"class_name": class_name}

        if embedded is not None:
            result["description"] = embedded

        if schema is not None:
            result["schema"] = schema

        return result

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Full-text search across cached embedded docs.

        Searches doc content by substring match (case-insensitive).
        """
        query_lower = query.lower()
        results = []

        for class_name in self._store.list_embedded_classes():
            content = self._store.get_embedded(class_name)
            if content is None:
                continue
            if query_lower and query_lower not in content.lower():
                continue
            # Include a snippet
            lines = content.strip().split("\n")
            snippet = lines[0] if lines else ""
            results.append({
                "class_name": class_name,
                "snippet": snippet[:200],
            })

        return results[:limit]

    def get_guide(self, topic: str) -> dict | None:
        """Retrieve a guide section from llms-full.txt by topic."""
        return self._store.get_section(topic)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_docs_index.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/docs/index.py tests/test_docs_index.py && git commit -m "feat(v0.4): add DocsIndex with lookup, search, and guide retrieval"
```

---

## Chunk 4: MCP Tools + Integration

### Task 7: MCP tools for docs

**Files:**
- Create: `src/comfy_mcp/tools/docs.py`
- Create: `tests/test_tools_docs.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools_docs.py
"""Tests for docs MCP tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def docs_ctx(mock_ctx):
    """Mock context with docs_store in lifespan."""
    store_mock = MagicMock()
    store_mock.get_embedded = MagicMock(return_value="# KSampler\nSamples latents.")
    store_mock.get_section = MagicMock(return_value={"title": "Sampling", "level": 2, "content": "How sampling works."})
    store_mock.save_embedded = MagicMock()
    store_mock.save_llms = MagicMock()
    store_mock.summary = MagicMock(return_value={"embedded_docs": 5, "stale": False})
    store_mock.is_stale = MagicMock(return_value=False)
    store_mock.list_embedded_classes = MagicMock(return_value=["KSampler"])

    fetcher_mock = AsyncMock()
    fetcher_mock.fetch_embedded_doc = AsyncMock(return_value="# KSampler\nFresh doc.")
    fetcher_mock.fetch_llms_full = AsyncMock(return_value="# Docs\nContent.")

    mock_ctx.request_context.lifespan_context["docs_store"] = store_mock
    mock_ctx.request_context.lifespan_context["docs_fetcher"] = fetcher_mock
    return mock_ctx


class TestGetNodeDocs:
    @pytest.mark.asyncio
    async def test_returns_doc(self, docs_ctx):
        from comfy_mcp.tools.docs import comfy_get_node_docs
        result = json.loads(await comfy_get_node_docs(class_name="KSampler", ctx=docs_ctx))
        assert "description" in result

    @pytest.mark.asyncio
    async def test_returns_not_found(self, docs_ctx):
        docs_ctx.request_context.lifespan_context["docs_store"].get_embedded = MagicMock(return_value=None)
        from comfy_mcp.tools.docs import comfy_get_node_docs
        result = json.loads(await comfy_get_node_docs(class_name="FakeNode", ctx=docs_ctx))
        assert "not_found" in result.get("status", "") or result.get("description") is None


class TestSearchDocs:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, docs_ctx):
        from comfy_mcp.tools.docs import comfy_search_docs
        result = json.loads(await comfy_search_docs(query="sampl", ctx=docs_ctx))
        assert "results" in result
        assert result["count"] >= 1
        assert len(result["results"]) >= 1


class TestGetGuide:
    @pytest.mark.asyncio
    async def test_get_guide_returns_section(self, docs_ctx):
        from comfy_mcp.tools.docs import comfy_get_guide
        result = json.loads(await comfy_get_guide(topic="sampling", ctx=docs_ctx))
        assert "content" in result


class TestRefreshDocs:
    @pytest.mark.asyncio
    async def test_refresh_happy_path(self, docs_ctx):
        """Successful refresh fetches and caches docs."""
        from comfy_mcp.tools.docs import comfy_refresh_docs
        result = json.loads(await comfy_refresh_docs(ctx=docs_ctx))
        assert result["status"] == "ok"
        assert result["llms_cached"] is True

    @pytest.mark.asyncio
    async def test_refresh_partial_on_fetch_failure(self, docs_ctx):
        """Fetch failure returns partial success, does not crash."""
        docs_ctx.request_context.lifespan_context["docs_fetcher"].fetch_llms_full = AsyncMock(return_value=None)
        from comfy_mcp.tools.docs import comfy_refresh_docs
        result = json.loads(await comfy_refresh_docs(ctx=docs_ctx))
        assert result["status"] == "partial"
        assert len(result["errors"]) >= 1
        assert result["llms_cached"] is False


class TestDocsStatus:
    @pytest.mark.asyncio
    async def test_status_returns_summary(self, docs_ctx):
        from comfy_mcp.tools.docs import comfy_docs_status
        result = json.loads(await comfy_docs_status(ctx=docs_ctx))
        assert "embedded_docs" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_tools_docs.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement MCP tools**

```python
# src/comfy_mcp/tools/docs.py
"""Docs tools — MCP surface for the documentation engine."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _store(ctx: Context):
    return ctx.request_context.lifespan_context["docs_store"]


def _fetcher(ctx: Context):
    return ctx.request_context.lifespan_context["docs_fetcher"]


@mcp.tool(
    annotations={
        "title": "Get Node Docs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_get_node_docs(class_name: str, ctx: Context) -> str:
    """Get documentation for a specific ComfyUI node class.

    Returns embedded documentation merged with object_info schema.
    Fetches from remote source if not cached. Falls back to schema-only
    if remote docs are unavailable.

    Args:
        class_name: The node class name (e.g., KSampler, SaveImage).
    """
    store = _store(ctx)
    fetcher = _fetcher(ctx)

    # Try cache first
    doc = store.get_embedded(class_name)

    # If not cached, try fetching
    if doc is None:
        doc = await fetcher.fetch_embedded_doc(class_name)
        if doc is not None:
            store.save_embedded(class_name, doc)

    # Merge with object_info if available
    install_graph = ctx.request_context.lifespan_context.get("install_graph")
    schema = None
    if install_graph and install_graph.snapshot:
        schema = install_graph.snapshot.get("object_info", {}).get(class_name)

    if doc is None and schema is None:
        return json.dumps({"class_name": class_name, "status": "not_found",
                           "note": "No documentation or schema found for this node class."}, indent=2)

    result = {"class_name": class_name}
    if doc is not None:
        result["description"] = doc
    if schema is not None:
        result["schema"] = schema
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Search Docs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_search_docs(query: str, limit: int = 10, ctx: Context) -> str:
    """Full-text search across cached ComfyUI documentation.

    Searches node descriptions and guide content by keyword.

    Args:
        query: Search query string.
        limit: Maximum number of results (default 10).
    """
    store = _store(ctx)
    from comfy_mcp.docs.index import DocsIndex

    object_info = {}
    install_graph = ctx.request_context.lifespan_context.get("install_graph")
    if install_graph and install_graph.snapshot:
        object_info = install_graph.snapshot.get("object_info", {})

    # NOTE: DocsIndex is intentionally re-created on every call. object_info may
    # change between calls (e.g., after comfy_refresh), so we keep the index fresh
    # rather than caching a stale instance.
    index = DocsIndex(store, object_info=object_info)
    results = index.search(query, limit=limit)
    return json.dumps({"query": query, "count": len(results), "results": results}, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Guide",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_guide(topic: str, ctx: Context) -> str:
    """Retrieve a guide section from ComfyUI documentation by topic.

    Searches the llms-full.txt section index for matching content.

    Args:
        topic: Topic to search for (e.g., "sampling", "models", "installation").
    """
    store = _store(ctx)
    result = store.get_section(topic)
    if result is None:
        return json.dumps({"topic": topic, "status": "not_found",
                           "note": "No guide section found. Try comfy_search_docs for broader search."}, indent=2)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Refresh Docs",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_refresh_docs(ctx: Context) -> str:
    """Re-fetch all documentation sources and rebuild the cache.

    Fetches embedded-docs and llms-full.txt from remote sources.
    Safe to call anytime — will not crash on network errors.
    """
    store = _store(ctx)
    fetcher = _fetcher(ctx)
    errors = []

    # Fetch llms-full.txt
    llms = await fetcher.fetch_llms_full()
    if llms is not None:
        store.save_llms(llms)
    else:
        errors.append("llms-full.txt: fetch failed (network error or source unavailable)")

    # Fetch embedded docs for all known node classes in parallel.
    # Uses asyncio.gather with a semaphore to limit concurrency (max 10)
    # so we don't overwhelm the remote server with 500+ simultaneous requests.
    import asyncio
    install_graph = ctx.request_context.lifespan_context.get("install_graph")
    fetched_count = 0
    if install_graph and install_graph.snapshot:
        node_classes = sorted(install_graph.snapshot.get("node_classes", set()))
        semaphore = asyncio.Semaphore(10)

        async def _fetch_one(cn: str) -> tuple[str, str | None]:
            async with semaphore:
                doc = await fetcher.fetch_embedded_doc(cn)
                return cn, doc

        results = await asyncio.gather(*[_fetch_one(cn) for cn in node_classes])
        for class_name, doc in results:
            if doc is not None:
                store.save_embedded(class_name, doc)
                fetched_count += 1

    return json.dumps({
        "status": "ok" if not errors else "partial",
        "embedded_docs_fetched": fetched_count,
        "llms_cached": llms is not None,
        "errors": errors,
        "summary": store.summary(),
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Docs Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_docs_status(ctx: Context) -> str:
    """Show documentation cache status.

    Returns cache freshness, source availability, and content hashes.
    """
    store = _store(ctx)
    return json.dumps(store.summary(), indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_tools_docs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/tools/docs.py tests/test_tools_docs.py && git commit -m "feat(v0.4): add 5 MCP tools for documentation engine"
```

---

### Task 8: Server integration — lifespan + resource + registry

**Files:**
- Modify: `src/comfy_mcp/server.py`
- Modify: `src/comfy_mcp/tool_registry.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add DocsStore and DocsFetcher to lifespan in server.py**

In `comfy_lifespan`, after the `install_graph` section, add:

```python
    from comfy_mcp.docs.store import DocsStore
    from comfy_mcp.docs.fetcher import DocsFetcher

    docs_store = DocsStore()
    docs_fetcher = DocsFetcher()
```

Add to the yield dict:
```python
            "docs_store": docs_store,
            "docs_fetcher": docs_fetcher,
```

Add cleanup in the finally block (before `await client.close()`):
```python
        await docs_fetcher.close()
```

- [ ] **Step 2: Add docs_store to module-level globals and resource**

Add at module level (near `_shared_install_graph`):
```python
_shared_docs_store = None
```

Add `_shared_docs_store` to the existing `global` statement inside `comfy_lifespan` (alongside `_shared_install_graph`):
```python
    global _shared_install_graph, _shared_docs_store
```

Set it in lifespan (after `docs_store = DocsStore()`):
```python
    _shared_docs_store = docs_store
```

Clear it in the finally block (near `_shared_install_graph = None`):
```python
        _shared_docs_store = None
```

Add resource after the existing resources:
```python
@mcp.resource("comfy://docs/status")
async def docs_status_resource() -> str:
    """Documentation cache status — freshness, counts, hashes."""
    if _shared_docs_store is None:
        return json.dumps({"status": "not_initialized"})
    return json.dumps(_shared_docs_store.summary(), indent=2)
```

- [ ] **Step 3: Register docs tools in tool_registry.py**

Add to `src/comfy_mcp/tool_registry.py`:
```python
from comfy_mcp.tools import docs         # noqa: F401 -- v0.4 Docs Engine
```

- [ ] **Step 4: Update conftest.py mock_ctx**

Add to the `lifespan_context` dict in `mock_ctx` fixture:
```python
        "docs_store": MagicMock(),
        "docs_fetcher": AsyncMock(),
```

- [ ] **Step 5: Run full test suite**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest -v`
Expected: ALL tests pass (existing 387 + new ~18 = ~405)

- [ ] **Step 6: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/server.py src/comfy_mcp/tool_registry.py tests/conftest.py && git commit -m "feat(v0.4): integrate DocsStore into lifespan, add docs resource"
```

---

### Task 9: Update test_event_lifecycle.py for new lifespan context

**Files:**
- Modify: `tests/test_event_lifecycle.py`

- [ ] **Step 1: Check if test_event_lifecycle passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_event_lifecycle.py -v`
If it fails because the lifespan now creates DocsStore/DocsFetcher:

- [ ] **Step 2: No mock changes needed (DocsStore and DocsFetcher don't need mock_client)**

DocsStore uses `Path.home()` (filesystem only). DocsFetcher creates its own httpx client. Neither depends on mock_client. The lifespan test should still pass because both constructors are side-effect free.

If the test does fail, the issue is likely that DocsFetcher's `__init__` creates an httpx.AsyncClient. The fix is to wrap the import in a try/except or make the DocsFetcher initialization conditional. Check error output.

- [ ] **Step 3: Run full suite to confirm**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest -v`
Expected: ALL pass

- [ ] **Step 4: Commit if changes were needed**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add tests/test_event_lifecycle.py && git commit -m "fix(v0.4): update event lifecycle test for docs engine integration"
```

---

### Task 10: README update + final commit

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README.md**

Changes needed:
- Version: `v0.4.0`
- Tool count: `76-tool runtime surface`
- Add Docs Engine to tool map (section 15)
- Update resources count to 8
- Add `comfy://docs/status` resource

Add after the Compatibility Engine section (### 14):

```markdown
### 15) Documentation Engine
Use for accessing official ComfyUI documentation and guides.

- `comfy_get_node_docs` — Get documentation for a specific node class (embedded docs + schema merged).
- `comfy_search_docs` — Full-text search across cached documentation.
- `comfy_get_guide` — Retrieve a guide section from the ComfyUI docs by topic.
- `comfy_refresh_docs` — Re-fetch documentation sources and rebuild cache.
- `comfy_docs_status` — Show cache freshness, source availability, content hashes.
```

Update the MCP Resources section to include:
```markdown
- `comfy://docs/status` — Documentation cache status and content hashes
```

- [ ] **Step 2: Run full test suite one final time**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest -v`
Expected: ALL pass

- [ ] **Step 3: Final commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add README.md && git commit -m "docs: update README for v0.4.0 — Docs Engine (76 tools, 8 resources)"
```

- [ ] **Step 4: Tag release commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add -A && git commit -m "feat: v0.4.0 — Docs Engine (official ComfyUI documentation access)" --allow-empty
```

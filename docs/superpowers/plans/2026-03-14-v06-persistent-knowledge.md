# v0.6 Persistent Knowledge Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify all disk caches into a coherent persistence layer with a shared KnowledgeStore pattern, add install graph disk caching for faster startup, and persist user preferences to config.json.

**Architecture:** New `src/comfy_mcp/knowledge/` package with a KnowledgeStore base pattern, config manager, and unified state tracking. Retrofits existing subsystems (DocsStore, TemplateIndex, InstallGraph) to the common interface. Adds disk caching for install graph and persistent config.json for user preferences.

**Tech Stack:** Python 3.12, pathlib, json, atomic file writes (write-to-temp-then-rename).

**Prerequisite:** v0.5 (Template Engine) must be implemented first.

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/comfy_mcp/knowledge/__init__.py` | Package init |
| Create | `src/comfy_mcp/knowledge/store.py` | KnowledgeStore protocol/base pattern |
| Create | `src/comfy_mcp/knowledge/config.py` | Config read/write with env var override, atomic writes |
| Create | `src/comfy_mcp/knowledge/manager.py` | Unified state.json management, refresh orchestration |
| Create | `src/comfy_mcp/knowledge/migration.py` | manifest.json → state.json migration with .bak backup |
| Create | `src/comfy_mcp/tools/knowledge.py` | 5 MCP tools |
| Create | `tests/test_knowledge_config.py` | Tests for config |
| Create | `tests/test_knowledge_store.py` | Tests for KnowledgeStore protocol and atomic_write |
| Create | `tests/test_knowledge_manager.py` | Tests for manager |
| Create | `tests/test_knowledge_migration.py` | Tests for manifest migration |
| Create | `tests/test_tools_knowledge.py` | Tests for MCP tools |
| Modify | `src/comfy_mcp/install/install_graph.py` | Add disk cache load/save, atomic snapshot swap |
| Modify | `src/comfy_mcp/docs/store.py` | Migrate manifest to state.json pattern |
| Modify | `src/comfy_mcp/templates/index.py` | Migrate manifest to state.json pattern |
| Modify | `src/comfy_mcp/server.py` | Add KnowledgeManager to lifespan, background refresh, replace knowledge/status resource |
| Modify | `src/comfy_mcp/tool_registry.py` | Add knowledge import |
| Modify | `tests/conftest.py` | Add knowledge_manager to mock_ctx |
| Modify | `README.md` | Update to 87 tools, 10 resources |

---

## Chunk 1: KnowledgeStore pattern + Config

### Task 1: KnowledgeStore protocol

**Files:**
- Create: `src/comfy_mcp/knowledge/__init__.py`
- Create: `src/comfy_mcp/knowledge/store.py`

- [ ] **Step 1: Create package init**

```python
# src/comfy_mcp/knowledge/__init__.py
```

- [ ] **Step 2: Create KnowledgeStore protocol**

```python
# src/comfy_mcp/knowledge/store.py
"""KnowledgeStore — protocol for subsystems that cache data to ~/.comfypilot/.

This is a duck-typed interface, not a base class. Each subsystem implements
these methods independently. The Protocol class is for type checking only.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class KnowledgeStore(Protocol):
    """Interface that cacheable subsystems implement."""

    def is_stale(self, max_age: float = 300) -> bool:
        """Check if cached data is missing or older than max_age seconds."""
        ...

    def content_hash(self) -> str:
        """SHA-256 prefix of cached content for change detection."""
        ...

    def summary(self) -> dict[str, Any]:
        """Return compact status summary."""
        ...

    def clear(self) -> None:
        """Remove all cached data."""
        ...


def atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically (write to temp, then rename).

    Prevents corruption from concurrent writes or crashes mid-write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    closed = False
    try:
        os.write(fd, content.encode())
        os.close(fd)
        closed = True
        # On Windows, need to remove target first
        if path.exists():
            path.unlink()
        os.rename(tmp_path, str(path))
    except Exception:
        if not closed:
            os.close(fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
```

- [ ] **Step 3: Write tests for KnowledgeStore protocol and atomic_write**

```python
# tests/test_knowledge_store.py
"""Tests for KnowledgeStore protocol and atomic_write utility."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


class TestAtomicWrite:
    def test_happy_path_writes_file(self, tmp_path):
        from comfy_mcp.knowledge.store import atomic_write
        target = tmp_path / "test.json"
        atomic_write(target, '{"hello": "world"}')
        assert target.exists()
        assert target.read_text() == '{"hello": "world"}'

    def test_creates_parent_directories(self, tmp_path):
        from comfy_mcp.knowledge.store import atomic_write
        target = tmp_path / "a" / "b" / "test.json"
        atomic_write(target, "content")
        assert target.exists()
        assert target.read_text() == "content"

    def test_cleanup_on_failure(self, tmp_path, monkeypatch):
        from comfy_mcp.knowledge.store import atomic_write
        import tempfile

        # Force os.rename to fail to simulate write failure
        original_rename = os.rename
        def failing_rename(src, dst):
            raise OSError("simulated rename failure")
        monkeypatch.setattr(os, "rename", failing_rename)

        target = tmp_path / "test.json"
        with pytest.raises(OSError, match="simulated rename failure"):
            atomic_write(target, "content")

        # Temp file should be cleaned up
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_overwrites_existing_file(self, tmp_path):
        from comfy_mcp.knowledge.store import atomic_write
        target = tmp_path / "test.json"
        target.write_text("old content")
        atomic_write(target, "new content")
        assert target.read_text() == "new content"


class TestKnowledgeStoreProtocol:
    def test_protocol_is_runtime_checkable(self):
        from comfy_mcp.knowledge.store import KnowledgeStore
        from typing import runtime_checkable, Protocol
        assert issubclass(KnowledgeStore, Protocol)

    def test_compliant_class_passes_isinstance(self):
        from comfy_mcp.knowledge.store import KnowledgeStore

        class FakeStore:
            def is_stale(self, max_age: float = 300) -> bool:
                return False
            def content_hash(self) -> str:
                return "abc123"
            def summary(self) -> dict:
                return {}
            def clear(self) -> None:
                pass

        assert isinstance(FakeStore(), KnowledgeStore)

    def test_non_compliant_class_fails_isinstance(self):
        from comfy_mcp.knowledge.store import KnowledgeStore

        class BadStore:
            pass

        assert not isinstance(BadStore(), KnowledgeStore)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_knowledge_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/knowledge/__init__.py src/comfy_mcp/knowledge/store.py tests/test_knowledge_store.py && git commit -m "feat(v0.6): add KnowledgeStore protocol and atomic_write utility with tests"
```

---

### Task 2: Config manager

**Files:**
- Create: `src/comfy_mcp/knowledge/config.py`
- Create: `tests/test_knowledge_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_knowledge_config.py
"""Tests for ConfigManager — persistent user preferences."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


class TestConfigDefaults:
    def test_returns_defaults_when_no_file(self, tmp_path):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        assert config.get("safety.vram_warn_pct") == 80
        assert config.get("safety.vram_block_pct") == 95
        assert config.get("cache.max_age_seconds") == 300

    def test_returns_none_for_unknown_key(self, tmp_path):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        assert config.get("nonexistent.key") is None

    def test_get_all_returns_full_config(self, tmp_path):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        full = config.get_all()
        assert "safety" in full
        assert "cache" in full


class TestConfigReadWrite:
    def test_set_and_get(self, tmp_path):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        config.set("safety.vram_warn_pct", 90)
        assert config.get("safety.vram_warn_pct") == 90

    def test_persists_to_disk(self, tmp_path):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        config.set("safety.vram_warn_pct", 90)
        # Reload from disk
        config2 = ConfigManager(config_dir=str(tmp_path))
        assert config2.get("safety.vram_warn_pct") == 90

    def test_creates_config_file(self, tmp_path):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        config.set("safety.vram_warn_pct", 90)
        assert (tmp_path / "config.json").exists()


class TestConfigEnvOverride:
    def test_env_var_overrides_file(self, tmp_path, monkeypatch):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        config.set("safety.vram_warn_pct", 90)
        monkeypatch.setenv("COMFY_VRAM_WARN_PCT", "75")
        # Env var should override
        assert config.get("safety.vram_warn_pct") == 75

    def test_env_var_for_output_dir(self, tmp_path, monkeypatch):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        monkeypatch.setenv("COMFY_OUTPUT_DIR", "/custom/output")
        assert config.get("output.default_dir") == "/custom/output"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_knowledge_config.py -v`
Expected: FAIL

- [ ] **Step 3: Implement ConfigManager**

```python
# src/comfy_mcp/knowledge/config.py
"""ConfigManager — persistent user preferences with env var override.

Reads/writes ~/.comfypilot/config.json. Environment variables always
take precedence over file-based config.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from comfy_mcp.knowledge.store import atomic_write

# Default configuration
DEFAULTS = {
    "safety": {
        "vram_warn_pct": 80,
        "vram_block_pct": 95,
        "max_queue_size": 10,
    },
    "output": {
        "default_dir": "~/comfypilot_output",
    },
    "cache": {
        "max_age_seconds": 300,
        "auto_refresh": True,
    },
}

# Map from dotted config key to environment variable name
ENV_MAP = {
    "safety.vram_warn_pct": "COMFY_VRAM_WARN_PCT",
    "safety.vram_block_pct": "COMFY_VRAM_BLOCK_PCT",
    "safety.max_queue_size": "COMFY_MAX_QUEUE_SIZE",
    "output.default_dir": "COMFY_OUTPUT_DIR",
    "cache.max_age_seconds": "COMFY_CACHE_MAX_AGE",
}


class ConfigManager:
    """Manages persistent configuration with env var override."""

    def __init__(self, config_dir: str | None = None):
        self._dir = Path(config_dir or Path.home() / ".comfypilot")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._config = self._load()

    def _config_path(self) -> Path:
        return self._dir / "config.json"

    def _load(self) -> dict[str, Any]:
        """Load config from disk, falling back to defaults."""
        import copy
        config = copy.deepcopy(DEFAULTS)
        path = self._config_path()
        if path.exists():
            try:
                disk = json.loads(path.read_text())
                # Deep merge disk values into defaults
                for section, values in disk.items():
                    if section in config and isinstance(values, dict):
                        config[section].update(values)
                    else:
                        config[section] = values
            except (json.JSONDecodeError, OSError):
                pass
        return config

    def _save(self) -> None:
        """Persist config to disk atomically."""
        atomic_write(self._config_path(), json.dumps(self._config, indent=2))

    def get(self, key: str) -> Any:
        """Get a config value by dotted key (e.g., 'safety.vram_warn_pct').

        Environment variables override file-based values.
        """
        # Check env override first
        env_name = ENV_MAP.get(key)
        if env_name:
            env_val = os.environ.get(env_name)
            if env_val is not None:
                # Try to cast to the same type as default
                default_val = self._get_from_dict(key)
                if isinstance(default_val, bool):
                    return env_val.lower() in ("true", "1", "yes")
                if isinstance(default_val, int):
                    try:
                        return int(env_val)
                    except ValueError:
                        pass
                if isinstance(default_val, float):
                    try:
                        return float(env_val)
                    except ValueError:
                        pass
                return env_val

        return self._get_from_dict(key)

    def _get_from_dict(self, key: str) -> Any:
        """Get value from in-memory config dict."""
        parts = key.split(".")
        current = self._config
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    def set(self, key: str, value: Any) -> None:
        """Set a config value by dotted key and persist to disk."""
        parts = key.split(".")
        current = self._config
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
        self._save()

    def get_all(self) -> dict[str, Any]:
        """Return the full config dict (file values, not env overrides)."""
        import copy
        return copy.deepcopy(self._config)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_knowledge_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/knowledge/config.py tests/test_knowledge_config.py && git commit -m "feat(v0.6): add ConfigManager with persistent config and env override"
```

---

## Chunk 2: KnowledgeManager + Install Graph disk cache

### Task 3: KnowledgeManager — unified state tracking

**Files:**
- Create: `src/comfy_mcp/knowledge/manager.py`
- Create: `tests/test_knowledge_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_knowledge_manager.py
"""Tests for KnowledgeManager — unified state tracking."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestKnowledgeManagerStatus:
    def test_status_aggregates_all_stores(self, tmp_path):
        from comfy_mcp.knowledge.manager import KnowledgeManager
        store1 = MagicMock()
        store1.is_stale = MagicMock(return_value=False)
        store1.content_hash = MagicMock(return_value="abc123")
        store1.summary = MagicMock(return_value={"count": 5})

        store2 = MagicMock()
        store2.is_stale = MagicMock(return_value=True)
        store2.content_hash = MagicMock(return_value="def456")
        store2.summary = MagicMock(return_value={"count": 3})

        mgr = KnowledgeManager({"docs": store1, "templates": store2}, state_dir=str(tmp_path))
        status = mgr.status()
        assert "docs" in status["stores"]
        assert "templates" in status["stores"]
        assert status["any_stale"] is True

    def test_status_with_no_stores(self, tmp_path):
        from comfy_mcp.knowledge.manager import KnowledgeManager
        mgr = KnowledgeManager({}, state_dir=str(tmp_path))
        status = mgr.status()
        assert status["any_stale"] is False


class TestKnowledgeManagerRefresh:
    @pytest.mark.asyncio
    async def test_refresh_all_calls_each_store(self, tmp_path):
        from comfy_mcp.knowledge.manager import KnowledgeManager
        store1 = AsyncMock()
        store1.is_stale = MagicMock(return_value=True)
        store1.content_hash = MagicMock(return_value="abc")
        store1.summary = MagicMock(return_value={})

        store2 = AsyncMock()
        store2.is_stale = MagicMock(return_value=True)
        store2.content_hash = MagicMock(return_value="def")
        store2.summary = MagicMock(return_value={})

        mgr = KnowledgeManager({"docs": store1, "templates": store2}, state_dir=str(tmp_path))
        await mgr.refresh_all()
        store1.refresh.assert_awaited_once()
        store2.refresh.assert_awaited_once()


class TestKnowledgeManagerClear:
    def test_clear_specific_store(self, tmp_path):
        from comfy_mcp.knowledge.manager import KnowledgeManager
        store1 = MagicMock()
        store1.is_stale = MagicMock(return_value=False)
        store1.content_hash = MagicMock(return_value="abc")
        store1.summary = MagicMock(return_value={})
        store1.clear = MagicMock()

        mgr = KnowledgeManager({"docs": store1}, state_dir=str(tmp_path))
        mgr.clear("docs")
        store1.clear.assert_called_once()

    def test_clear_all_stores(self, tmp_path):
        from comfy_mcp.knowledge.manager import KnowledgeManager
        store1 = MagicMock()
        store1.is_stale = MagicMock(return_value=False)
        store1.content_hash = MagicMock(return_value="abc")
        store1.summary = MagicMock(return_value={})
        store1.clear = MagicMock()

        store2 = MagicMock()
        store2.is_stale = MagicMock(return_value=False)
        store2.content_hash = MagicMock(return_value="def")
        store2.summary = MagicMock(return_value={})
        store2.clear = MagicMock()

        mgr = KnowledgeManager({"docs": store1, "templates": store2}, state_dir=str(tmp_path))
        mgr.clear("all")
        store1.clear.assert_called_once()
        store2.clear.assert_called_once()


class TestStatePersistence:
    def test_save_and_load_state(self, tmp_path):
        from comfy_mcp.knowledge.manager import KnowledgeManager
        store1 = MagicMock()
        store1.is_stale = MagicMock(return_value=False)
        store1.content_hash = MagicMock(return_value="abc123")
        store1.summary = MagicMock(return_value={"count": 5})

        mgr = KnowledgeManager({"docs": store1}, state_dir=str(tmp_path))
        mgr.save_state()
        assert (tmp_path / "state.json").exists()

        state = json.loads((tmp_path / "state.json").read_text())
        assert "docs" in state["stores"]

    def test_corrupted_state_triggers_rebuild(self, tmp_path):
        from comfy_mcp.knowledge.manager import KnowledgeManager
        # Write corrupted state
        (tmp_path / "state.json").write_text("{{invalid json")

        store1 = MagicMock()
        store1.is_stale = MagicMock(return_value=True)
        store1.content_hash = MagicMock(return_value="abc")
        store1.summary = MagicMock(return_value={})

        mgr = KnowledgeManager({"docs": store1}, state_dir=str(tmp_path))
        status = mgr.status()
        # Should not crash, stores report as stale
        assert status["any_stale"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_knowledge_manager.py -v`
Expected: FAIL

- [ ] **Step 3: Implement KnowledgeManager**

```python
# src/comfy_mcp/knowledge/manager.py
"""KnowledgeManager — unified state tracking across all knowledge stores.

Manages state.json for cross-subsystem staleness tracking and provides
orchestration for refresh-all and clear-cache operations.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from comfy_mcp.knowledge.store import atomic_write

logger = logging.getLogger("comfypilot.knowledge")


class KnowledgeManager:
    """Orchestrates multiple KnowledgeStore instances."""

    def __init__(self, stores: dict[str, Any], state_dir: str | None = None):
        self._stores = stores
        self._dir = Path(state_dir or Path.home() / ".comfypilot")
        self._dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self) -> Path:
        return self._dir / "state.json"

    def status(self) -> dict[str, Any]:
        """Aggregate status from all registered stores."""
        stores_status = {}
        any_stale = False

        for name, store in self._stores.items():
            try:
                stale = store.is_stale()
                stores_status[name] = {
                    "stale": stale,
                    "content_hash": store.content_hash(),
                    "summary": store.summary(),
                }
                if stale:
                    any_stale = True
            except Exception as exc:
                stores_status[name] = {"error": str(exc), "stale": True}
                any_stale = True

        return {
            "store_count": len(self._stores),
            "any_stale": any_stale,
            "stores": stores_status,
            "checked_at": time.time(),
        }

    async def refresh_all(self) -> dict[str, Any]:
        """Refresh all registered stores."""
        results = {}
        for name, store in self._stores.items():
            try:
                await store.refresh()
                results[name] = {"status": "ok"}
            except Exception as exc:
                logger.warning("Failed to refresh %s: %s", name, exc)
                results[name] = {"status": "error", "error": str(exc)}

        self.save_state()
        return {"refreshed": results}

    def clear(self, subsystem: str = "all") -> dict[str, Any]:
        """Clear cached data for one or all subsystems."""
        cleared = []
        if subsystem == "all":
            for name, store in self._stores.items():
                store.clear()
                cleared.append(name)
        elif subsystem in self._stores:
            self._stores[subsystem].clear()
            cleared.append(subsystem)
        else:
            return {"error": f"Unknown subsystem: {subsystem}", "available": list(self._stores.keys())}

        self.save_state()
        return {"cleared": cleared}

    def save_state(self) -> None:
        """Persist unified state to state.json."""
        state = {
            "saved_at": time.time(),
            "stores": {},
        }
        for name, store in self._stores.items():
            try:
                state["stores"][name] = {
                    "content_hash": store.content_hash(),
                    "stale": store.is_stale(),
                }
            except Exception as exc:
                state["stores"][name] = {"error": str(exc)}

        atomic_write(self._state_path(), json.dumps(state, indent=2))

    def load_state(self) -> dict[str, Any] | None:
        """Load state from disk. Returns None if missing or corrupted."""
        path = self._state_path()
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("state.json corrupted, treating all stores as stale")
            return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_knowledge_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/knowledge/manager.py tests/test_knowledge_manager.py && git commit -m "feat(v0.6): add KnowledgeManager with unified state tracking"
```

---

### Task 4: Install graph disk cache

**Files:**
- Modify: `src/comfy_mcp/install/install_graph.py`
- Add tests to: `tests/test_install_graph.py`

- [ ] **Step 1: Write failing tests for disk cache**

Add to `tests/test_install_graph.py`:

```python
class TestInstallGraphDiskCache:
    @pytest.mark.asyncio
    async def test_save_to_disk(self, tmp_path, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client, cache_dir=str(tmp_path))
        await graph.refresh()
        graph.save_to_disk()
        assert (tmp_path / "install_graph.json").exists()

    @pytest.mark.asyncio
    async def test_load_from_disk(self, tmp_path, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client, cache_dir=str(tmp_path))
        await graph.refresh()
        graph.save_to_disk()

        graph2 = InstallGraph(mock_client, cache_dir=str(tmp_path))
        loaded = graph2.load_from_disk()
        assert loaded is True
        assert graph2.snapshot is not None
        assert graph2.snapshot["node_count"] == graph.snapshot["node_count"]

    def test_load_from_disk_returns_false_when_no_cache(self, tmp_path, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client, cache_dir=str(tmp_path))
        loaded = graph.load_from_disk()
        assert loaded is False

    def test_load_from_disk_handles_corruption(self, tmp_path, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        (tmp_path / "install_graph.json").write_text("{{invalid")
        graph = InstallGraph(mock_client, cache_dir=str(tmp_path))
        loaded = graph.load_from_disk()
        assert loaded is False


class TestInstallGraphProtocolCompliance:
    """Verify InstallGraph satisfies the KnowledgeStore protocol."""

    def test_isinstance_check(self, mock_client, tmp_path):
        from comfy_mcp.install.install_graph import InstallGraph
        from comfy_mcp.knowledge.store import KnowledgeStore
        graph = InstallGraph(mock_client, cache_dir=str(tmp_path))
        assert isinstance(graph, KnowledgeStore)

    def test_content_hash_returns_string(self, mock_client, tmp_path):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client, cache_dir=str(tmp_path))
        h = graph.content_hash()
        assert isinstance(h, str) and len(h) > 0

    def test_summary_returns_dict(self, mock_client, tmp_path):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client, cache_dir=str(tmp_path))
        s = graph.summary()
        assert isinstance(s, dict)

    def test_clear_resets_state(self, mock_client, tmp_path):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client, cache_dir=str(tmp_path))
        graph.clear()
        assert graph._snapshot is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_install_graph.py::TestInstallGraphDiskCache -v`
Expected: FAIL

- [ ] **Step 3: Add disk cache methods to InstallGraph**

Add to `InstallGraph.__init__`:
```python
    def __init__(self, client, cache_dir: str | None = None):
        self._client = client
        self._snapshot: dict[str, Any] | None = None
        self._hashes: dict[str, str] = {}
        self._cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".comfypilot" / "cache"
```

Add methods:
```python
    def save_to_disk(self) -> None:
        """Persist current snapshot to disk cache."""
        if not self._snapshot:
            return
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        # Convert set to sorted list for JSON serialization
        serializable = dict(self._snapshot)
        serializable["node_classes"] = sorted(serializable["node_classes"])
        path = self._cache_dir / "install_graph.json"
        from comfy_mcp.knowledge.store import atomic_write
        atomic_write(path, json.dumps(serializable, indent=2))

    def load_from_disk(self) -> bool:
        """Load snapshot from disk cache. Returns True if loaded successfully."""
        path = self._cache_dir / "install_graph.json"
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text())
            # Restore node_classes as set
            data["node_classes"] = set(data.get("node_classes", []))
            self._snapshot = data
            self._hashes = data.get("hashes", {})
            return True
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            logger.warning("Failed to load install graph cache: %s", exc)
            return False
```

**Note:** Do NOT add `save_to_disk()` inside `refresh()`. Auto-saving in refresh would cause existing tests to write to the real home directory. Instead, save explicitly in the server.py lifespan after refresh completes (see Task 6).

- [ ] **Step 4: Retrofit KnowledgeStore protocol compliance on InstallGraph**

Add the following methods to InstallGraph so it satisfies the `KnowledgeStore` protocol (the KnowledgeManager calls `store.content_hash()`, `store.summary()`, and `store.clear()`):

```python
    def content_hash(self) -> str:
        """SHA-256 prefix of the combined hashes dict for change detection."""
        import hashlib
        raw = json.dumps(self._hashes, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    def summary(self) -> dict[str, Any]:
        """Return compact status summary for KnowledgeManager."""
        if not self._snapshot:
            return {"status": "empty", "node_count": 0}
        return {
            "status": "loaded",
            "node_count": self._snapshot.get("node_count", 0),
            "model_count": self._snapshot.get("model_count", 0),
        }

    def clear(self) -> None:
        """Remove all cached data (in-memory and on disk)."""
        self._snapshot = None
        self._hashes = {}
        path = self._cache_dir / "install_graph.json"
        if path.exists():
            path.unlink()
```

Verify protocol compliance with:
```python
from comfy_mcp.knowledge.store import KnowledgeStore
assert isinstance(install_graph, KnowledgeStore)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_install_graph.py -v`
Expected: PASS (all existing + new tests)

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/install/install_graph.py tests/test_install_graph.py && git commit -m "feat(v0.6): add install graph disk cache with atomic writes"
```

---

### Task 4b: Manifest migration (manifest.json → state.json)

**Files:**
- Create: `src/comfy_mcp/knowledge/migration.py`
- Create: `tests/test_knowledge_migration.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_knowledge_migration.py
"""Tests for manifest.json → state.json migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestManifestMigration:
    def test_migrates_manifest_to_state(self, tmp_path):
        from comfy_mcp.knowledge.migration import migrate_manifest_to_state
        manifest = {"version": 1, "docs": {"count": 5}}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        migrate_manifest_to_state(tmp_path)

        assert (tmp_path / "state.json").exists()
        state = json.loads((tmp_path / "state.json").read_text())
        assert "docs" in state or "migrated_from" in state

    def test_creates_backup_of_manifest(self, tmp_path):
        from comfy_mcp.knowledge.migration import migrate_manifest_to_state
        manifest = {"version": 1, "docs": {"count": 5}}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        migrate_manifest_to_state(tmp_path)

        assert (tmp_path / "manifest.json.bak").exists()
        backup = json.loads((tmp_path / "manifest.json.bak").read_text())
        assert backup == manifest

    def test_idempotent_rerun_does_not_overwrite(self, tmp_path):
        from comfy_mcp.knowledge.migration import migrate_manifest_to_state
        manifest = {"version": 1, "docs": {"count": 5}}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        migrate_manifest_to_state(tmp_path)
        first_state = (tmp_path / "state.json").read_text()

        # Run again — should be idempotent
        migrate_manifest_to_state(tmp_path)
        second_state = (tmp_path / "state.json").read_text()
        assert first_state == second_state

    def test_noop_when_no_manifest(self, tmp_path):
        from comfy_mcp.knowledge.migration import migrate_manifest_to_state
        migrate_manifest_to_state(tmp_path)
        # No crash, no state.json created from nothing
        assert not (tmp_path / "state.json").exists()

    def test_noop_when_state_already_exists(self, tmp_path):
        from comfy_mcp.knowledge.migration import migrate_manifest_to_state
        (tmp_path / "manifest.json").write_text('{"old": true}')
        (tmp_path / "state.json").write_text('{"already": "migrated"}')

        migrate_manifest_to_state(tmp_path)
        state = json.loads((tmp_path / "state.json").read_text())
        assert state == {"already": "migrated"}  # Not overwritten
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_knowledge_migration.py -v`
Expected: FAIL

- [ ] **Step 3: Implement migration logic**

```python
# src/comfy_mcp/knowledge/migration.py
"""Migration helper — manifest.json → state.json with .bak backup.

Handles idempotent migration: skips if state.json already exists,
creates .bak backup of manifest.json before migrating.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from comfy_mcp.knowledge.store import atomic_write

logger = logging.getLogger("comfypilot.knowledge.migration")


def migrate_manifest_to_state(data_dir: Path) -> bool:
    """Migrate manifest.json to state.json if needed.

    Returns True if migration was performed, False if skipped.
    """
    data_dir = Path(data_dir)
    manifest_path = data_dir / "manifest.json"
    state_path = data_dir / "state.json"
    backup_path = data_dir / "manifest.json.bak"

    # Skip if no manifest to migrate
    if not manifest_path.exists():
        return False

    # Skip if already migrated (state.json exists)
    if state_path.exists():
        logger.info("state.json already exists, skipping migration")
        return False

    try:
        manifest_data = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot read manifest.json for migration: %s", exc)
        return False

    # Create backup
    shutil.copy2(str(manifest_path), str(backup_path))

    # Build state from manifest
    state = {
        "migrated_from": "manifest.json",
        **manifest_data,
    }

    atomic_write(state_path, json.dumps(state, indent=2))
    logger.info("Migrated manifest.json → state.json (backup at manifest.json.bak)")
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_knowledge_migration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/knowledge/migration.py tests/test_knowledge_migration.py && git commit -m "feat(v0.6): add manifest.json → state.json migration with backup and idempotency"
```

---

## Chunk 3: MCP Tools + Integration

### Task 5: MCP tools for knowledge

**Files:**
- Create: `src/comfy_mcp/tools/knowledge.py`
- Create: `tests/test_tools_knowledge.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools_knowledge.py
"""Tests for knowledge MCP tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def knowledge_ctx(mock_ctx):
    mgr_mock = MagicMock()
    mgr_mock.status = MagicMock(return_value={"store_count": 2, "any_stale": False, "stores": {}})
    mgr_mock.refresh_all = AsyncMock(return_value={"refreshed": {}})
    mgr_mock.clear = MagicMock(return_value={"cleared": ["docs"]})

    config_mock = MagicMock()
    config_mock.get = MagicMock(return_value=80)
    config_mock.get_all = MagicMock(return_value={"safety": {"vram_warn_pct": 80}})
    config_mock.set = MagicMock()

    mock_ctx.request_context.lifespan_context["knowledge_manager"] = mgr_mock
    mock_ctx.request_context.lifespan_context["config_manager"] = config_mock
    return mock_ctx


class TestKnowledgeStatus:
    @pytest.mark.asyncio
    async def test_returns_status(self, knowledge_ctx):
        from comfy_mcp.tools.knowledge import comfy_knowledge_status
        result = json.loads(await comfy_knowledge_status(ctx=knowledge_ctx))
        assert "store_count" in result


class TestRefreshAll:
    @pytest.mark.asyncio
    async def test_refresh_all(self, knowledge_ctx):
        from comfy_mcp.tools.knowledge import comfy_refresh_all
        result = json.loads(await comfy_refresh_all(ctx=knowledge_ctx))
        assert "refreshed" in result


class TestClearCache:
    @pytest.mark.asyncio
    async def test_clear_specific(self, knowledge_ctx):
        from comfy_mcp.tools.knowledge import comfy_clear_cache
        result = json.loads(await comfy_clear_cache(subsystem="docs", ctx=knowledge_ctx))
        assert "cleared" in result


class TestGetConfig:
    @pytest.mark.asyncio
    async def test_get_specific_key(self, knowledge_ctx):
        from comfy_mcp.tools.knowledge import comfy_get_config
        result = json.loads(await comfy_get_config(key="safety.vram_warn_pct", ctx=knowledge_ctx))
        assert "value" in result

    @pytest.mark.asyncio
    async def test_get_all(self, knowledge_ctx):
        from comfy_mcp.tools.knowledge import comfy_get_config
        result = json.loads(await comfy_get_config(ctx=knowledge_ctx))
        assert "config" in result


class TestSetConfig:
    @pytest.mark.asyncio
    async def test_set_value(self, knowledge_ctx):
        from comfy_mcp.tools.knowledge import comfy_set_config
        result = json.loads(await comfy_set_config(key="safety.vram_warn_pct", value=90, ctx=knowledge_ctx))
        assert result["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_tools_knowledge.py -v`
Expected: FAIL

- [ ] **Step 3: Implement MCP tools**

```python
# src/comfy_mcp/tools/knowledge.py
"""Knowledge tools — MCP surface for unified knowledge management."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _manager(ctx: Context):
    return ctx.request_context.lifespan_context["knowledge_manager"]


def _config(ctx: Context):
    return ctx.request_context.lifespan_context["config_manager"]


@mcp.tool(
    annotations={
        "title": "Knowledge Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_knowledge_status(ctx: Context = None) -> str:
    """Unified view of all knowledge subsystem staleness, hashes, and cache sizes."""
    mgr = _manager(ctx)
    return json.dumps(mgr.status(), indent=2)


@mcp.tool(
    annotations={
        "title": "Refresh All Knowledge",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_refresh_all(ctx: Context = None) -> str:
    """Refresh all knowledge stores (docs, templates, install graph)."""
    mgr = _manager(ctx)
    result = await mgr.refresh_all()
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Clear Cache",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_clear_cache(subsystem: str = "all", ctx: Context = None) -> str:
    """Clear cached data for a specific subsystem or all caches.

    Args:
        subsystem: Which cache to clear ('docs', 'templates', 'install_graph', or 'all').
    """
    mgr = _manager(ctx)
    result = mgr.clear(subsystem)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Config",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_config(key: str | None = None, ctx: Context = None) -> str:
    """Read persisted user preferences.

    Args:
        key: Dotted config key (e.g., 'safety.vram_warn_pct'). If omitted, returns all config.
    """
    config = _config(ctx)
    if key:
        return json.dumps({"key": key, "value": config.get(key)}, indent=2)
    return json.dumps({"config": config.get_all()}, indent=2)


@mcp.tool(
    annotations={
        "title": "Set Config",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_set_config(key: str, value: Any, ctx: Context = None) -> str:
    """Write a persisted user preference.

    Args:
        key: Dotted config key (e.g., 'safety.vram_warn_pct').
        value: Value to set.
    """
    config = _config(ctx)
    config.set(key, value)
    return json.dumps({"status": "ok", "key": key, "value": value}, indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest tests/test_tools_knowledge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/tools/knowledge.py tests/test_tools_knowledge.py && git commit -m "feat(v0.6): add 5 MCP tools for knowledge management"
```

---

### Task 6: Server integration + README

**Files:**
- Modify: `src/comfy_mcp/server.py`
- Modify: `src/comfy_mcp/tool_registry.py`
- Modify: `tests/conftest.py`
- Modify: `README.md`

- [ ] **Step 1: Add to server.py lifespan**

After existing subsystem initialization, add:

```python
    from comfy_mcp.knowledge.config import ConfigManager
    from comfy_mcp.knowledge.manager import KnowledgeManager

    config_manager = ConfigManager()

    global _shared_knowledge_manager

    import asyncio

    # Try loading install graph from disk cache for faster startup
    if install_graph.load_from_disk() and not install_graph.is_stale():
        logger.info("Loaded install graph from disk cache")
    elif install_graph.load_from_disk():
        # Cache exists but is stale — use it immediately, refresh in background
        logger.info("Install graph cache stale, scheduling background refresh")
        async def _bg_refresh():
            try:
                await install_graph.refresh()
                install_graph.save_to_disk()
                logger.info("Background install graph refresh complete")
            except Exception as exc:
                logger.warning("Background refresh failed: %s", exc)
        asyncio.create_task(_bg_refresh())
    else:
        # No cache at all — must block on first refresh
        await install_graph.refresh()
        install_graph.save_to_disk()  # Explicit save after refresh (not inside refresh())
    _shared_install_graph = install_graph

    # Build stores dict dynamically — only include subsystems that are available
    stores = {"install_graph": install_graph}
    if "docs_store" in dir() and docs_store is not None:
        stores["docs"] = docs_store
    if "template_index" in dir() and template_index is not None:
        stores["templates"] = template_index

    knowledge_manager = KnowledgeManager(stores)
```

After creating the KnowledgeManager, set the global and add finally cleanup:
```python
    _shared_knowledge_manager = knowledge_manager

    try:
        yield {
            ...
            "knowledge_manager": knowledge_manager,
            "config_manager": config_manager,
        }
    finally:
        _shared_knowledge_manager = None
```

Replace the `comfy://knowledge/status` resource with `comfy://knowledge/full`:
```python
@mcp.resource("comfy://knowledge/full")
async def knowledge_full_resource() -> str:
    """Complete knowledge status across all subsystems."""
    if _shared_knowledge_manager is None:
        return json.dumps({"status": "not_initialized"})
    return json.dumps(_shared_knowledge_manager.status(), indent=2)
```

Add module-level global: `_shared_knowledge_manager = None`

- [ ] **Step 2: Register in tool_registry.py**

```python
from comfy_mcp.tools import knowledge     # noqa: F401 -- v0.6 Knowledge Management
```

- [ ] **Step 3: Update conftest.py**

Add to `lifespan_context`:
```python
        "knowledge_manager": MagicMock(),
        "config_manager": MagicMock(),
```

- [ ] **Step 4: Update README.md**

- Version: `v0.6.0`
- Tool count: `87-tool runtime surface`
- Add Knowledge Management section (### 17)
- Resources: 10 (replace `comfy://knowledge/status` with `comfy://knowledge/full`)

- [ ] **Step 5: Run full test suite**

Run: `cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && uv run pytest -v`
Expected: ALL pass

- [ ] **Step 6: Commit**

```bash
cd C:/Users/dr5090/AppData/Local/Temp/ComfyPilot && git add src/comfy_mcp/server.py src/comfy_mcp/tool_registry.py tests/conftest.py README.md && git commit -m "feat: v0.6.0 — Persistent Knowledge (87 tools, 10 resources)"
```

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

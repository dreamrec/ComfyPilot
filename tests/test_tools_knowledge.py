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

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
    fetcher_mock.fetch_embedded_doc = AsyncMock(side_effect=lambda cn: "# KSampler\nFresh doc." if cn == "KSampler" else None)
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
        from comfy_mcp.tools.docs import comfy_refresh_docs
        result = json.loads(await comfy_refresh_docs(ctx=docs_ctx))
        assert result["status"] == "ok"
        assert result["llms_cached"] is True

    @pytest.mark.asyncio
    async def test_refresh_partial_on_fetch_failure(self, docs_ctx):
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

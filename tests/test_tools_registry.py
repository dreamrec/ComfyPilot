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
        assert result["nodes"][0]["package"] is None
        assert result["unresolved"] == 1


class TestCheckCompatibility:
    @pytest.mark.asyncio
    async def test_compatible_package(self, registry_ctx):
        from comfy_mcp.tools.registry import comfy_check_compatibility
        result = json.loads(await comfy_check_compatibility(package_id="pkg-a", ctx=registry_ctx))
        assert result["compatible"] is True
        assert result["package_id"] == "pkg-a"
        assert "install_cmd" in result

    @pytest.mark.asyncio
    async def test_not_found_package(self, registry_ctx):
        from comfy_mcp.tools.registry import comfy_check_compatibility
        registry_ctx.request_context.lifespan_context["registry_client"].get_node = AsyncMock(return_value=None)
        result = json.loads(await comfy_check_compatibility(package_id="nonexistent", ctx=registry_ctx))
        assert "error" in result


class TestRegistryStatus:
    @pytest.mark.asyncio
    async def test_status(self, registry_ctx):
        from comfy_mcp.tools.registry import comfy_registry_status
        result = json.loads(await comfy_registry_status(ctx=registry_ctx))
        assert "total_entries" in result


class TestRegistryStatusResource:
    @pytest.mark.asyncio
    async def test_resource_returns_summary(self):
        import comfy_mcp.server as srv
        mock_index = MagicMock()
        mock_index.summary = MagicMock(return_value={
            "total_entries": 10, "positive_entries": 8, "negative_entries": 2,
        })
        srv._shared_registry_index = mock_index
        try:
            result = json.loads(await srv.registry_status_resource())
            assert result["total_entries"] == 10
            assert result["positive_entries"] == 8
        finally:
            srv._shared_registry_index = None

    @pytest.mark.asyncio
    async def test_resource_not_initialized(self):
        import comfy_mcp.server as srv
        srv._shared_registry_index = None
        result = json.loads(await srv.registry_status_resource())
        assert result["status"] == "not_initialized"

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
        {"id": "official_txt2img", "name": "txt2img_basic", "category": "text-to-image", "source": "official",
         "tags": ["txt2img", "basic", "generation"],
         "required_nodes": ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler", "EmptyLatentImage", "VAEDecode", "SaveImage"],
         "required_models": {"checkpoints": 1}},
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


class TestTemplateIndexResource:
    @pytest.mark.asyncio
    async def test_resource_returns_expected_json(self):
        """Verify the comfy://templates/index resource returns valid JSON with expected keys."""
        import comfy_mcp.server as server_module
        from comfy_mcp.server import templates_index_resource

        # Simulate initialized state
        mock_index = MagicMock()
        mock_index.summary = MagicMock(return_value={
            "template_count": 5,
            "categories": ["text-to-image", "controlnet"],
            "source_counts": {"official": 2, "builtin": 3},
            "stale": False,
            "last_updated": 1710000000.0,
            "content_hash": "abc123",
        })
        original = getattr(server_module, "_shared_template_index", None)
        server_module._shared_template_index = mock_index
        try:
            result = json.loads(await templates_index_resource())
            assert "template_count" in result
            assert result["template_count"] == 5
            assert "categories" in result
            assert isinstance(result["categories"], list)
        finally:
            server_module._shared_template_index = original

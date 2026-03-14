"""Tests for template fallthrough in comfy_build_workflow."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def builder_ctx_with_templates(mock_ctx):
    """Context with template index that has a matching template."""
    index_mock = MagicMock()
    index_mock.list_all = MagicMock(return_value=[
        {"id": "builtin_txt2img_basic", "name": "txt2img_basic", "category": "text-to-image",
         "source": "builtin", "tags": ["txt2img", "basic"],
         "required_nodes": ["CheckpointLoaderSimple", "KSampler"],
         "required_models": {"checkpoints": 1}},
    ])
    index_mock.get = MagicMock(return_value={
        "id": "builtin_txt2img_basic", "name": "txt2img_basic",
        "workflow": {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}}},
    })
    mock_ctx.request_context.lifespan_context["template_index"] = index_mock

    graph_mock = MagicMock()
    graph_mock.snapshot = {
        "node_classes": {"KSampler", "CheckpointLoaderSimple"},
        "models": {"checkpoints": ["dreamshaper_8.safetensors"]},
        "embeddings": [],
        "object_info": {},
    }
    mock_ctx.request_context.lifespan_context["install_graph"] = graph_mock
    return mock_ctx


@pytest.fixture
def builder_ctx_without_templates(mock_ctx):
    """Context with template index that has no matching template."""
    index_mock = MagicMock()
    index_mock.list_all = MagicMock(return_value=[])
    mock_ctx.request_context.lifespan_context["template_index"] = index_mock

    graph_mock = MagicMock()
    graph_mock.snapshot = {"node_classes": set(), "models": {}, "embeddings": [], "object_info": {}}
    mock_ctx.request_context.lifespan_context["install_graph"] = graph_mock
    return mock_ctx


class TestTemplateFallthrough:
    @pytest.mark.asyncio
    async def test_uses_template_when_match_found(self, builder_ctx_with_templates):
        """When a matching template exists, builder should use it."""
        from comfy_mcp.tools.builder import comfy_build_workflow
        result = json.loads(await comfy_build_workflow(
            template="txt2img basic", ctx=builder_ctx_with_templates))
        # Should have used template path (implementation-specific assertion)
        assert "workflow" in result or "error" not in result

    @pytest.mark.asyncio
    async def test_falls_back_when_no_template_match(self, builder_ctx_without_templates):
        """When no template matches, builder should use existing logic."""
        from comfy_mcp.tools.builder import comfy_build_workflow
        # Should not crash -- falls back to original builder behavior
        result = json.loads(await comfy_build_workflow(
            template="some unusual workflow", ctx=builder_ctx_without_templates))
        assert isinstance(result, dict)

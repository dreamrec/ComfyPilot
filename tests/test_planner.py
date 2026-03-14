"""Tests for workflow planner tools and resources."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.ecosystem import EcosystemRegistry, ModelAwarenessScanner
from comfy_mcp.planner import WorkflowPlanner


@pytest.fixture
def planner_ctx(mock_ctx):
    registry = EcosystemRegistry()
    scanner = ModelAwarenessScanner(registry)
    planner = WorkflowPlanner(registry, scanner)

    mock_ctx.request_context.lifespan_context["ecosystem_registry"] = registry
    mock_ctx.request_context.lifespan_context["model_awareness_scanner"] = scanner
    mock_ctx.request_context.lifespan_context["workflow_planner"] = planner
    mock_ctx.request_context.lifespan_context["template_index"] = MagicMock()
    mock_ctx.request_context.lifespan_context["template_index"].list_all = MagicMock(return_value=[
        {
            "id": "official_image_qwen_image",
            "name": "image_qwen_image",
            "title": "Qwen-Image Starter",
            "category": "text-to-image",
            "source": "official",
            "description": "Official starter workflow for Qwen-Image.",
            "tags": ["Text to Image", "Image"],
            "model_names": ["Qwen-Image"],
            "tutorial_url": "https://docs.comfy.org/tutorials/image/qwen/qwen-image",
            "workflow_file": "image_qwen_image.json",
            "workflow_url": "https://raw.githubusercontent.com/Comfy-Org/workflow_templates/refs/heads/main/templates/image_qwen_image.json",
            "open_source": True,
            "usage": 120,
            "distribution_targets": ["local"],
            "supports_instantiation": False,
        }
    ])
    mock_ctx.request_context.lifespan_context["template_index"].hydrate_template = AsyncMock(return_value={
        "id": "official_image_qwen_image",
        "name": "image_qwen_image",
        "workflow_format": "comfyui-ui",
        "workflow_summary": {"node_count": 12, "node_types": ["SaveImage", "QwenNode"]},
        "workflow_source": "remote",
        "translation_status": "translated",
        "translation_assessment": {
            "confidence": "high",
            "score": 0.86,
            "ready_for_queue": True,
            "recommended_action": "queue-or-instantiate",
        },
    })
    mock_ctx.request_context.lifespan_context["install_graph"] = MagicMock(snapshot={
        "models": {
            "checkpoints": ["ponyDiffusionV6XL.safetensors", "flux1-dev.safetensors"],
            "diffusion_models": ["qwen_image_fp8.safetensors"],
            "text_encoders": ["qwen_2.5_vl_7b_fp8_scaled.safetensors"],
            "vae": ["qwen_image_vae.safetensors"],
        },
        "node_classes": {"GoogleNanoBananaNode"},
    })
    return mock_ctx


class TestRecommendWorkflowTool:
    @pytest.mark.asyncio
    async def test_recommend_workflow_prefers_modern_local_family(self, planner_ctx):
        from comfy_mcp.tools.planner import comfy_recommend_workflow

        result = json.loads(await comfy_recommend_workflow(task="t2i", ctx=planner_ctx))
        assert result["task"] == "t2i"
        assert result["default_recommendation"]["family"] == "qwen-image"
        assert result["default_recommendation"]["runtime"] == "local-native"

    @pytest.mark.asyncio
    async def test_recommend_workflow_can_include_provider(self, planner_ctx):
        from comfy_mcp.tools.planner import comfy_recommend_workflow

        result = json.loads(await comfy_recommend_workflow(task="t2i", allow_providers=True, ctx=planner_ctx))
        strategies = result["recommendations"]
        assert any(item.get("provider") == "google" for item in strategies)

    @pytest.mark.asyncio
    async def test_recommend_workflow_includes_official_template_context(self, planner_ctx):
        from comfy_mcp.tools.planner import comfy_recommend_workflow

        result = json.loads(await comfy_recommend_workflow(task="t2i", ctx=planner_ctx))
        templates = [item for item in result["recommendations"] if item.get("type") == "template"]
        assert templates
        assert templates[0]["template_id"] == "official_image_qwen_image"
        assert templates[0]["tutorial_url"] == "https://docs.comfy.org/tutorials/image/qwen/qwen-image"
        assert templates[0]["actionability"] == "translatable-template"
        assert templates[0]["next_step_tool"] == "comfy_instantiate_template"
        assert templates[0]["translation_assessment"]["confidence"] == "high"

    @pytest.mark.asyncio
    async def test_recommend_workflow_uses_get_template_when_translation_is_unscored(self, planner_ctx):
        from comfy_mcp.tools.planner import comfy_recommend_workflow

        planner_ctx.request_context.lifespan_context["template_index"].hydrate_template = AsyncMock(return_value={
            "id": "official_image_qwen_image",
            "name": "image_qwen_image",
            "workflow_format": "comfyui-ui",
            "workflow_source": "remote",
            "translation_status": "needs_object_info",
            "translation_assessment": {
                "confidence": "unscored",
                "score": None,
                "ready_for_queue": False,
                "recommended_action": "refresh-install-graph",
            },
        })
        planner_ctx.request_context.lifespan_context["install_graph"] = None

        result = json.loads(await comfy_recommend_workflow(task="t2i", ctx=planner_ctx))
        templates = [item for item in result["recommendations"] if item.get("type") == "template"]
        assert templates
        assert templates[0]["next_step_tool"] == "comfy_get_template"


class TestPlannerResource:
    @pytest.mark.asyncio
    async def test_planner_resource_returns_common_tasks(self):
        import comfy_mcp.server as srv

        registry = EcosystemRegistry()
        scanner = ModelAwarenessScanner(registry)
        planner = WorkflowPlanner(registry, scanner)
        srv._shared_ecosystem_registry = registry
        srv._shared_model_awareness_scanner = scanner
        srv._shared_workflow_planner = planner
        srv._shared_client = MagicMock(capabilities={"profile": "local", "version": "0.17.0"})
        srv._shared_template_index = MagicMock()
        srv._shared_template_index.list_all = MagicMock(return_value=[])
        srv._shared_install_graph = MagicMock(snapshot={
            "models": {
                "checkpoints": ["flux1-dev.safetensors"],
                "diffusion_models": ["wan2.2_t2v.safetensors"],
                "text_encoders": ["umt5_xxl_fp8.safetensors"],
                "vae": ["wan_2.2_vae.safetensors"],
            },
            "node_classes": set(),
        })
        try:
            result = json.loads(await srv.planner_recommendations_resource())
            assert "t2i" in result
            assert "t2v" in result
            assert result["t2v"][0]["family"] == "wan22"
        finally:
            srv._shared_ecosystem_registry = None
            srv._shared_model_awareness_scanner = None
            srv._shared_workflow_planner = None
            srv._shared_client = None
            srv._shared_template_index = None
            srv._shared_install_graph = None

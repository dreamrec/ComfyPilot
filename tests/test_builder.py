"""Tests for builder tools — 5 tools for programmatic workflow construction."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.tools.builder import (
    comfy_add_node,
    comfy_apply_template,
    comfy_build_workflow,
    comfy_connect_nodes,
    comfy_set_widget_value,
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def builder_ctx():
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {}
    return ctx


# ---------------------------------------------------------------------------
# comfy_build_workflow
# ---------------------------------------------------------------------------


class TestBuildWorkflow:
    @pytest.mark.asyncio
    async def test_txt2img_returns_valid_workflow(self, builder_ctx):
        result = json.loads(await comfy_build_workflow("txt2img", ctx=builder_ctx))
        assert "workflow" in result
        assert result["template"] == "txt2img"
        assert result["node_count"] == 7
        wf = result["workflow"]
        assert "1" in wf
        assert wf["1"]["class_type"] == "CheckpointLoaderSimple"
        assert "5" in wf
        assert wf["5"]["class_type"] == "KSampler"
        assert "7" in wf
        assert wf["7"]["class_type"] == "SaveImage"

    @pytest.mark.asyncio
    async def test_unknown_template_returns_error(self, builder_ctx):
        result = json.loads(await comfy_build_workflow("nonexistent", ctx=builder_ctx))
        assert "error" in result
        assert "nonexistent" in result["error"]
        assert "available" in result
        assert "txt2img" in result["available"]

    @pytest.mark.asyncio
    async def test_params_override_defaults(self, builder_ctx):
        params = {
            "positive": "a cat on a moon",
            "steps": 30,
            "cfg": 8.5,
            "seed": 999,
            "width": 768,
            "height": 768,
        }
        result = json.loads(await comfy_build_workflow("txt2img", params=params, ctx=builder_ctx))
        wf = result["workflow"]
        assert wf["2"]["inputs"]["text"] == "a cat on a moon"
        assert wf["5"]["inputs"]["steps"] == 30
        assert wf["5"]["inputs"]["cfg"] == 8.5
        assert wf["5"]["inputs"]["seed"] == 999
        assert wf["4"]["inputs"]["width"] == 768
        assert wf["4"]["inputs"]["height"] == 768

    @pytest.mark.asyncio
    async def test_img2img_template(self, builder_ctx):
        result = json.loads(await comfy_build_workflow("img2img", ctx=builder_ctx))
        wf = result["workflow"]
        assert result["template"] == "img2img"
        # Must have LoadImage node
        class_types = {v["class_type"] for v in wf.values()}
        assert "LoadImage" in class_types
        assert "VAEEncode" in class_types
        # Default denoise for img2img is 0.75
        ksampler = next(v for v in wf.values() if v["class_type"] == "KSampler")
        assert ksampler["inputs"]["denoise"] == 0.75

    @pytest.mark.asyncio
    async def test_upscale_template(self, builder_ctx):
        result = json.loads(await comfy_build_workflow("upscale", ctx=builder_ctx))
        wf = result["workflow"]
        assert result["template"] == "upscale"
        class_types = {v["class_type"] for v in wf.values()}
        assert "LatentUpscale" in class_types
        # Two KSampler nodes expected
        ksampler_nodes = [v for v in wf.values() if v["class_type"] == "KSampler"]
        assert len(ksampler_nodes) == 2

    @pytest.mark.asyncio
    async def test_inpaint_template(self, builder_ctx):
        result = json.loads(await comfy_build_workflow("inpaint", ctx=builder_ctx))
        wf = result["workflow"]
        assert result["template"] == "inpaint"
        class_types = {v["class_type"] for v in wf.values()}
        assert "SetLatentNoiseMask" in class_types
        assert "LoadImage" in class_types

    @pytest.mark.asyncio
    async def test_controlnet_template(self, builder_ctx):
        result = json.loads(await comfy_build_workflow("controlnet", ctx=builder_ctx))
        wf = result["workflow"]
        assert result["template"] == "controlnet"
        class_types = {v["class_type"] for v in wf.values()}
        assert "ControlNetLoader" in class_types
        assert "ControlNetApply" in class_types

    @pytest.mark.asyncio
    async def test_no_params_uses_defaults(self, builder_ctx):
        result = json.loads(await comfy_build_workflow("txt2img", ctx=builder_ctx))
        wf = result["workflow"]
        assert wf["5"]["inputs"]["steps"] == 20
        assert wf["5"]["inputs"]["cfg"] == 7.0
        assert wf["5"]["inputs"]["seed"] == 42
        assert wf["4"]["inputs"]["width"] == 512

    @pytest.mark.asyncio
    async def test_checkpoint_param_override(self, builder_ctx):
        params = {"checkpoint": "dreamshaper_8.safetensors"}
        result = json.loads(await comfy_build_workflow("txt2img", params=params, ctx=builder_ctx))
        wf = result["workflow"]
        assert wf["1"]["inputs"]["ckpt_name"] == "dreamshaper_8.safetensors"

    @pytest.mark.asyncio
    async def test_build_workflow_detects_installed_checkpoint(self, builder_ctx):
        """If no checkpoint specified, builder should detect first available."""
        builder_ctx.request_context.lifespan_context["comfy_client"] = MagicMock()
        builder_ctx.request_context.lifespan_context["comfy_client"].capabilities = {"profile": "local"}
        builder_ctx.request_context.lifespan_context["comfy_client"].get_models = AsyncMock(
            return_value=["sdxl_base.safetensors", "v1-5-pruned.safetensors"]
        )
        builder_ctx.request_context.lifespan_context["install_graph"] = MagicMock(snapshot={
            "models": {"checkpoints": ["sdxl_base.safetensors", "v1-5-pruned.safetensors"]},
            "node_classes": set(),
        })

        result = json.loads(await comfy_build_workflow("txt2img", params={}, ctx=builder_ctx))
        ckpt = result["workflow"]["1"]["inputs"]["ckpt_name"]
        assert ckpt == "sdxl_base.safetensors"

    @pytest.mark.asyncio
    async def test_family_field_in_response(self, builder_ctx):
        """Response should include a 'family' field."""
        result = json.loads(await comfy_build_workflow("txt2img", ctx=builder_ctx))
        assert "family" in result
        assert result["family"] == "sd1.5"

    @pytest.mark.asyncio
    async def test_sdxl_checkpoint_gets_1024_defaults(self, builder_ctx):
        """SDXL checkpoint should produce 1024x1024 when width/height not specified."""
        params = {"checkpoint": "sd_xl_base_1.0.safetensors"}
        result = json.loads(await comfy_build_workflow("txt2img", params=params, ctx=builder_ctx))
        wf = result["workflow"]
        assert wf["4"]["inputs"]["width"] == 1024
        assert wf["4"]["inputs"]["height"] == 1024
        assert result["family"] == "sdxl"

    @pytest.mark.asyncio
    async def test_sd15_checkpoint_keeps_512_defaults(self, builder_ctx):
        """SD1.5 checkpoint should keep 512x512 defaults."""
        params = {"checkpoint": "v1-5-pruned-emaonly.safetensors"}
        result = json.loads(await comfy_build_workflow("txt2img", params=params, ctx=builder_ctx))
        wf = result["workflow"]
        assert wf["4"]["inputs"]["width"] == 512
        assert wf["4"]["inputs"]["height"] == 512
        assert result["family"] == "sd1.5"

    @pytest.mark.asyncio
    async def test_explicit_dimensions_override_family_defaults(self, builder_ctx):
        """User-specified width/height should override family defaults."""
        params = {"checkpoint": "sd_xl_base_1.0.safetensors", "width": 768, "height": 768}
        result = json.loads(await comfy_build_workflow("txt2img", params=params, ctx=builder_ctx))
        wf = result["workflow"]
        assert wf["4"]["inputs"]["width"] == 768
        assert wf["4"]["inputs"]["height"] == 768

    @pytest.mark.asyncio
    async def test_builder_uses_planner_to_pick_best_checkpoint(self, builder_ctx):
        builder_ctx.request_context.lifespan_context["comfy_client"] = MagicMock()
        builder_ctx.request_context.lifespan_context["comfy_client"].capabilities = {"profile": "local"}
        builder_ctx.request_context.lifespan_context["comfy_client"].get_models = AsyncMock(
            return_value=["v1-5-pruned-emaonly.safetensors", "flux1-dev.safetensors"]
        )
        builder_ctx.request_context.lifespan_context["install_graph"] = MagicMock(snapshot={
            "models": {"checkpoints": ["v1-5-pruned-emaonly.safetensors", "flux1-dev.safetensors"]},
            "node_classes": set(),
        })

        result = json.loads(await comfy_build_workflow("txt2img", params={}, ctx=builder_ctx))
        assert result["workflow"]["1"]["inputs"]["ckpt_name"] == "flux1-dev.safetensors"
        assert result["recommendation"]["family"] == "flux1"

    @pytest.mark.asyncio
    async def test_builder_warns_when_best_family_needs_modern_workflow(self, builder_ctx):
        builder_ctx.request_context.lifespan_context["comfy_client"] = MagicMock()
        builder_ctx.request_context.lifespan_context["comfy_client"].capabilities = {"profile": "local"}
        builder_ctx.request_context.lifespan_context["comfy_client"].get_models = AsyncMock(return_value=[])
        builder_ctx.request_context.lifespan_context["template_index"] = MagicMock()
        builder_ctx.request_context.lifespan_context["template_index"].list_all = MagicMock(return_value=[
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
        builder_ctx.request_context.lifespan_context["template_index"].get = MagicMock(return_value=None)
        builder_ctx.request_context.lifespan_context["template_index"].hydrate_template = AsyncMock(return_value={
            "id": "official_image_qwen_image",
            "workflow_format": "comfyui-ui",
            "workflow_summary": {"node_count": 12, "node_types": ["SaveImage", "QwenNode"]},
            "translation_status": "translated",
            "translation_assessment": {
                "confidence": "high",
                "score": 0.86,
                "ready_for_queue": True,
            },
        })
        builder_ctx.request_context.lifespan_context["install_graph"] = MagicMock(snapshot={
            "models": {
                "diffusion_models": ["qwen_image_fp8.safetensors"],
                "text_encoders": ["qwen_2.5_vl_7b_fp8_scaled.safetensors"],
                "vae": ["qwen_image_vae.safetensors"],
            },
            "node_classes": set(),
        })

        result = json.loads(await comfy_build_workflow("txt2img", params={}, ctx=builder_ctx))
        assert result["recommendation"]["family"] == "qwen-image"
        assert result["warnings"]
        assert "Qwen-Image" in result["warnings"][0]
        assert result["suggested_template"]["template_id"] == "official_image_qwen_image"
        assert result["suggested_template"]["actionability"] == "translatable-template"
        assert "comfy_instantiate_template" in result["warnings"][1]
        assert "confidence looks high" in result["warnings"][1]


# ---------------------------------------------------------------------------
# comfy_add_node
# ---------------------------------------------------------------------------


class TestAddNode:
    @pytest.fixture
    def base_workflow(self, builder_ctx):
        """A minimal workflow to work from."""
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "v1-5.safetensors"},
            }
        }

    @pytest.mark.asyncio
    async def test_add_node_increases_count(self, base_workflow, builder_ctx):
        result = json.loads(
            await comfy_add_node(base_workflow, "2", "CLIPTextEncode", ctx=builder_ctx)
        )
        assert result["node_count"] == 2
        assert result["added"] == "2"
        assert "2" in result["workflow"]
        assert result["workflow"]["2"]["class_type"] == "CLIPTextEncode"

    @pytest.mark.asyncio
    async def test_add_node_with_inputs(self, base_workflow, builder_ctx):
        inputs = {"text": "a sunset", "clip": ["1", 1]}
        result = json.loads(
            await comfy_add_node(base_workflow, "2", "CLIPTextEncode", inputs=inputs, ctx=builder_ctx)
        )
        assert result["workflow"]["2"]["inputs"]["text"] == "a sunset"
        assert result["workflow"]["2"]["inputs"]["clip"] == ["1", 1]

    @pytest.mark.asyncio
    async def test_add_node_without_inputs_gets_empty_dict(self, base_workflow, builder_ctx):
        result = json.loads(
            await comfy_add_node(base_workflow, "2", "EmptyLatentImage", ctx=builder_ctx)
        )
        assert result["workflow"]["2"]["inputs"] == {}

    @pytest.mark.asyncio
    async def test_add_node_does_not_mutate_original(self, base_workflow, builder_ctx):
        original_keys = set(base_workflow.keys())
        await comfy_add_node(base_workflow, "99", "NullNode", ctx=builder_ctx)
        assert set(base_workflow.keys()) == original_keys


# ---------------------------------------------------------------------------
# comfy_connect_nodes
# ---------------------------------------------------------------------------


class TestConnectNodes:
    @pytest.fixture
    def two_node_workflow(self):
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "v1-5.safetensors"},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "a sunset"},
            },
        }

    @pytest.mark.asyncio
    async def test_connect_creates_correct_link_format(self, two_node_workflow, builder_ctx):
        result = json.loads(
            await comfy_connect_nodes(
                two_node_workflow, "1", 1, "2", "clip", ctx=builder_ctx
            )
        )
        assert "connected" in result
        assert result["workflow"]["2"]["inputs"]["clip"] == ["1", 1]

    @pytest.mark.asyncio
    async def test_connect_missing_target_returns_error(self, two_node_workflow, builder_ctx):
        result = json.loads(
            await comfy_connect_nodes(
                two_node_workflow, "1", 0, "99", "model", ctx=builder_ctx
            )
        )
        assert "error" in result
        assert "99" in result["error"]

    @pytest.mark.asyncio
    async def test_connect_missing_source_returns_error(self, two_node_workflow, builder_ctx):
        result = json.loads(
            await comfy_connect_nodes(
                two_node_workflow, "99", 0, "2", "clip", ctx=builder_ctx
            )
        )
        assert "error" in result
        assert "99" in result["error"]

    @pytest.mark.asyncio
    async def test_connect_does_not_mutate_original(self, two_node_workflow, builder_ctx):
        before = two_node_workflow["2"]["inputs"].get("clip")
        await comfy_connect_nodes(two_node_workflow, "1", 1, "2", "clip", ctx=builder_ctx)
        assert two_node_workflow["2"]["inputs"].get("clip") == before

    @pytest.mark.asyncio
    async def test_connected_message_format(self, two_node_workflow, builder_ctx):
        result = json.loads(
            await comfy_connect_nodes(two_node_workflow, "1", 2, "2", "vae", ctx=builder_ctx)
        )
        assert result["connected"] == "1[2] -> 2.vae"


# ---------------------------------------------------------------------------
# comfy_set_widget_value
# ---------------------------------------------------------------------------


class TestSetWidgetValue:
    @pytest.fixture
    def simple_workflow(self):
        return {
            "5": {
                "class_type": "KSampler",
                "inputs": {"steps": 20, "cfg": 7.0},
            }
        }

    @pytest.mark.asyncio
    async def test_set_existing_widget(self, simple_workflow, builder_ctx):
        result = json.loads(
            await comfy_set_widget_value(simple_workflow, "5", "steps", 30, ctx=builder_ctx)
        )
        assert result["workflow"]["5"]["inputs"]["steps"] == 30
        assert "5.steps = 30" in result["set"]

    @pytest.mark.asyncio
    async def test_set_new_widget(self, simple_workflow, builder_ctx):
        result = json.loads(
            await comfy_set_widget_value(simple_workflow, "5", "sampler_name", "dpm_2", ctx=builder_ctx)
        )
        assert result["workflow"]["5"]["inputs"]["sampler_name"] == "dpm_2"

    @pytest.mark.asyncio
    async def test_set_widget_missing_node_returns_error(self, simple_workflow, builder_ctx):
        result = json.loads(
            await comfy_set_widget_value(simple_workflow, "99", "steps", 10, ctx=builder_ctx)
        )
        assert "error" in result
        assert "99" in result["error"]

    @pytest.mark.asyncio
    async def test_set_widget_does_not_mutate_original(self, simple_workflow, builder_ctx):
        original_steps = simple_workflow["5"]["inputs"]["steps"]
        await comfy_set_widget_value(simple_workflow, "5", "steps", 50, ctx=builder_ctx)
        assert simple_workflow["5"]["inputs"]["steps"] == original_steps


# ---------------------------------------------------------------------------
# comfy_apply_template
# ---------------------------------------------------------------------------


class TestApplyTemplate:
    @pytest.mark.asyncio
    async def test_apply_template_same_as_build_workflow(self, builder_ctx):
        build_result = json.loads(
            await comfy_build_workflow("txt2img", ctx=builder_ctx)
        )
        apply_result = json.loads(
            await comfy_apply_template("txt2img", ctx=builder_ctx)
        )
        assert build_result == apply_result

    @pytest.mark.asyncio
    async def test_apply_template_with_params(self, builder_ctx):
        params = {"steps": 25, "seed": 777}
        result = json.loads(
            await comfy_apply_template("txt2img", params=params, ctx=builder_ctx)
        )
        assert result["workflow"]["5"]["inputs"]["steps"] == 25
        assert result["workflow"]["5"]["inputs"]["seed"] == 777

    @pytest.mark.asyncio
    async def test_apply_template_unknown_returns_error(self, builder_ctx):
        result = json.loads(
            await comfy_apply_template("bad_template", ctx=builder_ctx)
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# Round-trip integration test
# ---------------------------------------------------------------------------


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_full_round_trip(self, builder_ctx):
        """Build → add_node → connect → set_widget → verify final state."""
        # 1. Build a txt2img workflow
        build_result = json.loads(
            await comfy_build_workflow("txt2img", ctx=builder_ctx)
        )
        wf = build_result["workflow"]
        assert len(wf) == 7

        # 2. Add a new node (LoRA loader)
        add_result = json.loads(
            await comfy_add_node(
                wf,
                "8",
                "LoraLoader",
                inputs={"lora_name": "my_lora.safetensors", "strength_model": 0.8},
                ctx=builder_ctx,
            )
        )
        wf = add_result["workflow"]
        assert len(wf) == 8
        assert wf["8"]["class_type"] == "LoraLoader"

        # 3. Connect LoRA output to KSampler model input
        connect_result = json.loads(
            await comfy_connect_nodes(wf, "8", 0, "5", "model", ctx=builder_ctx)
        )
        wf = connect_result["workflow"]
        assert wf["5"]["inputs"]["model"] == ["8", 0]

        # 4. Change the steps via set_widget_value
        widget_result = json.loads(
            await comfy_set_widget_value(wf, "5", "steps", 35, ctx=builder_ctx)
        )
        wf = widget_result["workflow"]
        assert wf["5"]["inputs"]["steps"] == 35

        # 5. Verify original intermediate dicts were not mutated
        assert build_result["workflow"]["5"]["inputs"]["model"] == ["1", 0]
        assert build_result["workflow"]["5"]["inputs"]["steps"] == 20

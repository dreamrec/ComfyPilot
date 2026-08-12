"""Tests for family-aware builder routing in comfy_build_workflow."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import Context

from comfy_mcp.tools.builder import comfy_build_workflow


def _ctx(mock_client, snapshot_mgr=None):
    ctx = MagicMock(spec=Context)
    ctx.request_context.lifespan_context = {
        "comfy_client": mock_client,
        "snapshot_manager": snapshot_mgr,
    }
    return ctx


@pytest.mark.asyncio
async def test_flux2_checkpoint_routes_to_flux2_template():
    client = MagicMock()
    client.get_models = AsyncMock(return_value=["flux2-klein.safetensors"])

    result = json.loads(
        await comfy_build_workflow(template="txt2img", params=None, ctx=_ctx(client))
    )
    assert result["family"] == "flux2"
    class_types = {n["class_type"] for n in result["workflow"].values()}
    assert "UNETLoader" in class_types
    assert "CheckpointLoaderSimple" not in class_types


@pytest.mark.asyncio
async def test_sd15_checkpoint_routes_to_sd15_template():
    client = MagicMock()
    client.get_models = AsyncMock(return_value=["v1-5-pruned-emaonly.safetensors"])

    result = json.loads(
        await comfy_build_workflow(template="txt2img", params=None, ctx=_ctx(client))
    )
    assert result["family"] == "sd15"
    class_types = {n["class_type"] for n in result["workflow"].values()}
    assert "CheckpointLoaderSimple" in class_types
    assert "UNETLoader" not in class_types


@pytest.mark.asyncio
async def test_wan22_checkpoint_routes_to_video_template():
    client = MagicMock()
    client.get_models = AsyncMock(return_value=["wan2.2-t2v-14b.safetensors"])

    result = json.loads(
        await comfy_build_workflow(template="txt2video", params=None, ctx=_ctx(client))
    )
    assert result["family"] == "wan22"
    class_types = {n["class_type"] for n in result["workflow"].values()}
    assert "SaveAnimatedWEBP" in class_types


@pytest.mark.asyncio
async def test_ace_step_checkpoint_routes_to_music_template():
    client = MagicMock()
    client.get_models = AsyncMock(return_value=["ace-step-1.5-xl.safetensors"])

    result = json.loads(
        await comfy_build_workflow(template="txt2music", params=None, ctx=_ctx(client))
    )
    assert result["family"] == "ace_step"
    class_types = {n["class_type"] for n in result["workflow"].values()}
    assert "SaveAudio" in class_types


@pytest.mark.asyncio
async def test_explicit_params_checkpoint_wins_over_auto_detect():
    client = MagicMock()
    client.get_models = AsyncMock(return_value=["sd_xl_base_1.0.safetensors"])

    # Explicit Flux 2 checkpoint overrides the installed SDXL
    result = json.loads(
        await comfy_build_workflow(
            template="txt2img",
            params={"checkpoint": "flux2-klein.safetensors"},
            ctx=_ctx(client),
        )
    )
    assert result["family"] == "flux2"


@pytest.mark.asyncio
async def test_unknown_checkpoint_falls_back_to_sd15():
    client = MagicMock()
    client.get_models = AsyncMock(return_value=["unknown-checkpoint.safetensors"])

    result = json.loads(
        await comfy_build_workflow(template="txt2img", params=None, ctx=_ctx(client))
    )
    # Unknown family routed to SD15 baseline
    assert result["family"] == "sd15"


@pytest.mark.asyncio
async def test_intent_not_in_family_returns_error():
    client = MagicMock()
    client.get_models = AsyncMock(return_value=["flux2-klein.safetensors"])

    # Flux 2 has no txt2music intent
    result = json.loads(
        await comfy_build_workflow(template="txt2music", params=None, ctx=_ctx(client))
    )
    assert "error" in result
    assert result["detected_family"] == "flux2"
    assert "available_intents_for_family" in result


@pytest.mark.asyncio
async def test_get_models_failure_falls_back_to_default():
    """If the client can't list models, builder uses the family's default checkpoint."""
    client = MagicMock()
    client.get_models = AsyncMock(side_effect=Exception("connection refused"))

    result = json.loads(
        await comfy_build_workflow(template="txt2img", params=None, ctx=_ctx(client))
    )
    # No checkpoint detected -> UNKNOWN -> SD15 fallback
    assert result["family"] == "sd15"


@pytest.mark.asyncio
async def test_response_shape_has_intent_family_checkpoint():
    client = MagicMock()
    client.get_models = AsyncMock(return_value=["flux2-klein.safetensors"])

    result = json.loads(
        await comfy_build_workflow(template="txt2img", params=None, ctx=_ctx(client))
    )
    assert set(result.keys()) >= {"intent", "family", "checkpoint", "node_count", "workflow"}
    assert result["intent"] == "txt2img"
    assert result["checkpoint"] == "flux2-klein.safetensors"


@pytest.mark.asyncio
async def test_diffusion_models_folder_discovered_when_checkpoints_empty():
    """Modern families (Wan 2.2, Qwen, Hunyuan) store weights under
    diffusion_models/. A valid install with an empty checkpoints/ folder
    must still route correctly."""
    client = MagicMock()

    async def get_models(folder):
        if folder == "diffusion_models":
            return ["wan2.2-t2v-14b.safetensors"]
        if folder == "checkpoints":
            return []
        return []
    client.get_models = AsyncMock(side_effect=get_models)

    result = json.loads(
        await comfy_build_workflow(template="txt2video", params=None, ctx=_ctx(client))
    )
    assert result["family"] == "wan22"
    assert result["checkpoint"] == "wan2.2-t2v-14b.safetensors"
    assert "SaveAnimatedWEBP" in {n["class_type"] for n in result["workflow"].values()}


@pytest.mark.asyncio
async def test_builder_prefers_candidate_that_supports_intent():
    """When both folders have recognised models, prefer the one whose family
    actually supports the requested intent - so asking for txt2video with
    both a Flux 2 checkpoint and a Wan 2.2 model installed picks Wan 2.2."""
    client = MagicMock()

    async def get_models(folder):
        return {
            "diffusion_models": ["flux2-klein.safetensors", "wan2.2-t2v-14b.safetensors"],
            "checkpoints": ["v1-5-pruned-emaonly.safetensors"],
        }.get(folder, [])
    client.get_models = AsyncMock(side_effect=get_models)

    result = json.loads(
        await comfy_build_workflow(template="txt2video", params=None, ctx=_ctx(client))
    )
    assert result["family"] == "wan22"


@pytest.mark.asyncio
async def test_builder_falls_back_to_any_model_when_none_match_intent():
    """If nothing matches the requested intent, still return a concrete
    checkpoint filename rather than an empty string so downstream tools
    have something to inspect."""
    client = MagicMock()

    async def get_models(folder):
        return {
            "diffusion_models": ["flux2-klein.safetensors"],
            "checkpoints": [],
        }.get(folder, [])
    client.get_models = AsyncMock(side_effect=get_models)

    # txt2music is ACE-Step-only; Flux 2 doesn't support it.
    result = json.loads(
        await comfy_build_workflow(template="txt2music", params=None, ctx=_ctx(client))
    )
    assert "error" in result
    assert result["detected_family"] == "flux2"
    assert "txt2music" not in result["available_intents_for_family"]


@pytest.mark.asyncio
async def test_explicit_family_override_is_honored():
    client = MagicMock()
    client.get_models = AsyncMock(return_value=[])
    result = json.loads(await comfy_build_workflow(
        template="txt2img",
        params={"checkpoint": "custom-name.safetensors"},
        family="sdxl",
        ctx=_ctx(client),
    ))
    assert result["family"] == "sdxl"
    assert result["workflow"]["1"]["class_type"] == "CheckpointLoaderSimple"


@pytest.mark.asyncio
async def test_ltx_diffusion_model_uses_separate_model_loaders():
    client = MagicMock()

    async def get_models(folder):
        return {
            "diffusion_models": [r"LTXVideo\v2\ltx-2.3-transformer.safetensors"],
            "text_encoders": ["gemma_3_12B_it_fpmixed.safetensors", "ltx-2.3_text_projection_bf16.safetensors"],
            "vae": ["LTX23_video_vae_bf16_KJ.safetensors"],
        }.get(folder, [])
    client.get_models = AsyncMock(side_effect=get_models)
    result = json.loads(await comfy_build_workflow("txt2video", ctx=_ctx(client)))
    classes = {node["class_type"] for node in result["workflow"].values()}
    assert result["model_folder"] == "diffusion_models"
    assert {"UNETLoader", "DualCLIPLoader", "VAELoader"} <= classes
    assert "CheckpointLoaderSimple" not in classes


@pytest.mark.asyncio
async def test_image2_3d_routes_parent_folder_hunyuan_model():
    client = MagicMock()

    async def get_models(folder):
        return {
            "diffusion_models": [
                r"LTXVideo\v2\ltx-2.3-transformer.safetensors",
                r"hunyuan3d-dit-v2-1\model.fp16.ckpt",
            ],
            "vae": [r"hunyuan3d-vae-v2-1\model.fp16.ckpt"],
            "clip_vision": ["clip_vision_h.safetensors"],
        }.get(folder, [])
    client.get_models = AsyncMock(side_effect=get_models)
    result = json.loads(await comfy_build_workflow("image2_3d", ctx=_ctx(client)))
    assert result["family"] == "hunyuan_3d"
    classes = {node["class_type"] for node in result["workflow"].values()}
    assert {"CLIPVisionEncode", "VoxelToMesh", "SaveGLB"} <= classes


@pytest.mark.asyncio
async def test_builder_live_validation_tries_next_candidate(monkeypatch):
    client = MagicMock()

    async def get_models(folder):
        return ["flux2-first.safetensors", "flux2-second.safetensors"] if folder == "diffusion_models" else []
    client.get_models = AsyncMock(side_effect=get_models)
    client.get_object_info = AsyncMock(return_value={"catalog-present": {}})

    calls = 0
    async def validate(workflow, ctx):
        nonlocal calls
        calls += 1
        valid = calls == 2
        return SimpleNamespace(
            valid=valid,
            errors=[] if valid else ["first model invalid"],
            model_dump=lambda: {"valid": valid, "errors": [] if valid else ["first model invalid"]},
        )

    monkeypatch.setattr("comfy_mcp.tools.workflow.comfy_validate_workflow", validate)
    result = json.loads(await comfy_build_workflow("txt2img", ctx=_ctx(client)))
    assert result["checkpoint"] == "flux2-second.safetensors"
    assert result["validation"]["valid"] is True

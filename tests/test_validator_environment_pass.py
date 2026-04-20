"""Tests for validator environment pass (model-file existence check)."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import Context

from comfy_mcp.tools.workflow import comfy_validate_workflow


def _ctx(client):
    ctx = MagicMock(spec=Context)
    ctx.request_context.lifespan_context = {"comfy_client": client}
    return ctx


@pytest.mark.asyncio
async def test_missing_checkpoint_fails_environment_pass():
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value={"CheckpointLoaderSimple": {}})
    client.get_models = AsyncMock(side_effect=lambda folder:
        ["other-checkpoint.safetensors"] if folder == "checkpoints" else [])

    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "missing.safetensors"}},
    }
    result = await comfy_validate_workflow(workflow=workflow, ctx=_ctx(client))
    assert result.valid is False
    assert any("missing.safetensors" in e and "checkpoints" in e for e in result.errors)
    assert "environment" in result.passes


@pytest.mark.asyncio
async def test_installed_checkpoint_passes_environment():
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value={"CheckpointLoaderSimple": {}, "SaveImage": {}})
    client.get_models = AsyncMock(side_effect=lambda folder:
        ["flux2-klein.safetensors"] if folder == "checkpoints" else [])

    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux2-klein.safetensors"}},
        "2": {"class_type": "SaveImage", "inputs": {"filename_prefix": "out", "images": ["1", 0]}},
    }
    result = await comfy_validate_workflow(workflow=workflow, ctx=_ctx(client))
    # No environment errors
    assert not any("Environment" in e for e in result.errors)


@pytest.mark.asyncio
async def test_missing_lora_and_vae_both_surface():
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value={
        "LoraLoader": {}, "VAELoader": {}, "SaveImage": {},
    })

    async def get_models(folder):
        return {
            "loras": ["only_lora.safetensors"],
            "vae": ["only_vae.safetensors"],
            "checkpoints": [],
        }.get(folder, [])
    client.get_models = AsyncMock(side_effect=get_models)

    workflow = {
        "1": {"class_type": "LoraLoader", "inputs": {"lora_name": "my_lora.safetensors", "model": ["x", 0], "clip": ["x", 1]}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": "my_vae.safetensors"}},
        "3": {"class_type": "SaveImage", "inputs": {"filename_prefix": "out", "images": ["1", 0]}},
    }
    result = await comfy_validate_workflow(workflow=workflow, ctx=_ctx(client))
    assert result.valid is False
    errors_joined = " ".join(result.errors)
    assert "my_lora.safetensors" in errors_joined
    assert "my_vae.safetensors" in errors_joined


@pytest.mark.asyncio
async def test_unreachable_folder_degrades_gracefully():
    """If a folder lookup fails, environment pass warns but doesn't error-out."""
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value={"CheckpointLoaderSimple": {}})
    client.get_models = AsyncMock(side_effect=Exception("offline"))

    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "whatever.safetensors"}},
    }
    result = await comfy_validate_workflow(workflow=workflow, ctx=_ctx(client))
    # No hard error - the environment pass was skipped
    assert not any("not found" in e for e in result.errors)
    # A warning explains what happened
    assert any("environment" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_dual_clip_loader_checks_both_clips():
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value={"DualCLIPLoader": {}})

    async def get_models(folder):
        return ["t5xxl_fp16.safetensors"] if folder == "text_encoders" else []
    client.get_models = AsyncMock(side_effect=get_models)

    workflow = {
        "1": {
            "class_type": "DualCLIPLoader",
            "inputs": {"clip_name1": "t5xxl_fp16.safetensors", "clip_name2": "clip_l.safetensors", "type": "flux"},
        },
    }
    result = await comfy_validate_workflow(workflow=workflow, ctx=_ctx(client))
    # t5xxl exists, clip_l is missing -> exactly one env error
    env_errors = [e for e in result.errors if "Environment" in e]
    assert len(env_errors) == 1
    assert "clip_l.safetensors" in env_errors[0]


@pytest.mark.asyncio
async def test_no_model_nodes_still_passes_environment():
    """A workflow without any loader nodes has no env references to check."""
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value={"PreviewImage": {}})
    client.get_models = AsyncMock(return_value=[])

    workflow = {
        "1": {"class_type": "PreviewImage", "inputs": {"images": ["x", 0]}},
    }
    result = await comfy_validate_workflow(workflow=workflow, ctx=_ctx(client))
    assert "environment" in result.passes
    # No environment errors
    assert not any("Environment" in e for e in result.errors)

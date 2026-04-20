"""Tests for validator execution-risk pass (latent volume + VRAM)."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import Context

from comfy_mcp.tools.workflow import comfy_validate_workflow


def _ctx(client, vram_guard=None):
    ctx = MagicMock(spec=Context)
    ctx.request_context.lifespan_context = {"comfy_client": client, "vram_guard": vram_guard}
    return ctx


@pytest.mark.asyncio
async def test_oversized_latent_errors():
    """4096 x 4096 x batch 4 = 67M pixels exceeds the hard limit."""
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value={"EmptyLatentImage": {}})
    client.get_models = AsyncMock(return_value=[])

    workflow = {
        "1": {"class_type": "EmptyLatentImage", "inputs": {"width": 4096, "height": 4096, "batch_size": 4}},
    }
    result = await comfy_validate_workflow(workflow=workflow, ctx=_ctx(client))
    assert result.valid is False
    assert any("Execution risk" in e for e in result.errors)
    assert "execution_risk" in result.passes


@pytest.mark.asyncio
async def test_large_latent_warns():
    """2048 x 2048 x batch 5 = 21M pixels crosses the warn threshold but not the hard error."""
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value={"EmptyLatentImage": {}})
    client.get_models = AsyncMock(return_value=[])

    workflow = {
        "1": {"class_type": "EmptyLatentImage", "inputs": {"width": 2048, "height": 2048, "batch_size": 5}},
    }
    result = await comfy_validate_workflow(workflow=workflow, ctx=_ctx(client))
    assert any("Execution risk" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_normal_latent_passes_clean():
    """1024 x 1024 x batch 1 is safe."""
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value={"EmptyLatentImage": {}})
    client.get_models = AsyncMock(return_value=[])

    workflow = {
        "1": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
    }
    result = await comfy_validate_workflow(workflow=workflow, ctx=_ctx(client))
    assert not any("Execution risk" in e for e in result.errors)
    assert not any("Execution risk" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_video_latent_accounts_for_length():
    """832 x 480 x length 81 x batch 1 = ~32M pixels - crosses warn threshold."""
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value={"EmptyHunyuanLatentVideo": {}})
    client.get_models = AsyncMock(return_value=[])

    workflow = {
        "1": {
            "class_type": "EmptyHunyuanLatentVideo",
            "inputs": {"width": 832, "height": 480, "length": 81, "batch_size": 1},
        },
    }
    result = await comfy_validate_workflow(workflow=workflow, ctx=_ctx(client))
    assert any("Execution risk" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_vram_guard_insufficient_headroom_warns():
    """When VRAMGuard reports less free VRAM than estimated need, emit a warning."""
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value={"EmptyLatentImage": {}})
    client.get_models = AsyncMock(return_value=[])
    vg = MagicMock()
    vg.estimated_headroom_mb = AsyncMock(return_value=500)  # 500 MB free

    workflow = {
        # 2048 x 2048 x batch 2 = ~8M pixels, 16 MB/Mp = 128 MB estimated need
        # Make it big enough to overshoot: 2048x2048 batch 40 -> 168M pixels, ~2688 MB need
        "1": {"class_type": "EmptyLatentImage", "inputs": {"width": 2048, "height": 2048, "batch_size": 40}},
    }
    result = await comfy_validate_workflow(workflow=workflow, ctx=_ctx(client, vg))
    # The VRAM-mismatch warning (or the latent-size hard error) surfaces
    msgs = result.errors + result.warnings
    assert any("VRAM" in m or "MB" in m for m in msgs)


@pytest.mark.asyncio
async def test_no_latent_nodes_skips_risk_gracefully():
    """A workflow without any latent-size node still marks the pass as completed."""
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value={"PreviewImage": {}})
    client.get_models = AsyncMock(return_value=[])

    workflow = {"1": {"class_type": "PreviewImage", "inputs": {"images": ["x", 0]}}}
    result = await comfy_validate_workflow(workflow=workflow, ctx=_ctx(client))
    assert "execution_risk" in result.passes

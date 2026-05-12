"""Tests for validator anti-cycle pass.

ComfyUI v0.20.0 added anti-cycle validation to its execution engine. ComfyPilot
mirrors that check client-side so cyclic graphs fail validation before they
hit the server.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import Context

from comfy_mcp.tools.workflow import comfy_validate_workflow


def _ctx(client, vram_guard=None):
    ctx = MagicMock(spec=Context)
    ctx.request_context.lifespan_context = {"comfy_client": client, "vram_guard": vram_guard}
    return ctx


def _client_with(catalog: dict | None = None) -> MagicMock:
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value=catalog or {})
    client.get_models = AsyncMock(return_value=[])
    return client


@pytest.mark.asyncio
async def test_validate_detects_direct_cycle():
    """Two nodes that reference each other's outputs form a 2-cycle."""
    workflow = {
        "1": {"class_type": "ImageOp", "inputs": {"in": ["2", 0]}},
        "2": {"class_type": "ImageOp", "inputs": {"in": ["1", 0]}},
    }
    result = await comfy_validate_workflow(
        workflow=workflow,
        ctx=_ctx(_client_with({"ImageOp": {}})),
    )
    assert result.valid is False
    assert any("cycle" in e.lower() for e in result.errors)
    assert "anti_cycle" in result.passes


@pytest.mark.asyncio
async def test_validate_detects_three_node_cycle():
    """A 3-node cycle (A->B->C->A) is also detected."""
    workflow = {
        "a": {"class_type": "ImageOp", "inputs": {"in": ["b", 0]}},
        "b": {"class_type": "ImageOp", "inputs": {"in": ["c", 0]}},
        "c": {"class_type": "ImageOp", "inputs": {"in": ["a", 0]}},
    }
    result = await comfy_validate_workflow(
        workflow=workflow,
        ctx=_ctx(_client_with({"ImageOp": {}})),
    )
    assert result.valid is False
    assert any("cycle" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_validate_accepts_acyclic_dag():
    """A linear DAG (A->B->C) passes the anti-cycle check."""
    workflow = {
        "a": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "b": {"class_type": "VAEDecode", "inputs": {"samples": ["a", 0]}},
        "c": {"class_type": "SaveImage", "inputs": {"images": ["b", 0]}},
    }
    result = await comfy_validate_workflow(
        workflow=workflow,
        ctx=_ctx(_client_with({
            "EmptyLatentImage": {},
            "VAEDecode": {},
            "SaveImage": {},
        })),
    )
    assert not any("cycle" in e.lower() for e in result.errors)
    assert "anti_cycle" in result.passes


@pytest.mark.asyncio
async def test_self_loop_is_a_cycle():
    """A node linking to itself counts as a cycle."""
    workflow = {
        "1": {"class_type": "ImageOp", "inputs": {"in": ["1", 0]}},
    }
    result = await comfy_validate_workflow(
        workflow=workflow,
        ctx=_ctx(_client_with({"ImageOp": {}})),
    )
    assert result.valid is False
    assert any("cycle" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_diamond_dag_is_acyclic():
    """A diamond (A->B, A->C, B->D, C->D) is a DAG, not a cycle."""
    workflow = {
        "a": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "b": {"class_type": "VAEDecode", "inputs": {"samples": ["a", 0]}},
        "c": {"class_type": "VAEDecode", "inputs": {"samples": ["a", 0]}},
        "d": {"class_type": "SaveImage", "inputs": {"left": ["b", 0], "right": ["c", 0]}},
    }
    result = await comfy_validate_workflow(
        workflow=workflow,
        ctx=_ctx(_client_with({
            "EmptyLatentImage": {},
            "VAEDecode": {},
            "SaveImage": {},
        })),
    )
    assert not any("cycle" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_ksampler_shared_loader_is_acyclic():
    """A realistic KSampler shape (one loader feeds multiple downstreams) is a DAG.

    Regression guard against the false-positive class that 3-coloring DFS would
    hit if the algorithm walked dependencies in the wrong direction. The
    CheckpointLoader feeds model+clip+vae into KSampler, VAEDecode receives
    both samples and the same loader's vae - this is a diamond every real
    SD 1.5 workflow has.
    """
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "p", "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "n", "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
        }},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0]}},
    }
    result = await comfy_validate_workflow(
        workflow=workflow,
        ctx=_ctx(_client_with({
            "CheckpointLoaderSimple": {}, "CLIPTextEncode": {}, "EmptyLatentImage": {},
            "KSampler": {}, "VAEDecode": {}, "SaveImage": {},
        })),
    )
    assert not any("cycle" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_long_chain_cycle_back_to_middle():
    """A->B->C->D->E->C closes a cycle through C from E. Must be detected."""
    workflow = {
        "A": {"class_type": "Op", "inputs": {}},
        "B": {"class_type": "Op", "inputs": {"in": ["A", 0]}},
        "C": {"class_type": "Op", "inputs": {"in": ["B", 0], "loop": ["E", 0]}},
        "D": {"class_type": "Op", "inputs": {"in": ["C", 0]}},
        "E": {"class_type": "Op", "inputs": {"in": ["D", 0]}},
    }
    result = await comfy_validate_workflow(
        workflow=workflow,
        ctx=_ctx(_client_with({"Op": {}})),
    )
    assert result.valid is False
    assert any("cycle" in e.lower() for e in result.errors)

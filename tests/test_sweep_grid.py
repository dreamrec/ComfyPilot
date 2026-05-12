"""Tests for comfy_sweep_grid - n-dimensional parameter sweep."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.tools.sweep import comfy_sweep_grid


def _make_ctx() -> MagicMock:
    client = MagicMock()
    counter = {"n": 0}

    async def fake_queue(workflow, front=False):
        counter["n"] += 1
        return {"prompt_id": f"pid-{counter['n']}"}

    client.queue_prompt = AsyncMock(side_effect=fake_queue)
    tracker = MagicMock()
    tracker.track = AsyncMock()
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"comfy_client": client, "job_tracker": tracker}
    return ctx


@pytest.mark.asyncio
async def test_sweep_grid_2d_returns_expected_count():
    workflow = {
        "5": {"class_type": "KSampler", "inputs": {"seed": 1, "cfg": 7.0}},
    }
    result = await comfy_sweep_grid(
        workflow=workflow,
        axes={"5.seed": [1, 2], "5.cfg": [5.0, 7.0]},
        ctx=_make_ctx(),
    )
    parsed = json.loads(result)
    assert parsed["grid_shape"] == [2, 2]
    assert parsed["total_combinations"] == 4
    assert len(parsed["prompt_ids"]) == 4


@pytest.mark.asyncio
async def test_sweep_grid_3d_cartesian_product():
    workflow = {
        "5": {"class_type": "KSampler", "inputs": {"seed": 0, "cfg": 7.0, "steps": 20}},
    }
    result = await comfy_sweep_grid(
        workflow=workflow,
        axes={"5.seed": [1, 2, 3], "5.cfg": [5.0, 7.0], "5.steps": [10, 20]},
        ctx=_make_ctx(),
    )
    parsed = json.loads(result)
    assert parsed["grid_shape"] == [3, 2, 2]
    assert parsed["total_combinations"] == 12
    assert len(parsed["prompt_ids"]) == 12


@pytest.mark.asyncio
async def test_sweep_grid_caps_combinations():
    """A 9x9 grid would be 81 - default cap is 64. Should refuse."""
    workflow = {"5": {"class_type": "KSampler", "inputs": {"seed": 0, "cfg": 7.0}}}
    result = await comfy_sweep_grid(
        workflow=workflow,
        axes={"5.seed": list(range(9)), "5.cfg": list(range(9))},
        ctx=_make_ctx(),
    )
    parsed = json.loads(result)
    assert "error" in parsed
    assert "exceeds max_combinations" in parsed["error"]


@pytest.mark.asyncio
async def test_sweep_grid_max_combinations_override():
    workflow = {"5": {"class_type": "KSampler", "inputs": {"seed": 0, "cfg": 7.0}}}
    result = await comfy_sweep_grid(
        workflow=workflow,
        axes={"5.seed": list(range(9)), "5.cfg": list(range(9))},
        max_combinations=200,
        ctx=_make_ctx(),
    )
    parsed = json.loads(result)
    assert parsed["total_combinations"] == 81
    assert len(parsed["prompt_ids"]) == 81


@pytest.mark.asyncio
async def test_sweep_grid_assignments_record_each_combo():
    workflow = {"5": {"class_type": "KSampler", "inputs": {"seed": 0}}}
    result = await comfy_sweep_grid(
        workflow=workflow,
        axes={"5.seed": [10, 20]},
        ctx=_make_ctx(),
    )
    parsed = json.loads(result)
    seeds = [a["5.seed"] for a in parsed["assignments"]]
    assert sorted(seeds) == [10, 20]


@pytest.mark.asyncio
async def test_sweep_grid_rejects_bad_axis_key():
    workflow = {"5": {"class_type": "KSampler", "inputs": {"seed": 0}}}
    result = await comfy_sweep_grid(
        workflow=workflow,
        axes={"missing_dot": [1, 2]},
        ctx=_make_ctx(),
    )
    parsed = json.loads(result)
    assert "error" in parsed


@pytest.mark.asyncio
async def test_sweep_grid_rejects_unknown_node():
    workflow = {"5": {"class_type": "KSampler", "inputs": {"seed": 0}}}
    result = await comfy_sweep_grid(
        workflow=workflow,
        axes={"99.seed": [1, 2]},
        ctx=_make_ctx(),
    )
    parsed = json.loads(result)
    assert "error" in parsed

"""Tests for comfy_randomize_seeds."""
from __future__ import annotations

import json

import pytest

from comfy_mcp.tools.randomize_seeds import comfy_randomize_seeds


@pytest.mark.asyncio
async def test_replaces_seed_sentinel_minus_one():
    wf = {
        "5": {"class_type": "KSampler", "inputs": {"seed": -1, "steps": 20}},
    }
    result = await comfy_randomize_seeds(workflow=wf, ctx=None)
    parsed = json.loads(result)
    assert parsed["randomized_count"] == 1
    new_seed = parsed["workflow"]["5"]["inputs"]["seed"]
    assert new_seed != -1
    assert 0 <= new_seed < 2 ** 32
    assert parsed["assignments"]["5.seed"] == new_seed


@pytest.mark.asyncio
async def test_leaves_explicit_seeds_alone_by_default():
    """Without force=True, seeds with non--1 values are untouched."""
    wf = {
        "5": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20}},
    }
    result = await comfy_randomize_seeds(workflow=wf, ctx=None)
    parsed = json.loads(result)
    assert parsed["randomized_count"] == 0
    assert parsed["workflow"]["5"]["inputs"]["seed"] == 42


@pytest.mark.asyncio
async def test_force_replaces_every_seed():
    wf = {
        "5": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20}},
        "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": 100}},
    }
    result = await comfy_randomize_seeds(workflow=wf, force=True, ctx=None)
    parsed = json.loads(result)
    assert parsed["randomized_count"] == 2
    assert parsed["workflow"]["5"]["inputs"]["seed"] != 42
    assert parsed["workflow"]["8"]["inputs"]["noise_seed"] != 100


@pytest.mark.asyncio
async def test_noise_seed_field_also_recognized():
    wf = {
        "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": -1}},
    }
    result = await comfy_randomize_seeds(workflow=wf, ctx=None)
    parsed = json.loads(result)
    assert "8.noise_seed" in parsed["assignments"]


@pytest.mark.asyncio
async def test_does_not_overwrite_linked_seeds():
    """If seed is wired from another node (link tuple), leave it alone."""
    wf = {
        "1": {"class_type": "IntegerNode", "inputs": {"value": 99}},
        "5": {"class_type": "KSampler", "inputs": {"seed": ["1", 0], "steps": 20}},
    }
    result = await comfy_randomize_seeds(workflow=wf, force=True, ctx=None)
    parsed = json.loads(result)
    # Seed wired from "1" must stay as the link tuple
    assert parsed["workflow"]["5"]["inputs"]["seed"] == ["1", 0]
    assert "5.seed" not in parsed["assignments"]


@pytest.mark.asyncio
async def test_caller_workflow_not_mutated():
    wf = {"5": {"class_type": "KSampler", "inputs": {"seed": -1}}}
    await comfy_randomize_seeds(workflow=wf, ctx=None)
    assert wf["5"]["inputs"]["seed"] == -1


@pytest.mark.asyncio
async def test_empty_workflow_errors():
    result = await comfy_randomize_seeds(workflow={}, ctx=None)
    parsed = json.loads(result)
    assert "error" in parsed


@pytest.mark.asyncio
async def test_no_seeds_returns_zero_count():
    wf = {"1": {"class_type": "SaveImage", "inputs": {"filename_prefix": "x"}}}
    result = await comfy_randomize_seeds(workflow=wf, ctx=None)
    parsed = json.loads(result)
    assert parsed["randomized_count"] == 0

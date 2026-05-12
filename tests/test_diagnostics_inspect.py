"""Tests for comfy_inspect_workflow - custom-node trust check."""
from __future__ import annotations

import json

import pytest

from comfy_mcp.tools.diagnostics import comfy_inspect_workflow


@pytest.mark.asyncio
async def test_pure_stock_workflow_marked_stock():
    wf = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
        "2": {"class_type": "KSampler", "inputs": {"seed": 1}},
        "3": {"class_type": "VAEDecode", "inputs": {}},
        "4": {"class_type": "SaveImage", "inputs": {}},
    }
    result = await comfy_inspect_workflow(workflow=wf, ctx=None)
    parsed = json.loads(result)
    assert parsed["trust_level"] == "stock"
    assert parsed["custom_nodes"] == []
    assert parsed["warnings"] == []


@pytest.mark.asyncio
async def test_pure_custom_workflow_marked_fully_custom():
    wf = {
        "1": {"class_type": "WeirdCustomLoader", "inputs": {}},
        "2": {"class_type": "EvilNode", "inputs": {}},
    }
    result = await comfy_inspect_workflow(workflow=wf, ctx=None)
    parsed = json.loads(result)
    assert parsed["trust_level"] == "fully_custom"
    assert set(parsed["custom_nodes"]) == {"WeirdCustomLoader", "EvilNode"}
    assert parsed["warnings"]  # at least one warning


@pytest.mark.asyncio
async def test_mixed_workflow_marked_mixed():
    wf = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
        "2": {"class_type": "KSampler", "inputs": {}},
        "3": {"class_type": "ImpactWildcardEncode", "inputs": {}},
        "4": {"class_type": "SaveImage", "inputs": {}},
    }
    result = await comfy_inspect_workflow(workflow=wf, ctx=None)
    parsed = json.loads(result)
    assert parsed["trust_level"] == "mixed"
    assert "ImpactWildcardEncode" in parsed["custom_nodes"]
    assert "CheckpointLoaderSimple" in parsed["stock_nodes"]


@pytest.mark.asyncio
async def test_recognizes_supir_and_sam3_as_stock():
    """v1.7.0-introduced families should be classified as stock now."""
    wf = {
        "1": {"class_type": "SUPIRLoader", "inputs": {}},
        "2": {"class_type": "SAM3Segment", "inputs": {}},
        "3": {"class_type": "RIFE_VFI", "inputs": {}},
        "4": {"class_type": "TrainLora", "inputs": {}},
    }
    result = await comfy_inspect_workflow(workflow=wf, ctx=None)
    parsed = json.loads(result)
    assert parsed["trust_level"] == "stock"


@pytest.mark.asyncio
async def test_warning_mentions_arbitrary_python():
    wf = {"1": {"class_type": "RandomCustomNode", "inputs": {}}}
    result = await comfy_inspect_workflow(workflow=wf, ctx=None)
    parsed = json.loads(result)
    assert any("arbitrary python" in w.lower() for w in parsed["warnings"])


@pytest.mark.asyncio
async def test_empty_workflow_errors():
    result = await comfy_inspect_workflow(workflow={}, ctx=None)
    parsed = json.loads(result)
    assert "error" in parsed


@pytest.mark.asyncio
async def test_total_class_types_is_set_count_not_node_count():
    """Three nodes that all use the same class should report total_class_types=1."""
    wf = {
        "1": {"class_type": "KSampler", "inputs": {}},
        "2": {"class_type": "KSampler", "inputs": {}},
        "3": {"class_type": "KSampler", "inputs": {}},
    }
    result = await comfy_inspect_workflow(workflow=wf, ctx=None)
    parsed = json.loads(result)
    assert parsed["total_class_types"] == 1

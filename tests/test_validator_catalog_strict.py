"""Strict object_info-backed workflow validation regressions."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.tools.workflow import comfy_validate_workflow


CATALOG = {
    "SourceImage": {
        "input": {"required": {}},
        "output": ["IMAGE", "MASK"],
        "output_name": ["image", "mask"],
        "output_node": False,
    },
    "StrictNode": {
        "input": {
            "required": {
                "image": ["IMAGE", {}],
                "steps": ["INT", {"min": 1, "max": 50}],
                "mode": [["fast", "quality"]],
            }
        },
        "output": ["IMAGE"],
        "output_node": False,
    },
    "DynamicNode": {
        "input": {
            "required": {
                "image": ["IMAGE", {}],
                "operation": [
                    "COMFY_DYNAMICCOMBO_V3",
                    {
                        "options": [
                            {
                                "key": "translate",
                                "inputs": {
                                    "required": {
                                        "x": ["FLOAT", {"default": 0.0, "min": -10, "max": 10}]
                                    }
                                },
                            },
                            {
                                "key": "rotate",
                                "inputs": {
                                    "required": {
                                        "angle": ["FLOAT", {"default": 0.0, "min": -360, "max": 360}]
                                    }
                                },
                            },
                        ]
                    },
                ],
                "divider": ["ZIPN_SEPARATOR", {"mode": "divider"}],
            },
            "optional": {
                "operation.x": ["FLOAT", {"default": 0.0, "min": -10, "max": 10}],
                "operation.angle": ["FLOAT", {"default": 0.0, "min": -360, "max": 360}],
            },
        },
        "output": ["IMAGE"],
        "output_node": False,
    },
    "CustomSink": {
        "input": {"required": {"image": ["IMAGE", {}]}},
        "output": [],
        "is_output_node": True,
    },
}


def _ctx(catalog=CATALOG):
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value=catalog)
    client.get_models = AsyncMock(return_value=[])
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"comfy_client": client}
    return ctx


def _valid_workflow():
    return {
        "1": {"class_type": "SourceImage", "inputs": {}},
        "2": {
            "class_type": "StrictNode",
            "inputs": {"image": ["1", 0], "steps": 20, "mode": "fast"},
        },
        "3": {"class_type": "CustomSink", "inputs": {"image": ["2", 0]}},
    }


@pytest.mark.asyncio
async def test_validates_required_unknown_ranges_and_choices():
    workflow = _valid_workflow()
    del workflow["2"]["inputs"]["steps"]
    workflow["2"]["inputs"].update({"bogus": 1, "mode": "invalid"})
    report = await comfy_validate_workflow(workflow, ctx=_ctx())
    assert report.valid is False
    assert any("missing required input 'steps'" in error for error in report.errors)
    assert any("unknown input" in error for error in report.errors)
    assert any("not one of" in error for error in report.errors)


@pytest.mark.asyncio
async def test_validates_output_index_and_socket_type():
    workflow = _valid_workflow()
    workflow["2"]["inputs"]["image"] = ["1", 2]
    report = await comfy_validate_workflow(workflow, ctx=_ctx())
    assert any("output index 2 is out of range" in error for error in report.errors)

    workflow["2"]["inputs"]["image"] = ["1", 1]
    report = await comfy_validate_workflow(workflow, ctx=_ctx())
    assert any("socket type mismatch" in error for error in report.errors)


@pytest.mark.asyncio
async def test_dynamic_combo_requires_flat_api_shape_and_active_fields():
    nested = {
        "1": {"class_type": "SourceImage", "inputs": {}},
        "2": {
            "class_type": "DynamicNode",
            "inputs": {
                "image": ["1", 0],
                "operation": {"operation": "translate", "x": 1.0},
            },
        },
        "3": {"class_type": "CustomSink", "inputs": {"image": ["2", 0]}},
    }
    report = await comfy_validate_workflow(nested, ctx=_ctx())
    assert any("DynamicCombo selector must be a string" in error for error in report.errors)

    flat = _valid_workflow()
    flat["2"] = {
        "class_type": "DynamicNode",
        "inputs": {
            "image": ["1", 0],
            "operation": "translate",
            "operation.x": 1.0,
        },
    }
    report = await comfy_validate_workflow(flat, ctx=_ctx())
    assert report.valid is True
    assert not any("divider" in error for error in report.errors)

    flat["2"]["inputs"]["operation.angle"] = 90.0
    report = await comfy_validate_workflow(flat, ctx=_ctx())
    assert any("not valid for operation='translate'" in error for error in report.errors)


@pytest.mark.asyncio
async def test_live_output_flag_avoids_hardcoded_sink_warning():
    report = await comfy_validate_workflow(_valid_workflow(), ctx=_ctx())
    assert report.valid is True
    assert not any("No node marked as an output" in warning for warning in report.warnings)

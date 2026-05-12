"""Tests for the normalized NodeSchema parser (V1 + V3 object_info shapes)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from comfy_mcp.schemas.node_schema import NodeSchema, parse_object_info

FIX = Path(__file__).parent / "fixtures"


def _v1() -> dict:
    return json.loads((FIX / "object_info_v1.json").read_text())


def _v3() -> dict:
    return json.loads((FIX / "object_info_v3.json").read_text())


def test_parses_v1_checkpoint_loader():
    schema = parse_object_info("CheckpointLoaderSimple", _v1()["CheckpointLoaderSimple"])
    assert isinstance(schema, NodeSchema)
    assert schema.class_type == "CheckpointLoaderSimple"
    assert schema.schema_version == "v1"
    assert schema.category == "loaders"
    assert schema.is_output_node is False
    # Has the ckpt_name required input
    names = {i.name for i in schema.inputs}
    assert "ckpt_name" in names
    # The outputs are normalized
    out_types = [o.type_name for o in schema.outputs]
    assert out_types == ["MODEL", "CLIP", "VAE"]


def test_parses_v1_ksampler_constraints():
    schema = parse_object_info("KSampler", _v1()["KSampler"])
    steps = next(i for i in schema.inputs if i.name == "steps")
    assert steps.type_name == "INT"
    assert steps.constraints is not None
    assert steps.constraints["default"] == 20
    assert steps.constraints["min"] == 1
    assert steps.required is True


def test_v1_output_node_flag_preserved():
    schema = parse_object_info("SaveImage", _v1()["SaveImage"])
    assert schema.is_output_node is True


def test_v1_link_target_detection():
    """MODEL/CONDITIONING/LATENT/IMAGE inputs are link targets, primitives are not."""
    schema = parse_object_info("KSampler", _v1()["KSampler"])
    by_name = {i.name: i for i in schema.inputs}
    assert by_name["model"].is_link_target is True
    assert by_name["positive"].is_link_target is True
    assert by_name["latent_image"].is_link_target is True
    assert by_name["steps"].is_link_target is False
    assert by_name["cfg"].is_link_target is False


def test_parses_v3_node():
    schema = parse_object_info("ExampleV3Node", _v3()["ExampleV3Node"])
    assert schema.class_type == "ExampleV3Node"
    assert schema.schema_version == "v3"
    assert schema.category == "utils/testing"
    names = {i.name for i in schema.inputs}
    assert {"image", "strength", "iterations", "note"} <= names


def test_v3_constraints_preserved():
    schema = parse_object_info("ExampleV3Node", _v3()["ExampleV3Node"])
    strength = next(i for i in schema.inputs if i.name == "strength")
    assert strength.type_name == "FLOAT"
    assert strength.constraints is not None
    assert strength.constraints["default"] == 1.0
    assert strength.constraints["max"] == 10.0


def test_v3_optional_input():
    schema = parse_object_info("ExampleV3Node", _v3()["ExampleV3Node"])
    note = next(i for i in schema.inputs if i.name == "note")
    assert note.required is False


def test_v3_is_link_target_flag():
    schema = parse_object_info("ExampleV3Node", _v3()["ExampleV3Node"])
    image_in = next(i for i in schema.inputs if i.name == "image")
    assert image_in.is_link_target is True


def test_rejects_non_dict():
    with pytest.raises(TypeError):
        parse_object_info("X", [])  # type: ignore[arg-type]


def test_roundtrips_to_json():
    schema = parse_object_info("CheckpointLoaderSimple", _v1()["CheckpointLoaderSimple"])
    payload = schema.model_dump()
    assert payload["class_type"] == "CheckpointLoaderSimple"
    assert isinstance(payload["inputs"], list)


def test_v3_range_type_recognized():
    """ComfyUI v0.20.1 added a RANGE input type with min/max/step bounds.

    RANGE is a numeric-range widget (two-handle slider), not a link target.
    """
    raw = {
        "schema_version": "v3",
        "category": "utils",
        "inputs": [
            {
                "name": "speed_range",
                "type": "RANGE",
                "required": True,
                "min": 0.0,
                "max": 1.0,
                "step": 0.01,
                "default": [0.0, 1.0],
            }
        ],
        "outputs": [],
    }
    schema = parse_object_info("RangeNode", raw)
    by_name = {i.name: i for i in schema.inputs}
    speed = by_name["speed_range"]
    assert speed.type_name == "RANGE"
    assert speed.is_link_target is False, "RANGE is a widget, not a link"
    assert speed.constraints is not None
    assert speed.constraints["min"] == 0.0
    assert speed.constraints["max"] == 1.0
    assert speed.constraints["step"] == 0.01


def test_v1_range_type_recognized():
    """If a custom node exposes RANGE via the V1 dict-of-tuples shape, treat it as a widget."""
    raw = {
        "category": "utils",
        "input": {
            "required": {
                "speed_range": ["RANGE", {"min": 0.0, "max": 1.0, "step": 0.01}],
            }
        },
    }
    schema = parse_object_info("RangeNode", raw)
    speed = next(i for i in schema.inputs if i.name == "speed_range")
    assert speed.type_name == "RANGE"
    assert speed.is_link_target is False

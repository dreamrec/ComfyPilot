"""Normalized NodeSchema - hides V1 dict-of-tuples vs V3 io.Schema shape.

ComfyUI's /object_info endpoint returns two different shapes:

V1 (legacy, most custom nodes today):
    {
      "input": {"required": {"name": ["INT", {"min": 0, "max": 9}]}},
      "output": ["MODEL"], "output_name": ["MODEL"],
      "category": "loaders", "output_node": false,
      ...
    }

V3 (class-based schema, since ComfyUI ~0.17):
    {
      "schema_version": "v3",
      "inputs": [{"name": "image", "type": "IMAGE", "required": true}],
      "outputs": [{"name": "image", "type": "IMAGE"}],
      "category": "utils", "output_node": false,
      ...
    }

This module normalizes both shapes into a single `NodeSchema` model so the
rest of the codebase never has to care which shape came back.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# Types that carry data between nodes (vs primitives edited in widgets).
# Used to decide whether an input expects a link from another node.
# RANGE was added in ComfyUI v0.20.1 as a two-handle numeric-range widget.
_PRIMITIVE_TYPES = frozenset({"STRING", "INT", "FLOAT", "BOOLEAN", "BOOL", "RANGE"})


class InputSpec(BaseModel):
    """Normalized input spec: name, type, required flag, widget constraints, link-target hint."""

    name: str
    type_name: str
    required: bool = True
    constraints: dict[str, Any] | None = None
    is_link_target: bool = False


class OutputSpec(BaseModel):
    """Normalized output spec: emitted-data name and type."""

    name: str
    type_name: str


class NodeSchema(BaseModel):
    """Normalized node schema. Agents can consume this without caring about V1 vs V3."""

    class_type: str
    category: str = ""
    description: str = ""
    inputs: list[InputSpec] = Field(default_factory=list)
    outputs: list[OutputSpec] = Field(default_factory=list)
    is_output_node: bool = False
    schema_version: Literal["v1", "v3"] = "v1"


# ---------- shape detection ----------


def _looks_v3(raw: dict) -> bool:
    """A V3 node exposes `inputs` as a list (or declares schema_version='v3').

    V1 uses an `input` (singular) dict. This check is robust across both.
    """
    if raw.get("schema_version") == "v3":
        return True
    if isinstance(raw.get("inputs"), list):
        return True
    return False


# ---------- V1 parsing ----------


def _is_link_target(type_name: str, spec: Any) -> bool:
    """Primitive types (STRING/INT/FLOAT/BOOL) are widgets; everything else is a link."""
    if type_name in _PRIMITIVE_TYPES:
        return False
    # V1 encodes combo boxes as a list of options inside a tuple: ["ckpt_name", [["a.safetensors", "b.safetensors"]]]
    # Those are widgets (dropdown selection), not links.
    if isinstance(spec, (list, tuple)) and spec and isinstance(spec[0], (list, tuple)):
        return False
    return True


def _extract_v1_input(spec: Any) -> tuple[str, dict[str, Any] | None, bool]:
    """V1 inputs are tuples like ['INT', {'min': 0}] or a bare 'STRING' or [['option_a', 'option_b']].

    Returns (type_name, constraints, is_combo).
    """
    if isinstance(spec, (list, tuple)) and spec:
        first = spec[0]
        if isinstance(first, (list, tuple)):
            # Combo box: ["option_a", "option_b", ...] - treat as STRING-selection widget
            return "STRING", {"choices": list(first)}, True
        if isinstance(first, str):
            type_name = first
            constraints = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else None
            return type_name, constraints, False
    if isinstance(spec, str):
        return spec, None, False
    return "UNKNOWN", None, False


def _parse_v1(class_type: str, raw: dict) -> NodeSchema:
    inputs: list[InputSpec] = []
    input_block = raw.get("input", {})

    for required_flag, group in (
        (True, input_block.get("required", {})),
        (False, input_block.get("optional", {})),
    ):
        if not isinstance(group, dict):
            continue
        for name, spec in group.items():
            type_name, constraints, is_combo = _extract_v1_input(spec)
            link_target = False if is_combo else _is_link_target(type_name, spec)
            inputs.append(
                InputSpec(
                    name=name,
                    type_name=type_name,
                    required=required_flag,
                    constraints=constraints,
                    is_link_target=link_target,
                )
            )

    # Outputs: V1 uses `output` (list of type names) and `output_name` (display names)
    outputs: list[OutputSpec] = []
    out_types = raw.get("output", []) or []
    out_names = raw.get("output_name") or []
    for i, type_name in enumerate(out_types):
        out_name = out_names[i] if i < len(out_names) and out_names[i] else str(type_name).lower()
        outputs.append(OutputSpec(name=str(out_name), type_name=str(type_name)))

    return NodeSchema(
        class_type=class_type,
        category=raw.get("category", "") or "",
        description=raw.get("description", "") or "",
        inputs=inputs,
        outputs=outputs,
        is_output_node=bool(raw.get("output_node", False)),
        schema_version="v1",
    )


# ---------- V3 parsing ----------


def _parse_v3(class_type: str, raw: dict) -> NodeSchema:
    inputs: list[InputSpec] = []
    for entry in raw.get("inputs", []) or []:
        if not isinstance(entry, dict):
            continue
        type_name = str(entry.get("type", "UNKNOWN"))
        # Everything except {name, type, required, is_link_target} is a constraint
        constraints: dict[str, Any] = {
            k: v for k, v in entry.items() if k not in {"name", "type", "required", "is_link_target"}
        }
        inputs.append(
            InputSpec(
                name=str(entry.get("name", "")),
                type_name=type_name,
                required=bool(entry.get("required", True)),
                constraints=constraints or None,
                is_link_target=bool(entry.get("is_link_target", type_name not in _PRIMITIVE_TYPES)),
            )
        )

    outputs: list[OutputSpec] = [
        OutputSpec(
            name=str(o.get("name", "")),
            type_name=str(o.get("type", "UNKNOWN")),
        )
        for o in (raw.get("outputs") or [])
        if isinstance(o, dict)
    ]

    return NodeSchema(
        class_type=class_type,
        category=raw.get("category", "") or "",
        description=raw.get("description", "") or "",
        inputs=inputs,
        outputs=outputs,
        is_output_node=bool(raw.get("output_node", False)),
        schema_version="v3",
    )


# ---------- public entry point ----------


def parse_object_info(class_type: str, raw: dict) -> NodeSchema:
    """Normalize a single object_info entry into NodeSchema.

    Accepts both V1 (dict-of-tuples) and V3 (class-based) shapes.
    """
    if not isinstance(raw, dict):
        raise TypeError(f"object_info entry for {class_type!r} must be a dict, got {type(raw).__name__}")
    if _looks_v3(raw):
        return _parse_v3(class_type, raw)
    return _parse_v1(class_type, raw)

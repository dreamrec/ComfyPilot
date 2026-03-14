"""Compatibility Pass 2: Schema validation against object_info.

Checks that workflow nodes match their live definitions:
- Node type exists in object_info
- Required inputs are present (or linked)
- Enum values are valid
"""

from __future__ import annotations

from typing import Any


def check_schema(workflow: dict, object_info: dict) -> dict[str, Any]:
    """Validate workflow nodes against object_info schemas."""
    errors: list[str] = []
    warnings: list[str] = []
    nodes_checked = 0

    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        if not class_type:
            continue

        schema = object_info.get(class_type)
        if schema is None:
            errors.append(f"Node {node_id}: unknown node type '{class_type}'")
            continue

        nodes_checked += 1
        inputs = node.get("inputs", {})
        required = schema.get("input", {}).get("required", {})

        for input_name, input_spec in required.items():
            value = inputs.get(input_name)

            # Missing required input
            if value is None:
                errors.append(f"Node {node_id} ({class_type}): missing required input '{input_name}'")
                continue

            # Linked inputs are valid by definition (type checking is structural)
            if isinstance(value, list) and len(value) == 2 and isinstance(value[1], int):
                continue

            # Check enum (COMBO) values
            if isinstance(input_spec, list) and len(input_spec) >= 1:
                if isinstance(input_spec[0], list):
                    # This is a COMBO: [["option1", "option2", ...]]
                    allowed = input_spec[0]
                    if value not in allowed:
                        warnings.append(
                            f"Node {node_id} ({class_type}): input '{input_name}' "
                            f"value '{value}' not in allowed values"
                        )

    return {
        "pass": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "nodes_checked": nodes_checked,
    }

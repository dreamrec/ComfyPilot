"""Compatibility Pass 1: Structural validation.

Checks that a workflow is a valid API-format graph:
- Is a non-empty dict
- Every node has class_type
- All link references point to existing nodes
- At least one likely output node exists (warning, not error)
"""

from __future__ import annotations

from typing import Any

OUTPUT_NODE_HINTS = {"SaveImage", "PreviewImage", "SaveAnimatedWEBP", "SaveAnimatedPNG",
                     "VHS_VideoCombine", "SaveVideo", "SaveAudio"}


def check_structural(workflow: Any) -> dict[str, Any]:
    """Run structural validation on an API-format workflow."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(workflow, dict):
        return {"pass": False, "errors": ["Workflow must be a dict, got " + type(workflow).__name__],
                "warnings": [], "node_count": 0}

    if len(workflow) == 0:
        return {"pass": False, "errors": ["Workflow is empty (no nodes)"],
                "warnings": [], "node_count": 0}

    node_ids = set(workflow.keys())
    has_output = False

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            errors.append(f"Node {node_id}: value is not a dict")
            continue

        class_type = node.get("class_type")
        if not class_type:
            errors.append(f"Node {node_id}: missing class_type")
            continue

        if class_type in OUTPUT_NODE_HINTS:
            has_output = True

        # Check link references in inputs
        inputs = node.get("inputs", {})
        for input_name, value in inputs.items():
            if isinstance(value, list) and len(value) == 2:
                ref_id = str(value[0])
                if ref_id not in node_ids:
                    errors.append(f"Node {node_id}.{input_name}: broken link to node {ref_id}")

    if not has_output and not errors:
        warnings.append("No recognized output node found (SaveImage, PreviewImage, etc)")

    return {
        "pass": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "node_count": len(workflow),
    }

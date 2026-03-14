"""Helpers for distinguishing ComfyUI API prompts from UI workflow JSON."""

from __future__ import annotations

from typing import Any


def is_api_prompt_workflow(payload: Any) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False
    return all(isinstance(node, dict) and "class_type" in node for node in payload.values())


def is_comfyui_ui_workflow(payload: Any) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("nodes"), list)


def describe_workflow(payload: Any) -> dict[str, Any]:
    """Detect workflow format and return a compact summary."""
    if payload is None:
        return {"format": "unavailable", "summary": {"node_count": 0, "node_types": []}}

    if is_api_prompt_workflow(payload):
        node_types = sorted({
            node.get("class_type", "")
            for node in payload.values()
            if isinstance(node, dict) and node.get("class_type")
        })
        output_types = sorted({
            node.get("class_type", "")
            for node in payload.values()
            if isinstance(node, dict) and node.get("class_type", "").startswith(("Save", "Preview"))
        })
        return {
            "format": "api-prompt",
            "summary": {
                "node_count": len(payload),
                "node_types": node_types[:50],
                "output_node_types": output_types,
            },
        }

    if is_comfyui_ui_workflow(payload):
        nodes = payload.get("nodes", [])
        node_types = sorted({
            node.get("type", "")
            for node in nodes
            if isinstance(node, dict) and node.get("type")
        })
        output_types = sorted({
            node.get("type", "")
            for node in nodes
            if isinstance(node, dict) and node.get("type", "").startswith(("Save", "Preview"))
        })
        return {
            "format": "comfyui-ui",
            "summary": {
                "node_count": len(nodes),
                "node_types": node_types[:50],
                "output_node_types": output_types,
                "link_count": len(payload.get("links", [])) if isinstance(payload.get("links", []), list) else 0,
                "group_count": len(payload.get("groups", [])) if isinstance(payload.get("groups", []), list) else 0,
            },
        }

    return {
        "format": "unknown-json",
        "summary": {
            "top_level_keys": sorted(payload.keys())[:50] if isinstance(payload, dict) else [],
        },
    }

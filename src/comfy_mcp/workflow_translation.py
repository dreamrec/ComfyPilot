"""Conservative translation from ComfyUI UI workflows to API prompt format."""

from __future__ import annotations

from collections import deque
from typing import Any

from comfy_mcp.workflow_formats import describe_workflow

PASSIVE_UI_NODE_TYPES = {"MarkdownNote", "Note"}
HELPER_UI_NODE_TYPES = {"Reroute", "PrimitiveNode"}
OUTPUT_TYPE_PREFIXES = ("Save", "Preview")
LINK_ONLY_TYPES = {
    "MODEL",
    "CLIP",
    "VAE",
    "LATENT",
    "CONDITIONING",
    "CONTROL_NET",
    "IMAGE",
    "MASK",
    "NOISE",
    "GUIDER",
    "SAMPLER",
    "SIGMAS",
    "CLIP_VISION",
    "CLIP_VISION_OUTPUT",
    "AUDIO",
    "VIDEO",
    "LATENT_UPSCALE_MODEL",
}
SCALAR_TYPES = {
    "STRING",
    "INT",
    "FLOAT",
    "BOOLEAN",
    "NUMBER",
}


def _link_index(links: list[Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for entry in links:
        if isinstance(entry, list) and len(entry) >= 5:
            index[str(entry[0])] = {
                "source_node_id": str(entry[1]),
                "source_output_index": int(entry[2]),
                "target_node_id": str(entry[3]),
                "target_input_index": int(entry[4]),
                "type": entry[5] if len(entry) > 5 else None,
            }
        elif isinstance(entry, dict) and "id" in entry:
            index[str(entry["id"])] = {
                "source_node_id": str(entry.get("origin_id") or entry.get("source_node_id")),
                "source_output_index": int(entry.get("origin_slot") or entry.get("source_output_index") or 0),
                "target_node_id": str(entry.get("target_id") or entry.get("target_node_id")),
                "target_input_index": int(entry.get("target_slot") or entry.get("target_input_index") or 0),
                "type": entry.get("type"),
            }
    return index


def _schema_entries(schema: dict[str, Any]) -> list[tuple[str, Any]]:
    input_schema = schema.get("input", {})
    entries: list[tuple[str, Any]] = []
    for section in ("required", "optional"):
        for name, spec in input_schema.get(section, {}).items():
            entries.append((name, spec))
    return entries


def _is_widget_input(name: str, spec: Any) -> bool:
    if not isinstance(spec, list) or not spec:
        return False
    first = spec[0]
    if isinstance(first, list):
        return True
    if not isinstance(first, str):
        return False
    if first in SCALAR_TYPES:
        return True
    if first in LINK_ONLY_TYPES:
        return False
    if len(spec) > 1 and isinstance(spec[1], dict):
        return True
    return first not in LINK_ONLY_TYPES


def _candidate_widget_names(
    node: dict[str, Any],
    schema: dict[str, Any],
    linked_names: set[str],
) -> list[str]:
    names: list[str] = []
    for name, spec in _schema_entries(schema):
        if name in linked_names:
            continue
        if _is_widget_input(name, spec):
            names.append(name)

    # Some UI workflows expose explicit widget input metadata.
    for input_entry in node.get("inputs", []):
        if not isinstance(input_entry, dict):
            continue
        if input_entry.get("link") is not None:
            continue
        if "widget" not in input_entry:
            continue
        name = input_entry.get("name")
        if name and name not in names:
            names.append(name)

    return names


def _resolve_link_value(
    link_id: Any,
    links: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    warnings: list[str],
    *,
    _seen: set[str] | None = None,
) -> dict[str, Any] | None:
    normalized = str(link_id)
    if _seen is None:
        _seen = set()
    if normalized in _seen:
        warnings.append(f"Detected cyclic UI helper chain for link {normalized}")
        return None
    _seen.add(normalized)

    link = links.get(normalized)
    if link is None:
        warnings.append(f"Missing link metadata for UI link {normalized}")
        return None

    source_id = link["source_node_id"]
    source_node = nodes.get(source_id)
    if source_node is None:
        warnings.append(f"Link {normalized} points to missing source node {source_id}")
        return None

    source_type = source_node.get("type", "")
    if source_type == "Reroute":
        upstream = next(
            (
                input_entry.get("link")
                for input_entry in source_node.get("inputs", [])
                if isinstance(input_entry, dict) and input_entry.get("link") is not None
            ),
            None,
        )
        if upstream is None:
            warnings.append(f"Reroute node {source_id} has no upstream link")
            return None
        return _resolve_link_value(upstream, links, nodes, warnings, _seen=_seen)

    if source_type == "PrimitiveNode":
        values = source_node.get("widgets_values", [])
        if values:
            return {
                "kind": "scalar",
                "value": values[0],
                "source_node_id": source_id,
                "source_output_index": 0,
            }
        warnings.append(f"PrimitiveNode {source_id} has no widget value to inline")
        return None

    return {
        "kind": "link",
        "value": [source_id, link["source_output_index"]],
        "source_node_id": source_id,
        "source_output_index": link["source_output_index"],
    }


def _output_node_ids(nodes: dict[str, dict[str, Any]], object_info: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for node_id, node in nodes.items():
        node_type = node.get("type", "")
        schema = object_info.get(node_type, {})
        if schema.get("output_node") or node_type.startswith(OUTPUT_TYPE_PREFIXES):
            result.add(node_id)
    return result


def _relevant_node_ids(
    nodes: dict[str, dict[str, Any]],
    links: dict[str, dict[str, Any]],
    object_info: dict[str, Any],
) -> set[str]:
    output_ids = _output_node_ids(nodes, object_info)
    if not output_ids:
        return {
            node_id
            for node_id, node in nodes.items()
            if node.get("type") not in PASSIVE_UI_NODE_TYPES | HELPER_UI_NODE_TYPES
        }

    relevant: set[str] = set()
    queue = deque(output_ids)
    while queue:
        node_id = queue.popleft()
        if node_id in relevant:
            continue
        relevant.add(node_id)
        node = nodes.get(node_id)
        if not node:
            continue
        for input_entry in node.get("inputs", []):
            if not isinstance(input_entry, dict):
                continue
            link_id = input_entry.get("link")
            if link_id is None:
                continue
            link = links.get(str(link_id))
            if link is None:
                continue
            source_id = link["source_node_id"]
            source_type = nodes.get(source_id, {}).get("type", "")
            if source_type == "Reroute":
                upstream = next(
                    (
                        item.get("link")
                        for item in nodes.get(source_id, {}).get("inputs", [])
                        if isinstance(item, dict) and item.get("link") is not None
                    ),
                    None,
                )
                if upstream is not None and str(upstream) in links:
                    queue.append(links[str(upstream)]["source_node_id"])
                continue
            if source_type == "PrimitiveNode":
                continue
            queue.append(source_id)
    return relevant


def _assign_widget_values(
    inputs: dict[str, Any],
    widget_names: list[str],
    widget_values: list[Any],
    warnings: list[str],
    *,
    node_type: str,
    node_id: str,
) -> None:
    value_index = 0
    for idx, name in enumerate(widget_names):
        if value_index >= len(widget_values):
            break
        inputs[name] = widget_values[value_index]
        value_index += 1

        if name.endswith("seed"):
            remaining_values = len(widget_values) - value_index
            remaining_names = len(widget_names) - (idx + 1)
            if remaining_values > remaining_names:
                value_index += 1
                warnings.append(
                    f"Ignored UI-only seed control value on {node_type} ({node_id}) while translating."
                )

    if value_index < len(widget_values):
        warnings.append(
            f"Left {len(widget_values) - value_index} widget value(s) unmapped on {node_type} ({node_id})."
        )


def translate_workflow(
    workflow: dict[str, Any],
    object_info: dict[str, Any],
) -> dict[str, Any]:
    """Translate a workflow payload when possible.

    Returns a structured report with `status`, `workflow_format`, and
    optionally `workflow` when a queueable API prompt could be built.
    """
    workflow_info = describe_workflow(workflow)
    workflow_format = workflow_info["format"]

    if workflow_format == "api-prompt":
        return {
            "status": "already_api_prompt",
            "workflow_format": workflow_format,
            "workflow": workflow,
            "warnings": [],
            "errors": [],
            "summary": workflow_info["summary"],
        }

    if workflow_format != "comfyui-ui":
        return {
            "status": "unsupported",
            "workflow_format": workflow_format,
            "warnings": [],
            "errors": ["Workflow is not in a recognized ComfyUI UI workflow format."],
            "summary": workflow_info["summary"],
        }

    nodes = {
        str(node["id"]): node
        for node in workflow.get("nodes", [])
        if isinstance(node, dict) and "id" in node
    }
    links = _link_index(workflow.get("links", []))
    relevant_ids = _relevant_node_ids(nodes, links, object_info)

    translated: dict[str, Any] = {}
    warnings: list[str] = []
    errors: list[str] = []
    skipped_nodes: list[dict[str, Any]] = []
    unsupported_nodes: list[dict[str, Any]] = []

    for node in workflow.get("nodes", []):
        if not isinstance(node, dict) or "id" not in node:
            continue
        node_id = str(node["id"])
        node_type = node.get("type", "")
        if node_id not in relevant_ids:
            skipped_nodes.append({"node_id": node_id, "node_type": node_type, "reason": "not_relevant"})
            continue
        if node_type in PASSIVE_UI_NODE_TYPES:
            skipped_nodes.append({"node_id": node_id, "node_type": node_type, "reason": "ui_note"})
            continue
        if node_type in HELPER_UI_NODE_TYPES:
            skipped_nodes.append({"node_id": node_id, "node_type": node_type, "reason": "ui_helper"})
            continue

        schema = object_info.get(node_type)
        if schema is None:
            unsupported_nodes.append({
                "node_id": node_id,
                "node_type": node_type,
                "reason": "missing_object_info_schema",
            })
            continue

        inputs: dict[str, Any] = {}
        linked_names: set[str] = set()
        for input_entry in node.get("inputs", []):
            if not isinstance(input_entry, dict):
                continue
            name = input_entry.get("name")
            link_id = input_entry.get("link")
            if not name or link_id is None:
                continue
            resolved = _resolve_link_value(link_id, links, nodes, warnings)
            if resolved is None:
                errors.append(f"Could not resolve link for {node_type}.{name} on node {node_id}")
                continue
            inputs[name] = resolved["value"]
            if resolved["kind"] == "link":
                linked_names.add(name)

        widget_values = node.get("widgets_values", [])
        if isinstance(widget_values, list) and widget_values:
            widget_names = _candidate_widget_names(node, schema, linked_names)
            _assign_widget_values(
                inputs,
                widget_names,
                widget_values,
                warnings,
                node_type=node_type,
                node_id=node_id,
            )

        for required_name in schema.get("input", {}).get("required", {}).keys():
            if required_name not in inputs:
                errors.append(
                    f"Missing required input {required_name} on {node_type} ({node_id}) during translation."
                )

        translated[node_id] = {
            "class_type": node_type,
            "inputs": inputs,
        }

    blocking_nodes = [entry["node_id"] for entry in unsupported_nodes]
    ready_for_queue = bool(translated) and not blocking_nodes and not errors
    status = "translated" if ready_for_queue else ("partial" if translated else "unsupported")

    return {
        "status": status,
        "workflow_format": workflow_format,
        "workflow": translated if ready_for_queue else None,
        "warnings": warnings,
        "errors": errors,
        "summary": {
            **workflow_info["summary"],
            "relevant_node_count": len(relevant_ids),
            "translated_node_count": len(translated),
            "unsupported_node_count": len(unsupported_nodes),
            "skipped_node_count": len(skipped_nodes),
            "ready_for_queue": ready_for_queue,
        },
        "unsupported_nodes": unsupported_nodes,
        "skipped_nodes": skipped_nodes,
    }

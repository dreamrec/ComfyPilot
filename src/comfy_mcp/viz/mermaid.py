"""Render a ComfyUI API-format workflow as a Mermaid flowchart.

Output is a valid `flowchart TD` directive string suitable for any
Mermaid renderer (GitHub, mermaid.ink, mermaid-cli, Notion, etc.).
One node per class_type + node_id. Arrows trace input links (source_id
flowing into target_id.input_name).
"""
from __future__ import annotations


def _sanitize(text: str) -> str:
    """Escape Mermaid-unfriendly characters in node labels."""
    return str(text).replace("\"", "'").replace("\n", " ")


def _sort_key(node_id: str) -> tuple[int, str]:
    """Sort numerically when possible so the diagram reads top-down in node-id order."""
    try:
        return (0, f"{int(node_id):010d}")
    except (ValueError, TypeError):
        return (1, str(node_id))


def workflow_to_mermaid(workflow: dict, title: str | None = None) -> str:
    """Render a workflow as a Mermaid flowchart source string.

    Args:
        workflow: {node_id: {class_type, inputs}} API-format workflow.
        title: Optional title injected as a diagram header comment.
    """
    if not isinstance(workflow, dict):
        raise TypeError("workflow must be a dict")

    lines: list[str] = ["flowchart TD"]
    if title:
        lines.append(f"    %% {_sanitize(title)}")

    # Nodes first
    for node_id in sorted(workflow.keys(), key=_sort_key):
        node = workflow[node_id]
        if not isinstance(node, dict):
            continue
        class_type = _sanitize(node.get("class_type", "?"))
        lines.append(f'    n{node_id}["{node_id}: {class_type}"]')

    # Then edges - each link is [source_id, output_index]
    for node_id in sorted(workflow.keys(), key=_sort_key):
        node = workflow[node_id]
        if not isinstance(node, dict):
            continue
        for input_name, input_val in (node.get("inputs", {}) or {}).items():
            if isinstance(input_val, (list, tuple)) and len(input_val) == 2:
                source_id = str(input_val[0])
                if source_id in workflow:
                    lines.append(
                        f'    n{source_id} -->|{_sanitize(input_name)}| n{node_id}'
                    )

    return "\n".join(lines) + "\n"

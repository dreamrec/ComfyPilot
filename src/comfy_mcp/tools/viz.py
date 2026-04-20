"""Visualization tools - 1 tool for rendering workflows as Mermaid diagrams."""
from __future__ import annotations

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp
from comfy_mcp.viz.mermaid import workflow_to_mermaid


@mcp.tool(
    annotations={
        "title": "Visualize Workflow",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_visualize_workflow(
    workflow: dict,
    title: str = "",
    ctx: Context = None,
) -> str:
    """Render an API-format workflow as a Mermaid flowchart.

    The returned string is valid Mermaid source (flowchart TD).
    Paste into any Mermaid renderer (GitHub, mermaid.ink, mermaid-cli).

    Args:
        workflow: API-format {node_id: {class_type, inputs}} dict.
        title: Optional title string inserted as a diagram comment.
    """
    try:
        return workflow_to_mermaid(workflow, title=title or None)
    except TypeError as e:
        return f"%% Error: {e}\nflowchart TD\n"

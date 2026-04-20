"""Ingest tools - 1 tool for extracting workflows from PNG metadata."""
from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from comfy_mcp.ingest.png_metadata import extract_workflow_from_png
from comfy_mcp.server import mcp


@mcp.tool(
    annotations={
        "title": "Import Workflow From PNG",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_import_workflow_from_png(
    png_path: str,
    ctx: Context = None,
) -> str:
    """Extract a workflow from a ComfyUI-saved PNG's tEXt metadata.

    ComfyUI embeds the workflow JSON in the PNG on save:
    - 'prompt' chunk: API format (directly queueable)
    - 'workflow' chunk: UI format (with positions, widgets)

    This tool prefers 'prompt' and falls back to 'workflow'. Returns
    {format: 'api' | 'ui' | 'none', workflow: dict, path: str}.

    Args:
        png_path: Absolute path to the PNG file.
    """
    try:
        result = extract_workflow_from_png(png_path)
    except FileNotFoundError:
        return json.dumps({"error": f"File not found: {png_path}"})
    except ValueError as e:
        return json.dumps({"error": str(e), "path": png_path})
    return json.dumps(result, indent=2)

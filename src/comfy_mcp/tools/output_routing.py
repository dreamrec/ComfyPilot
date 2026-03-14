"""Output routing tools — 4 tools for cross-app image delivery."""

from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


@mcp.tool(
    annotations={
        "title": "Send to Disk",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_send_to_disk(
    filename: str,
    subfolder: str = "",
    output_dir: str = "",
    ctx: Context = None,
) -> str:
    """Download an image from ComfyUI and save to local disk.

    Args:
        filename: The image filename in ComfyUI outputs
        subfolder: Optional subfolder in ComfyUI outputs
        output_dir: Optional override for output directory (default: COMFY_OUTPUT_DIR env var)
    """
    client = _client(ctx)
    image_bytes = await client.get_image(filename, subfolder=subfolder)

    dest_dir = Path(
        output_dir
        or os.environ.get(
            "COMFY_OUTPUT_DIR", str(Path.home() / "comfypilot_output")
        )
    )
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    dest_path.write_bytes(image_bytes)

    return json.dumps(
        {
            "status": "saved",
            "path": str(dest_path),
            "size_bytes": len(image_bytes),
        },
        indent=2,
    )


@mcp.tool(
    annotations={
        "title": "Send to TouchDesigner",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_send_to_td(
    filename: str,
    subfolder: str = "",
    ctx: Context = None,
) -> str:
    """Download image and save for TouchDesigner consumption.

    Args:
        filename: The image filename in ComfyUI outputs
        subfolder: Optional subfolder in ComfyUI outputs
    """
    client = _client(ctx)
    image_bytes = await client.get_image(filename, subfolder=subfolder)

    dest_dir = Path(
        os.environ.get(
            "COMFY_TD_OUTPUT_DIR",
            str(Path.home() / "comfypilot_output" / "touchdesigner"),
        )
    )
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    dest_path.write_bytes(image_bytes)

    td_command = f"op('moviefilein1').par.file = '{dest_path}'"

    return json.dumps(
        {
            "status": "saved",
            "path": str(dest_path),
            "size_bytes": len(image_bytes),
            "td_command": td_command,
            "suggestion": f"Use td_exec_python with: {td_command}",
        },
        indent=2,
    )


@mcp.tool(
    annotations={
        "title": "Send to Blender",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_send_to_blender(
    filename: str,
    subfolder: str = "",
    ctx: Context = None,
) -> str:
    """Download image and save for Blender consumption.

    Args:
        filename: The image filename in ComfyUI outputs
        subfolder: Optional subfolder in ComfyUI outputs
    """
    client = _client(ctx)
    image_bytes = await client.get_image(filename, subfolder=subfolder)

    dest_dir = Path(
        os.environ.get(
            "COMFY_BLENDER_OUTPUT_DIR",
            str(Path.home() / "comfypilot_output" / "blender"),
        )
    )
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    dest_path.write_bytes(image_bytes)

    blender_command = f"bpy.data.images.load('{dest_path}')"

    return json.dumps(
        {
            "status": "saved",
            "path": str(dest_path),
            "size_bytes": len(image_bytes),
            "blender_command": blender_command,
            "suggestion": f"Use Blender Python console with: {blender_command}",
        },
        indent=2,
    )


@mcp.tool(
    annotations={
        "title": "List Destinations",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_destinations(ctx: Context = None) -> str:
    """List configured output destinations and their paths."""
    destinations = {
        "disk": {
            "configured": bool(os.environ.get("COMFY_OUTPUT_DIR")),
            "path": os.environ.get(
                "COMFY_OUTPUT_DIR", str(Path.home() / "comfypilot_output")
            ),
        },
        "touchdesigner": {
            "configured": bool(os.environ.get("COMFY_TD_OUTPUT_DIR")),
            "path": os.environ.get(
                "COMFY_TD_OUTPUT_DIR",
                str(Path.home() / "comfypilot_output" / "touchdesigner"),
            ),
        },
        "blender": {
            "configured": bool(os.environ.get("COMFY_BLENDER_OUTPUT_DIR")),
            "path": os.environ.get(
                "COMFY_BLENDER_OUTPUT_DIR",
                str(Path.home() / "comfypilot_output" / "blender"),
            ),
        },
    }
    return json.dumps({"destinations": destinations}, indent=2)

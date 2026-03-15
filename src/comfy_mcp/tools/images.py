"""Image tools — 5 tools for image upload, download, and viewing."""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import urlencode

from mcp.server.fastmcp import Context
from mcp.types import TextContent, ImageContent

from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


@mcp.tool(
    annotations={
        "title": "Get Output Image",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_output_image(filename: str, subfolder: str = "", ctx: Context = None) -> list:
    """Download an output image from ComfyUI and return it as an image content block.

    Args:
        filename: Image filename (e.g. "ComfyUI_00001_.png")
        subfolder: Optional subfolder within the output directory
    """
    image_bytes = await _client(ctx).get_image(filename, subfolder)
    return [
        TextContent(type="text", text=json.dumps({"filename": filename, "size_bytes": len(image_bytes)})),
        ImageContent(type="image", data=base64.b64encode(image_bytes).decode(), mimeType="image/png"),
    ]


@mcp.tool(
    annotations={
        "title": "Upload Image",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_upload_image(
    image_data: str,
    filename: str,
    subfolder: str = "",
    overwrite: bool = False,
    ctx: Context = None,
) -> str:
    """Upload an image to ComfyUI.

    Args:
        image_data: Base64-encoded image data
        filename: Destination filename
        subfolder: Optional subfolder within the input directory
        overwrite: Whether to overwrite an existing file with the same name
    """
    file_bytes = base64.b64decode(image_data)
    result = await _client(ctx).upload_image(file_bytes, filename, subfolder, overwrite=overwrite)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "List Output Images",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_output_images(subfolder: str = "", limit: int = 50, ctx: Context = None) -> str:
    """List images in the output directory by scanning recent history.

    Args:
        subfolder: Optional subfolder to filter by
        limit: Maximum number of filenames to return
    """
    history = await _client(ctx).get_history()
    filenames: list[str] = []
    for prompt_id, entry in history.items():
        outputs = entry.get("outputs", {})
        for node_id, node_output in outputs.items():
            images = node_output.get("images", [])
            for img in images:
                name = img.get("filename", "")
                img_subfolder = img.get("subfolder", "")
                if subfolder and img_subfolder != subfolder:
                    continue
                if name and name not in filenames:
                    filenames.append(name)
                if len(filenames) >= limit:
                    break
            if len(filenames) >= limit:
                break
        if len(filenames) >= limit:
            break
    return json.dumps({"images": filenames, "count": len(filenames)}, indent=2)


@mcp.tool(
    annotations={
        "title": "Download Batch Metadata",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_download_batch(filenames: list[str], subfolder: str = "", ctx: Context = None) -> str:
    """Get metadata for multiple output images (no image bytes returned).

    Args:
        filenames: List of image filenames to query
        subfolder: Optional subfolder within the output directory
    """
    results = []
    for filename in filenames:
        image_bytes = await _client(ctx).get_image(filename, subfolder)
        results.append({"filename": filename, "size_bytes": len(image_bytes)})
    return json.dumps({"images": results, "count": len(results)}, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Image URL",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_image_url(
    filename: str,
    subfolder: str = "",
    image_type: str = "output",
    ctx: Context = None,
) -> str:
    """Get the URL to view an image on the ComfyUI server.

    Args:
        filename: Image filename
        subfolder: Optional subfolder
        image_type: Image type (output, input, temp)
    """
    base_url = _client(ctx).base_url
    query = urlencode({"filename": filename, "type": image_type, "subfolder": subfolder})
    url = f"{base_url}/view?{query}"
    return json.dumps({"url": url, "filename": filename, "type": image_type}, indent=2)

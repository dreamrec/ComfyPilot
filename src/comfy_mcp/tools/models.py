"""Models tools — 5 tools for model management."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


@mcp.tool(
    annotations={
        "title": "List Models",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_models(
    folder: str,
    limit: int = 50,
    offset: int = 0,
    ctx: Context = None,
) -> str:
    """List models in a folder with pagination.

    Args:
        folder: Model folder name (e.g., "checkpoints", "loras", "vae")
        limit: Maximum number of results per page
        offset: Starting position for pagination
    """
    models = await _client(ctx).get_models(folder)
    total_count = len(models)
    has_more = offset + limit < total_count
    paginated_models = models[offset : offset + limit]
    next_offset = offset + limit if has_more else None

    result = {
        "models": paginated_models,
        "folder": folder,
        "total_count": total_count,
        "has_more": has_more,
        "next_offset": next_offset,
    }
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Model Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_model_info(node_type: str, ctx: Context = None) -> str:
    """Get node schema for a model-related node type.

    Returns the node's input/output definition from ComfyUI's object_info,
    not model file metadata.

    Args:
        node_type: The node class type to inspect (e.g., "CheckpointLoaderSimple")
    """
    result = await _client(ctx).get_object_info(node_type)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "List Model Folders",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_model_folders(ctx: Context = None) -> str:
    """List available model folder names.

    Returns common ComfyUI model folders.
    """
    folders = [
        "checkpoints",
        "loras",
        "vae",
        "clip",
        "diffusers",
        "controlnet",
        "upscale_models",
        "embeddings",
        "hypernetworks",
    ]
    result = {"folders": folders, "count": len(folders)}
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Search Models",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_search_models(
    query: str,
    folders: list[str] | None = None,
    ctx: Context = None,
) -> str:
    """Search for models across folders by name.

    Args:
        query: Search query (case-insensitive substring match)
        folders: Specific folders to search. If None, searches common folders.
    """
    if folders is None:
        folders = ["checkpoints", "loras", "vae", "controlnet", "upscale_models"]

    matches = {}
    query_lower = query.lower()

    for folder in folders:
        try:
            models = await _client(ctx).get_models(folder)
            folder_matches = [m for m in models if query_lower in m.lower()]
            if folder_matches:
                matches[folder] = folder_matches
        except Exception:
            # Skip folders that don't exist or error
            pass

    result = {"query": query, "matches": matches, "total_matches": sum(len(m) for m in matches.values())}
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Refresh Models",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_refresh_models(ctx: Context = None) -> str:
    """Re-fetch the model list from ComfyUI.

    Note: This re-reads ComfyUI's current model cache. It does NOT
    trigger a server-side filesystem rescan.
    """
    models = await _client(ctx).get_models("checkpoints")
    result = {
        "status": "ok",
        "message": "Model list re-fetched from ComfyUI cache",
        "checkpoint_count": len(models),
    }
    return json.dumps(result, indent=2)

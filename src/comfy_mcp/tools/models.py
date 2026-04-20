"""Models tools - 5 tools for model management.

Folder discovery is live: every tool that touches multiple folders asks
ComfyUI's `/models` endpoint for the real folder list at call time.
Modern families (Flux 2, Wan 2.2, Qwen-Image, LTX-2, HunyuanVideo,
Hunyuan3D) store weights under `diffusion_models/` via UNETLoader;
DualCLIPLoader / CLIPLoader weights live under `text_encoders/`.
The pre-1.6 hardcoded defaults (`["checkpoints", "loras", "vae",
"controlnet", "upscale_models"]`) missed all of those entirely.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.responses import ModelList
from comfy_mcp.server import mcp


# Fallback folder list used when ComfyUI's /models endpoint is unreachable or
# returns something unexpected. Order is irrelevant - it's a name bag, not a
# priority. Covers every folder type a modern ComfyUI v0.17+ install exposes.
_FALLBACK_FOLDERS = [
    "checkpoints",
    "diffusion_models",
    "unet",
    "loras",
    "vae",
    "vae_approx",
    "clip",
    "text_encoders",
    "clip_vision",
    "controlnet",
    "upscale_models",
    "style_models",
    "embeddings",
    "hypernetworks",
    "gligen",
    "diffusers",
]


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


async def _discover_folders(ctx: Context) -> tuple[list[str], str]:
    """Return (folders, source) where source is 'live' or 'fallback'."""
    try:
        live = await _client(ctx).get_model_folders()
    except Exception:
        return list(_FALLBACK_FOLDERS), "fallback"
    if live:
        return live, "live"
    return list(_FALLBACK_FOLDERS), "fallback"


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
) -> ModelList:
    """List models in a folder with pagination. Returns structured ModelList.

    Args:
        folder: Model folder name (e.g., "checkpoints", "diffusion_models",
            "loras", "vae", "text_encoders"). Call comfy_list_model_folders
            to see every folder the connected ComfyUI actually exposes.
        limit: Maximum number of results per page.
        offset: Starting position for pagination.
    """
    models = await _client(ctx).get_models(folder)
    total_count = len(models)
    has_more = offset + limit < total_count
    paginated_models = models[offset : offset + limit]
    next_offset = offset + limit if has_more else None

    return ModelList(
        folder=folder,
        models=paginated_models,
        total_count=total_count,
        has_more=has_more,
        next_offset=next_offset,
    )


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
    """List every model-folder name the connected ComfyUI exposes.

    Uses ComfyUI's `/models` endpoint to discover folders live. Reports the
    data source ("live" vs "fallback") so callers know whether the list
    reflects their actual install.
    """
    folders, source = await _discover_folders(ctx)
    result = {
        "folders": folders,
        "count": len(folders),
        "source": source,
    }
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
    """Search for models by name across folders.

    By default searches every folder ComfyUI exposes (discovered live via
    /models). Pass `folders=["checkpoints", "loras"]` to narrow.

    Args:
        query: Case-insensitive substring match against filenames. Empty
            string returns every model in every folder (useful for a
            full inventory).
        folders: Explicit folder list to restrict the search. None means
            search all discovered folders.
    """
    if folders is None:
        folders, source = await _discover_folders(ctx)
    else:
        source = "caller"

    matches: dict[str, list[str]] = {}
    query_lower = query.lower()
    folders_scanned: list[str] = []

    for folder in folders:
        try:
            models = await _client(ctx).get_models(folder)
        except Exception:
            # Folder exists in the index but the listing endpoint errored -
            # skip without aborting the whole search
            continue
        folders_scanned.append(folder)
        if query_lower:
            folder_matches = [m for m in models if query_lower in m.lower()]
        else:
            folder_matches = list(models)
        if folder_matches:
            matches[folder] = folder_matches

    return json.dumps({
        "query": query,
        "folders_source": source,
        "folders_scanned": folders_scanned,
        "matches": matches,
        "total_matches": sum(len(m) for m in matches.values()),
    }, indent=2)


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
    """Re-fetch the model list from ComfyUI across every known folder.

    Note: this re-reads ComfyUI's current model cache. It does NOT trigger
    a server-side filesystem rescan. Returns per-folder counts so the
    caller can see where the installed weights live.
    """
    folders, source = await _discover_folders(ctx)
    counts: dict[str, int] = {}
    errors: list[dict[str, str]] = []
    total = 0
    for folder in folders:
        try:
            models = await _client(ctx).get_models(folder)
        except Exception as e:
            errors.append({"folder": folder, "error": str(e)})
            continue
        counts[folder] = len(models)
        total += len(models)
    return json.dumps({
        "status": "ok",
        "folders_source": source,
        "total_models": total,
        "counts_by_folder": counts,
        "errors": errors,
        "message": f"Refreshed {len(counts)} folders, {total} models total",
    }, indent=2)

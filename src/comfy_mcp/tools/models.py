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
from pathlib import PurePosixPath
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

# ComfyUI custom nodes can register arbitrary directories as model folders.
# Some return Python sources, wheel caches and Hugging Face lock metadata from
# `/models/{folder}`. Keep useful weights/configuration while hiding that noise
# by default; callers can explicitly request the raw listing when diagnosing a
# custom folder.
_MODEL_EXTENSIONS = {
    ".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".onnx",
    ".engine", ".plan", ".model", ".pb", ".tflite", ".h5", ".hdf5",
    ".npz", ".npy", ".pkl", ".pickle", ".yaml", ".yml", ".toml", ".json",
}
_NOISE_SUFFIXES = {
    ".lock", ".py", ".pyc", ".pyo", ".pyd", ".whl", ".zip", ".tar",
    ".gz", ".7z", ".rar", ".md", ".rst", ".log", ".tmp", ".part",
    ".etag", ".sha256",
}
_NOISE_SEGMENTS = {
    ".cache", "__pycache__", ".git", ".github", "node_modules",
    "site-packages", "dist-info", "egg-info", "locks", "__tests__", "tests",
    "test", "docs", "examples", "workflows", "web",
}


def _is_model_candidate(name: Any) -> bool:
    if not isinstance(name, str) or not name.strip():
        return False
    normalised = name.replace("\\", "/")
    path = PurePosixPath(normalised)
    lower_parts = [part.lower() for part in path.parts]
    if any(
        part in _NOISE_SEGMENTS
        or part.endswith(".dist-info")
        or part.endswith(".egg-info")
        for part in lower_parts[:-1]
    ):
        return False
    basename = lower_parts[-1]
    if basename.startswith(".") or basename.endswith(tuple(_NOISE_SUFFIXES)):
        return False
    return PurePosixPath(basename).suffix in _MODEL_EXTENSIONS


def _filter_models(models: list[Any], include_non_model_files: bool) -> list[str]:
    strings = [model for model in models if isinstance(model, str)]
    if include_non_model_files:
        return strings
    return [model for model in strings if _is_model_candidate(model)]


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
    include_non_model_files: bool = False,
    ctx: Context = None,
) -> ModelList:
    """List models in a folder with pagination. Returns structured ModelList.

    Args:
        folder: Model folder name (e.g., "checkpoints", "diffusion_models",
            "loras", "vae", "text_encoders"). Call comfy_list_model_folders
            to see every folder the connected ComfyUI actually exposes.
        limit: Maximum number of results per page.
        offset: Starting position for pagination.
        include_non_model_files: Include caches, source files, lock metadata,
            archives, and unknown extensions returned by custom folders.
    """
    if limit < 1:
        limit = 1
    if offset < 0:
        offset = 0
    models = _filter_models(await _client(ctx).get_models(folder), include_non_model_files)
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
    include_non_model_files: bool = False,
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
        include_non_model_files: Include cache locks, Python sources, wheels,
            archives, and unknown file types. Default False.
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
            models = _filter_models(
                await _client(ctx).get_models(folder), include_non_model_files
            )
        except Exception:
            # Folder exists in the index but the listing endpoint errored -
            # skip without aborting the whole search
            continue
        folders_scanned.append(folder)
        if query_lower and query_lower not in folder.lower():
            folder_matches = [m for m in models if query_lower in m.lower()]
        else:
            folder_matches = list(models)
        if folder_matches:
            matches[folder] = folder_matches

    return json.dumps({
        "query": query,
        "folders_source": source,
        "folders_scanned": folders_scanned,
        "include_non_model_files": include_non_model_files,
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
            raw_models = await _client(ctx).get_models(folder)
        except Exception as e:
            errors.append({"folder": folder, "error": str(e)})
            continue
        models = _filter_models(raw_models, False)
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

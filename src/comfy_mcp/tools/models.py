"""Models tools — 7 tools for model management and awareness."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.ecosystem import EcosystemRegistry, ModelAwarenessScanner
from comfy_mcp.install.install_graph import MODEL_FOLDERS
from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


def _install_graph(ctx: Context):
    return ctx.request_context.lifespan_context.get("install_graph")


def _registry(ctx: Context) -> EcosystemRegistry:
    return ctx.request_context.lifespan_context.get("ecosystem_registry") or EcosystemRegistry()


def _scanner(ctx: Context) -> ModelAwarenessScanner:
    return ctx.request_context.lifespan_context.get("model_awareness_scanner") or ModelAwarenessScanner(_registry(ctx))


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
    folders = list(MODEL_FOLDERS) + ["embeddings"]
    result = {
        "folders": folders,
        "count": len(folders),
        "groups": {
            "legacy": ["checkpoints", "loras", "vae", "controlnet", "upscale_models"],
            "modern": ["diffusion_models", "text_encoders", "model_patches", "latent_upscale_models", "clip_vision"],
            "auxiliary": ["clip", "diffusers", "hypernetworks", "embeddings"],
        },
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
    """Search for models across folders by name.

    Args:
        query: Search query (case-insensitive substring match)
        folders: Specific folders to search. If None, searches common folders.
    """
    if folders is None:
        folders = list(MODEL_FOLDERS)

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
    model_counts: dict[str, int] = {}
    total_models = 0
    for folder in MODEL_FOLDERS:
        try:
            models = await _client(ctx).get_models(folder)
        except Exception:
            continue
        model_counts[folder] = len(models)
        total_models += len(models)
    result = {
        "status": "ok",
        "message": "Model list re-fetched from ComfyUI cache",
        "checkpoint_count": model_counts.get("checkpoints", 0),
        "folder_count": len(model_counts),
        "total_models": total_models,
        "model_counts": model_counts,
    }
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "List Model Families",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_model_families(
    kind: str = "family",
    modality: str = "",
    runtime_mode: str = "",
    ctx: Context = None,
) -> str:
    """List curated model families, ecosystems, or provider catalogs.

    Args:
        kind: One of family, ecosystem, provider
        modality: Optional modality filter (image, video, audio)
        runtime_mode: Optional runtime filter (local-native, partner-nodes, cloud)
    """
    if kind not in {"family", "ecosystem", "provider"}:
        return json.dumps({
            "error": f"Unknown kind: {kind}",
            "available": ["family", "ecosystem", "provider"],
        }, indent=2)

    entries = _registry(ctx).list_entries(kind=kind, modality=modality, runtime_mode=runtime_mode)
    return json.dumps({
        "kind": kind,
        "entries": entries,
        "total_count": len(entries),
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Detect Model Capabilities",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_detect_model_capabilities(ctx: Context = None) -> str:
    """Summarize installed model families, capabilities, and provider signals."""
    install_graph = _install_graph(ctx)
    snapshot: dict[str, Any] | None = None
    if install_graph is not None:
        snapshot = getattr(install_graph, "snapshot", None)

    if not snapshot:
        snapshot = {
            "models": {},
            "node_classes": set(),
        }
        for folder in MODEL_FOLDERS:
            try:
                snapshot["models"][folder] = await _client(ctx).get_models(folder)
            except Exception:
                continue
        try:
            object_info = await _client(ctx).get_object_info()
        except Exception:
            object_info = {}
        snapshot["node_classes"] = set(object_info.keys())

    result = _scanner(ctx).scan(snapshot, capabilities=getattr(_client(ctx), "capabilities", {}))
    return json.dumps(result, indent=2)

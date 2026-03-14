"""System tools — 6 tools for ComfyUI system info and management."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


@mcp.tool(
    annotations={
        "title": "Get System Stats",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_system_stats(ctx: Context) -> str:
    """Get ComfyUI system stats: OS, GPU, VRAM, version info."""
    result = await _client(ctx).get_system_stats()
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Get GPU Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_gpu_info(ctx: Context) -> str:
    """Get detailed GPU info: VRAM total/free/used, torch version, device names."""
    stats = await _client(ctx).get_system_stats()
    devices = stats.get("devices", [])
    gpu_info = {"devices": devices, "count": len(devices)}
    for dev in devices:
        total = dev.get("vram_total", 0)
        free = dev.get("vram_free", 0)
        dev["vram_used"] = total - free
        if total > 0:
            dev["vram_used_pct"] = round((total - free) / total * 100, 1)
    return json.dumps(gpu_info, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Features",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_features(ctx: Context) -> str:
    """List enabled ComfyUI features (v0.17+)."""
    result = await _client(ctx).get_features()
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "List Extensions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_extensions(ctx: Context) -> str:
    """List all installed ComfyUI custom nodes and extensions."""
    extensions = await _client(ctx).get_extensions()
    return json.dumps({"extensions": extensions, "count": len(extensions)}, indent=2)


@mcp.tool(
    annotations={
        "title": "Restart ComfyUI",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_restart(ctx: Context) -> str:
    """Restart ComfyUI (not supported via API).

    ComfyUI does not expose a restart endpoint. Use system-level
    restart (e.g., systemctl, docker restart) instead.
    """
    return json.dumps({
        "status": "not_supported",
        "message": "ComfyUI does not expose a restart endpoint in the standard API. Use system-level restart.",
    })


@mcp.tool(
    annotations={
        "title": "Free VRAM",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_free_vram(
    unload_models: bool = False,
    free_memory: bool = False,
    ctx: Context = None,
) -> str:
    """Unload models and/or free VRAM memory.

    Args:
        unload_models: Unload all loaded models from VRAM
        free_memory: Free cached memory allocations
    """
    result = await _client(ctx).free_vram(
        unload_models=unload_models,
        free_memory=free_memory,
    )
    return json.dumps({"status": "ok", "unloaded_models": unload_models, "freed_memory": free_memory})

"""Knowledge tools — MCP surface for unified knowledge management."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _manager(ctx: Context):
    return ctx.request_context.lifespan_context["knowledge_manager"]


def _config(ctx: Context):
    return ctx.request_context.lifespan_context["config_manager"]


@mcp.tool(
    annotations={
        "title": "Knowledge Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_knowledge_status(*, ctx: Context) -> str:
    """Unified view of all knowledge subsystem staleness, hashes, and cache sizes."""
    mgr = _manager(ctx)
    return json.dumps(mgr.status(), indent=2)


@mcp.tool(
    annotations={
        "title": "Refresh All Knowledge",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_refresh_all(*, ctx: Context) -> str:
    """Refresh all knowledge stores (docs, templates, install graph)."""
    mgr = _manager(ctx)
    result = await mgr.refresh_all()
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Clear Cache",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_clear_cache(subsystem: str = "all", *, ctx: Context) -> str:
    """Clear cached data for a specific subsystem or all caches.

    Args:
        subsystem: Which cache to clear ('docs', 'templates', 'install_graph', or 'all').
    """
    mgr = _manager(ctx)
    result = mgr.clear(subsystem)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Config",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_config(key: str | None = None, *, ctx: Context) -> str:
    """Read persisted user preferences.

    Args:
        key: Dotted config key (e.g., 'safety.vram_warn_pct'). If omitted, returns all config.
    """
    config = _config(ctx)
    if key:
        return json.dumps({"key": key, "value": config.get(key)}, indent=2)
    return json.dumps({"config": config.get_all()}, indent=2)


@mcp.tool(
    annotations={
        "title": "Set Config",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_set_config(key: str, value: Any, *, ctx: Context) -> str:
    """Write a persisted user preference.

    Args:
        key: Dotted config key (e.g., 'safety.vram_warn_pct').
        value: Value to set.
    """
    _ALLOWED_KEYS = {
        "safety.vram_warn_pct", "safety.vram_block_pct", "safety.max_queue",
        "cache.ttl", "output.default_dir",
    }
    if key not in _ALLOWED_KEYS:
        return json.dumps({
            "error": f"Unknown config key: {key}",
            "allowed_keys": sorted(_ALLOWED_KEYS),
        }, indent=2)

    config = _config(ctx)
    config.set(key, value)
    return json.dumps({"status": "ok", "key": key, "value": value}, indent=2)

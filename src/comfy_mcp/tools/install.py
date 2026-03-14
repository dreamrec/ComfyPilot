"""Install tools — MCP surface for InstallGraph and ModelResolver."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _graph(ctx: Context):
    return ctx.request_context.lifespan_context["install_graph"]


@mcp.tool(
    annotations={
        "title": "Refresh Install Graph",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_refresh_install_graph(ctx: Context) -> str:
    """Re-scan the connected ComfyUI instance and rebuild the install graph.

    Queries object_info, models, features, extensions, embeddings, and system stats.
    Call this after installing custom nodes, adding models, or updating ComfyUI.
    """
    graph = _graph(ctx)
    await graph.refresh()
    return json.dumps({"status": "ok", "summary": graph.summary()}, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Install Summary",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_install_summary(ctx: Context) -> str:
    """Get a compact summary of the machine's ComfyUI installation.

    Returns counts of installed nodes, models, extensions, embeddings, GPU info.
    """
    graph = _graph(ctx)
    if not graph.snapshot:
        await graph.refresh()
    return json.dumps(graph.summary(), indent=2)


@mcp.tool(
    annotations={
        "title": "Check Model",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_check_model(
    name: str,
    folder: str | None = None,
    ctx: Context = None,
) -> str:
    """Check if a model is installed and resolvable.

    Args:
        name: Model filename or partial name
        folder: Specific folder (checkpoints, loras, vae, etc). If omitted, searches all.
    """
    graph = _graph(ctx)
    if not graph.snapshot:
        await graph.refresh()
    from comfy_mcp.install.model_resolver import ModelResolver
    resolver = ModelResolver(graph.snapshot)
    result = resolver.resolve(name, folder)
    return json.dumps(result, indent=2)

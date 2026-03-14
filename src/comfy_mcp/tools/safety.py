"""Safety tools — 5 tools for VRAM monitoring and safety enforcement."""
from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _vram_guard(ctx: Context):
    return ctx.request_context.lifespan_context["vram_guard"]


@mcp.tool(
    annotations={
        "title": "Check VRAM",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_check_vram(ctx: Context = None) -> str:
    """Check current GPU VRAM usage and status (ok/warn/critical)."""
    guard = _vram_guard(ctx)
    result = await guard.check_vram()
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Set Safety Limits",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_set_limits(
    warn_pct: float | None = None,
    block_pct: float | None = None,
    max_queue: int | None = None,
    timeout: int | None = None,
    ctx: Context = None,
) -> str:
    """Update VRAMGuard safety thresholds.

    Args:
        warn_pct: VRAM percentage to trigger warn status (default 80.0)
        block_pct: VRAM percentage to trigger critical/block status (default 95.0)
        max_queue: Maximum queue depth before blocking (default 10)
        timeout: Job timeout in seconds (default 300)

    Returns:
        JSON with updated threshold values
    """
    # Validate inputs
    if warn_pct is not None and not (0 <= warn_pct <= 100):
        return json.dumps({"error": "warn_pct must be between 0 and 100"})
    if block_pct is not None and not (0 <= block_pct <= 100):
        return json.dumps({"error": "block_pct must be between 0 and 100"})
    if max_queue is not None and max_queue < 1:
        return json.dumps({"error": "max_queue must be >= 1"})
    if timeout is not None and timeout < 1:
        return json.dumps({"error": "timeout must be >= 1"})

    guard = _vram_guard(ctx)
    kwargs = {}
    if warn_pct is not None:
        kwargs["warn_pct"] = warn_pct
    if block_pct is not None:
        kwargs["block_pct"] = block_pct
    if max_queue is not None:
        kwargs["max_queue"] = max_queue
    if timeout is not None:
        kwargs["timeout"] = timeout
    result = guard.set_limits(**kwargs)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Detect Instability",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_detect_instability(ctx: Context = None) -> str:
    """Check for stuck jobs, OOM patterns, and other instability signals.

    Returns:
        JSON with stable flag, issues list, and queue counts
    """
    guard = _vram_guard(ctx)
    result = await guard.detect_instability()
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Emergency Stop",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_emergency_stop(ctx: Context = None) -> str:
    """Emergency stop: interrupt current job, clear queue, and free VRAM.

    WARNING: This is destructive — it will cancel all running and pending jobs.

    Returns:
        JSON with status and list of actions taken
    """
    guard = _vram_guard(ctx)
    result = await guard.emergency_stop()
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Validate Before Queue",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_validate_before_queue(ctx: Context = None) -> str:
    """Pre-flight safety check before queueing a prompt.

    Checks VRAM headroom and current queue depth.

    Returns:
        JSON with safe_to_queue flag, VRAM status, queue counts, and any issues
    """
    guard = _vram_guard(ctx)
    result = await guard.validate_before_queue()
    return json.dumps(result, indent=2)

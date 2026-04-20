"""Monitoring tools - 6 tools for real-time monitoring and event management."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.responses import DynamicsReport, WatchProgressFrame
from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


def _event_mgr(ctx: Context):
    return ctx.request_context.lifespan_context["event_manager"]


def _job_tracker(ctx: Context):
    return ctx.request_context.lifespan_context["job_tracker"]


@mcp.tool(
    annotations={
        "title": "Watch Prompt Progress",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_watch_progress(prompt_id: str, ctx: Context = None) -> WatchProgressFrame:
    """Poll EventManager for a prompt's execution progress. Returns structured WatchProgressFrame.

    Args:
        prompt_id: The prompt ID to watch
    """
    import time as _time

    event_mgr = _event_mgr(ctx)
    progress = event_mgr.get_latest_progress(prompt_id)
    if not progress:
        return WatchProgressFrame(prompt_id=prompt_id, status="no_progress")

    data = progress.get("data", {}) or {}
    timestamp = float(progress.get("timestamp", 0.0) or 0.0)
    elapsed = max(0.0, _time.time() - timestamp) if timestamp else 0.0
    return WatchProgressFrame(
        prompt_id=prompt_id,
        status="ok",
        progress=float(data.get("value", 0) or 0),
        max_progress=float(data.get("max", 0) or 0),
        timestamp=timestamp,
        elapsed_s=elapsed,
    )


@mcp.tool(
    annotations={
        "title": "Subscribe to Events",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_subscribe(event_type: str, ctx: Context = None) -> str:
    """Register interest in an event type.

    Args:
        event_type: The event type to subscribe to (e.g., 'progress', 'error', 'complete')

    Returns:
        JSON confirming subscription
    """
    event_mgr = _event_mgr(ctx)
    event_mgr.subscribe(event_type)
    return json.dumps({
        "status": "subscribed",
        "event_type": event_type,
    })


@mcp.tool(
    annotations={
        "title": "Unsubscribe from Events",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_unsubscribe(event_type: str, ctx: Context = None) -> str:
    """Remove subscription to an event type.

    Args:
        event_type: The event type to unsubscribe from

    Returns:
        JSON confirming removal
    """
    event_mgr = _event_mgr(ctx)
    event_mgr.unsubscribe(event_type)
    return json.dumps({
        "status": "unsubscribed",
        "event_type": event_type,
    })


@mcp.tool(
    annotations={
        "title": "Get Buffered Events",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_get_events(
    event_type: str | None = None,
    limit: int = 100,
    ctx: Context = None,
) -> str:
    """Drain buffered events from EventManager.

    Args:
        event_type: Optional filter by event type
        limit: Maximum number of events to return (default 100)

    Returns:
        JSON with events list and count
    """
    event_mgr = _event_mgr(ctx)
    events = event_mgr.drain_events(event_type, limit)
    return json.dumps({
        "count": len(events) if events else 0,
        "events": events if events else [],
    })


@mcp.tool(
    annotations={
        "title": "Describe System Dynamics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_describe_dynamics(ctx: Context = None) -> DynamicsReport:
    """One-shot snapshot of system dynamics (queue + recent events + active jobs).

    Returns structured DynamicsReport with queue counts, recent event types,
    and active job summary.
    """
    client = _client(ctx)
    event_mgr = _event_mgr(ctx)
    job_tracker = _job_tracker(ctx)

    queue = await client.get_queue()
    queue_running = queue.get("queue_running", [])
    queue_pending = queue.get("queue_pending", [])

    recent_events = event_mgr.peek_events(limit=10) if hasattr(event_mgr, "peek_events") else []
    event_types: set[str] = set()
    for event in recent_events or []:
        event_types.add(event.get("type", "unknown"))

    active_jobs = list(job_tracker.list_active() or [])

    return DynamicsReport(
        queue_running=len(queue_running),
        queue_pending=len(queue_pending),
        event_types_seen=sorted(event_types),
        recent_event_count=len(recent_events) if recent_events else 0,
        active_job_count=len(active_jobs),
        active_jobs=active_jobs,
    )


@mcp.tool(
    annotations={
        "title": "Get System Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_status(ctx: Context = None) -> str:
    """One-shot status overview (queue + GPU + execution state + events).

    Returns:
        Combined status JSON with queue info, system stats, and event health
    """
    client = _client(ctx)

    # Get queue
    queue = await client.get_queue()
    queue_running = queue.get("queue_running", [])
    queue_pending = queue.get("queue_pending", [])

    # Get system stats
    system_stats = await client.get_system_stats()

    # Get event health
    event_mgr = _event_mgr(ctx)
    event_health = event_mgr.health() if hasattr(event_mgr, "health") else {}

    return json.dumps({
        "queue": {
            "running": len(queue_running),
            "pending": len(queue_pending),
        },
        "system": system_stats,
        "events": event_health,
    })

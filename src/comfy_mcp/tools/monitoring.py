"""Monitoring tools — 6 tools for real-time monitoring and event management."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

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
async def comfy_watch_progress(prompt_id: str, ctx: Context = None) -> str:
    """Poll EventManager for a prompt's execution progress.

    Args:
        prompt_id: The prompt ID to watch

    Returns:
        JSON with progress data or "no progress yet" status
    """
    event_mgr = _event_mgr(ctx)
    progress = event_mgr.get_latest_progress(prompt_id)
    if progress:
        return json.dumps({"status": "ok", "progress": progress})
    return json.dumps({"status": "no_progress", "prompt_id": prompt_id})


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
async def comfy_describe_dynamics(ctx: Context = None) -> str:
    """One-shot snapshot of system dynamics (queue + recent events + active jobs).

    Returns:
        JSON summary with queue counts, event types seen, active job count
    """
    client = _client(ctx)
    event_mgr = _event_mgr(ctx)
    job_tracker = _job_tracker(ctx)

    # Get queue state
    queue = await client.get_queue()
    queue_running = queue.get("queue_running", [])
    queue_pending = queue.get("queue_pending", [])

    # Get recent events (small window to avoid draining all)
    recent_events = event_mgr.drain_events(limit=10)
    event_types = set()
    if recent_events:
        for event in recent_events:
            event_types.add(event.get("type", "unknown"))

    # Get active jobs from job_tracker
    active_jobs = job_tracker.list_active()

    return json.dumps({
        "queue": {
            "running": len(queue_running),
            "pending": len(queue_pending),
        },
        "events": {
            "recent_count": len(recent_events) if recent_events else 0,
            "types_seen": list(event_types),
        },
        "jobs": {
            "active": len(active_jobs) if active_jobs else 0,
        },
    })


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
    """One-shot status overview (queue + GPU + execution state).

    Returns:
        Combined status JSON with queue info and system stats
    """
    client = _client(ctx)

    # Get queue
    queue = await client.get_queue()
    queue_running = queue.get("queue_running", [])
    queue_pending = queue.get("queue_pending", [])

    # Get system stats
    system_stats = await client.get_system_stats()

    return json.dumps({
        "queue": {
            "running": len(queue_running),
            "pending": len(queue_pending),
        },
        "system": system_stats,
    })

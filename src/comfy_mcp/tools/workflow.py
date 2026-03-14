"""Workflow tools — 8 tools for workflow execution and queue management."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


@mcp.tool(
    annotations={
        "title": "Queue Prompt",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_queue_prompt(
    workflow: dict,
    front: bool = False,
    ctx: Context = None,
) -> str:
    """Queue a workflow for execution.

    Args:
        workflow: Workflow dict to queue
        front: If True, insert at front of queue instead of back
    """
    await ctx.report_progress(0, 100)
    result = await _client(ctx).queue_prompt(workflow, front=front)
    prompt_id = result.get("prompt_id")

    # Register with job tracker
    job_tracker = ctx.request_context.lifespan_context["job_tracker"]
    if prompt_id:
        await job_tracker.track(prompt_id)

    await ctx.report_progress(100, 100)

    # Preserve full upstream response alongside normalized fields
    response = {
        "prompt_id": prompt_id,
        "queue_position": result.get("number"),
    }
    # Preserve validation errors from ComfyUI if present
    if "error" in result:
        response["error"] = result["error"]
    if "node_errors" in result:
        response["node_errors"] = result["node_errors"]

    return json.dumps(response, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Queue",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_queue(ctx: Context = None) -> str:
    """Get current queue state including running and pending prompts."""
    result = await _client(ctx).get_queue()
    queue_running = result.get("queue_running", [])
    queue_pending = result.get("queue_pending", [])
    return json.dumps({
        "queue_running": queue_running,
        "queue_pending": queue_pending,
        "running_count": len(queue_running),
        "pending_count": len(queue_pending),
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Cancel Run",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_cancel_run(
    prompt_id: str,
    ctx: Context = None,
) -> str:
    """Cancel a specific queued prompt by ID.

    Args:
        prompt_id: The prompt ID to cancel
    """
    result = await _client(ctx).cancel_prompt(prompt_id)
    return json.dumps({
        "status": "cancelled",
        "prompt_id": prompt_id,
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Interrupt",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_interrupt(ctx: Context = None) -> str:
    """Interrupt the currently executing prompt."""
    await _client(ctx).interrupt()
    return json.dumps({
        "status": "interrupted",
        "message": "Current prompt execution interrupted",
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Clear Queue",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_clear_queue(ctx: Context = None) -> str:
    """Clear all pending prompts from the queue."""
    await _client(ctx).clear_queue()
    return json.dumps({
        "status": "cleared",
        "message": "All pending prompts removed from queue",
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Validate Workflow",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_validate_workflow(
    workflow: dict,
    ctx: Context = None,
) -> str:
    """Validate a workflow dict structure without executing.

    Performs client-side validation: checks it's a dict, each node has 'class_type', etc.
    Does not call the ComfyUI API.
    """
    errors: list[str] = []

    # Check it's a dict
    if not isinstance(workflow, dict):
        errors.append("Workflow must be a dict")
        return json.dumps({
            "valid": False,
            "errors": errors,
            "node_count": 0,
        }, indent=2)

    # Empty workflow is invalid
    if not workflow:
        errors.append("Workflow cannot be empty")
        return json.dumps({
            "valid": False,
            "errors": errors,
            "node_count": 0,
        }, indent=2)

    # Check each node has class_type
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            errors.append(f"Node '{node_id}' is not a dict: {type(node)}")
            continue
        if "class_type" not in node:
            errors.append(f"Node '{node_id}' missing 'class_type' field")

    return json.dumps({
        "valid": len(errors) == 0,
        "errors": errors,
        "node_count": len(workflow),
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Export Workflow",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_export_workflow(
    workflow: dict,
    ctx: Context = None,
) -> str:
    """Export/serialize a workflow to JSON string.

    Simply returns the workflow formatted nicely as JSON string.
    """
    return json.dumps(workflow, indent=2)


@mcp.tool(
    annotations={
        "title": "Import Workflow",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_import_workflow(
    workflow_json: str,
    ctx: Context = None,
) -> str:
    """Parse a JSON string into a workflow dict.

    Parses the JSON string and validates basic structure.
    Returns the parsed workflow dict as JSON.
    """
    try:
        workflow = json.loads(workflow_json)
        if not isinstance(workflow, dict):
            return json.dumps({
                "error": "Parsed JSON is not a dict",
                "workflow": None,
            }, indent=2)
        return json.dumps(workflow, indent=2)
    except json.JSONDecodeError as e:
        return json.dumps({
            "error": f"Invalid JSON: {str(e)}",
            "workflow": None,
        }, indent=2)

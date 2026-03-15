"""Workflow tools - 8 tools for workflow execution and queue management."""

from __future__ import annotations

import inspect
import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


def _job_tracker(ctx: Context):
    return ctx.request_context.lifespan_context["job_tracker"]


def _maybe_auto_snapshot(ctx: Context | None, workflow: dict) -> dict | None:
    if ctx is None:
        return None

    snapshot_mgr = ctx.request_context.lifespan_context.get("snapshot_manager")
    if snapshot_mgr is None or getattr(snapshot_mgr, "auto_snapshot", False) is not True:
        return None

    return snapshot_mgr.add(workflow, name="auto-before-queue")


def _prompt_ids_from_queue(entries: list[Any]) -> list[str]:
    prompt_ids: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            prompt_ids.append(entry)
        elif isinstance(entry, (list, tuple)) and entry:
            prompt_ids.append(str(entry[0]))
        elif isinstance(entry, dict):
            prompt_id = entry.get("prompt_id") or entry.get("id")
            if prompt_id:
                prompt_ids.append(str(prompt_id))
    return prompt_ids


async def _await_if_needed(result: Any) -> Any:
    if inspect.isawaitable(result):
        return await result
    return result


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
    snapshot = _maybe_auto_snapshot(ctx, workflow)
    result = await _client(ctx).queue_prompt(workflow, front=front)
    prompt_id = result.get("prompt_id")

    # Register with job tracker
    job_tracker = _job_tracker(ctx)
    if prompt_id:
        await _await_if_needed(job_tracker.track(prompt_id))

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
    if snapshot is not None:
        response["auto_snapshot"] = snapshot

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
    job_tracker = ctx.request_context.lifespan_context["job_tracker"]
    await _await_if_needed(job_tracker.mark_cancelled(prompt_id))
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
    running_ids = _prompt_ids_from_queue((await _client(ctx).get_queue()).get("queue_running", []))
    await _client(ctx).interrupt()
    tracker = _job_tracker(ctx)
    for prompt_id in running_ids:
        await _await_if_needed(tracker.mark_interrupted(prompt_id))
    return json.dumps({
        "status": "interrupted",
        "message": "Current prompt execution interrupted",
        "interrupted_prompt_ids": running_ids,
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
    """Validate a workflow against ComfyUI's node catalog.

    Performs three validation passes:
    1. Schema: dict structure, class_type presence
    2. Catalog: node types exist in object_info
    3. Graph: link targets reference real nodes
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Pass 1: Schema
    if not isinstance(workflow, dict):
        return json.dumps({"valid": False, "errors": ["Workflow must be a dict"], "warnings": [], "node_count": 0}, indent=2)
    if not workflow:
        return json.dumps({"valid": False, "errors": ["Workflow cannot be empty"], "warnings": [], "node_count": 0}, indent=2)

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            errors.append(f"Node '{node_id}' is not a dict: {type(node)}")
            continue
        if "class_type" not in node:
            errors.append(f"Node '{node_id}' missing 'class_type' field")

    # Pass 2: Catalog (if we can reach ComfyUI)
    catalog = None
    catalog_available = False
    try:
        result = await _client(ctx).get_object_info()
        if isinstance(result, dict) and result:
            catalog = result
            catalog_available = True
    except Exception:
        warnings.append("Could not fetch object_info - skipping catalog validation")

    if catalog_available and catalog:
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type", "")
            if class_type and class_type not in catalog:
                errors.append(f"Node '{node_id}': unknown class_type '{class_type}' - not in ComfyUI catalog")

    # Pass 3: Graph - check link targets
    node_ids = set(workflow.keys())
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        for input_name, input_val in node.get("inputs", {}).items():
            if isinstance(input_val, list) and len(input_val) == 2:
                source_id = str(input_val[0])
                if source_id not in node_ids:
                    errors.append(f"Node '{node_id}'.{input_name}: links to non-existent node '{source_id}'")

    # Check for output nodes
    has_output = False
    output_types = {"SaveImage", "PreviewImage", "SaveAnimatedWEBP", "SaveAnimatedPNG"}
    for node in workflow.values():
        if isinstance(node, dict) and node.get("class_type") in output_types:
            has_output = True
            break
    if not has_output:
        warnings.append("No output node found (SaveImage, PreviewImage, etc.) - workflow may produce no visible output")

    return json.dumps({
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "node_count": len(workflow),
        "passes": ["schema", "catalog" if catalog_available else "catalog_skipped", "graph"],
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

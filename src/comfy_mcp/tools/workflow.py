"""Workflow tools — 8 tools for workflow execution and queue management."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp
from comfy_mcp.workflow_formats import describe_workflow
from comfy_mcp.workflow_translation import translate_workflow


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
    workflow_info = describe_workflow(workflow)
    if workflow_info["format"] != "api-prompt":
        return json.dumps({
            "error": "Workflow must be in ComfyUI API prompt format before queueing.",
            "workflow_format": workflow_info["format"],
            "workflow_summary": workflow_info["summary"],
            "suggested_next_step": "Use comfy_translate_workflow for supported UI workflows before queueing.",
        }, indent=2)

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
    job_tracker = ctx.request_context.lifespan_context["job_tracker"]
    await job_tracker.mark_cancelled(prompt_id)
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
    client = _client(ctx)
    # Snapshot queue BEFORE interrupt so running entries are still present
    queue = await client.get_queue()
    await client.interrupt()
    running_ids = set()
    for entry in queue.get("queue_running", []):
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            running_ids.add(str(entry[1]))
        elif isinstance(entry, dict) and "prompt_id" in entry:
            running_ids.add(entry["prompt_id"])
    job_tracker = ctx.request_context.lifespan_context["job_tracker"]
    job_tracker.refresh_active_states(running_prompt_ids=running_ids)
    interrupted_ids = []
    queued_ids = []
    for job in job_tracker.list_active():
        if job["status"] == "running":
            await job_tracker.mark_interrupted(job["prompt_id"])
            interrupted_ids.append(job["prompt_id"])
        else:
            queued_ids.append(job["prompt_id"])
    response = {
        "status": "interrupted",
        "message": "Current prompt execution interrupted",
        "interrupted_prompt_ids": interrupted_ids,
    }
    if queued_ids:
        response["queued_prompt_ids_unchanged"] = queued_ids
    return json.dumps(response, indent=2)


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

    workflow_info = describe_workflow(workflow)
    if workflow_info["format"] == "comfyui-ui":
        return json.dumps({
            "valid": False,
            "errors": [
                "Workflow is in ComfyUI UI workflow format, not API prompt format.",
                "Use it as a reference workflow or translate it before queueing.",
            ],
            "warnings": [],
            "node_count": workflow_info["summary"].get("node_count", 0),
            "workflow_format": workflow_info["format"],
            "workflow_summary": workflow_info["summary"],
            "passes": ["format"],
        }, indent=2)

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
        warnings.append("Could not fetch object_info — skipping catalog validation")

    if catalog_available and catalog:
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type", "")
            if class_type and class_type not in catalog:
                errors.append(f"Node '{node_id}': unknown class_type '{class_type}' — not in ComfyUI catalog")

    # Pass 3: Graph — check link targets
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
        warnings.append("No output node found (SaveImage, PreviewImage, etc.) — workflow may produce no visible output")

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
        "title": "Translate Workflow",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_translate_workflow(
    workflow: dict,
    ctx: Context = None,
) -> str:
    """Attempt a conservative translation from UI workflow JSON to API prompt format."""
    install_graph = ctx.request_context.lifespan_context.get("install_graph") if ctx else None
    snapshot = getattr(install_graph, "snapshot", None) if install_graph else None
    object_info = snapshot.get("object_info", {}) if snapshot else {}
    if not object_info:
        return json.dumps({
            "error": "Install graph object_info is required. Run comfy_refresh_install_graph first.",
        }, indent=2)

    result = translate_workflow(workflow, object_info)
    return json.dumps(result, indent=2)


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
        if workflow == {}:
            return json.dumps(workflow, indent=2)
        workflow_info = describe_workflow(workflow)
        if workflow_info["format"] != "api-prompt":
            response = {
                "format": workflow_info["format"],
                "workflow": workflow,
                "workflow_summary": workflow_info["summary"],
                "warning": (
                    "Imported JSON is not in ComfyUI API prompt format. "
                    "It can be kept as a reference workflow but cannot be queued directly."
                ),
            }
            install_graph = ctx.request_context.lifespan_context.get("install_graph") if ctx else None
            snapshot = getattr(install_graph, "snapshot", None) if install_graph else None
            object_info = snapshot.get("object_info", {}) if snapshot else {}
            if workflow_info["format"] == "comfyui-ui" and object_info:
                translation = translate_workflow(workflow, object_info)
                response["translation_report"] = translation
                if translation["status"] == "translated":
                    response["translated_workflow"] = translation["workflow"]
            return json.dumps(response, indent=2)
        return json.dumps(workflow, indent=2)
    except json.JSONDecodeError as e:
        return json.dumps({
            "error": f"Invalid JSON: {str(e)}",
            "workflow": None,
        }, indent=2)

"""Workflow tools - 8 tools for workflow execution and queue management.

Validation is now multi-pass: schema -> catalog -> graph -> environment. The
environment pass cross-checks that every model filename referenced by a
loader node actually exists in the corresponding /models/ folder. This is
the difference between "the workflow is syntactically valid" and "the
workflow can actually run on this server right now."
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.responses import QueueAck, ValidationReport
from comfy_mcp.server import mcp


# Maps node class_type -> [(input_field, /models/ folder), ...] so the validator
# environment pass can cross-check every referenced model filename against the
# list that ComfyUI actually has installed. Extend when new loader nodes land.
_MODEL_INPUT_FIELDS: dict[str, list[tuple[str, str]]] = {
    "CheckpointLoaderSimple": [("ckpt_name", "checkpoints")],
    "CheckpointLoader": [("ckpt_name", "checkpoints"), ("config_name", "configs")],
    "UNETLoader": [("unet_name", "diffusion_models")],
    "VAELoader": [("vae_name", "vae")],
    "LoraLoader": [("lora_name", "loras")],
    "LoraLoaderModelOnly": [("lora_name", "loras")],
    "ControlNetLoader": [("control_net_name", "controlnet")],
    "CLIPLoader": [("clip_name", "text_encoders")],
    "DualCLIPLoader": [("clip_name1", "text_encoders"), ("clip_name2", "text_encoders")],
    "TripleCLIPLoader": [
        ("clip_name1", "text_encoders"),
        ("clip_name2", "text_encoders"),
        ("clip_name3", "text_encoders"),
    ],
    "CLIPVisionLoader": [("clip_name", "clip_vision")],
    "StyleModelLoader": [("style_model_name", "style_models")],
    "UpscaleModelLoader": [("model_name", "upscale_models")],
    "GLIGENLoader": [("gligen_name", "gligen")],
}


# Node class_types that create an image-shaped latent (width x height x batch).
_LATENT_IMAGE_NODES = {
    "EmptyLatentImage",
    "EmptySD3LatentImage",
}


# Node class_types that create a video-shaped latent (width x height x length x batch).
_LATENT_VIDEO_NODES = {
    "EmptyHunyuanLatentVideo",
    "EmptyLTXVLatentVideo",
}


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
) -> QueueAck:
    """Queue a workflow for execution. Returns structured QueueAck.

    Args:
        workflow: Workflow dict to queue
        front: If True, insert at front of queue instead of back
    """
    await ctx.report_progress(0, 100)
    snapshot = _maybe_auto_snapshot(ctx, workflow)
    result = await _client(ctx).queue_prompt(workflow, front=front)
    prompt_id = result.get("prompt_id")

    job_tracker = _job_tracker(ctx)
    if prompt_id:
        await _await_if_needed(job_tracker.track(prompt_id))

    await ctx.report_progress(100, 100)

    return QueueAck(
        prompt_id=prompt_id,
        queue_position=result.get("number"),
        error=result.get("error"),
        node_errors=result.get("node_errors"),
        auto_snapshot=snapshot,
    )


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
async def comfy_clear_queue(confirm: bool = False, ctx: Context = None) -> str:
    """Clear all pending prompts from the queue. Destructive.

    Args:
        confirm: If False, the tool asks for explicit confirmation via
            elicitation before proceeding. Pass True to skip the prompt.
    """
    from comfy_mcp.safety.confirm import confirm_destructive
    if not await confirm_destructive(ctx, "Clear all pending prompts from the ComfyUI queue?", confirm):
        return json.dumps({"status": "cancelled", "reason": "user_declined"}, indent=2)

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
) -> ValidationReport:
    """Validate a workflow with a 5-pass check. Returns structured ValidationReport.

    Passes: schema -> catalog -> graph -> environment -> execution_risk.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Pass 1: Schema
    if not isinstance(workflow, dict):
        return ValidationReport(valid=False, errors=["Workflow must be a dict"], node_count=0, passes=["schema"])
    if not workflow:
        return ValidationReport(valid=False, errors=["Workflow cannot be empty"], node_count=0, passes=["schema"])

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

    # Pass 4: Environment - referenced model files exist in ComfyUI's model folders
    env_checked = False
    referenced_models: dict[str, set[str]] = {}
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        node_inputs = node.get("inputs", {}) or {}
        for field, folder in _MODEL_INPUT_FIELDS.get(class_type, []):
            val = node_inputs.get(field)
            if isinstance(val, str) and val:
                referenced_models.setdefault(folder, set()).add(val)

    if referenced_models:
        any_folder_checked = False
        for folder, names in referenced_models.items():
            try:
                installed = set(await _client(ctx).get_models(folder))
            except Exception:
                warnings.append(f"Environment: could not list /models/{folder} - skipped")
                continue
            any_folder_checked = True
            missing = sorted(names - installed)
            for n in missing:
                errors.append(f"Environment: model {n!r} not found in /models/{folder}")
        env_checked = any_folder_checked
    else:
        # No model-loading nodes in workflow - nothing to check, treat as pass
        env_checked = True

    # Pass 5: Execution risk - latent volume + VRAM headroom
    risk_checked = False
    try:
        latent_pixels = 0
        latent_frames = 0
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type", "")
            inp = node.get("inputs", {}) or {}
            if class_type in _LATENT_IMAGE_NODES:
                w = int(inp.get("width", 0) or 0)
                h = int(inp.get("height", 0) or 0)
                b = int(inp.get("batch_size", 1) or 1)
                latent_pixels += w * h * b
            elif class_type in _LATENT_VIDEO_NODES:
                w = int(inp.get("width", 0) or 0)
                h = int(inp.get("height", 0) or 0)
                length = int(inp.get("length", 1) or 1)
                b = int(inp.get("batch_size", 1) or 1)
                latent_pixels += w * h * length * b
                latent_frames += length * b

        # Hard error at >64M pixels (4K x 4K x 4), warn at >16M (2K x 2K x 4)
        if latent_pixels > 64_000_000:
            errors.append(
                f"Execution risk: total latent volume {latent_pixels:,} pixels likely OOM on most GPUs"
            )
        elif latent_pixels > 16_000_000:
            warnings.append(
                f"Execution risk: large latent volume {latent_pixels:,} pixels - confirm VRAM headroom"
            )

        # VRAM headroom cross-check when a VRAMGuard is available
        vg = ctx.request_context.lifespan_context.get("vram_guard") if ctx else None
        if vg is not None and latent_pixels > 0:
            free_mb = None
            try:
                if hasattr(vg, "estimated_headroom_mb"):
                    headroom = vg.estimated_headroom_mb()
                    free_mb = await headroom if inspect.isawaitable(headroom) else headroom
            except Exception:
                free_mb = None
            if isinstance(free_mb, (int, float)):
                # Rough estimate: 16 MB per megapixel for SD-class latent
                est_needed_mb = (latent_pixels / 1_000_000) * 16
                if est_needed_mb > free_mb:
                    warnings.append(
                        f"Execution risk: estimated {est_needed_mb:.0f} MB needed, "
                        f"{free_mb:.0f} MB VRAM headroom reported"
                    )

        risk_checked = True
    except Exception as e:
        warnings.append(f"Execution-risk pass error: {e}")

    # Check for output nodes
    has_output = False
    output_types = {
        "SaveImage", "PreviewImage", "SaveAnimatedWEBP", "SaveAnimatedPNG",
        "SaveGLB", "SaveAudio",
    }
    for node in workflow.values():
        if isinstance(node, dict) and node.get("class_type") in output_types:
            has_output = True
            break
    if not has_output:
        warnings.append("No output node found (SaveImage, SaveAnimatedWEBP, SaveGLB, SaveAudio, etc.) - workflow may produce no visible output")

    return ValidationReport(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        node_count=len(workflow),
        passes=[
            "schema",
            "catalog" if catalog_available else "catalog_skipped",
            "graph",
            "environment" if env_checked else "environment_skipped",
            "execution_risk" if risk_checked else "execution_risk_skipped",
        ],
    )


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

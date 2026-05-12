"""comfy_run_with_inputs - upload local images and queue in one shot.

img2img / inpaint workflows usually need a local image uploaded first,
then the workflow patched to reference the uploaded filename, then
queued. This tool collapses the three steps into one MCP call.

Input shape:
    inputs = {"image": "/local/path/photo.png", "mask_image": "/local/path/mask.png"}

For each (label, path):
1. Read the local file bytes.
2. POST /upload/image to ComfyUI, capturing the canonical filename.
3. Patch the workflow: find LoadImage nodes whose `image` widget matches
   the label, and replace with the uploaded filename. Also accept
   explicit "{node_id}.{input}" labels for finer targeting.
4. Queue the patched workflow.
"""
from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path

from mcp.server.fastmcp import Context

from comfy_mcp.responses import QueueAck
from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


def _job_tracker(ctx: Context):
    return ctx.request_context.lifespan_context.get("job_tracker")


def _read_local_file(path: str) -> bytes:
    """Read bytes from a local path; raise FileNotFoundError / ValueError."""
    if not path:
        raise ValueError("input path cannot be empty")
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {p}")
    if not p.is_file():
        raise ValueError(f"Input path is not a regular file: {p}")
    return p.read_bytes()


def _apply_label_to_workflow(
    workflow: dict,
    label: str,
    canonical_filename: str,
) -> list[str]:
    """Patch every node input matching `label` to point at the uploaded file.

    Label resolution:
    - "node_id.input" - explicit: patch exactly that node's input.
    - "input_name"    - implicit: patch every LoadImage / VHS_LoadVideo / etc.
                        whose input field name matches `label`. Also patches
                        any node that has an input field named `label` whose
                        current widget value looks like a filename string.

    Returns the list of "node_id.input_name" assignments that were applied.
    """
    assignments: list[str] = []

    if "." in label and label.count(".") == 1:
        node_id, field = label.split(".", 1)
        if node_id in workflow and isinstance(workflow[node_id], dict):
            workflow[node_id].setdefault("inputs", {})[field] = canonical_filename
            assignments.append(f"{node_id}.{field}")
        return assignments

    # Implicit: match input field name across all nodes.
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {}) or {}
        if label not in inputs:
            continue
        current = inputs[label]
        # Only patch widget-style (string) values - don't overwrite link tuples.
        if isinstance(current, str):
            inputs[label] = canonical_filename
            assignments.append(f"{node_id}.{label}")

    return assignments


@mcp.tool(
    annotations={
        "title": "Run Workflow with Local Inputs",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def comfy_run_with_inputs(
    workflow: dict,
    inputs: dict,
    front: bool = False,
    ctx: Context = None,
) -> QueueAck:
    """Upload local images, inject as workflow inputs, then queue.

    Combines the three-step img2img / inpaint flow (upload + patch + queue)
    into one tool call. Each entry in `inputs` is a (label, local_path)
    pair: the file is uploaded to ComfyUI's input directory and the
    workflow's matching input widget is set to the uploaded filename.

    Args:
        workflow: API-format workflow dict (will be deep-copied before
            patching - the caller's dict is not mutated).
        inputs: Mapping of label -> local file path. Labels may be
            "node_id.input_name" for explicit targeting or just
            "input_name" to patch every matching widget.
        front: Insert at the front of the queue (default False).

    Returns:
        QueueAck (typed) with prompt_id, queue_position, plus an
        `auto_snapshot` field listing the upload mapping that was applied.
    """
    if not isinstance(workflow, dict) or not workflow:
        return QueueAck(error="workflow must be a non-empty dict")
    if not isinstance(inputs, dict):
        return QueueAck(error="inputs must be a dict of label -> local path")

    patched = copy.deepcopy(workflow)
    upload_map: dict[str, dict] = {}

    client = _client(ctx)
    for label, local_path in inputs.items():
        try:
            data = _read_local_file(str(local_path))
        except (FileNotFoundError, ValueError) as e:
            return QueueAck(error=f"Input '{label}' failed: {e}")

        filename = Path(str(local_path)).name
        try:
            upload_resp = await client.upload_image(
                data, filename, subfolder="", image_type="input", overwrite=True,
            )
        except Exception as e:
            return QueueAck(error=f"Upload for label '{label}' failed: {e}")

        canonical = (
            upload_resp.get("name") if isinstance(upload_resp, dict) else None
        ) or filename
        applied = _apply_label_to_workflow(patched, label, canonical)
        upload_map[label] = {
            "local_path": str(local_path),
            "uploaded_filename": canonical,
            "size_bytes": len(data),
            "applied_to": applied,
        }

    try:
        result = await client.queue_prompt(patched, front=front)
    except Exception as e:
        return QueueAck(error=f"queue_prompt failed: {e}")

    prompt_id = result.get("prompt_id") if isinstance(result, dict) else None

    tracker = _job_tracker(ctx)
    if prompt_id and tracker is not None:
        try:
            maybe = tracker.track(prompt_id)
            if hasattr(maybe, "__await__"):
                await maybe
        except Exception:
            pass

    return QueueAck(
        prompt_id=prompt_id,
        queue_position=result.get("number") if isinstance(result, dict) else None,
        error=result.get("error") if isinstance(result, dict) else None,
        node_errors=result.get("node_errors") if isinstance(result, dict) else None,
        upload_map=upload_map,
    )

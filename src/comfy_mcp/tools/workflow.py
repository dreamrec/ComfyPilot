"""Workflow tools - 11 tools for workflow execution and queue management.

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
from comfy_mcp.schemas.node_schema import InputSpec, NodeSchema, parse_object_info
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


def _is_link_value(value: Any) -> bool:
    """Return whether *value* has ComfyUI's ``[node_id, output_index]`` shape."""
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    )


def _detect_cycle(
    workflow: dict,
    link_inputs: set[tuple[str, str]] | None = None,
) -> list[str]:
    """Return node IDs forming a sample cycle, or [] if the workflow is acyclic.

    ComfyUI v0.20.0 added anti-cycle validation to its execution engine. We
    mirror that check client-side so cyclic graphs fail validation before
    they hit /prompt. Build a dependency graph (target -> set of sources it
    links from) and run an iterative DFS with 3-coloring. The first back
    edge found returns the gray-path stack so the caller can name the cycle.
    """
    deps: dict[str, set[str]] = {}
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        sources: set[str] = set()
        for input_name, inp in (node.get("inputs", {}) or {}).items():
            if link_inputs is not None and (str(node_id), str(input_name)) not in link_inputs:
                continue
            if _is_link_value(inp):
                src = str(inp[0])
                if src in workflow:
                    sources.add(src)
        deps[node_id] = sources

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {nid: WHITE for nid in deps}

    for start in sorted(deps):
        if color[start] != WHITE:
            continue
        stack: list[tuple[str, list[str]]] = [(start, sorted(deps[start]))]
        color[start] = GRAY
        while stack:
            node, todo = stack[-1]
            if not todo:
                color[node] = BLACK
                stack.pop()
                continue
            nb = todo.pop()
            nb_color = color.get(nb, WHITE)
            if nb_color == GRAY:
                # Back edge - cycle. Return the gray frames from `nb` onward.
                gray_path = [n for n, _ in stack]
                if nb in gray_path:
                    idx = gray_path.index(nb)
                    return gray_path[idx:]
                return gray_path + [nb]
            if nb_color == WHITE:
                color[nb] = GRAY
                stack.append((nb, sorted(deps.get(nb, ()))))

    return []


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
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            # Current ComfyUI queue tuples are
            # (monotonic_number, prompt_id, prompt, extra_data, outputs_to_execute).
            # Older ComfyPilot tests accidentally encoded the reverse order.
            prompt_ids.append(str(entry[1]))
        elif isinstance(entry, dict):
            prompt_id = entry.get("prompt_id") or entry.get("id")
            if prompt_id:
                prompt_ids.append(str(prompt_id))
    return prompt_ids


def _is_ui_only_input(spec: InputSpec) -> bool:
    constraints = spec.constraints or {}
    return (
        str(constraints.get("mode", "")).lower() in {"divider", "spacer", "separator"}
        or spec.type_name.upper() in {"ZIPN_SEPARATOR", "DIVIDER", "SEPARATOR"}
    )


def _choice_values(spec: InputSpec) -> list[Any] | None:
    constraints = spec.constraints or {}
    choices = constraints.get("choices", constraints.get("options"))
    if isinstance(choices, (list, tuple)):
        return list(choices)
    return None


def _validate_scalar_value(path: str, value: Any, spec: InputSpec, errors: list[str]) -> None:
    """Validate a non-link API input against a normalized object_info spec."""
    type_name = spec.type_name.upper()
    constraints = spec.constraints or {}

    if type_name == "COMFY_DYNAMICCOMBO_V3":
        options = constraints.get("options")
        keys = [item.get("key") for item in options or [] if isinstance(item, dict)]
        if not isinstance(value, str):
            errors.append(
                f"{path}: DynamicCombo selector must be a string key with child values "
                f"flattened as '{spec.name}.<input>'; nested objects are not API format"
            )
        elif keys and value not in keys:
            errors.append(f"{path}: value {value!r} is not one of {keys!r}")
        return

    choices = _choice_values(spec)
    if choices is not None:
        multiselect = bool(constraints.get("multiselect", False))
        values = value if multiselect and isinstance(value, list) else [value]
        if multiselect and not isinstance(value, list):
            errors.append(f"{path}: expected a list of choices")
            return
        invalid = [item for item in values if item not in choices]
        if invalid:
            errors.append(f"{path}: value {invalid[0]!r} is not one of {choices!r}")
        return

    valid_type = True
    expected = type_name
    if type_name == "INT":
        valid_type = isinstance(value, int) and not isinstance(value, bool)
    elif type_name == "FLOAT":
        valid_type = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif type_name in {"BOOLEAN", "BOOL"}:
        valid_type = isinstance(value, bool)
    elif type_name == "STRING":
        valid_type = isinstance(value, str)
    elif type_name == "RANGE":
        valid_type = (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
        )

    if not valid_type:
        errors.append(f"{path}: expected {expected}, got {type(value).__name__}")
        return

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = constraints.get("min")
        maximum = constraints.get("max")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"{path}: value {value!r} is below minimum {minimum!r}")
        if isinstance(maximum, (int, float)) and value > maximum:
            errors.append(f"{path}: value {value!r} exceeds maximum {maximum!r}")


def _types_compatible(source_type: str, target_type: str) -> bool:
    """Conservative socket compatibility for catalog types and union types."""
    def split(value: str) -> set[str]:
        return {part.strip().upper() for part in str(value).split(",") if part.strip()}

    source = split(source_type)
    target = split(target_type)
    wildcards = {"*", "ANY", "ANY_TYPE", "UNKNOWN"}
    if source & wildcards or target & wildcards:
        return True
    if source & target:
        return True
    numeric = {"INT", "FLOAT", "NUMBER"}
    return bool(source & numeric and target & numeric and "NUMBER" in (source | target))


def _dynamic_child_specs(spec: InputSpec, selected: Any) -> dict[str, InputSpec]:
    """Return normalized child specs for the selected DynamicCombo option."""
    options = (spec.constraints or {}).get("options")
    for option in options or []:
        if not isinstance(option, dict) or option.get("key") != selected:
            continue
        result: dict[str, InputSpec] = {}
        inputs = option.get("inputs") or {}
        for required, group_name in ((True, "required"), (False, "optional")):
            group = inputs.get(group_name) or {}
            if not isinstance(group, dict):
                continue
            for child_name, raw in group.items():
                # Reuse the V1 parser for an individual DynamicCombo child.
                child_schema = parse_object_info(
                    "_DynamicChild",
                    {"input": {group_name: {child_name: raw}}, "output": []},
                )
                if child_schema.inputs:
                    child = child_schema.inputs[0]
                    child.required = required
                    result[child_name] = child
        return result
    return {}


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
    workflow_id: str | None = None,
    workflow_version_id: str | None = None,
    partial_execution_targets: list[str] | None = None,
    extra_data: dict[str, Any] | None = None,
    ctx: Context = None,
) -> QueueAck:
    """Queue a workflow for execution. Returns structured QueueAck.

    Args:
        workflow: Workflow dict to queue
        front: If True, insert at front of queue instead of back
        workflow_id: Optional stable workflow UUID for ComfyUI job metadata
        workflow_version_id: Optional workflow-version UUID
        partial_execution_targets: Optional output node IDs to execute
        extra_data: Optional metadata to attach to the queued prompt
    """
    await ctx.report_progress(0, 100)
    snapshot = _maybe_auto_snapshot(ctx, workflow)
    metadata = {
        "workflow_id": workflow_id,
        "workflow_version_id": workflow_version_id,
        "partial_execution_targets": partial_execution_targets,
        "extra_data": extra_data,
    }
    if any(value is not None for value in metadata.values()):
        result = await _client(ctx).queue_prompt(workflow, front=front, **metadata)
    else:
        # Preserve the historical call shape for older client adapters.
        result = await _client(ctx).queue_prompt(workflow, front=front)
    prompt_id = result.get("prompt_id")

    job_tracker = _job_tracker(ctx)
    if prompt_id:
        await _await_if_needed(job_tracker.track(prompt_id))

    await ctx.report_progress(100, 100)

    return QueueAck(
        prompt_id=prompt_id,
        queue_number=result.get("number"),
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
    """Cancel a running or queued prompt by ID.

    Args:
        prompt_id: The prompt ID to cancel
    """
    result = await _client(ctx).cancel_prompt(prompt_id)
    cancelled = result.get("cancelled", True) if isinstance(result, dict) else True
    if cancelled:
        job_tracker = ctx.request_context.lifespan_context["job_tracker"]
        await _await_if_needed(job_tracker.mark_cancelled(prompt_id))
    return json.dumps({
        "status": "cancelled" if cancelled else "not_found",
        "prompt_id": prompt_id,
        "result": result,
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "List Jobs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_jobs(
    status: str | None = None,
    workflow_id: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "desc",
    limit: int = 100,
    offset: int = 0,
    after: str | None = None,
    ctx: Context = None,
) -> str:
    """List ComfyUI jobs using the v0.20+ canonical jobs API.

    Args:
        status: Optional job state filter
        workflow_id: Optional workflow UUID filter
        sort_by: Optional server-supported sort field
        sort_order: `asc` or `desc`
        limit: Maximum records to return (1-1000)
        offset: Offset pagination when `after` is omitted
        after: Cursor pagination token when supported
    """
    if sort_order not in {"asc", "desc"}:
        return json.dumps({"error": "sort_order must be 'asc' or 'desc'"})
    limit = max(1, min(int(limit), 1000))
    offset = max(0, int(offset))
    result = await _client(ctx).get_jobs(
        status=status,
        workflow_id=workflow_id,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
        after=after,
    )
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Job",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_job(job_id: str, ctx: Context = None) -> str:
    """Get a full modern job record, with a legacy history fallback."""
    result = await _client(ctx).get_job(job_id)
    if not result:
        result = {
            "error": "not_found",
            "status": "not_found",
            "job_id": job_id,
        }
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Cancel Jobs",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_cancel_jobs(job_ids: list[str], ctx: Context = None) -> str:
    """Cancel multiple running or queued jobs (v0.26+, with legacy fallback)."""
    normalized = list(dict.fromkeys(str(value).strip() for value in job_ids if str(value).strip()))
    if not normalized:
        return json.dumps({"error": "job_ids must contain at least one ID"})
    result = await _client(ctx).cancel_jobs(normalized)
    cancelled = result.get("cancelled", True) if isinstance(result, dict) else True
    if cancelled:
        tracker = _job_tracker(ctx)
        for job_id in normalized:
            await _await_if_needed(tracker.mark_cancelled(job_id))
    return json.dumps(result, indent=2)


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
    """Validate a workflow with a 6-pass check. Returns structured ValidationReport.

    Passes: schema -> catalog -> graph -> anti_cycle -> environment -> execution_risk.
    A pre-pass detects ComfyUI editor-format (top-level `nodes`/`links` arrays)
    and short-circuits with a specific re-export instruction.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Pass 0 (pre-flight): Editor-format detection. ComfyUI's web UI exports
    # workflows in two shapes - "API format" (each top-level key is a node ID
    # whose value carries `class_type`) and "editor format" (top-level
    # `nodes` + `links` arrays plus `groups`/`config`/`extra` metadata). Only
    # API format is queueable. Catching this before pass 1 lets us issue a
    # specific, actionable error instead of "missing class_type" * N.
    if (
        isinstance(workflow, dict)
        and isinstance(workflow.get("nodes"), list)
        and isinstance(workflow.get("links"), list)
    ):
        return ValidationReport(
            valid=False,
            errors=[
                "Workflow appears to be in ComfyUI editor format (top-level "
                "'nodes' and 'links' arrays). Only API format is queueable. "
                "Open the workflow in ComfyUI's web UI and use Workflow -> "
                "Export (API) (or the legacy 'Save (API Format)' button) to "
                "re-export, then retry."
            ],
            node_count=len(workflow.get("nodes") or []),
            passes=["editor_format_detected"],
        )

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

    # Pass 2: Catalog/schema validation (if we can reach ComfyUI).  object_info
    # is the execution contract: validate every supplied value against it,
    # instead of maintaining a second, inevitably stale node allowlist.
    catalog: dict[str, Any] | None = None
    schemas: dict[str, NodeSchema] = {}
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
                continue
            if not class_type:
                continue
            try:
                schema = parse_object_info(class_type, catalog[class_type])
                schemas[str(node_id)] = schema
            except (TypeError, ValueError) as exc:
                warnings.append(f"Node '{node_id}': could not normalize catalog schema: {exc}")
                continue

            inputs = node.get("inputs", {})
            if not isinstance(inputs, dict):
                errors.append(f"Node '{node_id}'.inputs must be a dict")
                continue

            specs = {spec.name: spec for spec in schema.inputs}
            for spec in schema.inputs:
                if spec.required and not _is_ui_only_input(spec) and spec.name not in inputs:
                    errors.append(f"Node '{node_id}': missing required input '{spec.name}'")

            for input_name in inputs:
                if input_name not in specs:
                    errors.append(
                        f"Node '{node_id}'.{input_name}: unknown input for class_type '{class_type}'"
                    )

            # DynamicCombo V3 is serialized in API prompts as a string selector
            # plus flat ``selector.child`` fields.  The live catalog exposes the
            # flat children as optional inputs, so validate both the selector and
            # the selected option's children here.
            for spec in schema.inputs:
                if spec.name not in inputs or spec.type_name.upper() != "COMFY_DYNAMICCOMBO_V3":
                    continue
                selected = inputs[spec.name]
                _validate_scalar_value(f"Node '{node_id}'.{spec.name}", selected, spec, errors)
                child_specs = _dynamic_child_specs(spec, selected)
                allowed_flat = {f"{spec.name}.{name}" for name in child_specs}
                supplied_flat = {
                    name for name in inputs if name.startswith(f"{spec.name}.")
                }
                inactive = sorted(supplied_flat - allowed_flat)
                for name in inactive:
                    errors.append(
                        f"Node '{node_id}'.{name}: field is not valid for "
                        f"{spec.name}={selected!r}"
                    )
                for child_name, child_spec in child_specs.items():
                    flat_name = f"{spec.name}.{child_name}"
                    if flat_name in inputs:
                        _validate_scalar_value(
                            f"Node '{node_id}'.{flat_name}", inputs[flat_name], child_spec, errors
                        )

    # Pass 3: Graph - validate link shape, source output index, and socket type.
    node_ids = {str(value) for value in workflow.keys()}
    link_inputs: set[tuple[str, str]] = set()
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        schema = schemas.get(str(node_id))
        specs = {spec.name: spec for spec in schema.inputs} if schema else {}
        for input_name, input_val in inputs.items():
            spec = specs.get(input_name)
            expects_link = spec.is_link_target if spec is not None else _is_link_value(input_val)
            path = f"Node '{node_id}'.{input_name}"

            if expects_link:
                if not _is_link_value(input_val):
                    errors.append(f"{path}: expected a [source_node_id, output_index] link")
                    continue
                link_inputs.add((str(node_id), str(input_name)))
                source_id = str(input_val[0])
                if source_id not in node_ids:
                    errors.append(f"{path}: links to non-existent node '{source_id}'")
                    continue

                output_index = input_val[1]
                source_schema = schemas.get(source_id)
                if source_schema is not None:
                    if output_index < 0 or output_index >= len(source_schema.outputs):
                        errors.append(
                            f"{path}: output index {output_index} is out of range for "
                            f"node '{source_id}' ({len(source_schema.outputs)} outputs)"
                        )
                        continue
                    if spec is not None:
                        source_type = source_schema.outputs[output_index].type_name
                        if not _types_compatible(source_type, spec.type_name):
                            errors.append(
                                f"{path}: socket type mismatch; node '{source_id}' output "
                                f"{output_index} is {source_type}, expected {spec.type_name}"
                            )
            elif (
                spec is not None
                and not _is_ui_only_input(spec)
                and spec.type_name.upper() != "COMFY_DYNAMICCOMBO_V3"
            ):
                _validate_scalar_value(path, input_val, spec, errors)

    # Pass 4: Anti-cycle - mirror ComfyUI v0.20 execution-side cycle detection.
    # Catches A->B->A and self-loops that the graph pass alone misses (a link
    # to an existing node passes the link-target check but can still cycle).
    cycle = _detect_cycle(workflow, link_inputs if catalog_available else None)
    if cycle:
        errors.append(
            f"Anti-cycle: workflow contains a cycle through nodes {cycle!r} "
            "- ComfyUI v0.20+ rejects cyclic graphs at execution time"
        )

    # Pass 5: Environment - referenced model files exist in ComfyUI's model folders
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
        from comfy_mcp.safety.deprecated_models import lint_model_name

        # Deprecation lint first - advisory, runs regardless of whether the
        # /models/{folder} endpoint is reachable. Operating purely on names
        # ensures network hiccups don't silence stale-model warnings.
        for folder, names in referenced_models.items():
            for n in sorted(names):
                lint = lint_model_name(n)
                if lint is not None:
                    reason, replacement = lint
                    msg = f"Deprecated: {n!r} - {reason}"
                    if replacement:
                        msg += f" (consider {replacement})"
                    warnings.append(msg)

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

    # Pass 6: Execution risk - latent volume + VRAM headroom
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

    # Check for output nodes from the live schema.  Only use a naming fallback
    # when object_info was unavailable.
    if catalog_available:
        has_output = any(schema.is_output_node for schema in schemas.values())
    else:
        has_output = any(
            isinstance(node, dict)
            and str(node.get("class_type", "")).lower().startswith(("save", "preview", "export"))
            for node in workflow.values()
        )
    if not has_output:
        warnings.append(
            "No node marked as an output node by ComfyUI was found; workflow may produce no visible output"
        )

    return ValidationReport(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        node_count=len(workflow),
        passes=[
            "schema",
            "catalog" if catalog_available else "catalog_skipped",
            "graph",
            "anti_cycle",
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

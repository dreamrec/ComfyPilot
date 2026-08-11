"""Builder tools - 5 tools for programmatic workflow construction.

Templates are resolved through the family registry (comfy_mcp.families):
the detected checkpoint family picks which template module handles each
intent (txt2img, img2img, txt2video, image2_3d, txt2music, etc.). This
stops the old behavior of stuffing a Flux 2 / Wan / LTX checkpoint into
an SD 1.5-shaped graph that cannot execute.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.families import Family, detect_family
from comfy_mcp.families import registry as family_registry
from comfy_mcp.schemas.node_schema import parse_object_info
from comfy_mcp.server import mcp



# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


_MODEL_FOLDERS = ("diffusion_models", "checkpoints")
_SEPARATE_MODEL_FAMILIES = {
    Family.FLUX1, Family.FLUX2, Family.QWEN, Family.WAN22,
    Family.HUNYUAN_VIDEO, Family.HUNYUAN_3D, Family.ERNIE_IMAGE,
}


async def _model_inventory(client: Any) -> dict[str, list[str]]:
    inventory: dict[str, list[str]] = {}
    for folder in (*_MODEL_FOLDERS, "text_encoders", "vae", "clip_vision"):
        try:
            values = await client.get_models(folder)
        except Exception:
            values = []
        inventory[folder] = [str(value) for value in values or [] if isinstance(value, str)]
    return inventory


def _pick_model(models: list[str], *preferences: tuple[str, ...]) -> str | None:
    """Pick the first installed model matching the first ranked token group."""
    for tokens in preferences:
        for model in models:
            lowered = model.lower()
            if all(token.lower() in lowered for token in tokens):
                return model
    return None


def _resolve_aux_models(family: Family, params: dict, inventory: dict[str, list[str]]) -> None:
    text = inventory.get("text_encoders", [])
    vae = inventory.get("vae", [])
    vision = inventory.get("clip_vision", [])

    if family == Family.FLUX2:
        params.setdefault("clip_name1", _pick_model(text, ("clip_l.safetensors",), ("clip_l",)))
        params.setdefault("clip_name2", _pick_model(text, ("mistral", "flux2")))
        params.setdefault("vae", _pick_model(vae, ("flux2", "vae"), ("ae.safetensors",)))
    elif family == Family.LTX2 and params.get("model_folder") == "diffusion_models":
        params.setdefault("clip_name1", _pick_model(text, ("gemma_3_12b",), ("gemma",)))
        params.setdefault("clip_name2", _pick_model(text, ("ltx", "projection")))
        params.setdefault("vae", _pick_model(vae, ("ltx23", "video"), ("ltx", "video")))
    elif family == Family.WAN22:
        params.setdefault("clip_name", _pick_model(text, ("umt5",)))
        params.setdefault("vae", _pick_model(vae, ("wan2.2",), ("wan2_1",), ("wan",)))
    elif family == Family.QWEN:
        params.setdefault("clip_name", _pick_model(text, ("qwen_2.5_vl",), ("qwen",)))
        params.setdefault("vae", _pick_model(vae, ("qwen_image_vae",), ("qwen", "vae")))
    elif family == Family.HUNYUAN_3D:
        params.setdefault("vae", _pick_model(vae, ("hunyuan3d",)))
        params.setdefault("clip_vision", _pick_model(vision, ("clip_vision_h",), ("vit-h",)))

    # Never pass None through to a builder: setdefault considers a present
    # None authoritative, while builders expect a filename string.
    for key in ("clip_name", "clip_name1", "clip_name2", "clip_vision", "vae"):
        if params.get(key) is None:
            params.pop(key, None)


def _catalog_default(spec: Any) -> tuple[bool, Any]:
    constraints = spec.constraints or {}
    if "default" in constraints:
        return True, constraints["default"]
    choices = constraints.get("choices", constraints.get("options"))
    if isinstance(choices, (list, tuple)) and choices:
        first = choices[0]
        if isinstance(first, dict) and "key" in first:
            return True, first["key"]
        return True, first
    return False, None


def _fill_catalog_defaults(workflow: dict, catalog: dict[str, Any]) -> None:
    """Fill omitted required widgets from live defaults; never invent links."""
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        raw = catalog.get(class_type)
        if not isinstance(class_type, str) or not isinstance(raw, dict):
            continue
        try:
            schema = parse_object_info(class_type, raw)
        except (TypeError, ValueError):
            continue
        inputs = node.setdefault("inputs", {})
        if not isinstance(inputs, dict):
            continue
        for spec in schema.inputs:
            mode = str((spec.constraints or {}).get("mode", "")).lower()
            if (
                not spec.required or spec.name in inputs or spec.is_link_target
                or mode in {"divider", "spacer", "separator"}
            ):
                continue
            found, value = _catalog_default(spec)
            if found:
                inputs[spec.name] = value


async def _live_catalog(client: Any) -> dict[str, Any] | None:
    try:
        catalog = await client.get_object_info()
    except Exception:
        return None
    return catalog if isinstance(catalog, dict) and catalog else None


def _family_override(value: str | None) -> Family | None:
    if value is None:
        return None
    try:
        selected = Family(str(value).lower())
    except ValueError:
        return None
    return None if selected == Family.UNKNOWN else selected


def _maybe_auto_snapshot(ctx: Context | None, workflow: dict, action: str) -> dict | None:
    if ctx is None:
        return None

    snapshot_mgr = ctx.request_context.lifespan_context.get("snapshot_manager")
    if snapshot_mgr is None or getattr(snapshot_mgr, "auto_snapshot", False) is not True:
        return None

    return snapshot_mgr.add(workflow, name=f"auto-before-{action}")


@mcp.tool(
    annotations={
        "title": "Build Workflow",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_build_workflow(
    template: str,
    params: dict | None = None,
    family: str | None = None,
    ctx: Context = None,
) -> str:
    """Build a ComfyUI workflow for an intent, routed to the detected model family.

    The checkpoint family is detected from params['checkpoint'] (or auto-detected
    from the first installed checkpoint if ctx is provided) and dispatched to a
    family-specific builder. SD 1.5 is the fallback when the family can't be
    determined.

    Intents by family:
      SD 1.5:          txt2img, img2img, upscale, inpaint, controlnet
      SDXL / SD 3.5:   txt2img
      Flux 2 / Qwen:   txt2img
      Wan 2.2:         txt2video, img2video
      LTX-2:           txt2video
      HunyuanVideo:    txt2video, img2video
      Hunyuan3D:       image2_3d
      ACE-Step:        txt2music

    Args:
        template: Intent name (e.g. 'txt2img', 'txt2video', 'image2_3d', 'txt2music').
        params: Optional param overrides. If 'checkpoint' is set, family routing
            uses it; otherwise the first installed checkpoint is auto-detected.
    """
    resolved_params = dict(params or {})
    raw_override = family if family is not None else resolved_params.pop("family", None)
    selected_family = _family_override(raw_override)
    if raw_override is not None and selected_family is None:
        return json.dumps({
            "error": f"Unknown family override {raw_override!r}",
            "available_families": [item.value for item in Family if item != Family.UNKNOWN],
        })

    client = None
    inventory: dict[str, list[str]] = {}
    catalog: dict[str, Any] | None = None
    if ctx is not None:
        try:
            client = ctx.request_context.lifespan_context["comfy_client"]
        except (KeyError, TypeError, AttributeError):
            client = None
    if client is not None:
        inventory = await _model_inventory(client)
        catalog = await _live_catalog(client)

    # Family-agnostic intents (SUPIR super-resolution, RIFE/FILM frame
    # interpolation, SAM 3.1 segmentation, training, audio t2a) skip family
    # detection entirely - they operate on any input regardless of the
    # upstream model that produced it. The intent-override map registered
    # in family_registry takes precedence over family routing.
    if family_registry.has_intent_override(template):
        workflow = family_registry.build_intent(template, resolved_params)
        if catalog:
            _fill_catalog_defaults(workflow, catalog)
        return json.dumps(
            {
                "intent": template,
                "family": "intent_override",
                "checkpoint": resolved_params.get("checkpoint", ""),
                "node_count": len(workflow),
                "workflow": workflow,
            },
            indent=2,
        )

    # Candidate tuples retain their source folder because loader topology is a
    # property of the folder, not merely the filename.  In particular, LTX can
    # be either a bundled checkpoint or a transformer-only diffusion model.
    candidates: list[tuple[str, Family, str]] = []
    explicit_checkpoint = resolved_params.get("checkpoint")
    if isinstance(explicit_checkpoint, str) and explicit_checkpoint:
        folder = str(resolved_params.get("model_folder", ""))
        if not folder:
            folder = next(
                (name for name in _MODEL_FOLDERS if explicit_checkpoint in inventory.get(name, [])),
                "",
            )
        detected = selected_family or detect_family(explicit_checkpoint)
        if detected == Family.UNKNOWN:
            detected = Family.SD15
        if not folder:
            folder = "diffusion_models" if detected in _SEPARATE_MODEL_FAMILIES else "checkpoints"
        candidates.append((explicit_checkpoint, detected, folder))
    else:
        seen: set[tuple[str, str]] = set()
        for folder in _MODEL_FOLDERS:
            for checkpoint in inventory.get(folder, []):
                key = (folder, checkpoint)
                if key in seen:
                    continue
                seen.add(key)
                detected = detect_family(checkpoint)
                if detected == Family.UNKNOWN:
                    continue
                if selected_family is None or detected == selected_family:
                    candidates.append((checkpoint, detected, folder))

        # Intent-aware routing is the primary ordering.  This prevents an LTX
        # model from blocking image2_3d when Hunyuan3D is installed later in the
        # same folder.
        candidates.sort(key=lambda item: 0 if family_registry.has(item[1], template) else 1)

        if not candidates and selected_family is None:
            unknown_checkpoint = next(iter(inventory.get("checkpoints", [])), "")
            candidates.append((unknown_checkpoint, Family.SD15, "checkpoints"))
        elif not candidates and selected_family is not None:
            candidates.append(("", selected_family, "diffusion_models" if selected_family in _SEPARATE_MODEL_FAMILIES else "checkpoints"))

    # Offline/no-model fallback preserves the useful SD 1.5 baseline.
    if not candidates:
        candidates = [("", selected_family or Family.SD15, "checkpoints")]

    supported = [item for item in candidates if family_registry.has(item[1], template)]
    if not supported:
        detected_family = candidates[0][1]
        return json.dumps({
            "error": f"No template for intent={template!r} in family={detected_family.value}",
            "detected_family": detected_family.value,
            "available_intents_for_family": family_registry.list_intents(detected_family),
            "all_supported_families": [f.value for f in family_registry.list_families()],
        })

    validation_attempts: list[dict[str, Any]] = []
    for checkpoint, detected_family, folder in supported:
        attempt_params = dict(resolved_params)
        if checkpoint:
            attempt_params["checkpoint"] = checkpoint
        attempt_params["model_folder"] = folder
        _resolve_aux_models(detected_family, attempt_params, inventory)
        workflow = family_registry.build(detected_family, template, attempt_params)
        if catalog:
            _fill_catalog_defaults(workflow, catalog)

            # Validate with the same public validator agents use.  On failure,
            # try the next installed model that supports the requested intent.
            from comfy_mcp.tools.workflow import comfy_validate_workflow
            report = await comfy_validate_workflow(workflow=workflow, ctx=ctx)
            report_data = report.model_dump()
            if not report.valid:
                validation_attempts.append({
                    "checkpoint": checkpoint,
                    "family": detected_family.value,
                    "model_folder": folder,
                    "errors": report.errors,
                })
                continue
        else:
            report_data = {"valid": None, "reason": "live object_info unavailable"}

        return json.dumps(
            {
                "intent": template,
                "family": detected_family.value,
                "checkpoint": checkpoint,
                "model_folder": folder,
                "node_count": len(workflow),
                "validation": report_data,
                "workflow": workflow,
            },
            indent=2,
        )

    return json.dumps({
        "error": f"No installed {template!r} candidate produced a valid live workflow",
        "intent": template,
        "attempts": validation_attempts,
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Add Node",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_add_node(
    workflow: dict,
    node_id: str,
    class_type: str,
    inputs: dict | None = None,
    ctx: Context = None,
) -> str:
    """Add a node to a workflow.

    Args:
        workflow: The workflow dictionary to modify
        node_id: ID for the new node (string, e.g. "8")
        class_type: ComfyUI node class type
        inputs: Optional input values for the node
    """
    workflow = copy.deepcopy(workflow)
    snapshot = _maybe_auto_snapshot(ctx, workflow, "add-node")
    workflow[node_id] = {
        "class_type": class_type,
        "inputs": inputs or {},
    }
    result = {"node_count": len(workflow), "added": node_id, "workflow": workflow}
    if snapshot is not None:
        result["auto_snapshot"] = snapshot
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Connect Nodes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_connect_nodes(
    workflow: dict,
    source_node: str,
    source_output: int,
    target_node: str,
    target_input: str,
    ctx: Context = None,
) -> str:
    """Connect two nodes in a workflow.

    Args:
        workflow: The workflow dictionary
        source_node: ID of the source node
        source_output: Output index on the source node
        target_node: ID of the target node
        target_input: Input name on the target node
    """
    workflow = copy.deepcopy(workflow)
    snapshot = _maybe_auto_snapshot(ctx, workflow, "connect-nodes")
    if target_node not in workflow:
        return json.dumps({"error": f"Target node {target_node} not found"})
    if source_node not in workflow:
        return json.dumps({"error": f"Source node {source_node} not found"})
    workflow[target_node]["inputs"][target_input] = [source_node, source_output]
    result = {
        "connected": f"{source_node}[{source_output}] -> {target_node}.{target_input}",
        "workflow": workflow,
    }
    if snapshot is not None:
        result["auto_snapshot"] = snapshot
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Set Widget Value",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_set_widget_value(
    workflow: dict,
    node_id: str,
    widget_name: str,
    value: Any = None,
    ctx: Context = None,
) -> str:
    """Set a widget value on a workflow node.

    Args:
        workflow: The workflow dictionary
        node_id: ID of the node to modify
        widget_name: Name of the widget/input to set
        value: Value to set
    """
    workflow = copy.deepcopy(workflow)
    snapshot = _maybe_auto_snapshot(ctx, workflow, "set-widget-value")
    if node_id not in workflow:
        return json.dumps({"error": f"Node {node_id} not found"})
    workflow[node_id]["inputs"][widget_name] = value
    result = {"set": f"{node_id}.{widget_name} = {value}", "workflow": workflow}
    if snapshot is not None:
        result["auto_snapshot"] = snapshot
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Apply Template",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_apply_template(
    template: str,
    params: dict | None = None,
    ctx: Context = None,
) -> str:
    """Apply a workflow template and return the resulting workflow.

    Convenience alias for comfy_build_workflow.

    Args:
        template: Template name (txt2img, img2img, upscale, inpaint, controlnet)
        params: Optional parameters to override template defaults
    """
    return await comfy_build_workflow(template=template, params=params, ctx=ctx)

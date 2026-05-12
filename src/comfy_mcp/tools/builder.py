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
from comfy_mcp.server import mcp



# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


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

    # Family-agnostic intents (SUPIR super-resolution, RIFE/FILM frame
    # interpolation, SAM 3.1 segmentation, training, audio t2a) skip family
    # detection entirely - they operate on any input regardless of the
    # upstream model that produced it. The intent-override map registered
    # in family_registry takes precedence over family routing.
    if family_registry.has_intent_override(template):
        workflow = family_registry.build_intent(template, resolved_params)
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

    # Auto-detect an installed model if none provided. Modern families (Flux 2,
    # Qwen, Wan 2.2, LTX-2, HunyuanVideo, Hunyuan3D) store weights under
    # `diffusion_models/` via UNETLoader; traditional SD-family checkpoints live
    # under `checkpoints/` via CheckpointLoaderSimple. Probe both and prefer
    # whichever yields a family that supports the requested intent.
    if ctx and "checkpoint" not in resolved_params:
        try:
            client = ctx.request_context.lifespan_context["comfy_client"]
            candidates: list[tuple[str, Family]] = []
            for folder in ("diffusion_models", "checkpoints"):
                try:
                    models = await client.get_models(folder)
                except Exception:
                    continue
                for name in models or []:
                    fam = detect_family(name)
                    if fam != Family.UNKNOWN:
                        candidates.append((name, fam))

            # 1) Prefer the first candidate whose family supports this intent.
            picked = next(
                (c for c in candidates if family_registry.has(c[1], template)),
                None,
            )
            # 2) Otherwise the first recognised family at all (still better than
            #    guessing SD 1.5).
            if picked is None and candidates:
                picked = candidates[0]

            if picked is not None:
                resolved_params["checkpoint"] = picked[0]
            else:
                # No recognisable model found - fall back to first available file
                # so the user at least gets a concrete filename back in the graph.
                for folder in ("checkpoints", "diffusion_models"):
                    try:
                        models = await client.get_models(folder)
                    except Exception:
                        continue
                    if models:
                        resolved_params["checkpoint"] = models[0]
                        break
        except Exception:
            pass  # Fallback to family default below

    checkpoint = resolved_params.get("checkpoint", "")
    family = detect_family(checkpoint)

    # If the checkpoint is unknown or empty, fall back to SD 1.5 baseline
    if family == Family.UNKNOWN:
        family = Family.SD15

    if not family_registry.has(family, template):
        return json.dumps({
            "error": f"No template for intent={template!r} in family={family.value}",
            "detected_family": family.value,
            "available_intents_for_family": family_registry.list_intents(family),
            "all_supported_families": [f.value for f in family_registry.list_families()],
        })

    workflow = family_registry.build(family, template, resolved_params)
    return json.dumps(
        {
            "intent": template,
            "family": family.value,
            "checkpoint": checkpoint,
            "node_count": len(workflow),
            "workflow": workflow,
        },
        indent=2,
    )


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

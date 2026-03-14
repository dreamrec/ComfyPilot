"""Builder tools — 5 tools for programmatic workflow construction."""
from __future__ import annotations

import copy
import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


# ---------------------------------------------------------------------------
# Template functions
# ---------------------------------------------------------------------------


def _build_txt2img(params: dict) -> dict:
    """Standard txt2img workflow."""
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": params.get("checkpoint", "v1-5-pruned-emaonly.safetensors"),
            },
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("positive", "beautiful landscape"),
                "clip": ["1", 1],
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("negative", "ugly, blurry"),
                "clip": ["1", 1],
            },
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": params.get("width", 512),
                "height": params.get("height", 512),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 20),
                "cfg": params.get("cfg", 7.0),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "normal"),
                "denoise": params.get("denoise", 1.0),
            },
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["5", 0],
                "vae": ["1", 2],
            },
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["6", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot"),
            },
        },
    }


def _build_img2img(params: dict) -> dict:
    """img2img workflow — loads an input image and denoises it."""
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": params.get("checkpoint", "v1-5-pruned-emaonly.safetensors"),
            },
        },
        "2": {
            "class_type": "LoadImage",
            "inputs": {
                "image": params.get("image", "input.png"),
            },
        },
        "3": {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": ["2", 0],
                "vae": ["1", 2],
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("positive", "beautiful landscape"),
                "clip": ["1", 1],
            },
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("negative", "ugly, blurry"),
                "clip": ["1", 1],
            },
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["3", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 20),
                "cfg": params.get("cfg", 7.0),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "normal"),
                "denoise": params.get("denoise", 0.75),
            },
        },
        "7": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["6", 0],
                "vae": ["1", 2],
            },
        },
        "8": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["7", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_img2img"),
            },
        },
    }


def _build_upscale(params: dict) -> dict:
    """Upscale workflow — latent upscale then re-sample."""
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": params.get("checkpoint", "v1-5-pruned-emaonly.safetensors"),
            },
        },
        "2": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": params.get("width", 512),
                "height": params.get("height", 512),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("positive", "beautiful landscape"),
                "clip": ["1", 1],
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("negative", "ugly, blurry"),
                "clip": ["1", 1],
            },
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["2", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 20),
                "cfg": params.get("cfg", 7.0),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "normal"),
                "denoise": params.get("denoise", 1.0),
            },
        },
        "6": {
            "class_type": "LatentUpscale",
            "inputs": {
                "samples": ["5", 0],
                "upscale_method": params.get("upscale_method", "nearest-exact"),
                "width": params.get("upscale_width", 1024),
                "height": params.get("upscale_height", 1024),
                "crop": params.get("crop", "disabled"),
            },
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["6", 0],
                "seed": params.get("upscale_seed", 43),
                "steps": params.get("upscale_steps", 10),
                "cfg": params.get("cfg", 7.0),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "normal"),
                "denoise": params.get("upscale_denoise", 0.5),
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["7", 0],
                "vae": ["1", 2],
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_upscale"),
            },
        },
    }


def _build_inpaint(params: dict) -> dict:
    """Inpaint workflow — img2img with a noise mask for masked regions."""
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": params.get("checkpoint", "v1-5-pruned-emaonly.safetensors"),
            },
        },
        "2": {
            "class_type": "LoadImage",
            "inputs": {
                "image": params.get("image", "input.png"),
            },
        },
        "3": {
            "class_type": "LoadImage",
            "inputs": {
                "image": params.get("mask", "mask.png"),
            },
        },
        "4": {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": ["2", 0],
                "vae": ["1", 2],
            },
        },
        "5": {
            "class_type": "SetLatentNoiseMask",
            "inputs": {
                "samples": ["4", 0],
                "mask": ["3", 0],
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("positive", "beautiful landscape"),
                "clip": ["1", 1],
            },
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("negative", "ugly, blurry"),
                "clip": ["1", 1],
            },
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 20),
                "cfg": params.get("cfg", 7.0),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "normal"),
                "denoise": params.get("denoise", 0.75),
            },
        },
        "9": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["8", 0],
                "vae": ["1", 2],
            },
        },
        "10": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["9", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_inpaint"),
            },
        },
    }


def _build_controlnet(params: dict) -> dict:
    """ControlNet workflow — condition generation on a control image."""
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": params.get("checkpoint", "v1-5-pruned-emaonly.safetensors"),
            },
        },
        "2": {
            "class_type": "ControlNetLoader",
            "inputs": {
                "control_net_name": params.get(
                    "controlnet_name", "control_v11p_sd15_canny.pth"
                ),
            },
        },
        "3": {
            "class_type": "LoadImage",
            "inputs": {
                "image": params.get("control_image", "control.png"),
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("positive", "beautiful landscape"),
                "clip": ["1", 1],
            },
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("negative", "ugly, blurry"),
                "clip": ["1", 1],
            },
        },
        "6": {
            "class_type": "ControlNetApply",
            "inputs": {
                "conditioning": ["4", 0],
                "control_net": ["2", 0],
                "image": ["3", 0],
                "strength": params.get("controlnet_strength", 1.0),
            },
        },
        "7": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": params.get("width", 512),
                "height": params.get("height", 512),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["6", 0],
                "negative": ["5", 0],
                "latent_image": ["7", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 20),
                "cfg": params.get("cfg", 7.0),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "normal"),
                "denoise": params.get("denoise", 1.0),
            },
        },
        "9": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["8", 0],
                "vae": ["1", 2],
            },
        },
        "10": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["9", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_controlnet"),
            },
        },
    }


_TEMPLATES = {
    "txt2img": _build_txt2img,
    "img2img": _build_img2img,
    "upscale": _build_upscale,
    "inpaint": _build_inpaint,
    "controlnet": _build_controlnet,
}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


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
    """Build a ComfyUI workflow from a template.

    Args:
        template: Template name (txt2img, img2img, upscale, inpaint, controlnet)
        params: Optional parameters to override template defaults
    """
    if template not in _TEMPLATES:
        return json.dumps({
            "error": f"Unknown template: {template}",
            "available": list(_TEMPLATES.keys()),
        })

    resolved_params = dict(params or {})

    # If ctx available, try to detect installed models
    if ctx and "checkpoint" not in resolved_params:
        try:
            client = ctx.request_context.lifespan_context["comfy_client"]
            models = await client.get_models("checkpoints")
            if models:
                resolved_params["checkpoint"] = models[0]
        except Exception:
            pass  # Fallback to template default

    workflow = _TEMPLATES[template](resolved_params)
    return json.dumps(
        {"template": template, "node_count": len(workflow), "workflow": workflow},
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
    workflow[node_id] = {
        "class_type": class_type,
        "inputs": inputs or {},
    }
    return json.dumps(
        {"node_count": len(workflow), "added": node_id, "workflow": workflow},
        indent=2,
    )


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
    if target_node not in workflow:
        return json.dumps({"error": f"Target node {target_node} not found"})
    if source_node not in workflow:
        return json.dumps({"error": f"Source node {source_node} not found"})
    workflow[target_node]["inputs"][target_input] = [source_node, source_output]
    return json.dumps(
        {
            "connected": f"{source_node}[{source_output}] -> {target_node}.{target_input}",
            "workflow": workflow,
        },
        indent=2,
    )


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
    if node_id not in workflow:
        return json.dumps({"error": f"Node {node_id} not found"})
    workflow[node_id]["inputs"][widget_name] = value
    return json.dumps(
        {"set": f"{node_id}.{widget_name} = {value}", "workflow": workflow},
        indent=2,
    )


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

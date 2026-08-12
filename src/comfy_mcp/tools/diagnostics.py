"""Diagnostic tools - workflow introspection, runtime advice, trust checks.

This module bundles the v1.8.0 operational toolkit:
- comfy_extract_schema  - workflow-level controllable param + dependency summary
- comfy_fetch_logs      - traceback retrieval from /history/{prompt_id}
- comfy_inspect_workflow - trust check (custom-node enumeration)
- comfy_recommend_runtime - hardware verdict (ok / marginal / cloud)
- comfy_suggest_timeout - per-workflow timeout advice based on output-node class

These are diagnostic rather than execution tools: each is read-only and
returns structured JSON for the caller to act on. None modify workflows
or server state.
"""
from __future__ import annotations

import json
import re
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.schemas.node_schema import NodeSchema, parse_object_info
from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


# Loader fields keyed by class_type -> [(input_name, /models/ folder), ...].
# Mirrors tools/workflow.py::_MODEL_INPUT_FIELDS so the schema tool reports
# the same dependencies the validator's environment pass checks.
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
    # Video/audio loaders
    "VHS_LoadVideo": [("video", "input")],
    "LoadVideo": [("video", "input")],
}


# A conservative list of ComfyUI "core" / stock node prefixes. Anything not
# matching one of these patterns is treated as a custom-node class for the
# trust check. This is intentionally permissive - the goal is to surface
# unfamiliar packages, not to gatekeep every node.
_STOCK_NODE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(Checkpoint|UNET|VAE|CLIP|Triple|Dual|Lora|Style|Upscale|GLIGEN|ControlNet|Diffusers)Loader"),
    re.compile(r"^Empty(Latent|SD3Latent|Hunyuan|LTXV|AceStep|LatentHunyuan|LatentAudio).*"),
    re.compile(r"^Save(Image|AnimatedWEBP|AnimatedPNG|GLB|Audio|Video|Lora|Latent)"),
    re.compile(r"^(Preview|Load)(Image|Video|Audio|Latent)"),
    re.compile(r"^(KSampler|KSamplerAdvanced|KSamplerSelect|SamplerCustom|SamplerCustomAdvanced)"),
    re.compile(r"^(BasicScheduler|BasicGuider|RandomNoise|ModelSamplingSD3|FluxGuidance)"),
    re.compile(r"^CLIPTextEncode(SDXL|SD3|Flux|HunyuanVideo)?$"),
    re.compile(r"^(VAEDecode|VAEEncode|LatentUpscale|SetLatentNoiseMask)"),
    re.compile(r"^(ImageScale|ImageBatch|ImageBlend|ImageCrop|GetImageSize|ImageStitch)"),
    re.compile(r"^(MaskToImage|ImageToMask|Mask|InvertMask)"),
    re.compile(r"^(Hunyuan|LTXV|Wan|AceStep|Qwen|Ernie|SAM3|RIFE_VFI|FILM_VFI|SUPIR)"),
    re.compile(r"^(TextEncodeAceStepAudio|VAEDecodeAudio|VAEDecodeHunyuan3D|ConditioningStableAudio)"),
    re.compile(r"^(TrainLora|TrainLoraDataLoader)"),
)


def _is_stock_node(class_type: str) -> bool:
    """Return True if the class_type looks like a ComfyUI core / first-party node."""
    return any(p.match(class_type) for p in _STOCK_NODE_PATTERNS)


def _is_link(value: Any) -> bool:
    """A link value is a [source_node_id, output_index] pair."""
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
    )


def _extract_embedding_refs(text: str) -> list[str]:
    """Find `embedding:NAME` references inside a text input."""
    return re.findall(r"embedding:([\w\-.]+)", text)


async def _workflow_schemas(workflow: dict, ctx: Context | None) -> dict[str, NodeSchema]:
    """Resolve the workflow's node schemas from the live object_info catalog."""
    if ctx is None:
        return {}
    try:
        catalog = await _client(ctx).get_object_info()
    except Exception:
        return {}
    if not isinstance(catalog, dict):
        return {}

    result: dict[str, NodeSchema] = {}
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        raw = catalog.get(class_type)
        if isinstance(class_type, str) and isinstance(raw, dict):
            try:
                result[str(node_id)] = parse_object_info(class_type, raw)
            except (TypeError, ValueError):
                continue
    return result


def _looks_like_output(class_type: str) -> bool:
    lowered = class_type.lower()
    return lowered.startswith(("save", "preview", "export")) or "videocombine" in lowered


def _timeout_for_node(class_type: str, schema: NodeSchema | None) -> int | None:
    """Infer a timeout from live category/output types plus semantic node names."""
    metadata = " ".join(
        [
            class_type,
            schema.category if schema else "",
            schema.python_module if schema else "",
            " ".join(output.type_name for output in schema.outputs) if schema else "",
        ]
    ).lower()
    if "train" in metadata and ("lora" in metadata or "model" in metadata):
        return 3600
    if any(token in metadata for token in ("video", "vhs_", "videocombine")):
        return 900
    if any(token in metadata for token in ("animated", "webp", "animation")):
        return 600
    if any(token in metadata for token in ("trellis", "hunyuan3d", "3d", "mesh", "voxel", "glb", "gltf")):
        return 600
    if any(token in metadata for token in ("supir", "upscale", "super_resolution")):
        return 600
    if "audio" in metadata:
        return 450
    return None


@mcp.tool(
    annotations={
        "title": "Extract Workflow Schema",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_extract_schema(
    workflow: dict,
    summary_only: bool = False,
    ctx: Context = None,
) -> str:
    """Extract the controllability / dependency surface of a workflow.

    Returns a structured summary of every controllable widget input across
    all nodes, every model the workflow depends on (loader nodes), every
    embedding reference embedded in text inputs, and every output node.
    Lets an agent decide what to parameterise without walking the graph
    node-by-node.

    Args:
        workflow: API-format workflow dict.
        summary_only: If True, return just the high-level counts/flags
            (`parameter_count`, `has_negative_prompt`, `has_seed`,
            `model_count`, `node_count`) without the per-parameter list.
    """
    if not isinstance(workflow, dict) or not workflow:
        return json.dumps({"error": "workflow must be a non-empty dict"})

    # Editor-format short-circuit, same as the validator.
    if isinstance(workflow.get("nodes"), list) and isinstance(workflow.get("links"), list):
        return json.dumps({
            "error": "Workflow is in editor format. Re-export via Workflow -> Export (API).",
        })

    parameters: list[dict] = []
    model_dependencies: list[dict] = []
    embedding_references: set[str] = set()
    output_nodes: list[dict] = []

    has_negative_prompt = False
    has_seed = False
    schemas = await _workflow_schemas(workflow, ctx)

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {}) or {}

        # Output node?
        schema = schemas.get(str(node_id))
        if (schema is not None and schema.is_output_node) or (
            schema is None and _looks_like_output(class_type)
        ):
            output_nodes.append({"node_id": node_id, "class_type": class_type})

        # Model dependencies
        for field, folder in _MODEL_INPUT_FIELDS.get(class_type, []):
            val = inputs.get(field)
            if isinstance(val, str) and val:
                model_dependencies.append({
                    "node_id": node_id,
                    "class_type": class_type,
                    "field": field,
                    "value": val,
                    "folder": folder,
                })

        # Widget parameters (non-link inputs)
        for name, value in inputs.items():
            if _is_link(value):
                continue  # link, not a widget
            param_type = type(value).__name__
            entry = {
                "node_id": node_id,
                "class_type": class_type,
                "name": name,
                "type": param_type,
                "current_value": value,
            }
            parameters.append(entry)

            # Heuristic flags
            if name == "seed" or name == "noise_seed":
                has_seed = True
            # A widget named exactly `negative` / `negative_prompt` carrying
            # non-empty text is a direct signal. (We don't try to infer from
            # `text` widgets - node IDs in API format are numeric, so the
            # old "negative in node_id" heuristic never fired.) Embeddings
            # referenced from any text widget are still collected.
            if name in {"negative", "negative_prompt"} and isinstance(value, str) and value:
                has_negative_prompt = True
            if isinstance(value, str):
                embedding_references.update(_extract_embedding_refs(value))

    # Second pass for has_negative_prompt: the canonical SD-style negative
    # prompt is a CLIPTextEncode node whose output is wired into another
    # node's `negative` input (usually KSampler). Detect via the link
    # rather than text content.
    if not has_negative_prompt:
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            for input_name, input_val in (node.get("inputs", {}) or {}).items():
                if input_name == "negative" and _is_link(input_val):
                    has_negative_prompt = True
                    break

    summary = {
        "parameter_count": len(parameters),
        "has_negative_prompt": has_negative_prompt,
        "has_seed": has_seed,
        "node_count": len(workflow),
        "model_count": len(model_dependencies),
        "embedding_count": len(embedding_references),
        "output_node_count": len(output_nodes),
    }

    if summary_only:
        return json.dumps(summary, indent=2)

    return json.dumps({
        **summary,
        "parameters": parameters,
        "model_dependencies": model_dependencies,
        "embedding_references": sorted(embedding_references),
        "output_nodes": output_nodes,
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Fetch Logs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_fetch_logs(prompt_id: str, ctx: Context = None) -> str:
    """Retrieve execution logs / error traceback for a specific prompt.

    ComfyUI's /history/{prompt_id} response carries a `status.messages`
    array with per-step execution events and `status.exec_info.errors`
    with traceback strings on failure. This tool extracts just the
    log-relevant fields (status, errors, per-node traceback, completed
    nodes) so the caller doesn't have to walk the full response.

    Args:
        prompt_id: Prompt ID returned by `comfy_queue_prompt`.
    """
    if not prompt_id or not isinstance(prompt_id, str):
        return json.dumps({"error": "prompt_id must be a non-empty string"})

    try:
        history = await _client(ctx).get_history(prompt_id=prompt_id)
    except Exception as e:
        return json.dumps({"error": f"Could not fetch /history/{prompt_id}: {e}"})

    if not history:
        return json.dumps({
            "prompt_id": prompt_id,
            "error": "Not found in history (job may still be running or never queued)",
        })

    entry = history.get(prompt_id, {}) if isinstance(history, dict) else {}
    status_dict = entry.get("status", {}) if isinstance(entry, dict) else {}

    status_str = status_dict.get("status_str", "unknown")
    completed = bool(status_dict.get("completed", False))
    messages = status_dict.get("messages", []) or []

    # Errors may live under status.exec_info.errors (list of dicts) AND/OR
    # under status.messages of type 'execution_error'. Stock ComfyUI
    # populates BOTH for the same failure, so we deduplicate on
    # (node_id, message) to avoid double-counting.
    errors: list[dict] = []
    seen: set[tuple] = set()

    def _add(entry: dict) -> None:
        key = (entry.get("node_id"), entry.get("message"))
        if key in seen:
            return
        seen.add(key)
        errors.append(entry)

    exec_info = status_dict.get("exec_info", {}) or {}
    for err in exec_info.get("errors", []) or []:
        if isinstance(err, dict):
            _add({
                "node_id": err.get("node_id") or err.get("node"),
                "class_type": err.get("class_type") or err.get("node_type"),
                "message": err.get("message") or err.get("exception_message", ""),
                "traceback": err.get("traceback") or err.get("exception_traceback", ""),
            })

    for msg in messages:
        if isinstance(msg, (list, tuple)) and len(msg) >= 2 and msg[0] == "execution_error":
            payload = msg[1] if isinstance(msg[1], dict) else {}
            _add({
                "node_id": payload.get("node_id") or payload.get("node"),
                "class_type": payload.get("node_type") or payload.get("class_type"),
                "message": payload.get("exception_message") or payload.get("message", ""),
                "traceback": payload.get("exception_traceback") or payload.get("traceback", ""),
            })

    # Completed nodes - status.messages of type 'executed' or 'execution_cached'
    completed_nodes: list[str] = []
    for msg in messages:
        if isinstance(msg, (list, tuple)) and len(msg) >= 2 and msg[0] in ("executed", "execution_cached"):
            payload = msg[1] if isinstance(msg[1], dict) else {}
            nid = payload.get("node") or payload.get("node_id")
            if nid is not None:
                completed_nodes.append(str(nid))

    failed_node = errors[0]["node_id"] if errors else None

    return json.dumps({
        "prompt_id": prompt_id,
        "status": status_str,
        "completed": completed,
        "errors": errors,
        "error_count": len(errors),
        "failed_node": failed_node,
        "completed_nodes": completed_nodes,
        "raw_message_count": len(messages),
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Inspect Workflow Trust",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_inspect_workflow(workflow: dict, ctx: Context = None) -> str:
    """Enumerate custom (non-stock) node class types in a workflow.

    Workflow JSON is arbitrary code - custom nodes run Python on the
    ComfyUI server. This tool surfaces which class_types are NOT in the
    set of ComfyUI core / first-party node patterns, so an agent can warn
    the user (or refuse to auto-queue) before submitting a workflow from
    an untrusted source.

    Returns a JSON report with trust_level (`stock` | `mixed` | `fully_custom`),
    the stock + custom class lists, and per-warning strings.
    """
    if not isinstance(workflow, dict) or not workflow:
        return json.dumps({"error": "workflow must be a non-empty dict"})

    class_types: list[str] = []
    for node in workflow.values():
        if isinstance(node, dict):
            ct = node.get("class_type", "")
            if ct:
                class_types.append(ct)

    stock: list[str] = sorted({ct for ct in class_types if _is_stock_node(ct)})
    custom: list[str] = sorted({ct for ct in class_types if not _is_stock_node(ct)})

    if not custom:
        trust_level = "stock"
    elif not stock:
        trust_level = "fully_custom"
    else:
        trust_level = "mixed"

    warnings: list[str] = []
    if custom:
        warnings.append(
            f"Workflow contains {len(custom)} custom node type(s). Custom "
            "nodes execute arbitrary Python on the ComfyUI server - inspect "
            "their source before queueing if the workflow is from an "
            "untrusted source."
        )

    return json.dumps({
        "total_class_types": len(set(class_types)),
        "trust_level": trust_level,
        "stock_nodes": stock,
        "custom_nodes": custom,
        "warnings": warnings,
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Recommend Runtime",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_recommend_runtime(ctx: Context = None) -> str:
    """Inspect connected GPU and recommend local vs Comfy Cloud routing.

    Returns one of three verdicts:
    - `ok`     - run everything locally (>=8 GB discrete VRAM or >=32 GB
                 unified Apple Silicon)
    - `marginal` - SD 1.5 OK, SDXL tight, Flux/video unlikely. Cloud
                 recommended for heavy workloads.
    - `cloud`  - no usable GPU, <6 GB VRAM, <16 GB unified, Intel Mac, or
                 Rosetta Python. Route to Comfy Cloud.

    Also reports the appropriate `comfy-cli` install flag (--nvidia,
    --amd, --m-series, --cpu) so the caller can pass it to
    comfy_install_node / comfy_launch_server flows.
    """
    try:
        stats = await _client(ctx).get_system_stats()
    except Exception as e:
        return json.dumps({
            "verdict": "cloud",
            "reasons": [f"Could not reach ComfyUI /system_stats: {e}"],
            "route_to_cloud": True,
            "comfy_cli_flag": None,
            "supports": {"sd15": False, "sdxl": False, "flux2": False, "video": False},
        }, indent=2)

    devices = stats.get("devices", []) or []
    system = stats.get("system", {}) or {}
    os_name = (system.get("os") or "").lower()

    reasons: list[str] = []
    supports = {"sd15": False, "sdxl": False, "flux2": False, "video": False}
    cli_flag: str | None = None
    verdict = "cloud"

    if not devices:
        reasons.append("No GPU devices reported by ComfyUI")
        cli_flag = "--cpu"
        verdict = "cloud"
    else:
        # Pick the highest-VRAM device; that's what matters for routing.
        best = max(devices, key=lambda d: int(d.get("vram_total", 0) or 0))
        vram_total = int(best.get("vram_total", 0) or 0)
        vram_total_gb = vram_total / (1024 ** 3)
        device_type = (best.get("type") or "").lower()
        device_name = (best.get("name") or "").lower()

        # CLI flag heuristic
        if "mps" in device_type or "apple" in device_name or "m1" in device_name or "m2" in device_name or "m3" in device_name or "m4" in device_name:
            cli_flag = "--m-series"
        elif "cuda" in device_type or "nvidia" in device_name or "rtx" in device_name or "geforce" in device_name:
            cli_flag = "--nvidia"
        elif "rocm" in device_type or "amd" in device_name or "radeon" in device_name:
            cli_flag = "--amd"
        elif "cpu" in device_type:
            cli_flag = "--cpu"
        else:
            cli_flag = "--nvidia"  # most likely default

        is_apple_silicon = cli_flag == "--m-series"

        if is_apple_silicon:
            # On Apple Silicon, "VRAM" reported by ComfyUI is unified memory.
            if vram_total_gb >= 32:
                verdict = "ok"
                supports = {"sd15": True, "sdxl": True, "flux2": True, "video": True}
                reasons.append(f"Apple Silicon with {vram_total_gb:.0f} GB unified memory: comfortable headroom")
            elif vram_total_gb >= 16:
                verdict = "marginal"
                supports = {"sd15": True, "sdxl": True, "flux2": False, "video": False}
                reasons.append(f"Apple Silicon with {vram_total_gb:.0f} GB unified: SD 1.5/SDXL OK, Flux/video tight")
            else:
                verdict = "cloud"
                reasons.append(f"Apple Silicon with only {vram_total_gb:.0f} GB unified - route to cloud")
        else:
            # Discrete GPU heuristic
            if vram_total_gb >= 12:
                verdict = "ok"
                supports = {"sd15": True, "sdxl": True, "flux2": True, "video": True}
                reasons.append(f"{best.get('name', 'GPU')} with {vram_total_gb:.0f} GB VRAM: full workflow support")
            elif vram_total_gb >= 8:
                verdict = "ok"
                supports = {"sd15": True, "sdxl": True, "flux2": False, "video": False}
                reasons.append(f"{best.get('name', 'GPU')} with {vram_total_gb:.0f} GB VRAM: SD 1.5/SDXL OK, Flux/video may OOM")
            elif vram_total_gb >= 6:
                verdict = "marginal"
                supports = {"sd15": True, "sdxl": False, "flux2": False, "video": False}
                reasons.append(f"{best.get('name', 'GPU')} with {vram_total_gb:.0f} GB VRAM: SD 1.5 only - SDXL tight")
            else:
                verdict = "cloud"
                reasons.append(f"{best.get('name', 'GPU')} with only {vram_total_gb:.0f} GB VRAM - cloud recommended")

    if "intel" in os_name and verdict == "ok":
        # Intel CPU / Intel Mac warning kept advisory
        reasons.append("Intel platform detected - performance may lag NVIDIA / Apple Silicon")

    return json.dumps({
        "verdict": verdict,
        "reasons": reasons,
        "route_to_cloud": verdict == "cloud",
        "comfy_cli_flag": cli_flag,
        "supports": supports,
        "device_count": len(devices),
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Suggest Timeout",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_suggest_timeout(workflow: dict, ctx: Context = None) -> str:
    """Recommend an HTTP timeout for a workflow based on its output nodes.

    Default ComfyPilot timeout is 300 s. Video / audio / 3D / training
    workflows routinely exceed that. This tool walks the workflow, finds
    every output-producing node, and returns the largest matching timeout
    plus the node that drove the decision.

    Args:
        workflow: API-format workflow dict.
    """
    if not isinstance(workflow, dict) or not workflow:
        return json.dumps({"error": "workflow must be a non-empty dict"})

    default = 300
    suggested = default
    drivers: list[dict] = []
    schemas = await _workflow_schemas(workflow, ctx)

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type", "")
        t = _timeout_for_node(ct, schemas.get(str(node_id)))
        if t is not None:
            drivers.append({"node_id": node_id, "class_type": ct, "suggested_seconds": t})
            if t > suggested:
                suggested = t

    rationale = (
        f"Default timeout of {default}s applies."
        if suggested == default
        else f"Bumped from {default}s to {suggested}s due to {len(drivers)} long-running node(s)."
    )

    return json.dumps({
        "default_seconds": default,
        "suggested_seconds": suggested,
        "drivers": drivers,
        "rationale": rationale,
    }, indent=2)

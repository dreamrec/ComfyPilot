"""Output routing tools - 4 tools for cross-app image delivery.

Each send tool:
1. Atomically writes the image (temp file + os.replace).
2. Emits a <filename>.json sidecar manifest with generation metadata
   (prompt_id, seed, model refs, dimensions, timestamp) when a prompt_id
   is supplied and job history is reachable.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


def _destination_dir(configured: str, default: Path) -> Path:
    return Path(configured or str(default)).expanduser()


def _validate_filename(filename: str) -> str:
    if not filename:
        raise ValueError("Filename cannot be empty")

    for path_cls in (PurePosixPath, PureWindowsPath):
        parsed = path_cls(filename)
        if parsed.anchor or len(parsed.parts) != 1 or parsed.parts[0] in {"", ".", ".."}:
            raise ValueError("Filename must be a simple file name without path components")

    return filename


def _prepare_destination_path(dest_dir: Path, filename: str) -> Path:
    safe_name = _validate_filename(filename)
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir / safe_name


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via <path>.tmp.<uuid> then os.replace onto <path>. Rename is atomic on POSIX + NT."""
    tmp = path.with_name(path.name + f".tmp.{uuid.uuid4().hex[:6]}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _manifest_from_history(history_entry: dict) -> dict[str, Any]:
    """Extract a stable metadata summary from a ComfyUI /history/{id} entry."""
    prompt = history_entry.get("prompt", [])
    # Prompt is typically [priority, id, graph_api_format, extra, client_id]
    workflow = {}
    if isinstance(prompt, list) and len(prompt) >= 3 and isinstance(prompt[2], dict):
        workflow = prompt[2]

    seeds: list[int] = []
    model_refs: list[str] = []
    dimensions: list[dict[str, int]] = []

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {}) or {}
        class_type = node.get("class_type", "")
        if "seed" in inputs and isinstance(inputs["seed"], int):
            seeds.append(inputs["seed"])
        if class_type in {"CheckpointLoaderSimple", "UNETLoader", "VAELoader", "LoraLoader", "ControlNetLoader"}:
            for key in ("ckpt_name", "unet_name", "vae_name", "lora_name", "control_net_name"):
                val = inputs.get(key)
                if isinstance(val, str) and val:
                    model_refs.append(val)
        if class_type in {"EmptyLatentImage", "EmptySD3LatentImage", "EmptyHunyuanLatentVideo", "EmptyLTXVLatentVideo"}:
            w = inputs.get("width", 0) or 0
            h = inputs.get("height", 0) or 0
            dimensions.append({"width": int(w), "height": int(h)})

    return {
        "seeds": seeds,
        "model_refs": sorted(set(model_refs)),
        "dimensions": dimensions,
    }


async def _build_manifest(ctx: Context | None, prompt_id: str | None, filename: str, subfolder: str, dest_path: Path, size_bytes: int) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema_version": "comfypilot/manifest/v1",
        "filename": filename,
        "subfolder": subfolder,
        "destination_path": str(dest_path),
        "size_bytes": size_bytes,
        "timestamp": time.time(),
        "prompt_id": prompt_id,
    }
    if ctx is None or not prompt_id:
        return manifest

    try:
        client = _client(ctx)
        history = await client.get_history(prompt_id=prompt_id)
        entry = history.get(prompt_id) if isinstance(history, dict) else None
        if isinstance(entry, dict):
            manifest.update(_manifest_from_history(entry))
    except Exception:
        pass
    return manifest


def _write_manifest_sidecar(dest_path: Path, manifest: dict[str, Any]) -> Path:
    sidecar = dest_path.with_suffix(dest_path.suffix + ".json")
    _atomic_write_bytes(sidecar, json.dumps(manifest, indent=2).encode("utf-8"))
    return sidecar


@mcp.tool(
    annotations={
        "title": "Send to Disk",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_send_to_disk(
    filename: str,
    subfolder: str = "",
    output_dir: str = "",
    prompt_id: str = "",
    ctx: Context = None,
) -> str:
    """Download an image from ComfyUI and save to local disk atomically with a sidecar manifest.

    Args:
        filename: The image filename in ComfyUI outputs
        subfolder: Optional subfolder in ComfyUI outputs
        output_dir: Optional override for output directory (default: COMFY_OUTPUT_DIR env var)
        prompt_id: Optional prompt_id to enrich the manifest with history metadata
    """
    dest_dir = _destination_dir(
        output_dir or os.environ.get("COMFY_OUTPUT_DIR", ""),
        Path.home() / "comfypilot_output",
    )
    try:
        dest_path = _prepare_destination_path(dest_dir, filename)
    except ValueError as exc:
        return json.dumps({"error": str(exc), "filename": filename}, indent=2)

    client = _client(ctx)
    image_bytes = await client.get_image(filename, subfolder=subfolder)
    _atomic_write_bytes(dest_path, image_bytes)

    manifest = await _build_manifest(ctx, prompt_id or None, filename, subfolder, dest_path, len(image_bytes))
    sidecar = _write_manifest_sidecar(dest_path, manifest)

    return json.dumps(
        {
            "status": "saved",
            "path": str(dest_path),
            "manifest_path": str(sidecar),
            "size_bytes": len(image_bytes),
        },
        indent=2,
    )


@mcp.tool(
    annotations={
        "title": "Send to TouchDesigner",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_send_to_td(
    filename: str,
    subfolder: str = "",
    prompt_id: str = "",
    ctx: Context = None,
) -> str:
    """Download image and save for TouchDesigner consumption atomically with sidecar manifest.

    Args:
        filename: The image filename in ComfyUI outputs
        subfolder: Optional subfolder in ComfyUI outputs
        prompt_id: Optional prompt_id to enrich the manifest with history metadata
    """
    dest_dir = _destination_dir(
        os.environ.get("COMFY_TD_OUTPUT_DIR", ""),
        Path.home() / "comfypilot_output" / "touchdesigner",
    )
    try:
        dest_path = _prepare_destination_path(dest_dir, filename)
    except ValueError as exc:
        return json.dumps({"error": str(exc), "filename": filename}, indent=2)

    client = _client(ctx)
    image_bytes = await client.get_image(filename, subfolder=subfolder)
    _atomic_write_bytes(dest_path, image_bytes)

    manifest = await _build_manifest(ctx, prompt_id or None, filename, subfolder, dest_path, len(image_bytes))
    sidecar = _write_manifest_sidecar(dest_path, manifest)

    td_command = f"op('moviefilein1').par.file = {str(dest_path)!r}"

    return json.dumps(
        {
            "status": "saved",
            "path": str(dest_path),
            "manifest_path": str(sidecar),
            "size_bytes": len(image_bytes),
            "td_command": td_command,
            "suggestion": f"Use td_exec_python with: {td_command}",
        },
        indent=2,
    )


@mcp.tool(
    annotations={
        "title": "Send to Blender",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_send_to_blender(
    filename: str,
    subfolder: str = "",
    prompt_id: str = "",
    ctx: Context = None,
) -> str:
    """Download image and save for Blender consumption atomically with sidecar manifest.

    Args:
        filename: The image filename in ComfyUI outputs
        subfolder: Optional subfolder in ComfyUI outputs
        prompt_id: Optional prompt_id to enrich the manifest with history metadata
    """
    dest_dir = _destination_dir(
        os.environ.get("COMFY_BLENDER_OUTPUT_DIR", ""),
        Path.home() / "comfypilot_output" / "blender",
    )
    try:
        dest_path = _prepare_destination_path(dest_dir, filename)
    except ValueError as exc:
        return json.dumps({"error": str(exc), "filename": filename}, indent=2)

    client = _client(ctx)
    image_bytes = await client.get_image(filename, subfolder=subfolder)
    _atomic_write_bytes(dest_path, image_bytes)

    manifest = await _build_manifest(ctx, prompt_id or None, filename, subfolder, dest_path, len(image_bytes))
    sidecar = _write_manifest_sidecar(dest_path, manifest)

    blender_command = f"bpy.data.images.load({str(dest_path)!r})"

    return json.dumps(
        {
            "status": "saved",
            "path": str(dest_path),
            "manifest_path": str(sidecar),
            "size_bytes": len(image_bytes),
            "blender_command": blender_command,
            "suggestion": f"Use Blender Python console with: {blender_command}",
        },
        indent=2,
    )


@mcp.tool(
    annotations={
        "title": "List Destinations",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_destinations(ctx: Context = None) -> str:
    """List configured output destinations and their paths."""
    destinations = {
        "disk": {
            "configured": bool(os.environ.get("COMFY_OUTPUT_DIR")),
            "path": str(_destination_dir(os.environ.get("COMFY_OUTPUT_DIR", ""), Path.home() / "comfypilot_output")),
        },
        "touchdesigner": {
            "configured": bool(os.environ.get("COMFY_TD_OUTPUT_DIR")),
            "path": str(
                _destination_dir(
                    os.environ.get("COMFY_TD_OUTPUT_DIR", ""),
                    Path.home() / "comfypilot_output" / "touchdesigner",
                )
            ),
        },
        "blender": {
            "configured": bool(os.environ.get("COMFY_BLENDER_OUTPUT_DIR")),
            "path": str(
                _destination_dir(
                    os.environ.get("COMFY_BLENDER_OUTPUT_DIR", ""),
                    Path.home() / "comfypilot_output" / "blender",
                )
            ),
        },
    }
    return json.dumps({"destinations": destinations}, indent=2)

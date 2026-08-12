"""System tools - 6 tools for ComfyUI system info and management."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.responses import SystemStats
from comfy_mcp.errors import ComfyAPIError
from comfy_mcp.safety.confirm import confirm_destructive
from comfy_mcp.server import mcp
from comfy_mcp.tools.instance import inspect_instance


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


@mcp.tool(
    annotations={
        "title": "Get System Stats",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_system_stats(ctx: Context) -> SystemStats:
    """Get ComfyUI system stats: OS, GPU, VRAM, version info. Returns structured SystemStats."""
    result = await _client(ctx).get_system_stats()
    return SystemStats.model_validate(result)


@mcp.tool(
    annotations={
        "title": "Get GPU Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_gpu_info(ctx: Context) -> str:
    """Get detailed GPU info: VRAM total/free/used, torch version, device names."""
    stats = await _client(ctx).get_system_stats()
    devices = stats.get("devices", [])
    gpu_info = {"devices": devices, "count": len(devices)}
    for dev in devices:
        total = dev.get("vram_total", 0)
        free = dev.get("vram_free", 0)
        dev["vram_used"] = total - free
        if total > 0:
            dev["vram_used_pct"] = round((total - free) / total * 100, 1)
    return json.dumps(gpu_info, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Features",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_features(ctx: Context) -> str:
    """List enabled ComfyUI features (v0.17+)."""
    result = await _client(ctx).get_features()
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "List Extensions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_extensions(ctx: Context) -> str:
    """List all installed ComfyUI custom nodes and extensions."""
    extensions = await _client(ctx).get_extensions()
    return json.dumps({"extensions": extensions, "count": len(extensions)}, indent=2)


@mcp.tool(
    annotations={
        "title": "Restart ComfyUI",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_restart(
    expected_instance_id: str = "",
    expected_pid: int | None = None,
    confirm: bool = False,
    wait_for_health: bool = True,
    timeout_seconds: float = 120.0,
    ctx: Context = None,
) -> str:
    """Safely restart the selected local instance through Manager V2.

    First call ``comfy_instance_doctor`` and pass back either its
    ``instance_id`` or listener PID. The selector is checked immediately before
    the mutation. Desktop/Manager V2 is used when available; ComfyPilot never
    falls back to launching a competing server on port 8188.
    """
    before = await inspect_instance(ctx)
    if before.get("status") != "ok":
        return json.dumps({
            "status": "unavailable",
            "message": "The selected ComfyUI endpoint is not healthy enough to restart safely.",
            "instance": before,
        }, indent=2)
    if not before.get("local"):
        return json.dumps({
            "status": "controlled_fallback",
            "message": "Remote restart is intentionally disabled because no local PID/owner can be selected safely.",
            "base_url": before.get("base_url"),
        }, indent=2)
    actual_id = before.get("instance_id")
    old_pid = (before.get("listener") or {}).get("pid")

    if actual_id is None and old_pid is None:
        return json.dumps({
            "status": "controlled_fallback",
            "message": "No stable instance ID or listener PID was available for safe restart selection.",
            "base_url": before.get("base_url"),
            "owner_type": before.get("owner_type"),
        }, indent=2)

    if not expected_instance_id and expected_pid is None:
        selector = (
            {"expected_instance_id": actual_id}
            if actual_id
            else {"expected_pid": old_pid}
        )
        return json.dumps({
            "status": "selection_required",
            "message": "Pass the connected instance selector back to confirm the exact restart target.",
            "selector": selector,
            "instance_id": actual_id,
            "pid": old_pid,
            "base_url": before.get("base_url"),
        }, indent=2)
    if expected_instance_id and expected_instance_id != actual_id:
        return json.dumps({
            "status": "selection_mismatch",
            "message": f"Expected instance {expected_instance_id!r}, connected instance is {actual_id!r}.",
        }, indent=2)
    if expected_pid is not None and int(expected_pid) != old_pid:
        return json.dumps({
            "status": "selection_mismatch",
            "message": f"Expected listener PID {expected_pid}, connected listener PID is {old_pid}.",
        }, indent=2)

    manager = before.get("manager") or {}
    if not manager.get("available") or manager.get("api_generation") != "v2":
        return json.dumps({
            "status": "controlled_fallback",
            "message": "Manager V2 restart is unavailable. Restart the selected instance through its supervisor.",
            "owner_type": before.get("owner_type"),
            "supervisor": before.get("supervisor"),
            "instance_id": actual_id,
            "pid": old_pid,
            "reason": manager.get("error") or "Manager V2 was not detected",
        }, indent=2)

    if not await confirm_destructive(
        ctx,
        f"Restart ComfyUI instance {actual_id or old_pid!r} through Manager V2?",
        confirm,
    ):
        return json.dumps({
            "status": "cancelled",
            "operation": "restart",
            "reason": "confirmation_required_or_declined",
        }, indent=2)

    route = str(manager.get("restart_route") or "/v2/manager/reboot")
    request_uncertain = False
    try:
        await _client(ctx).post(route, {})
    except ComfyAPIError as exc:
        return json.dumps({
            "status": "rejected",
            "message": "ComfyUI Manager rejected the restart request.",
            "route": route,
            "error": exc.to_dict(),
        }, indent=2)
    except Exception as exc:
        # Manager exits the process from inside this handler and can close the
        # socket before an HTTP body is received. Health/PID verification below
        # decides whether the request actually succeeded.
        request_uncertain = True
        request_error = str(exc)
    else:
        request_error = None

    if not wait_for_health:
        return json.dumps({
            "status": "restart_requested",
            "route": route,
            "instance_id": actual_id,
            "previous_pid": old_pid,
            "request_uncertain": request_uncertain,
            "request_error": request_error,
        }, indent=2)

    timeout_seconds = min(max(float(timeout_seconds), 10.0), 300.0)
    deadline = time.monotonic() + timeout_seconds
    saw_offline = False
    last_error: str | None = None
    while time.monotonic() < deadline:
        await asyncio.sleep(1.0)
        try:
            current = await inspect_instance(ctx)
        except Exception as exc:
            saw_offline = True
            last_error = str(exc)
            continue
        if current.get("status") != "ok":
            saw_offline = True
            last_error = current.get("error")
            continue
        new_pid = (current.get("listener") or {}).get("pid")
        if (old_pid is not None and new_pid is not None and new_pid != old_pid) or (
            old_pid is None and saw_offline
        ):
            return json.dumps({
                "status": "restarted",
                "route": route,
                "instance_id": current.get("instance_id"),
                "previous_pid": old_pid,
                "pid": new_pid,
                "saw_offline": saw_offline,
                "request_uncertain": request_uncertain,
                "request_error": request_error,
                "health": "ok",
                "versions": current.get("versions"),
            }, indent=2)

    return json.dumps({
        "status": "restart_unverified",
        "message": "Restart was requested but a new healthy listener PID was not observed before timeout.",
        "route": route,
        "instance_id": actual_id,
        "previous_pid": old_pid,
        "saw_offline": saw_offline,
        "request_uncertain": request_uncertain,
        "request_error": request_error,
        "last_health_error": last_error,
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Free VRAM",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_free_vram(
    unload_models: bool = False,
    free_memory: bool = False,
    ctx: Context = None,
) -> str:
    """Unload models and/or free VRAM memory.

    Args:
        unload_models: Unload all loaded models from VRAM
        free_memory: Free cached memory allocations
    """
    result = await _client(ctx).free_vram(
        unload_models=unload_models,
        free_memory=free_memory,
    )
    return json.dumps({"status": "ok", "unloaded_models": unload_models, "freed_memory": free_memory})

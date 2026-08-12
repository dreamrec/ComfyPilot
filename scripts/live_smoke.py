#!/usr/bin/env python3
"""End-to-end smoke test for a live ComfyPilot/ComfyUI pair.

The default mode is read-only.  It starts a fresh ComfyPilot stdio server from
this checkout, initializes MCP, verifies the expected registry surface, and
exercises the operational read paths that are most useful for controlling a
ComfyUI Desktop installation.

Pass ``--run-3d`` to additionally queue a small, model-free GeometryPack
workflow.  That workflow combines three primitives and writes one uniquely
named GLB beneath ComfyUI's output directory.  The script never restarts,
stops, installs, cancels, clears, or deletes anything.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import AnyUrl


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMFY_URL = "http://127.0.0.1:8000"

REQUIRED_TOOLS = {
    "comfy_get_system_stats",
    "comfy_instance_doctor",
    "comfy_list_installed_nodes",
    "comfy_get_environment_status",
    "comfy_list_workers",
    "comfy_list_artifacts",
    "comfy_get_artifact",
    "comfy_check_vram",
    "comfy_get_status",
    "comfy_validate_workflow",
}

EXECUTION_TOOLS = {
    "comfy_queue_prompt",
    "comfy_get_run_result",
}

REQUIRED_RESOURCES = {
    "comfy://system/info",
    "comfy://server/capabilities",
    "comfy://nodes/catalog",
}

TOOL_INTEGRATION_HINTS = {
    "comfy_instance_doctor": "register comfy_mcp.tools.instance",
    "comfy_get_environment_status": "register comfy_mcp.tools.workers",
    "comfy_list_workers": "register comfy_mcp.tools.workers",
    "comfy_list_artifacts": "register comfy_mcp.tools.artifacts",
    "comfy_get_artifact": "register comfy_mcp.tools.artifacts",
}


class SmokeFailure(RuntimeError):
    """A failed smoke assertion with a concise operator-facing message."""


class SmokeRecorder:
    """Collect checks without hiding later diagnostics after one failure."""

    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.failures: list[dict[str, str]] = []

    async def run(
        self,
        name: str,
        operation: Callable[[], Awaitable[Any]],
        inspect: Callable[[Any], dict[str, Any]],
    ) -> Any | None:
        started = time.monotonic()
        try:
            value = await operation()
            details = inspect(value)
        except Exception as exc:
            elapsed = round((time.monotonic() - started) * 1000, 1)
            failure = {
                "name": name,
                "type": type(exc).__name__,
                "message": str(exc),
            }
            self.failures.append(failure)
            self.checks.append({
                "name": name,
                "ok": False,
                "duration_ms": elapsed,
                "error": failure,
            })
            return None

        elapsed = round((time.monotonic() - started) * 1000, 1)
        self.checks.append({
            "name": name,
            "ok": True,
            "duration_ms": elapsed,
            "details": details,
        })
        return value

    def fail(self, name: str, message: str, **details: Any) -> None:
        failure = {"name": name, "type": "SmokeFailure", "message": message}
        self.failures.append(failure)
        check: dict[str, Any] = {"name": name, "ok": False, "error": failure}
        if details:
            check["details"] = details
        self.checks.append(check)


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _as_mapping(value: Any, label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label} returned {type(value).__name__}, expected JSON object")
    return value


def _safe_prefix(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_-")
    return (cleaned or "comfypilot_smoke")[:64]


def make_unique_output_name(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{_safe_prefix(prefix)}_{stamp}_{uuid4().hex[:8]}"


def make_geometrypack_workflow(output_name: str) -> dict[str, dict[str, Any]]:
    """Build a model-free three-sphere composite with flat DynamicCombo inputs."""
    return {
        "1": {
            "class_type": "GeomPackCreatePrimitive",
            "inputs": {"shape": "sphere", "size": 0.80, "subdivisions": 2},
        },
        "2": {
            "class_type": "GeomPackCreatePrimitive",
            "inputs": {"shape": "sphere", "size": 0.60, "subdivisions": 2},
        },
        "3": {
            "class_type": "GeomPackTransformMesh",
            "inputs": {
                "trimesh": ["2", 0],
                "operation": "translate",
                "operation.translate_x": 0.0,
                "operation.translate_y": 0.0,
                "operation.translate_z": 1.25,
            },
        },
        "4": {
            "class_type": "GeomPackCreatePrimitive",
            "inputs": {"shape": "sphere", "size": 0.42, "subdivisions": 2},
        },
        "5": {
            "class_type": "GeomPackTransformMesh",
            "inputs": {
                "trimesh": ["4", 0],
                "operation": "translate",
                "operation.translate_x": 0.0,
                "operation.translate_y": 0.0,
                "operation.translate_z": 2.20,
            },
        },
        "6": {
            "class_type": "GeomPackCombineMeshes",
            "inputs": {
                "mesh_a": ["1", 0],
                "mesh_b": ["3", 0],
                "mesh_c": ["5", 0],
            },
        },
        "7": {
            "class_type": "GeomPackSaveMesh",
            "inputs": {
                "trimesh": ["6", 0],
                "file_path": output_name,
                "format": "glb",
            },
        },
    }


def _parse_text_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def decode_tool_result(result: Any, tool_name: str) -> Any:
    """Normalize MCP text and structured tool results into a Python value."""
    text_blocks = [
        content.text
        for content in getattr(result, "content", [])
        if isinstance(getattr(content, "text", None), str)
    ]
    if getattr(result, "isError", False):
        message = "\n".join(text_blocks).strip() or "MCP tool returned isError=true"
        raise SmokeFailure(f"{tool_name}: {message}")

    # FastMCP string-returning tools put their actual JSON in TextContent.
    # Prefer that over a possible structured wrapper such as {"result": ...}.
    for text in text_blocks:
        parsed = _parse_text_json(text)
        if parsed is not None:
            return parsed

    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        wrapped = structured.get("result")
        if len(structured) == 1 and isinstance(wrapped, str):
            parsed = _parse_text_json(wrapped)
            return parsed if parsed is not None else wrapped
        return structured

    if text_blocks:
        return "\n".join(text_blocks)
    raise SmokeFailure(f"{tool_name}: MCP returned no text or structured content")


def decode_resource_result(result: Any, uri: str) -> Any:
    texts = [
        content.text
        for content in getattr(result, "contents", [])
        if isinstance(getattr(content, "text", None), str)
    ]
    _require(texts, f"{uri}: resource returned no text content")
    for text in texts:
        parsed = _parse_text_json(text)
        if parsed is not None:
            return parsed
    return "\n".join(texts)


async def _bounded(awaitable: Awaitable[Any], seconds: float, label: str) -> Any:
    try:
        return await asyncio.wait_for(awaitable, timeout=seconds)
    except asyncio.TimeoutError as exc:
        raise SmokeFailure(f"{label} exceeded {seconds:.1f}s timeout") from exc


async def call_json(
    session: ClientSession,
    name: str,
    arguments: dict[str, Any] | None,
    timeout: float,
) -> Any:
    result = await _bounded(
        session.call_tool(
            name,
            arguments or {},
            read_timeout_seconds=timedelta(seconds=timeout),
        ),
        timeout + 2.0,
        name,
    )
    return decode_tool_result(result, name)


async def read_json_resource(
    session: ClientSession,
    uri: str,
    timeout: float,
) -> Any:
    result = await _bounded(session.read_resource(AnyUrl(uri)), timeout, uri)
    return decode_resource_result(result, uri)


async def list_all_tools(session: ClientSession, timeout: float) -> list[Any]:
    values: list[Any] = []
    cursor: str | None = None
    while True:
        page = await _bounded(session.list_tools(cursor=cursor), timeout, "tools/list")
        values.extend(page.tools)
        cursor = page.nextCursor
        if not cursor:
            return values


async def list_all_resources(session: ClientSession, timeout: float) -> list[Any]:
    values: list[Any] = []
    cursor: str | None = None
    while True:
        page = await _bounded(session.list_resources(cursor=cursor), timeout, "resources/list")
        values.extend(page.resources)
        cursor = page.nextCursor
        if not cursor:
            return values


async def list_all_resource_templates(session: ClientSession, timeout: float) -> list[Any]:
    values: list[Any] = []
    cursor: str | None = None
    while True:
        page = await _bounded(
            session.list_resource_templates(cursor=cursor),
            timeout,
            "resources/templates/list",
        )
        values.extend(page.resourceTemplates)
        cursor = page.nextCursor
        if not cursor:
            return values


def _normalise_url(url: str) -> str:
    value = url.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise argparse.ArgumentTypeError("COMFY_URL must be an absolute http(s) URL")
    return value


def _server_environment(args: argparse.Namespace) -> dict[str, str]:
    env = dict(os.environ)
    source_root = str(REPO_ROOT / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        os.pathsep.join([source_root, existing_pythonpath])
        if existing_pythonpath
        else source_root
    )
    env["COMFY_URL"] = args.comfy_url
    env["COMFY_TIMEOUT"] = str(args.call_timeout)
    env["COMFY_STRICT_CONFIRM"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _integration_hints(missing_tools: list[str]) -> list[str]:
    hints = {
        TOOL_INTEGRATION_HINTS[name]
        for name in missing_tools
        if name in TOOL_INTEGRATION_HINTS
    }
    if missing_tools and not hints:
        hints.add("ensure comfy_mcp.tool_registry imports the module defining each missing tool")
    return sorted(hints)


def inspect_system(value: Any) -> dict[str, Any]:
    data = _as_mapping(value, "comfy_get_system_stats")
    system = _as_mapping(data.get("system"), "comfy_get_system_stats.system")
    devices = data.get("devices")
    _require(isinstance(devices, list), "comfy_get_system_stats.devices is not a list")
    _require(system.get("comfyui_version"), "ComfyUI version is missing from system stats")
    return {
        "comfyui_version": system.get("comfyui_version"),
        "frontend_version": (
            system.get("comfyui_frontend_package")
            or system.get("required_frontend_version")
        ),
        "deploy_environment": system.get("deploy_environment"),
        "device_count": len(devices),
    }


def inspect_system_resource(value: Any) -> dict[str, Any]:
    data = _as_mapping(value, "comfy://system/info")
    system = _as_mapping(data.get("system"), "comfy://system/info.system")
    _require(system.get("comfyui_version"), "system resource omitted ComfyUI version")
    return {"comfyui_version": system.get("comfyui_version")}


def inspect_capabilities(value: Any) -> dict[str, Any]:
    data = _as_mapping(value, "comfy://server/capabilities")
    _require(data.get("version"), "capability resource omitted the detected ComfyUI version")
    _require(data.get("profile") in {"local", "cloud", "unknown"}, "capability resource omitted profile")
    return {
        "profile": data.get("profile"),
        "comfyui_version": data.get("version"),
        "ws_available": data.get("ws_available"),
        "jobs_api": data.get("jobs_api"),
        "auth_method": data.get("auth_method"),
    }


def inspect_instance(value: Any) -> dict[str, Any]:
    data = _as_mapping(value, "comfy_instance_doctor")
    _require(data.get("status") == "ok", f"instance doctor status is {data.get('status')!r}")
    _require(data.get("base_url"), "instance doctor omitted base_url")
    manager = data.get("manager") if isinstance(data.get("manager"), dict) else {}
    listener = data.get("listener") if isinstance(data.get("listener"), dict) else {}
    return {
        "instance_id": data.get("instance_id"),
        "base_url": data.get("base_url"),
        "owner_type": data.get("owner_type"),
        "listener_pid": listener.get("pid"),
        "manager_available": manager.get("available"),
        "manager_version": manager.get("version"),
        "warning_count": len(data.get("warnings") or []),
    }


def inspect_manager_inventory(value: Any) -> dict[str, Any]:
    data = _as_mapping(value, "comfy_list_installed_nodes")
    _require(data.get("status") == "ok", f"Manager inventory status is {data.get('status')!r}")
    _require(data.get("source") == "manager_v2", f"expected Manager V2, got {data.get('source')!r}")
    packages = data.get("packages")
    _require(isinstance(packages, list), "Manager V2 inventory omitted packages list")
    return {"source": data.get("source"), "mode": data.get("mode"), "package_count": len(packages)}


def inspect_environments(value: Any) -> dict[str, Any]:
    data = _as_mapping(value, "comfy_get_environment_status")
    _require(data.get("status") in {"ok", "partial"}, f"environment status is {data.get('status')!r}")
    _require(isinstance(data.get("environments"), list), "environment response omitted environments list")
    _require(isinstance(data.get("workers"), list), "environment response omitted workers list")
    errors = data.get("errors") if isinstance(data.get("errors"), dict) else {}
    return {
        "status": data.get("status"),
        "runtime_available": data.get("runtime_available"),
        "environment_count": data.get("environment_count"),
        "discovered_environment_count": data.get("total_discovered_environment_count"),
        "worker_count": data.get("worker_count"),
        "error_endpoints": sorted(errors),
    }


def inspect_workers(value: Any) -> dict[str, Any]:
    data = _as_mapping(value, "comfy_list_workers")
    _require(data.get("status") == "ok", f"worker listing status is {data.get('status')!r}")
    _require(isinstance(data.get("workers"), list), "worker listing omitted workers list")
    return {
        "count": data.get("count"),
        "alive_count": data.get("alive_count"),
        "endpoint_error": data.get("endpoint_error"),
    }


def inspect_artifacts(value: Any) -> dict[str, Any]:
    data = _as_mapping(value, "comfy_list_artifacts")
    _require(data.get("status") == "ok", f"artifact listing status is {data.get('status')!r}")
    _require(isinstance(data.get("artifacts"), list), "artifact listing omitted artifacts list")
    diagnostics = data.get("diagnostics") if isinstance(data.get("diagnostics"), dict) else {}
    return {
        "returned_count": data.get("count"),
        "total_count": data.get("total_count"),
        "output_root": diagnostics.get("output_root"),
        "filesystem_count": diagnostics.get("filesystem_count"),
        "history_count": diagnostics.get("history_count"),
    }


def inspect_vram(value: Any) -> dict[str, Any]:
    data = _as_mapping(value, "comfy_check_vram")
    _require(data.get("status") in {"ok", "warn", "critical", "unknown"}, "invalid VRAM status")
    _require(isinstance(data.get("devices"), list), "VRAM response omitted devices list")
    _require(isinstance(data.get("gpu_processes"), list), "VRAM response omitted gpu_processes list")
    return {
        "status": data.get("status"),
        "used_pct": data.get("vram_used_pct"),
        "device_count": len(data["devices"]),
        "nvml_available": data.get("nvml_available"),
        "gpu_process_count": len(data["gpu_processes"]),
    }


def inspect_status(value: Any, *, require_events: bool) -> dict[str, Any]:
    data = _as_mapping(value, "comfy_get_status")
    queue = _as_mapping(data.get("queue"), "comfy_get_status.queue")
    _require(isinstance(queue.get("running"), int), "status queue.running is not an integer")
    _require(isinstance(queue.get("pending"), int), "status queue.pending is not an integer")
    events = data.get("events") if isinstance(data.get("events"), dict) else {}
    if require_events:
        _require(events.get("running") is True, "event manager is not running")
        _require(events.get("connected") is True, "event manager did not connect to ComfyUI WebSocket")
    return {
        "queue_running": queue.get("running"),
        "queue_pending": queue.get("pending"),
        "events_running": events.get("running"),
        "events_connected": events.get("connected"),
        "event_reconnect_count": events.get("reconnect_count"),
        "event_buffer_size": events.get("buffer_size"),
    }


def inspect_invalid_validation(value: Any) -> dict[str, Any]:
    data = _as_mapping(value, "invalid workflow validation")
    errors = data.get("errors")
    _require(data.get("valid") is False, "workflow missing ckpt_name was incorrectly accepted")
    _require(isinstance(errors, list), "invalid validation omitted errors list")
    joined = "\n".join(str(item) for item in errors).lower()
    _require("missing required input" in joined and "ckpt_name" in joined, "missing ckpt_name error was not reported")
    return {"valid": False, "error_count": len(errors), "passes": data.get("passes")}


def inspect_valid_validation(value: Any) -> dict[str, Any]:
    data = _as_mapping(value, "GeometryPack workflow validation")
    _require(data.get("valid") is True, f"flattened GeometryPack workflow was rejected: {data.get('errors')}")
    errors = data.get("errors")
    _require(isinstance(errors, list) and not errors, "valid GeometryPack workflow returned errors")
    return {
        "valid": True,
        "node_count": data.get("node_count"),
        "passes": data.get("passes"),
        "warnings": data.get("warnings"),
    }


async def wait_for_connected_status(
    session: ClientSession,
    *,
    call_timeout: float,
    event_timeout: float,
    require_events: bool,
) -> dict[str, Any]:
    deadline = time.monotonic() + event_timeout
    last: dict[str, Any] | None = None
    while True:
        value = await call_json(session, "comfy_get_status", {}, call_timeout)
        last = _as_mapping(value, "comfy_get_status")
        events = last.get("events") if isinstance(last.get("events"), dict) else {}
        if not require_events or events.get("connected") is True:
            return last
        if time.monotonic() >= deadline:
            return last
        await asyncio.sleep(0.5)


def _terminal_history_state(data: dict[str, Any]) -> tuple[bool, bool, str]:
    """Return (terminal, success, description) for a RunResult payload."""
    error = data.get("error")
    if error:
        return False, False, str(error)
    status = data.get("status") if isinstance(data.get("status"), dict) else {}
    status_text = str(status.get("status_str") or status.get("status") or "").lower()
    completed = status.get("completed") is True
    if status_text in {"error", "failed", "cancelled", "canceled", "interrupted"}:
        return True, False, status_text
    if status_text in {"success", "completed", "complete"} or completed:
        success = status_text not in {"error", "failed"}
        return True, success, status_text or "completed"
    return False, False, status_text or "pending"


async def execute_geometry_smoke(
    session: ClientSession,
    workflow: dict[str, Any],
    output_name: str,
    *,
    call_timeout: float,
    execution_timeout: float,
    poll_interval: float,
) -> dict[str, Any]:
    queued = _as_mapping(
        await call_json(session, "comfy_queue_prompt", {"workflow": workflow}, call_timeout),
        "comfy_queue_prompt",
    )
    _require(not queued.get("error"), f"queue rejected workflow: {queued.get('error')}")
    prompt_id = queued.get("prompt_id")
    _require(isinstance(prompt_id, str) and prompt_id, "queue response omitted prompt_id")

    deadline = time.monotonic() + execution_timeout
    last_result: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_result = _as_mapping(
            await call_json(
                session,
                "comfy_get_run_result",
                {"prompt_id": prompt_id},
                call_timeout,
            ),
            "comfy_get_run_result",
        )
        terminal, success, description = _terminal_history_state(last_result)
        if terminal:
            _require(success, f"GeometryPack execution ended as {description}")
            break
        await asyncio.sleep(poll_interval)
    else:
        raise SmokeFailure(
            f"GeometryPack prompt {prompt_id} did not finish within {execution_timeout:.1f}s; "
            "it was left untouched"
        )

    artifact_listing = _as_mapping(
        await call_json(
            session,
            "comfy_list_artifacts",
            {"kind": "mesh", "query": output_name, "limit": 20},
            call_timeout,
        ),
        "comfy_list_artifacts",
    )
    artifacts = artifact_listing.get("artifacts")
    _require(isinstance(artifacts, list), "post-run artifact listing omitted artifacts")
    expected = f"{output_name}.glb".lower()
    artifact = next(
        (
            item
            for item in artifacts
            if isinstance(item, dict)
            and str(item.get("relative_path", "")).replace("\\", "/").lower().endswith(expected)
        ),
        None,
    )
    _require(artifact is not None, f"completed prompt did not expose {output_name}.glb")
    relative_path = str(artifact["relative_path"])

    metadata_response = _as_mapping(
        await call_json(
            session,
            "comfy_get_artifact",
            {"relative_path": relative_path, "include_data": False, "include_sha256": True},
            call_timeout,
        ),
        "comfy_get_artifact",
    )
    _require(
        metadata_response.get("status") == "ok" and not metadata_response.get("error"),
        f"artifact metadata failed: {metadata_response.get('error')}",
    )
    metadata = _as_mapping(metadata_response.get("artifact"), "comfy_get_artifact.artifact")
    _require(int(metadata.get("size_bytes") or 0) > 0, "saved GLB is empty")
    _require(bool(metadata.get("sha256")), "saved GLB SHA-256 was not returned")
    return {
        "prompt_id": prompt_id,
        "queue_number": queued.get("queue_number"),
        "output_name": output_name,
        "relative_path": relative_path,
        "size_bytes": metadata.get("size_bytes"),
        "sha256": metadata.get("sha256"),
        "history_status": last_result.get("status"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Spawn ComfyPilot over stdio and smoke-test a live ComfyUI instance. "
            "Read-only unless --run-3d is supplied."
        ),
    )
    parser.add_argument(
        "--comfy-url",
        type=_normalise_url,
        default=_normalise_url(os.environ.get("COMFY_URL", DEFAULT_COMFY_URL)),
        help=f"ComfyUI base URL (default: COMFY_URL or {DEFAULT_COMFY_URL})",
    )
    parser.add_argument(
        "--server-command",
        default=sys.executable,
        help="Executable used to spawn ComfyPilot (default: current Python)",
    )
    parser.add_argument(
        "--server-arg",
        action="append",
        default=None,
        help=(
            "Argument for the server command; repeat as needed. The default is "
            "'-m comfy_mcp.server --transport stdio'."
        ),
    )
    parser.add_argument("--startup-timeout", type=float, default=30.0)
    parser.add_argument("--call-timeout", type=float, default=45.0)
    parser.add_argument("--event-timeout", type=float, default=15.0)
    parser.add_argument("--execution-timeout", type=float, default=120.0)
    parser.add_argument("--poll-interval", type=float, default=0.75)
    parser.add_argument(
        "--run-3d",
        action="store_true",
        help="Queue one model-free GeometryPack composite and keep its uniquely named GLB output",
    )
    parser.add_argument("--output-prefix", default="comfypilot_smoke")
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Also write the final JSON summary to this path",
    )
    parser.add_argument("--compact", action="store_true", help="Print compact JSON")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    for name in (
        "startup_timeout",
        "call_timeout",
        "event_timeout",
        "execution_timeout",
        "poll_interval",
    ):
        value = float(getattr(args, name))
        if value <= 0:
            raise SmokeFailure(f"--{name.replace('_', '-')} must be greater than zero")


async def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    started_wall = datetime.now(timezone.utc)
    started = time.monotonic()
    recorder = SmokeRecorder()
    output_name = make_unique_output_name(args.output_prefix)
    workflow = make_geometrypack_workflow(output_name)
    server_args = args.server_arg or ["-m", "comfy_mcp.server", "--transport", "stdio"]
    summary: dict[str, Any] = {
        "ok": False,
        "mode": "read+model-free-3d" if args.run_3d else "read-only",
        "comfy_url": args.comfy_url,
        "started_at": started_wall.isoformat(),
        "server": {
            "command": args.server_command,
            "args": server_args,
            "cwd": str(REPO_ROOT),
        },
        "discovery": {},
        "checks": recorder.checks,
        "failures": recorder.failures,
        "execution": None,
    }

    parameters = StdioServerParameters(
        command=args.server_command,
        args=server_args,
        env=_server_environment(args),
        cwd=REPO_ROOT,
    )

    try:
        async with AsyncExitStack() as stack:
            read_stream, write_stream = await stack.enter_async_context(
                stdio_client(parameters, errlog=sys.stderr)
            )
            session = await stack.enter_async_context(
                ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timedelta(seconds=args.call_timeout),
                )
            )
            initialization = await _bounded(session.initialize(), args.startup_timeout, "MCP initialize")
            summary["server"].update({
                "protocol_version": initialization.protocolVersion,
                "name": initialization.serverInfo.name,
                "version": initialization.serverInfo.version,
            })

            tools = await list_all_tools(session, args.call_timeout)
            resources = await list_all_resources(session, args.call_timeout)
            templates = await list_all_resource_templates(session, args.call_timeout)
            tool_names = {tool.name for tool in tools}
            resource_uris = {str(resource.uri) for resource in resources}
            required_tools = set(REQUIRED_TOOLS)
            if args.run_3d:
                required_tools.update(EXECUTION_TOOLS)
            missing_tools = sorted(required_tools - tool_names)
            missing_resources = sorted(REQUIRED_RESOURCES - resource_uris)
            summary["discovery"] = {
                "tool_count": len(tool_names),
                "resource_count": len(resource_uris),
                "resource_template_count": len(templates),
                "missing_tools": missing_tools,
                "missing_resources": missing_resources,
                "integration_hints": _integration_hints(missing_tools),
            }
            if missing_tools or missing_resources:
                recorder.fail(
                    "registry",
                    "required ComfyPilot MCP surface is not registered; no live calls were made",
                    missing_tools=missing_tools,
                    missing_resources=missing_resources,
                    integration_hints=_integration_hints(missing_tools),
                )
                return summary
            recorder.checks.append({
                "name": "registry",
                "ok": True,
                "details": {
                    "tool_count": len(tool_names),
                    "resource_count": len(resource_uris),
                    "resource_template_count": len(templates),
                },
            })

            system_stats = await recorder.run(
                "system",
                lambda: call_json(session, "comfy_get_system_stats", {}, args.call_timeout),
                inspect_system,
            )
            await recorder.run(
                "system_resource",
                lambda: read_json_resource(session, "comfy://system/info", args.call_timeout),
                inspect_system_resource,
            )
            capabilities = await recorder.run(
                "capabilities_resource",
                lambda: read_json_resource(
                    session,
                    "comfy://server/capabilities",
                    args.call_timeout,
                ),
                inspect_capabilities,
            )
            await recorder.run(
                "instance_doctor",
                lambda: call_json(session, "comfy_instance_doctor", {}, args.call_timeout),
                inspect_instance,
            )
            await recorder.run(
                "manager_inventory",
                lambda: call_json(
                    session,
                    "comfy_list_installed_nodes",
                    {"mode": "imported", "prefer_manager_api": True},
                    args.call_timeout,
                ),
                inspect_manager_inventory,
            )
            await recorder.run(
                "environment_status",
                lambda: call_json(
                    session,
                    "comfy_get_environment_status",
                    {"configured_only": True, "limit": 500},
                    args.call_timeout,
                ),
                inspect_environments,
            )
            await recorder.run(
                "workers",
                lambda: call_json(session, "comfy_list_workers", {}, args.call_timeout),
                inspect_workers,
            )
            await recorder.run(
                "artifacts",
                lambda: call_json(
                    session,
                    "comfy_list_artifacts",
                    {"kind": "all", "limit": 5, "filesystem_fallback": True},
                    args.call_timeout,
                ),
                inspect_artifacts,
            )
            vram = await recorder.run(
                "vram",
                lambda: call_json(session, "comfy_check_vram", {}, args.call_timeout),
                inspect_vram,
            )
            if isinstance(system_stats, dict) and isinstance(vram, dict):
                system_devices = system_stats.get("devices")
                vram_devices = vram.get("devices")
                if isinstance(system_devices, list) and system_devices and not vram_devices:
                    recorder.fail("vram_device_consistency", "system reports a GPU but VRAM guard reports none")

            require_events = not (
                isinstance(capabilities, dict) and capabilities.get("ws_available") is False
            )
            await recorder.run(
                "status_and_events",
                lambda: wait_for_connected_status(
                    session,
                    call_timeout=args.call_timeout,
                    event_timeout=args.event_timeout,
                    require_events=require_events,
                ),
                lambda value: inspect_status(value, require_events=require_events),
            )

            invalid_workflow = {
                "1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
            }
            await recorder.run(
                "reject_missing_required_input",
                lambda: call_json(
                    session,
                    "comfy_validate_workflow",
                    {"workflow": invalid_workflow},
                    args.call_timeout,
                ),
                inspect_invalid_validation,
            )
            valid_report = await recorder.run(
                "accept_flattened_geometrypack",
                lambda: call_json(
                    session,
                    "comfy_validate_workflow",
                    {"workflow": workflow},
                    args.call_timeout,
                ),
                inspect_valid_validation,
            )

            if args.run_3d:
                if not isinstance(valid_report, dict) or valid_report.get("valid") is not True:
                    recorder.fail(
                        "geometrypack_execution",
                        "execution skipped because the workflow did not pass live validation",
                    )
                else:
                    execution = await recorder.run(
                        "geometrypack_execution",
                        lambda: execute_geometry_smoke(
                            session,
                            workflow,
                            output_name,
                            call_timeout=args.call_timeout,
                            execution_timeout=args.execution_timeout,
                            poll_interval=args.poll_interval,
                        ),
                        lambda value: dict(value),
                    )
                    if execution is not None:
                        summary["execution"] = execution
    except Exception as exc:
        recorder.fail("session", f"{type(exc).__name__}: {exc}")
    finally:
        summary["duration_seconds"] = round(time.monotonic() - started, 3)
        summary["ok"] = not recorder.failures
    return summary


def emit_summary(summary: dict[str, Any], args: argparse.Namespace) -> None:
    indent = None if args.compact else 2
    rendered = json.dumps(summary, indent=indent, sort_keys=False, ensure_ascii=False)
    print(rendered)
    if args.json_output:
        output_path = args.json_output.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_args(args)
        summary = asyncio.run(run_smoke(args))
    except KeyboardInterrupt:
        summary = {
            "ok": False,
            "mode": "read+model-free-3d" if args.run_3d else "read-only",
            "comfy_url": args.comfy_url,
            "failures": [{"name": "script", "type": "KeyboardInterrupt", "message": "interrupted"}],
        }
    except Exception as exc:
        summary = {
            "ok": False,
            "mode": "read+model-free-3d" if args.run_3d else "read-only",
            "comfy_url": args.comfy_url,
            "failures": [{
                "name": "script",
                "type": type(exc).__name__,
                "message": str(exc),
            }],
        }
    emit_summary(summary, args)
    return 0 if summary.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())

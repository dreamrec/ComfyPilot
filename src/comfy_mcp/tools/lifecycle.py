"""Lifecycle tools - 5 comfy-cli wrappers for setup-to-server flow.

These shell out to the comfy-cli binary because ComfyUI's REST API does
NOT cover installation, server start/stop, custom-node install, or model
download. The two-layer split (CLI for lifecycle, REST/WS for execution)
keeps subprocess concerns isolated to this module.

When comfy-cli is not installed, each tool returns a clear `error` JSON
with install hints. The agent can then surface the message to the user
without crashing.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from mcp.server.fastmcp import Context

from comfy_mcp.cli.comfy_cli import ComfyCliError, run_comfy_cli
from comfy_mcp.safety.confirm import confirm_destructive
from comfy_mcp.server import mcp
from comfy_mcp.tools.instance import inspect_instance


def _err(message: str, **extras) -> str:
    return json.dumps({"error": message, **extras}, indent=2)


def _cancelled(operation: str) -> str:
    return json.dumps({
        "status": "cancelled",
        "operation": operation,
        "reason": "confirmation_required_or_declined",
    }, indent=2)


async def _connected_instance(ctx: Context | None) -> dict | None:
    if ctx is None:
        return None
    try:
        return await inspect_instance(ctx)
    except Exception:
        return None


def _selector_error(
    instance: dict,
    *,
    expected_instance_id: str,
    expected_pid: int | None,
) -> str | None:
    actual_id = instance.get("instance_id")
    listener = instance.get("listener") or {}
    actual_pid = listener.get("pid")
    if expected_instance_id and expected_instance_id != actual_id:
        return f"expected instance_id {expected_instance_id!r}, connected instance is {actual_id!r}"
    if expected_pid is not None and int(expected_pid) != actual_pid:
        return f"expected PID {expected_pid}, connected listener PID is {actual_pid}"
    return None


@mcp.tool(
    annotations={
        "title": "Launch ComfyUI Server",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_launch_server(
    background: bool = True,
    port: int | None = None,
    host: str = "127.0.0.1",
    workspace: str = "",
    extra_args: list[str] | None = None,
    allow_parallel: bool = False,
    confirm: bool = False,
    ctx: Context = None,
) -> str:
    """Start an explicitly selected ComfyUI workspace via comfy-cli.

    This tool has no implicit 8188 fallback. ``workspace`` and ``port`` must
    be explicit, and a healthy connected endpoint blocks launch unless the
    caller deliberately sets ``allow_parallel=True``. This prevents a Desktop
    install on port 8000 from accidentally gaining a competing CLI process.

    Args:
        background: Run as a detached daemon (default True). False blocks
            until the server exits.
        port: Explicit port for ComfyUI's HTTP server.
        host: Host to bind on. Default 127.0.0.1; use 0.0.0.0 for LAN access.
        workspace: Optional --workspace path passed to comfy-cli (selects
            which ComfyUI install to launch when multiple are present).
        extra_args: Additional argv to forward verbatim after `--` (e.g.
            ['--listen', '0.0.0.0', '--cpu']).
        allow_parallel: Permit launch while the currently selected endpoint is
            already healthy. Default False.
        confirm: Explicitly confirm this process-start mutation.
    """
    extra = [str(value) for value in extra_args] if extra_args else []
    overrides = [flag for flag in ("--port", "--listen") if flag in extra]
    if overrides:
        return json.dumps({
            "status": "invalid_arguments",
            "error": "extra_args must not override structured --port/--listen values",
            "warning": (
                "Conflicting pass-through flags were blocked; use the structured "
                "port and host parameters instead."
            ),
            "overridden_flags": overrides,
        }, indent=2)

    active = await _connected_instance(ctx)
    if active and active.get("status") == "ok" and not allow_parallel:
        return json.dumps({
            "status": "already_running",
            "message": "The selected ComfyUI endpoint is healthy; no second server was launched.",
            "base_url": active.get("base_url"),
            "instance_id": active.get("instance_id"),
            "pid": (active.get("listener") or {}).get("pid"),
        }, indent=2)
    if not workspace:
        return _err(
            "workspace is required; refusing to launch an unselected ComfyUI installation",
            status="selection_required",
        )
    try:
        port = int(port) if port is not None else None
    except (TypeError, ValueError):
        port = None
    if port is None or not 1 <= port <= 65535:
        return _err("port must be explicitly set between 1 and 65535")
    if active and active.get("status") == "ok" and port == active.get("port"):
        return _err(
            "requested port is already owned by the connected ComfyUI instance",
            status="port_in_use",
            port=port,
        )

    if not await confirm_destructive(
        ctx,
        f"Launch ComfyUI workspace {workspace!r} on {host}:{port}?",
        confirm,
    ):
        return _cancelled("launch_server")

    args: list[str] = ["launch"]
    if background:
        args.append("--background")
    forwarded = ["--port", str(port), "--listen", host]
    if extra_args:
        forwarded.extend(extra)
    args.append("--")
    args.extend(forwarded)

    try:
        result = await run_comfy_cli(args, workspace=workspace or None, timeout=30.0)
    except ComfyCliError as e:
        return _err(str(e))

    response: dict = {
        "status": "launched" if result.ok else "failed",
        "background": background,
        "port": port,
        "host": host,
        "comfy_cli_returncode": result.returncode,
        "stdout_tail": result.stdout.splitlines()[-5:] if result.stdout else [],
        "stderr_tail": result.stderr.splitlines()[-5:] if result.stderr else [],
    }
    return json.dumps(response, indent=2)


@mcp.tool(
    annotations={
        "title": "Stop ComfyUI Server",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_stop_server(
    workspace: str = "",
    expected_instance_id: str = "",
    expected_pid: int | None = None,
    confirm: bool = False,
    ctx: Context = None,
) -> str:
    """Stop an explicitly selected non-Desktop ComfyUI server via comfy-cli.

    Desktop-supervised instances are never handed to ``comfy stop`` because
    that can target a different comfy-cli workspace. Use Comfy Desktop itself
    for a full stop, or ``comfy_restart`` for Manager V2 restart.

    Args:
        workspace: Optional --workspace path passed to comfy-cli (selects
            which ComfyUI install to stop when multiple are present).
        expected_instance_id: Optional Desktop instance selector from
            ``comfy_instance_doctor``.
        expected_pid: Optional listener PID selector.
        confirm: Explicit confirmation; otherwise MCP elicitation is used.

    Returns:
        JSON with one of three shapes:
        - {status: "stopped", comfy_cli_returncode: 0, stdout, stderr} on
          successful shutdown.
        - {status: "failed", comfy_cli_returncode: N, stdout, stderr}
          when the binary is present but the call exits non-zero (most
          commonly: no server was running to stop).
        - {error: "...install hints..."} when comfy-cli is not on PATH.
    """
    instance = await _connected_instance(ctx)
    if instance and instance.get("status") == "ok":
        selector_error = _selector_error(
            instance,
            expected_instance_id=expected_instance_id,
            expected_pid=expected_pid,
        )
        if selector_error:
            return _err(selector_error, status="selection_mismatch")
        if instance.get("owner_type") == "comfy_desktop":
            return json.dumps({
                "status": "controlled_fallback",
                "message": "This endpoint is supervised by Comfy Desktop; stop it from the Desktop UI.",
                "instance_id": instance.get("instance_id"),
                "pid": (instance.get("listener") or {}).get("pid"),
                "reason": "refusing to run comfy-cli stop against a Desktop-owned process",
            }, indent=2)
        if not workspace:
            install = (instance.get("paths") or {}).get("install_root") or {}
            workspace = str(install.get("path") or "")

    if not workspace:
        return _err(
            "workspace is required when the connected instance cannot supply a safe CLI workspace",
            status="selection_required",
        )
    if not await confirm_destructive(ctx, f"Stop ComfyUI workspace {workspace!r}?", confirm):
        return _cancelled("stop_server")

    try:
        result = await run_comfy_cli(["stop"], workspace=workspace or None, timeout=15.0)
    except ComfyCliError as e:
        return _err(str(e))

    return json.dumps({
        "status": "stopped" if result.ok else "failed",
        "comfy_cli_returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Install Custom Node",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_install_node(
    name: str,
    workspace: str = "",
    confirm: bool = False,
    ctx: Context = None,
) -> str:
    """Install a custom node via `comfy node install <name>`.

    Uses Comfy Manager under the hood. Name format is typically the
    GitHub repo's slug (e.g. 'comfyui-impact-pack', 'comfyui-controlnet-aux',
    'comfyui-animatediff-evolved').

    Args:
        name: Custom-node package name.
        workspace: Explicit comfy-cli workspace path.
        confirm: Explicitly confirm package installation.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", name or ""):
        return _err("name must be a non-empty package slug without path components")
    if not workspace:
        return _err("workspace is required for package installation", status="selection_required")
    if not await confirm_destructive(
        ctx,
        f"Install custom-node package {name!r} into workspace {workspace!r}?",
        confirm,
    ):
        return _cancelled("install_node")

    try:
        result = await run_comfy_cli(
            ["node", "install", name],
            workspace=workspace or None,
            timeout=600.0,
        )
    except ComfyCliError as e:
        return _err(str(e), name=name)

    return json.dumps({
        "status": "installed" if result.ok else "failed",
        "name": name,
        "comfy_cli_returncode": result.returncode,
        "stdout_tail": result.stdout.splitlines()[-10:] if result.stdout else [],
        "stderr_tail": result.stderr.splitlines()[-10:] if result.stderr else [],
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "List Installed Custom Nodes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_list_installed_nodes(
    workspace: str = "",
    mode: str = "imported",
    prefer_manager_api: bool = True,
    ctx: Context = None,
) -> str:
    """List custom-node packages, preferring the live Manager V2 API.

    Manager V2 is dramatically faster and, unlike comfy-cli, is guaranteed to
    describe the connected running installation. ``comfy-cli`` remains a
    compatibility fallback when no Context/API is available.

    Args:
        workspace: Optional --workspace path passed to comfy-cli.
        mode: Manager inventory mode (``imported`` by default).
        prefer_manager_api: Try ``/v2/customnode/installed`` first.

    Returns:
        JSON with one of three shapes:
        - {status: "ok", raw_lines: [...], line_count: N} when the
          listing succeeded. line_count==0 means no custom nodes are
          installed (or only stock ComfyUI is present).
        - {status: "failed", comfy_cli_returncode, stderr} when the
          binary is present but the call exits non-zero.
        - {error: "...install hints..."} when comfy-cli is not on PATH.
    """
    if mode not in {"imported", "default", "local", "remote"}:
        return _err("unsupported Manager inventory mode", mode=mode)

    manager_error: str | None = None
    if prefer_manager_api and ctx is not None:
        try:
            raw = await ctx.request_context.lifespan_context["comfy_client"].get(
                "/v2/customnode/installed",
                params={"mode": mode},
            )
            packages: list[dict] = []
            if isinstance(raw, dict):
                for name, details in raw.items():
                    details = details if isinstance(details, dict) else {}
                    packages.append({
                        "name": str(name),
                        "version": details.get("ver") or details.get("version"),
                        "enabled": details.get("enabled"),
                        "cnr_id": details.get("cnr_id"),
                        "aux_id": details.get("aux_id"),
                    })
            elif isinstance(raw, list):
                packages = [item for item in raw if isinstance(item, dict)]
            else:
                raise ValueError("Manager returned an unexpected inventory shape")
            packages.sort(key=lambda item: str(item.get("name", "")).lower())
            return json.dumps({
                "status": "ok",
                "source": "manager_v2",
                "mode": mode,
                "packages": packages,
                "count": len(packages),
            }, indent=2)
        except Exception as exc:
            manager_error = str(exc)

    if not workspace:
        return _err(
            "Manager V2 inventory was unavailable and no explicit comfy-cli workspace was provided",
            status="fallback_selection_required",
            manager_error=manager_error,
        )

    try:
        result = await run_comfy_cli(
            ["node", "show", "installed"],
            workspace=workspace or None,
            timeout=30.0,
        )
    except ComfyCliError as e:
        return _err(str(e))

    if not result.ok:
        return json.dumps({
            "status": "failed",
            "comfy_cli_returncode": result.returncode,
            "stderr": result.stderr,
        }, indent=2)

    # comfy-cli prints a human-readable list; we surface raw lines so the
    # caller can parse without a brittle regex. Strip blank / banner lines.
    lines = [
        ln.strip()
        for ln in result.stdout.splitlines()
        if ln.strip() and not ln.startswith("=") and not ln.startswith("-")
    ]

    return json.dumps({
        "status": "ok",
        "source": "comfy_cli",
        "raw_lines": lines,
        "line_count": len(lines),
        "manager_error": manager_error,
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Download Model",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_download_model(
    url: str,
    folder: str = "checkpoints",
    civitai_api_token: str = "",
    workspace: str = "",
    confirm: bool = False,
    ctx: Context = None,
) -> str:
    """Download a model via `comfy model download --url ... --relative-path models/<folder>`.

    Args:
        url: Direct download URL (HuggingFace, CivitAI, etc.). For
            CivitAI links, also pass `civitai_api_token`.
        folder: Subfolder under models/. Common values: checkpoints, loras,
            vae, diffusion_models, text_encoders, controlnet, upscale_models.
        civitai_api_token: Optional CivitAI API token for gated downloads.
        workspace: Optional --workspace path.
        confirm: Explicitly confirm the network download and filesystem write.
    """
    parsed_url = urlparse(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        return _err("url must start with http:// or https://")
    if parsed_url.username or parsed_url.password:
        return _err("url must not contain embedded credentials")
    if "/" in folder or ".." in folder or folder.startswith("."):
        return _err("folder must be a simple subfolder name without separators")
    if not workspace:
        return _err("workspace is required for model download", status="selection_required")
    if not await confirm_destructive(
        ctx,
        f"Download a model into workspace {workspace!r}, models/{folder}?",
        confirm,
    ):
        return _cancelled("download_model")

    args: list[str] = [
        "model", "download",
        "--url", url,
        "--relative-path", f"models/{folder}",
    ]
    if civitai_api_token:
        args.extend(["--set-civitai-api-token", civitai_api_token])

    try:
        result = await run_comfy_cli(
            args,
            workspace=workspace or None,
            timeout=3600.0,
        )
    except ComfyCliError as e:
        return _err(str(e), url=url, folder=folder)

    return json.dumps({
        "status": "downloaded" if result.ok else "failed",
        "url": url,
        "folder": folder,
        "comfy_cli_returncode": result.returncode,
        "stdout_tail": result.stdout.splitlines()[-10:] if result.stdout else [],
        "stderr_tail": result.stderr.splitlines()[-10:] if result.stderr else [],
    }, indent=2)

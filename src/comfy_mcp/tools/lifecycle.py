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

from mcp.server.fastmcp import Context

from comfy_mcp.cli.comfy_cli import ComfyCliError, run_comfy_cli
from comfy_mcp.server import mcp


def _err(message: str, **extras) -> str:
    return json.dumps({"error": message, **extras}, indent=2)


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
    port: int = 8188,
    host: str = "127.0.0.1",
    workspace: str = "",
    extra_args: list[str] | None = None,
    ctx: Context = None,
) -> str:
    """Start a ComfyUI server via comfy-cli.

    Wraps `comfy launch [--background] [-- --port N --listen HOST]`. The
    `--` separator passes flags through to ComfyUI's main.py. After this
    returns, poll `GET /system_stats` (via comfy_get_system_stats) to
    verify the server is actually accepting requests.

    Args:
        background: Run as a detached daemon (default True). False blocks
            until the server exits.
        port: Port for ComfyUI's HTTP server. Default 8188.
        host: Host to bind on. Default 127.0.0.1; use 0.0.0.0 for LAN access.
        workspace: Optional --workspace path passed to comfy-cli (selects
            which ComfyUI install to launch when multiple are present).
        extra_args: Additional argv to forward verbatim after `--` (e.g.
            ['--listen', '0.0.0.0', '--cpu']).
    """
    args: list[str] = ["launch"]
    if background:
        args.append("--background")
    forwarded = ["--port", str(port), "--listen", host]
    overrides: list[str] = []
    if extra_args:
        extra = [str(a) for a in extra_args]
        # argparse takes the LAST value when a flag appears twice, so an
        # extra_args entry of '--port 9000' silently overrides the
        # structured port= parameter. Detect and surface the conflict
        # rather than reporting a stale port in the response JSON.
        for flag in ("--port", "--listen"):
            if flag in extra:
                overrides.append(flag)
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
    if overrides:
        response["warning"] = (
            f"extra_args contains {overrides} which overrides the structured "
            "port/host parameters. The reported port/host values may be stale."
        )
        response["overridden_flags"] = overrides
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
async def comfy_stop_server(workspace: str = "", ctx: Context = None) -> str:
    """Stop the running ComfyUI server via `comfy stop`.

    Calls `comfy stop` (15s timeout) and reports the result. After this
    returns successfully, subsequent calls to `comfy_get_system_stats`
    will fail until the server is relaunched (`comfy_launch_server`).

    Args:
        workspace: Optional --workspace path passed to comfy-cli (selects
            which ComfyUI install to stop when multiple are present).

    Returns:
        JSON with one of three shapes:
        - {status: "stopped", comfy_cli_returncode: 0, stdout, stderr} on
          successful shutdown.
        - {status: "failed", comfy_cli_returncode: N, stdout, stderr}
          when the binary is present but the call exits non-zero (most
          commonly: no server was running to stop).
        - {error: "...install hints..."} when comfy-cli is not on PATH.
    """
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
    ctx: Context = None,
) -> str:
    """Install a custom node via `comfy node install <name>`.

    Uses Comfy Manager under the hood. Name format is typically the
    GitHub repo's slug (e.g. 'comfyui-impact-pack', 'comfyui-controlnet-aux',
    'comfyui-animatediff-evolved').

    Args:
        name: Custom-node package name.
        workspace: Optional --workspace path.
    """
    if not name or "/" in name or ".." in name:
        return _err("name must be a non-empty package slug without path components")

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
async def comfy_list_installed_nodes(workspace: str = "", ctx: Context = None) -> str:
    """List custom-node packages installed via Comfy Manager.

    Wraps `comfy node show installed` (30s timeout) and returns the
    human-readable list as raw lines. Pair with `comfy_install_node`
    when checking whether a package is already installed before
    re-installing.

    Args:
        workspace: Optional --workspace path passed to comfy-cli.

    Returns:
        JSON with one of three shapes:
        - {status: "ok", raw_lines: [...], line_count: N} when the
          listing succeeded. line_count==0 means no custom nodes are
          installed (or only stock ComfyUI is present).
        - {status: "failed", comfy_cli_returncode, stderr} when the
          binary is present but the call exits non-zero.
        - {error: "...install hints..."} when comfy-cli is not on PATH.
    """
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
        "raw_lines": lines,
        "line_count": len(lines),
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
    """
    if not url or not url.startswith(("http://", "https://")):
        return _err("url must start with http:// or https://")
    if "/" in folder or ".." in folder or folder.startswith("."):
        return _err("folder must be a simple subfolder name without separators")

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

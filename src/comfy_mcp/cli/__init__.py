"""comfy-cli subprocess wrappers for lifecycle tools.

Lifecycle (install ComfyUI, launch/stop server, install custom nodes,
download models) is not exposed by ComfyUI's REST API. The official
comfy-cli (https://github.com/Comfy-Org/comfy-cli) handles all of this,
so we shell out to it for the lifecycle tools.

This subpackage isolates the subprocess concerns - everything else in
ComfyPilot talks to ComfyUI over HTTP/WebSocket.
"""
from comfy_mcp.cli.comfy_cli import (
    ComfyCliError,
    ComfyCliResult,
    detect_comfy_cli,
    run_comfy_cli,
)

__all__ = ["ComfyCliError", "ComfyCliResult", "detect_comfy_cli", "run_comfy_cli"]

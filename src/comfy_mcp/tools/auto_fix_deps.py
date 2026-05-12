"""Auto-install missing custom-node dependencies from a workflow.

ComfyUI's validator (and our own) reports missing custom-node class types,
but only humans / agents can act on the report. This tool closes the loop:
write the workflow to a temp file and shell out to:

    comfy node install-deps --workflow=<temp>.json

which Comfy Manager uses to discover every custom-node package the
workflow references and install whatever's missing. Returns the comfy-cli
output so the caller can verify what happened.
"""
from __future__ import annotations

import json
import os
import tempfile

from mcp.server.fastmcp import Context

from comfy_mcp.cli.comfy_cli import ComfyCliError, run_comfy_cli
from comfy_mcp.server import mcp


@mcp.tool(
    annotations={
        "title": "Install Workflow Dependencies",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_install_workflow_deps(
    workflow: dict,
    workspace: str = "",
    ctx: Context = None,
) -> str:
    """Auto-install every custom-node package the workflow references.

    Wraps `comfy node install-deps --workflow=<file>`. The workflow is
    serialised to a temp file (in API format), passed to comfy-cli, and
    the temp file is removed after. Long-running call (each missing
    package downloads + installs): default timeout 600 s.

    Args:
        workflow: API-format workflow dict.
        workspace: Optional --workspace path passed to comfy-cli.
    """
    if not isinstance(workflow, dict) or not workflow:
        return json.dumps({"error": "workflow must be a non-empty dict"}, indent=2)

    # Editor-format short-circuit (same as the validator).
    if isinstance(workflow.get("nodes"), list) and isinstance(workflow.get("links"), list):
        return json.dumps({
            "error": "Workflow is in editor format. Re-export via Workflow -> Export (API).",
        }, indent=2)

    fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="comfypilot_deps_")
    # If os.fdopen itself raises (resource exhaustion, etc.) the raw fd
    # would leak. Wrap the takeover to guarantee close + unlink even then.
    try:
        try:
            f = os.fdopen(fd, "w", encoding="utf-8")
        except Exception:
            os.close(fd)
            raise
        with f:
            json.dump(workflow, f)
        try:
            result = await run_comfy_cli(
                ["node", "install-deps", f"--workflow={tmp_path}"],
                workspace=workspace or None,
                timeout=600.0,
            )
        except ComfyCliError as e:
            return json.dumps({"error": str(e)}, indent=2)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return json.dumps({
        "status": "ok" if result.ok else "failed",
        "comfy_cli_returncode": result.returncode,
        "stdout_tail": result.stdout.splitlines()[-15:] if result.stdout else [],
        "stderr_tail": result.stderr.splitlines()[-15:] if result.stderr else [],
    }, indent=2)

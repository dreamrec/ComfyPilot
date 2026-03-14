"""Compatibility tools — MCP surface for the Compatibility Engine."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _graph(ctx: Context):
    return ctx.request_context.lifespan_context["install_graph"]


@mcp.tool(
    annotations={
        "title": "Preflight Workflow",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_preflight_workflow(workflow: dict, ctx: Context = None) -> str:
    """Run a multi-pass compatibility check on a workflow before execution.

    Validates structural integrity, schema correctness, and environment
    compatibility (installed nodes, resolvable models).

    Args:
        workflow: API-format workflow dict

    Returns:
        JSON preflight report with status (verified/likely/blocked),
        errors, warnings, missing_nodes, missing_models, and confidence score.
    """
    graph = _graph(ctx)
    if not graph.snapshot:
        await graph.refresh()
    from comfy_mcp.compat.engine import run_preflight
    report = run_preflight(workflow, graph.snapshot)
    return json.dumps(report, indent=2)


@mcp.tool(
    annotations={
        "title": "Explain Incompatibilities",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_explain_incompatibilities(workflow: dict, ctx: Context = None) -> str:
    """Explain why a workflow may not run on this machine.

    Runs preflight and returns a human-readable explanation with
    actionable suggestions for each issue found.

    Args:
        workflow: API-format workflow dict
    """
    graph = _graph(ctx)
    if not graph.snapshot:
        await graph.refresh()
    from comfy_mcp.compat.engine import run_preflight
    report = run_preflight(workflow, graph.snapshot)

    explanations = []
    for node in report.get("missing_nodes", []):
        explanations.append(f"- Node '{node}' is not installed. Install the custom node pack that provides it.")
    for model in report.get("missing_models", []):
        explanations.append(
            f"- Model '{model['name']}' not found in {model['folder']}. "
            f"Download it or change the workflow to use an installed model."
        )
    for err in report.get("errors", []):
        explanations.append(f"- {err}")

    result = {
        "status": report["status"],
        "confidence": report["confidence"],
        "explanation": "\n".join(explanations) if explanations else "No issues found.",
        "raw_report": report,
    }
    return json.dumps(result, indent=2)

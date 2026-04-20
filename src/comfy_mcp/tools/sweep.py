"""Sweep tool - 1 tool for enqueueing N variations of a single parameter."""
from __future__ import annotations

import copy
import json
import math

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


def _job_tracker(ctx: Context):
    return ctx.request_context.lifespan_context["job_tracker"]


def _grid_layout(n: int) -> dict:
    """Square-ish (cols, rows) hint for rendering a sweep grid."""
    if n <= 0:
        return {"cols": 0, "rows": 0}
    cols = int(math.ceil(math.sqrt(n)))
    rows = int(math.ceil(n / cols))
    return {"cols": cols, "rows": rows}


@mcp.tool(
    annotations={
        "title": "Parameter Sweep",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_sweep(
    workflow: dict,
    node_id: str,
    param: str,
    values: list,
    ctx: Context = None,
) -> str:
    """Enqueue N copies of workflow, each with a different value for one widget.

    Useful for seed sweeps, CFG sweeps, step sweeps, denoise sweeps.
    Every queued prompt is also registered with the job tracker so the
    returned prompt_ids can be fed into comfy_watch_progress.

    Args:
        workflow: Base API-format workflow.
        node_id: Node id whose input to vary (e.g. "5" for KSampler).
        param: Input name to vary (e.g. "seed", "cfg", "steps").
        values: List of values to substitute. Each produces one queued prompt.
    """
    if not isinstance(workflow, dict) or not workflow:
        return json.dumps({"error": "workflow must be a non-empty dict"})
    if node_id not in workflow:
        return json.dumps({"error": f"Node {node_id!r} not in workflow"})
    if not isinstance(workflow[node_id], dict):
        return json.dumps({"error": f"Node {node_id!r} is not a dict"})
    if not isinstance(values, list) or not values:
        return json.dumps({"error": "values must be a non-empty list"})

    client = _client(ctx)
    tracker = _job_tracker(ctx)

    prompt_ids: list[str] = []
    errors: list[dict] = []

    for value in values:
        variant = copy.deepcopy(workflow)
        variant[node_id].setdefault("inputs", {})[param] = value

        try:
            result = await client.queue_prompt(variant)
        except Exception as e:
            errors.append({"value": value, "error": str(e)})
            continue

        prompt_id = result.get("prompt_id") if isinstance(result, dict) else None
        if prompt_id:
            prompt_ids.append(prompt_id)
            try:
                maybe = tracker.track(prompt_id)
                if hasattr(maybe, "__await__"):
                    await maybe
            except Exception:
                pass
        elif isinstance(result, dict) and "error" in result:
            errors.append({"value": value, "error": result["error"]})

    return json.dumps({
        "status": "queued",
        "node_id": node_id,
        "param": param,
        "values_requested": len(values),
        "prompt_ids": prompt_ids,
        "errors": errors,
        "grid_layout": _grid_layout(len(prompt_ids)),
    }, indent=2)

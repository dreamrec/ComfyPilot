"""Sweep tools - parameter sweeps over single and multi-dimensional axes."""
from __future__ import annotations

import copy
import itertools
import json
import math

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


_DEFAULT_MAX_COMBINATIONS = 64


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


def _parse_axis_key(key: str) -> tuple[str, str]:
    """Split an axis key 'node_id.param' into (node_id, param). Raises on bad shape."""
    if "." not in key:
        raise ValueError(
            f"Axis key {key!r} must be 'node_id.param' (e.g. '5.seed')"
        )
    node_id, _, param = key.partition(".")
    if not node_id or not param:
        raise ValueError(f"Axis key {key!r} must be 'node_id.param'")
    return node_id, param


@mcp.tool(
    annotations={
        "title": "Parameter Sweep Grid",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_sweep_grid(
    workflow: dict,
    axes: dict,
    max_combinations: int = _DEFAULT_MAX_COMBINATIONS,
    ctx: Context = None,
) -> str:
    """N-dimensional parameter sweep over a Cartesian product of axes.

    Where comfy_sweep varies one widget across a list, this enqueues every
    combination across multiple axes. E.g. seed x cfg x steps with 3 values
    on each axis produces 27 queued prompts.

    Args:
        workflow: Base API-format workflow.
        axes: Mapping of 'node_id.param' -> list of values. At least 1 axis;
            order is preserved for the returned grid_shape.
        max_combinations: Hard cap on total queued prompts. Reject the call
            when the Cartesian product would exceed this. Default 64.

    Returns:
        JSON with prompt_ids list (length = product of axis sizes), the
        grid_shape (e.g. [3, 3, 3] for 3x3x3), and a per-prompt assignment
        map so the caller can label each output.
    """
    if not isinstance(workflow, dict) or not workflow:
        return json.dumps({"error": "workflow must be a non-empty dict"})
    if not isinstance(axes, dict) or not axes:
        return json.dumps({"error": "axes must be a non-empty dict"})

    parsed_axes: list[tuple[str, str, list]] = []
    for key, values in axes.items():
        if not isinstance(values, list) or not values:
            return json.dumps({"error": f"Axis {key!r} values must be a non-empty list"})
        try:
            node_id, param = _parse_axis_key(key)
        except ValueError as e:
            return json.dumps({"error": str(e)})
        if node_id not in workflow:
            return json.dumps({"error": f"Axis {key!r}: node {node_id!r} not in workflow"})
        parsed_axes.append((node_id, param, list(values)))

    grid_shape = [len(v) for _, _, v in parsed_axes]
    total = 1
    for n in grid_shape:
        total *= n
    if total > max_combinations:
        return json.dumps({
            "error": (
                f"Cartesian product {total} exceeds max_combinations "
                f"{max_combinations}. Pass max_combinations=N to override."
            ),
            "grid_shape": grid_shape,
        })

    client = _client(ctx)
    tracker = _job_tracker(ctx)

    prompt_ids: list[str] = []
    assignments: list[dict] = []
    errors: list[dict] = []

    value_iters = [v for _, _, v in parsed_axes]
    for combo in itertools.product(*value_iters):
        variant = copy.deepcopy(workflow)
        assignment: dict = {}
        for (node_id, param, _values), value in zip(parsed_axes, combo):
            variant[node_id].setdefault("inputs", {})[param] = value
            assignment[f"{node_id}.{param}"] = value
        try:
            result = await client.queue_prompt(variant)
        except Exception as e:
            errors.append({"assignment": assignment, "error": str(e)})
            continue
        prompt_id = result.get("prompt_id") if isinstance(result, dict) else None
        if prompt_id:
            prompt_ids.append(prompt_id)
            assignments.append({"prompt_id": prompt_id, **assignment})
            try:
                maybe = tracker.track(prompt_id)
                if hasattr(maybe, "__await__"):
                    await maybe
            except Exception:
                pass
        elif isinstance(result, dict) and "error" in result:
            errors.append({"assignment": assignment, "error": result["error"]})

    return json.dumps({
        "status": "queued",
        "axes": list(axes.keys()),
        "grid_shape": grid_shape,
        "total_combinations": total,
        "prompt_ids": prompt_ids,
        "assignments": assignments,
        "errors": errors,
    }, indent=2)

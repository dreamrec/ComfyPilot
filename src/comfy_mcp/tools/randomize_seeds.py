"""comfy_randomize_seeds - inject fresh random seeds before queueing.

`seed: -1` is treated as a sentinel meaning "give me a fresh random seed
each time". ComfyUI itself does not honour this convention - if your
workflow has seed = -1 you'll get a deterministic -1 every run. This tool
walks a workflow and replaces every seed-shaped widget value of -1 (or
all of them if `force=True`) with a cryptographically random uint32.

The patched workflow is returned alongside a map of `node_id.field -> new
value` so the caller can log / archive the seeds that were used.
"""
from __future__ import annotations

import copy
import json
import secrets

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


# Field names that hold seed-like integers. ComfyUI is consistent here:
# KSampler uses `seed`, RandomNoise uses `noise_seed`, TrainLora uses
# `seed`, some custom nodes use both forms. Add to this set if you find a
# fork that uses something else.
_SEED_FIELDS = frozenset({"seed", "noise_seed"})


def _is_link(value) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
    )


@mcp.tool(
    annotations={
        "title": "Randomize Seeds",
        # Returns a NEW workflow dict; doesn't mutate the input. Marked
        # not-read-only because the same call produces different output
        # each invocation (secrets.randbelow). MCP spec treats a
        # read-only tool as effectively idempotent at the caller level,
        # which would contradict idempotentHint=False below.
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_randomize_seeds(
    workflow: dict,
    force: bool = False,
    ctx: Context = None,
) -> str:
    """Replace seed sentinels (-1) with fresh random uint32 values.

    By default, only widgets currently set to -1 are randomised; this lets
    a caller "opt in" by writing -1 for the seeds they want fresh while
    pinning the others to specific values. Set `force=True` to randomise
    every seed widget in the workflow regardless of its current value.

    Uses `secrets.randbelow(2**32)` for cryptographic-grade randomness -
    avoids the seeded global random module so concurrent randomisation
    calls don't share a stream.

    Args:
        workflow: API-format workflow dict (deep-copied; caller's dict
            stays unchanged).
        force: Randomise every seed widget regardless of current value.

    Returns:
        JSON with `workflow` (patched copy) and `assignments` mapping
        `node_id.field -> new_seed`.
    """
    if not isinstance(workflow, dict) or not workflow:
        return json.dumps({"error": "workflow must be a non-empty dict"})

    patched = copy.deepcopy(workflow)
    assignments: dict[str, int] = {}

    for node_id, node in patched.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {}) or {}
        for field, value in list(inputs.items()):
            if field not in _SEED_FIELDS:
                continue
            if _is_link(value):
                continue  # seed is wired from another node - leave it
            if force or value == -1:
                # Range [1, 2^32). We exclude 0 because some custom samplers
                # treat seed=0 as a re-randomise sentinel equivalent to -1,
                # which would defeat the point of injecting a fixed value.
                new_seed = secrets.randbelow(2 ** 32 - 1) + 1
                inputs[field] = new_seed
                assignments[f"{node_id}.{field}"] = new_seed

    return json.dumps({
        "assignments": assignments,
        "randomized_count": len(assignments),
        "workflow": patched,
    }, indent=2)

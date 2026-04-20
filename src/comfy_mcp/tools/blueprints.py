"""Subgraph blueprint tools - 3 tools for named reusable workflow macros.

Blueprints are the modern ComfyUI reuse primitive (superseding group nodes).
A blueprint is a named bundle of nodes that can be inserted into any workflow
with optional per-instance input overrides.

Storage:
- User-published: COMFY_BLUEPRINT_DIR (default ~/.comfypilot/blueprints)
- Bundled: the blueprints/ directory that ships with ComfyPilot
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import Context

from comfy_mcp.blueprints.store import BlueprintStore
from comfy_mcp.server import mcp


def _store(ctx: Context | None) -> BlueprintStore:
    user_dir = None
    bundled_dir = None
    if ctx is not None:
        user_dir = ctx.request_context.lifespan_context.get("blueprint_user_dir")
        bundled_dir = ctx.request_context.lifespan_context.get("blueprint_bundled_dir")
    if user_dir is None:
        user_dir = Path(os.environ.get("COMFY_BLUEPRINT_DIR", str(Path.home() / ".comfypilot" / "blueprints")))
    if bundled_dir is None:
        # Bundled dir sits at the repo root next to src/; resolve from this module's path.
        bundled_dir = Path(__file__).resolve().parents[3] / "blueprints"
    return BlueprintStore(user_dir=user_dir, bundled_dir=bundled_dir)


@mcp.tool(
    annotations={
        "title": "List Blueprints",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_blueprints(ctx: Context = None) -> str:
    """List all available subgraph blueprints (user-published + bundled).

    User blueprints shadow bundled ones when names collide.
    """
    store = _store(ctx)
    return json.dumps({"blueprints": store.list()}, indent=2)


@mcp.tool(
    annotations={
        "title": "Insert Blueprint",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_insert_blueprint(
    name: str,
    inputs: dict | None = None,
    ctx: Context = None,
) -> str:
    """Materialize a blueprint into a workflow dict.

    Args:
        name: Blueprint name (from comfy_list_blueprints).
        inputs: Optional {node_id: {input_name: value}} overrides applied to
            the blueprint's nodes when inserted.
    """
    store = _store(ctx)
    try:
        return json.dumps(store.insert(name, inputs), indent=2)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})


@mcp.tool(
    annotations={
        "title": "Publish Subgraph",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_publish_subgraph(
    name: str,
    nodes: dict,
    description: str = "",
    tags: list[str] | None = None,
    ctx: Context = None,
) -> str:
    """Save a set of nodes as a reusable blueprint.

    Args:
        name: Blueprint name (must not contain '/' or '..').
        nodes: Dict of {node_id: node_spec} forming the blueprint graph.
        description: Free-text description for discoverability.
        tags: Optional tags for search/filter.
    """
    store = _store(ctx)
    try:
        return json.dumps(store.publish(name, nodes, description, tags), indent=2)
    except (ValueError, RuntimeError) as e:
        return json.dumps({"error": str(e)})

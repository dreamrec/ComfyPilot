"""Memory tools — 5 tools for workflow technique library."""
from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _technique_store(ctx: Context):
    return ctx.request_context.lifespan_context["technique_store"]


def _extract_technique_metadata(workflow: dict) -> dict:
    """Extract compatibility metadata from a workflow."""
    node_classes = set()
    model_refs = set()

    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type", "")
        if ct:
            node_classes.add(ct)
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, str) and (val.endswith(".safetensors") or val.endswith(".ckpt") or val.endswith(".pth")):
                model_refs.add(val)

    return {
        "node_classes": sorted(node_classes),
        "model_references": sorted(model_refs),
        "node_count": len(workflow),
    }


@mcp.tool(
    annotations={
        "title": "Save Technique",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_save_technique(
    workflow: dict,
    name: str,
    description: str = "",
    tags: list[str] | None = None,
    ctx: Context = None,
) -> str:
    """Save a workflow as a reusable technique.

    Args:
        workflow: The workflow dictionary to save
        name: Name for the technique
        description: Optional description
        tags: Optional list of tags for categorization
    """
    store = _technique_store(ctx)
    metadata = _extract_technique_metadata(workflow)
    result = store.save(workflow, name, description=description, tags=tags, metadata=metadata)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Search Techniques",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_search_techniques(
    query: str = "",
    tags: list[str] | None = None,
    limit: int = 20,
    ctx: Context = None,
) -> str:
    """Search workflow techniques by text query and/or tags.

    Args:
        query: Text to search in name, description, and tags
        tags: Optional list of tags to filter by
        limit: Maximum number of results to return (default 20)
    """
    store = _technique_store(ctx)
    results = store.search(query=query, tags=tags, limit=limit)
    return json.dumps({
        "techniques": results,
        "total_count": len(results),
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "List Techniques",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_techniques(
    limit: int = 50,
    ctx: Context = None,
) -> str:
    """List all saved workflow techniques (newest first).

    Args:
        limit: Maximum number of techniques to return (default 50)
    """
    store = _technique_store(ctx)
    results = store.list(limit=limit)
    return json.dumps({
        "techniques": results,
        "total_count": len(results),
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Replay Technique",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_replay_technique(
    technique_id: str,
    ctx: Context = None,
) -> str:
    """Get the full technique data including workflow for re-use.

    Args:
        technique_id: The technique ID to retrieve
    """
    store = _technique_store(ctx)
    technique = store.get(technique_id)
    if technique is None:
        return json.dumps({
            "error": f"Technique {technique_id} not found",
            "technique_id": technique_id,
        }, indent=2)
    # Increment use_count via public API
    updated = store.record_use(technique_id)
    if updated:
        technique["use_count"] = updated["use_count"]
    return json.dumps(technique, indent=2)


@mcp.tool(
    annotations={
        "title": "Favorite Technique",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_favorite_technique(
    technique_id: str,
    favorite: bool = True,
    rating: int = -1,
    ctx: Context = None,
) -> str:
    """Set favorite status and/or rating for a technique.

    Args:
        technique_id: The technique ID to update
        favorite: Whether to mark as favorite (default True)
        rating: Rating from 0-5, or -1 to leave unchanged (default -1)
    """
    store = _technique_store(ctx)
    result = store.favorite(technique_id, favorite=favorite, rating=rating)
    return json.dumps(result, indent=2)

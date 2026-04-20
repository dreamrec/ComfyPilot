"""History tools - 5 tools for execution history management."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


@mcp.tool(
    annotations={
        "title": "Get History",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_history(limit: int = 20, ctx: Context = None) -> str:
    """Get execution history with pagination.

    Args:
        limit: Maximum number of entries to return (default 20)

    Returns:
        JSON with entries list and total count
    """
    history = await _client(ctx).get_history(max_items=limit)
    entries = []
    for prompt_id, data in history.items():
        entries.append({
            "prompt_id": prompt_id,
            "status": data.get("status", {}),
            "outputs": data.get("outputs", {}),
        })
    return json.dumps({
        "entries": entries,
        "total_count": len(history),
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Run Result",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_run_result(prompt_id: str, ctx: Context = None) -> "RunResult":
    """Get result of a specific prompt execution. Returns structured RunResult.

    Args:
        prompt_id: The ID of the prompt execution to retrieve
    """
    from comfy_mcp.responses import RunResult

    history = await _client(ctx).get_history(prompt_id=prompt_id)
    if not history:
        return RunResult(
            prompt_id=prompt_id,
            error=f"No history found for prompt_id: {prompt_id}",
        )

    data = history.get(prompt_id, {})
    return RunResult(
        prompt_id=prompt_id,
        status=data.get("status", {}) or {},
        outputs=data.get("outputs", {}) or {},
        prompt=data.get("prompt", []) or [],
    )


@mcp.tool(
    annotations={
        "title": "Delete History",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_delete_history(prompt_id: str, confirm: bool = False, ctx: Context = None) -> str:
    """Delete a specific history entry. Destructive.

    Args:
        prompt_id: The ID of the prompt execution to delete
        confirm: If False, the tool asks for explicit confirmation via
            elicitation before proceeding. Pass True to skip the prompt.
    """
    from comfy_mcp.safety.confirm import confirm_destructive
    if not await confirm_destructive(ctx, f"Delete history entry for prompt {prompt_id}?", confirm):
        return json.dumps({"status": "cancelled", "reason": "user_declined", "prompt_id": prompt_id}, indent=2)

    await _client(ctx).delete_history(prompt_id=prompt_id)
    return json.dumps({
        "status": "deleted",
        "prompt_id": prompt_id,
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Clear History",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_clear_history(confirm: bool = False, ctx: Context = None) -> str:
    """Clear ALL execution history. Destructive and cannot be undone.

    Args:
        confirm: If False, the tool asks for explicit confirmation via
            elicitation before proceeding. Pass True to skip the prompt.
    """
    from comfy_mcp.safety.confirm import confirm_destructive
    if not await confirm_destructive(ctx, "Clear ALL execution history? This cannot be undone.", confirm):
        return json.dumps({"status": "cancelled", "reason": "user_declined"}, indent=2)

    await _client(ctx).clear_history()
    return json.dumps({
        "status": "cleared",
        "message": "All execution history has been cleared",
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Search History",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_search_history(query: str, limit: int = 20, ctx: Context = None) -> str:
    """Search history for prompts containing specific node types.

    Args:
        query: Search term (case-insensitive substring match on node class_type)
        limit: Maximum number of matches to return (default 20)

    Returns:
        JSON with matching history entries
    """
    history = await _client(ctx).get_history()
    matches = []
    query_lower = query.lower()

    for prompt_id, data in history.items():
        # Get the workflow dict from prompt data
        prompt_data = data.get("prompt", [])
        if len(prompt_data) >= 3:
            workflow_dict = prompt_data[2]
            if isinstance(workflow_dict, dict):
                # Search for nodes matching the query
                for node_id, node_data in workflow_dict.items():
                    if isinstance(node_data, dict):
                        class_type = node_data.get("class_type", "").lower()
                        if query_lower in class_type:
                            matches.append({
                                "prompt_id": prompt_id,
                                "status": data.get("status", {}),
                                "outputs": data.get("outputs", {}),
                                "matched_node": class_type,
                            })
                            break  # Only add once per prompt_id

        if len(matches) >= limit:
            break

    return json.dumps({
        "query": query,
        "matches": matches[:limit],
        "match_count": len(matches[:limit]),
    }, indent=2)

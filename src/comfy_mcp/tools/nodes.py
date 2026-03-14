"""Node tools — 6 tools for node type inspection and search."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


@mcp.tool(
    annotations={
        "title": "List Node Types",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_node_types(
    limit: int = 50,
    offset: int = 0,
    ctx: Context = None,
) -> str:
    """List all available node types with pagination.

    Args:
        limit: Maximum number of results per page
        offset: Starting position for pagination

    Returns:
        JSON with node_types list, total_count, has_more, next_offset
    """
    all_nodes = await _client(ctx).get_object_info()
    sorted_types = sorted(all_nodes.keys())
    total_count = len(sorted_types)
    has_more = offset + limit < total_count
    paginated_types = sorted_types[offset : offset + limit]
    next_offset = offset + limit if has_more else None

    result = {
        "node_types": paginated_types,
        "total_count": total_count,
        "has_more": has_more,
        "next_offset": next_offset,
    }
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Node Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_node_info(node_type: str, ctx: Context = None) -> str:
    """Get detailed info about a specific node type.

    Args:
        node_type: The node type name to get info for

    Returns:
        JSON with full node info (inputs, outputs, category, etc.)
    """
    all_nodes = await _client(ctx).get_object_info()
    if node_type not in all_nodes:
        return json.dumps({
            "error": f"Node type '{node_type}' not found",
            "available_count": len(all_nodes),
        }, indent=2)

    result = {node_type: all_nodes[node_type]}
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Search Nodes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_search_nodes(
    query: str,
    limit: int = 20,
    ctx: Context = None,
) -> str:
    """Search for nodes by name (case-insensitive substring match).

    Args:
        query: Search query string
        limit: Maximum number of results to return

    Returns:
        JSON with matches list and total match count
    """
    all_nodes = await _client(ctx).get_object_info()
    query_lower = query.lower()
    matches = [name for name in all_nodes.keys() if query_lower in name.lower()]
    total_matches = len(matches)
    limited_matches = matches[:limit]

    result = {
        "query": query,
        "matches": limited_matches,
        "total_matches": total_matches,
        "returned": len(limited_matches),
    }
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Categories",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_categories(ctx: Context = None) -> str:
    """Get all node categories.

    Returns:
        JSON with sorted list of categories and their node counts
    """
    all_nodes = await _client(ctx).get_object_info()
    categories = {}

    for node_name, node_info in all_nodes.items():
        category = node_info.get("category", "uncategorized")
        if category not in categories:
            categories[category] = 0
        categories[category] += 1

    sorted_categories = sorted(categories.items())
    result = {
        "categories": [
            {"name": cat, "count": count} for cat, count in sorted_categories
        ],
        "total_categories": len(categories),
    }
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Embeddings",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_embeddings(ctx: Context = None) -> str:
    """List available embeddings.

    Returns:
        JSON with embeddings list and count
    """
    embeddings = await _client(ctx).get_embeddings()
    result = {
        "embeddings": embeddings,
        "count": len(embeddings),
    }
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Inspect Widget",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_inspect_widget(node_type: str, ctx: Context = None) -> str:
    """Get widget/input details for a specific node type.

    Args:
        node_type: The node type name to inspect

    Returns:
        JSON with input definitions (required and optional inputs)
    """
    all_nodes = await _client(ctx).get_object_info()
    if node_type not in all_nodes:
        return json.dumps({
            "error": f"Node type '{node_type}' not found",
        }, indent=2)

    node_info = all_nodes[node_type]
    inputs = node_info.get("input", {})

    result = {
        "node_type": node_type,
        "input": inputs,
    }
    return json.dumps(result, indent=2)

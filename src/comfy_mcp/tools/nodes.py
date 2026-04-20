"""Node tools - 6 tools for node type inspection and search.

All tools that return per-node detail use the normalized NodeSchema shape so
V1 (dict-of-tuples) and V3 (class-based) object_info entries look identical
to agents.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.schemas.node_schema import parse_object_info
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
    """Get detailed normalized info about a specific node type.

    Returns a NodeSchema-shaped payload: class_type, category, description,
    inputs (with name/type/required/constraints/is_link_target per input),
    outputs, is_output_node, schema_version ('v1' or 'v3').

    Args:
        node_type: The node type name to get info for
    """
    all_nodes = await _client(ctx).get_object_info()
    if node_type not in all_nodes:
        return json.dumps({
            "error": f"Node type '{node_type}' not found",
            "available_count": len(all_nodes),
        }, indent=2)

    schema = parse_object_info(node_type, all_nodes[node_type])
    return json.dumps(schema.model_dump(), indent=2)


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
    """Get widget/input details for a node type (normalized, V1/V3 transparent).

    Returns:
        node_type: class name
        inputs: list of {name, type_name, required, constraints, is_link_target}
        widget_inputs: subset of inputs that are widgets (is_link_target=False)
        link_inputs: subset of inputs that expect links from other nodes

    Args:
        node_type: The node type name to inspect
    """
    all_nodes = await _client(ctx).get_object_info()
    if node_type not in all_nodes:
        return json.dumps({
            "error": f"Node type '{node_type}' not found",
        }, indent=2)

    schema = parse_object_info(node_type, all_nodes[node_type])
    inputs_dump = [i.model_dump() for i in schema.inputs]
    widget_inputs = [i for i in inputs_dump if not i["is_link_target"]]
    link_inputs = [i for i in inputs_dump if i["is_link_target"]]

    return json.dumps({
        "node_type": node_type,
        "schema_version": schema.schema_version,
        "inputs": inputs_dump,
        "widget_inputs": widget_inputs,
        "link_inputs": link_inputs,
    }, indent=2)

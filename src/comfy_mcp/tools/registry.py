"""Registry tools -- MCP surface for ComfyUI package registry integration."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["registry_client"]


def _index(ctx: Context):
    return ctx.request_context.lifespan_context["registry_index"]


@mcp.tool(
    annotations={
        "title": "Search Registry",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_search_registry(
    query: str,
    tags: list[str] | None = None,
    limit: int = 10,
    *,
    ctx: Context,
) -> str:
    """Search the ComfyUI package registry.

    Args:
        query: Search query (package name, description, or node class name).
        tags: Optional tag filters.
        limit: Maximum results (default 10).
    """
    client = _client(ctx)
    extra = {}
    if tags:
        extra["tags"] = ",".join(tags)
    result = await client.search_nodes(query, limit=limit, **extra)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Package",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_get_package(package_id: str, *, ctx: Context) -> str:
    """Get full metadata for a registry package.

    Args:
        package_id: Package identifier (e.g., 'comfyui-animatediff-evolved').
    """
    client = _client(ctx)
    result = await client.get_node(package_id)
    if result is None:
        return json.dumps({"error": f"Package '{package_id}' not found"}, indent=2)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Resolve Missing Nodes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_resolve_missing(
    workflow: dict | None = None,
    node_classes: list[str] | None = None,
    *,
    ctx: Context,
) -> str:
    """Resolve missing node classes to their registry packages.

    Provide either a workflow dict or a list of node class names.
    Returns package info with install commands for each missing node.

    Args:
        workflow: Optional workflow dict -- extracts class_type from each node.
        node_classes: Optional explicit list of node class names to resolve.
    """
    client = _client(ctx)
    index = _index(ctx)
    install_graph = ctx.request_context.lifespan_context.get("install_graph")

    # Build list of class names to resolve
    classes = list(node_classes or [])
    if workflow:
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            ct = node.get("class_type", "")
            if ct and ct not in classes:
                classes.append(ct)

    # Filter to actually missing nodes
    if install_graph and install_graph.snapshot:
        installed = install_graph.snapshot.get("node_classes", set())
        classes = [c for c in classes if c not in installed]
        snapshot = install_graph.snapshot
    else:
        snapshot = {}

    if not classes:
        return json.dumps({"nodes": [], "resolved": 0, "unresolved": 0,
                           "resolution": "All nodes are already installed."}, indent=2)

    from comfy_mcp.registry.resolver import RegistryResolver
    resolver = RegistryResolver(client, index, snapshot)
    result = await resolver.resolve_batch(classes)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Check Package Compatibility",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_check_compatibility(package_id: str, *, ctx: Context) -> str:
    """Check if a registry package is compatible with the current environment.

    Args:
        package_id: Package identifier to check.
    """
    client = _client(ctx)
    pkg = await client.get_node(package_id)
    if pkg is None:
        return json.dumps({"error": f"Package '{package_id}' not found"}, indent=2)

    install_graph = ctx.request_context.lifespan_context.get("install_graph")
    warnings = []

    if install_graph and install_graph.snapshot:
        s = install_graph.snapshot
        # Check ComfyUI version
        required_version = pkg.get("supported_comfyui_version")
        if required_version and s.get("version"):
            warnings.append(f"Requires ComfyUI {required_version}, installed: {s['version']}")

        # Check OS
        supported_os = pkg.get("supported_os", [])
        if supported_os and s.get("os"):
            os_name = s["os"]
            if not any(os_name.lower() in so.lower() for so in supported_os):
                warnings.append(f"OS {os_name} may not be supported (supported: {supported_os})")

    return json.dumps({
        "package_id": package_id,
        "name": pkg.get("name", ""),
        "latest_version": pkg.get("latest_version", {}).get("version", "unknown"),
        "compatible": len(warnings) == 0,
        "warnings": warnings,
        "install_cmd": f"comfy node install {package_id}",
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Registry Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_registry_status(*, ctx: Context) -> str:
    """Show registry cache statistics -- index size, entry counts, last sync."""
    index = _index(ctx)
    return json.dumps(index.summary(), indent=2)

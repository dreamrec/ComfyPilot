"""Docs tools — MCP surface for the documentation engine."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _store(ctx: Context):
    return ctx.request_context.lifespan_context["docs_store"]


def _fetcher(ctx: Context):
    return ctx.request_context.lifespan_context["docs_fetcher"]


@mcp.tool(
    annotations={
        "title": "Get Node Docs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_get_node_docs(class_name: str, ctx: Context) -> str:
    """Get documentation for a specific ComfyUI node class.

    Returns embedded documentation merged with object_info schema.
    Fetches from remote source if not cached. Falls back to schema-only
    if remote docs are unavailable.

    Args:
        class_name: The node class name (e.g., KSampler, SaveImage).
    """
    store = _store(ctx)
    fetcher = _fetcher(ctx)

    doc = store.get_embedded(class_name)

    if doc is None:
        doc = await fetcher.fetch_embedded_doc(class_name)
        if doc is not None:
            store.save_embedded(class_name, doc)

    install_graph = ctx.request_context.lifespan_context.get("install_graph")
    schema = None
    if install_graph and install_graph.snapshot:
        schema = install_graph.snapshot.get("object_info", {}).get(class_name)

    if doc is None and schema is None:
        return json.dumps({"class_name": class_name, "status": "not_found",
                           "note": "No documentation or schema found for this node class."}, indent=2)

    result = {"class_name": class_name}
    if doc is not None:
        result["description"] = doc
    if schema is not None:
        result["schema"] = schema
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Search Docs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_search_docs(query: str, limit: int = 10, *, ctx: Context) -> str:
    """Full-text search across cached ComfyUI documentation.

    Args:
        query: Search query string.
        limit: Maximum number of results (default 10).
    """
    store = _store(ctx)
    from comfy_mcp.docs.index import DocsIndex

    object_info = {}
    install_graph = ctx.request_context.lifespan_context.get("install_graph")
    if install_graph and install_graph.snapshot:
        object_info = install_graph.snapshot.get("object_info", {})

    # NOTE: DocsIndex is intentionally re-created on every call. object_info may
    # change between calls, keeping the index fresh.
    index = DocsIndex(store, object_info=object_info)
    results = index.search(query, limit=limit)
    return json.dumps({"query": query, "count": len(results), "results": results}, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Guide",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_guide(topic: str, ctx: Context) -> str:
    """Retrieve a guide section from ComfyUI documentation by topic.

    Args:
        topic: Topic to search for (e.g., "sampling", "models", "installation").
    """
    store = _store(ctx)
    result = store.get_section(topic)
    if result is None:
        return json.dumps({"topic": topic, "status": "not_found",
                           "note": "No guide section found. Try comfy_search_docs for broader search."}, indent=2)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Refresh Docs",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_refresh_docs(ctx: Context) -> str:
    """Re-fetch all documentation sources and rebuild the cache.

    Fetches embedded-docs and llms-full.txt from remote sources.
    Safe to call anytime — will not crash on network errors.
    """
    store = _store(ctx)
    fetcher = _fetcher(ctx)
    errors = []

    llms = await fetcher.fetch_llms_full()
    if llms is not None:
        store.save_llms(llms)
    else:
        errors.append("llms-full.txt: fetch failed (network error or source unavailable)")

    import asyncio
    install_graph = ctx.request_context.lifespan_context.get("install_graph")
    fetched_count = 0
    if install_graph and install_graph.snapshot:
        node_classes = sorted(install_graph.snapshot.get("node_classes", set()))
        semaphore = asyncio.Semaphore(10)

        async def _fetch_one(cn: str) -> tuple[str, str | None]:
            async with semaphore:
                doc = await fetcher.fetch_embedded_doc(cn)
                return cn, doc

        results = await asyncio.gather(*[_fetch_one(cn) for cn in node_classes])
        for class_name, doc in results:
            if doc is not None:
                store.save_embedded(class_name, doc)
                fetched_count += 1

    return json.dumps({
        "status": "ok" if not errors else "partial",
        "embedded_docs_fetched": fetched_count,
        "llms_cached": llms is not None,
        "errors": errors,
        "summary": store.summary(),
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Docs Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_docs_status(ctx: Context) -> str:
    """Show documentation cache status."""
    store = _store(ctx)
    return json.dumps(store.summary(), indent=2)

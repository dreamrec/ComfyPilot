"""Template tools -- MCP surface for the template engine."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _index(ctx: Context):
    return ctx.request_context.lifespan_context["template_index"]


def _discovery(ctx: Context):
    return ctx.request_context.lifespan_context["template_discovery"]


@mcp.tool(
    annotations={
        "title": "Search Templates",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_search_templates(
    query: str,
    tags: list[str] | None = None,
    category: str | None = None,
    limit: int = 10,
    *,
    ctx: Context,
) -> str:
    """Search templates by query, tags, and/or category.

    Returns scored results ranked by relevance and compatibility.

    Args:
        query: Natural language search query.
        tags: Optional tag filters.
        category: Optional category filter.
        limit: Maximum results (default 10).
    """
    index = _index(ctx)
    install_graph = ctx.request_context.lifespan_context.get("install_graph")
    if install_graph and install_graph.snapshot:
        nodes = install_graph.snapshot.get("node_classes", set())
        models = install_graph.snapshot.get("models", {})
    else:
        nodes = set()
        models = {}

    from comfy_mcp.templates.scorer import TemplateScorer
    scorer = TemplateScorer(nodes, models)
    results = scorer.score(query, index.list_all(), tags=tags, category=category, limit=limit)
    return json.dumps({"query": query, "count": len(results), "results": results}, indent=2)


@mcp.tool(
    annotations={
        "title": "Get Template",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_template(
    template_id: str,
    include_workflow: bool = False,
    refresh_remote: bool = False,
    *,
    ctx: Context,
) -> str:
    """Get full template details including metadata and workflow format hints.

    Args:
        template_id: Template ID from search results.
        include_workflow: If True, include the fetched workflow JSON body when available.
        refresh_remote: If True, re-fetch the remote workflow instead of using the cached copy.
    """
    index = _index(ctx)
    if hasattr(index, "hydrate_template"):
        template = await index.hydrate_template(
            template_id,
            include_workflow=include_workflow,
            refresh_remote=refresh_remote,
        )
    else:
        template = index.get(template_id)
    if template is None:
        return json.dumps({"error": f"Template '{template_id}' not found"}, indent=2)
    return json.dumps(template, indent=2)


@mcp.tool(
    annotations={
        "title": "List Template Categories",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_template_categories(*, ctx: Context) -> str:
    """List all available template categories."""
    index = _index(ctx)
    return json.dumps({"categories": index.categories()}, indent=2)


@mcp.tool(
    annotations={
        "title": "Template Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_template_status(*, ctx: Context) -> str:
    """Show template index status -- counts, categories, cache freshness."""
    index = _index(ctx)
    return json.dumps(index.summary(), indent=2)


@mcp.tool(
    annotations={
        "title": "Discover Templates",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_discover_templates(*, ctx: Context) -> str:
    """Scan all template sources and rebuild the unified template index.

    Fetches from official ComfyUI templates, custom node examples, and built-in templates.
    """
    discovery = _discovery(ctx)
    index = _index(ctx)
    templates = await discovery.discover_all()
    index.rebuild(templates)
    return json.dumps({"status": "ok", "summary": index.summary()}, indent=2)


@mcp.tool(
    annotations={
        "title": "Instantiate Template",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_instantiate_template(
    template_id: str,
    overrides: dict | None = None,
    refresh_remote: bool = False,
    *,
    ctx: Context,
) -> str:
    """Instantiate a template with model substitution.

    Substitutes model references with installed models, applies overrides,
    and returns a ready-to-queue workflow.

    Args:
        template_id: Template ID to instantiate.
        overrides: Optional dict of parameter overrides (e.g., {"width": 768}).
        refresh_remote: If True, re-fetch the remote workflow instead of using the cached copy.
    """
    index = _index(ctx)
    if hasattr(index, "hydrate_template"):
        template = await index.hydrate_template(
            template_id,
            include_workflow=True,
            refresh_remote=refresh_remote,
        )
    else:
        template = index.get(template_id)
    if template is None:
        return json.dumps({"error": f"Template '{template_id}' not found"}, indent=2)

    install_graph = ctx.request_context.lifespan_context.get("install_graph")
    if not install_graph or not install_graph.snapshot:
        return json.dumps({"error": "Install graph not available. Run comfy_refresh_install_graph first."}, indent=2)

    workflow_format = template.get("workflow_format", "unknown")
    object_info = install_graph.snapshot.get("object_info", {})
    translation_report = None
    from comfy_mcp.templates.instantiator import TemplateInstantiator
    if workflow_format != "api-prompt":
        from comfy_mcp.workflow_translation import translate_workflow

        translation_report = translate_workflow(template.get("workflow", {}), object_info)
        if translation_report["status"] != "translated":
            return json.dumps({
                "status": "reference_only",
                "error": (
                    "Template workflow is not in ComfyUI API prompt format and could not be translated safely yet."
                ),
                "template_id": template.get("id", template_id),
                "template_name": template.get("title", template.get("name", "")),
                "workflow_format": workflow_format,
                "workflow_summary": template.get("workflow_summary", {}),
                "workflow_url": template.get("workflow_url", ""),
                "tutorial_url": template.get("tutorial_url", ""),
                "translation_report": translation_report,
            }, indent=2)
        template = dict(template)
        template["workflow"] = translation_report["workflow"]

    instantiator = TemplateInstantiator(install_graph.snapshot)
    result = instantiator.instantiate(template, overrides=overrides)
    if translation_report is not None:
        result["translation_report"] = translation_report
    return json.dumps(result, indent=2)

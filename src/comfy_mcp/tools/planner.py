"""Planner tools — workflow recommendation and strategy selection."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from comfy_mcp.ecosystem import EcosystemRegistry, ModelAwarenessScanner
from comfy_mcp.planner import WorkflowPlanner
from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


def _install_graph(ctx: Context):
    return ctx.request_context.lifespan_context.get("install_graph")


def _planner(ctx: Context) -> WorkflowPlanner:
    planner = ctx.request_context.lifespan_context.get("workflow_planner")
    if planner is not None:
        return planner
    registry = ctx.request_context.lifespan_context.get("ecosystem_registry") or EcosystemRegistry()
    scanner = ctx.request_context.lifespan_context.get("model_awareness_scanner") or ModelAwarenessScanner(registry)
    return WorkflowPlanner(registry, scanner)


@mcp.tool(
    annotations={
        "title": "Recommend Workflow",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_recommend_workflow(
    goal: str = "",
    task: str = "",
    prefer_local: bool = True,
    allow_providers: bool = True,
    speed_priority: str = "medium",
    quality_priority: str = "high",
    limit: int = 5,
    ctx: Context = None,
) -> str:
    """Recommend workflows, model families, templates, or providers for a goal."""
    install_graph = _install_graph(ctx)
    snapshot = getattr(install_graph, "snapshot", None) if install_graph is not None else None

    if not snapshot:
        snapshot = {
            "models": {},
            "node_classes": set(),
        }

    template_index = ctx.request_context.lifespan_context.get("template_index") if ctx else None
    result = _planner(ctx).recommend(
        snapshot,
        capabilities=getattr(_client(ctx), "capabilities", {}),
        goal=goal,
        task=task,
        prefer_local=prefer_local,
        allow_providers=allow_providers,
        speed_priority=speed_priority,
        quality_priority=quality_priority,
        template_index=template_index,
        limit=limit,
    )
    return json.dumps(result, indent=2)

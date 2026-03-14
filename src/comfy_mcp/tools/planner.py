"""Planner tools — workflow recommendation and strategy selection."""

from __future__ import annotations

import inspect
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


def _object_info(ctx: Context) -> dict:
    install_graph = _install_graph(ctx)
    snapshot = getattr(install_graph, "snapshot", None) if install_graph is not None else None
    return snapshot.get("object_info", {}) if snapshot else {}


def _translation_bonus(assessment: dict) -> float:
    confidence = assessment.get("confidence")
    ready_for_queue = assessment.get("ready_for_queue", False)
    if confidence == "direct":
        return 0.12
    if ready_for_queue and confidence == "high":
        return 0.1
    if ready_for_queue and confidence == "medium":
        return 0.06
    if ready_for_queue and confidence == "low":
        return 0.02
    if confidence == "unscored":
        return 0.0
    return -0.08


def _apply_template_assessment(item: dict, hydrated: dict) -> dict:
    enriched = dict(item)
    for key in ("workflow_format", "workflow_summary", "workflow_source", "translation_status", "translation_assessment"):
        if key in hydrated:
            enriched[key] = hydrated[key]

    assessment = hydrated.get("translation_assessment") or {}
    if assessment:
        enriched["score"] = round(enriched["score"] + _translation_bonus(assessment), 3)
        enriched.setdefault("why", []).append(
            f"Translation confidence is {assessment.get('confidence', 'unknown')} "
            f"(score {assessment.get('score', 'n/a')})."
        )
        if assessment.get("ready_for_queue"):
            enriched["next_step_tool"] = "comfy_instantiate_template"
        elif assessment.get("confidence") not in {"unscored", None}:
            enriched["next_step_tool"] = "comfy_get_template"
    return enriched


async def _enrich_template_recommendations(
    result: dict,
    *,
    ctx: Context,
    template_index,
) -> dict:
    hydrate_template = getattr(template_index, "hydrate_template", None)
    if template_index is None or not inspect.iscoroutinefunction(hydrate_template):
        return result

    object_info = _object_info(ctx)
    enriched: list[dict] = []
    for item in result.get("recommendations", []):
        if item.get("type") != "template" or not item.get("template_id"):
            enriched.append(item)
            continue
        hydrated = await hydrate_template(
            item["template_id"],
            object_info=object_info,
            assess_translation=True,
            include_workflow=False,
        )
        if hydrated is None:
            enriched.append(item)
            continue
        enriched.append(_apply_template_assessment(item, hydrated))

    enriched.sort(key=lambda item: item.get("score", 0), reverse=True)
    result = dict(result)
    result["recommendations"] = enriched
    result["default_recommendation"] = enriched[0] if enriched else None
    return result


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
    result = await _enrich_template_recommendations(
        result,
        ctx=ctx,
        template_index=template_index,
    )
    return json.dumps(result, indent=2)

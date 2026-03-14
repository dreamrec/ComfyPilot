"""Recommendation engine for matching user goals to available workflows."""

from __future__ import annotations

from typing import Any

from comfy_mcp.ecosystem import EcosystemRegistry, ModelAwarenessScanner
from comfy_mcp.templates.scorer import TemplateScorer

TASK_ALIASES = {
    "txt2img": "t2i",
    "text-to-image": "t2i",
    "text to image": "t2i",
    "t2i": "t2i",
    "img2img": "i2i",
    "image-to-image": "i2i",
    "image to image": "i2i",
    "i2i": "i2i",
    "edit": "edit",
    "image-edit": "edit",
    "image edit": "edit",
    "inpaint": "inpaint",
    "controlnet": "control",
    "control": "control",
    "text-to-video": "t2v",
    "text to video": "t2v",
    "t2v": "t2v",
    "image-to-video": "i2v",
    "image to video": "i2v",
    "i2v": "i2v",
    "upscale": "upscale",
}

TASK_TEMPLATE_MAP = {
    "t2i": "txt2img",
    "i2i": "img2img",
    "edit": "img2img",
    "inpaint": "inpaint",
    "control": "controlnet",
    "upscale": "upscale",
}

TASK_MODALITY = {
    "t2i": "image",
    "i2i": "image",
    "edit": "image",
    "inpaint": "image",
    "control": "image",
    "t2v": "video",
    "i2v": "video",
    "upscale": "image",
}

BUILDER_COMPATIBLE_FAMILIES = {"sd15", "sdxl", "flux1"}


def _normalize_task(task: str) -> str:
    return TASK_ALIASES.get(task.strip().lower(), task.strip().lower()) if task else ""


def _task_supported(requested: str, supported: list[str]) -> bool:
    if not requested:
        return True
    if requested in supported:
        return True
    if requested == "inpaint" and "edit" in supported:
        return True
    if requested == "edit" and "i2i" in supported:
        return True
    if requested == "control" and "t2i" in supported:
        return True
    return False


class WorkflowPlanner:
    """Rank local families, templates, and provider options for a workflow goal."""

    def __init__(self, registry: EcosystemRegistry, scanner: ModelAwarenessScanner) -> None:
        self._registry = registry
        self._scanner = scanner

    def infer_task(self, goal: str = "", task: str = "") -> str:
        explicit = _normalize_task(task)
        if explicit:
            return explicit
        text = goal.lower()
        if "upscale" in text:
            return "upscale"
        if "inpaint" in text or "mask" in text:
            return "inpaint"
        if "controlnet" in text or "depth" in text or "pose" in text or "canny" in text:
            return "control"
        if "image to video" in text or "i2v" in text or "animate image" in text:
            return "i2v"
        if "text to video" in text or "t2v" in text or "video" in text:
            return "t2v"
        if "edit" in text:
            return "edit"
        if "img2img" in text or "image to image" in text:
            return "i2i"
        return "t2i"

    def recommend(
        self,
        snapshot: dict[str, Any] | None,
        capabilities: dict[str, Any] | None = None,
        *,
        goal: str = "",
        task: str = "",
        prefer_local: bool = True,
        allow_providers: bool = True,
        speed_priority: str = "medium",
        quality_priority: str = "high",
        template_index: Any | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        snapshot = snapshot or {}
        capabilities = capabilities or {}
        inferred_task = self.infer_task(goal=goal, task=task)
        awareness = self._scanner.scan(snapshot, capabilities=capabilities)
        missing_lookup = {
            item["family"]: item["missing"]
            for item in awareness.get("missing_assets", [])
        }

        candidates: list[dict[str, Any]] = []
        family_summaries = {entry["id"]: entry for entry in self._registry.list_entries(kind="family")}

        for family_id in awareness.get("detected_architectures", []):
            family = self._registry.family_by_id(family_id)
            if family is None or not _task_supported(inferred_task, family.tasks):
                continue

            score = 0.45 + min(family.priority / 300.0, 0.35)
            reasons = [f"Detected installed family {family.display_name}"]
            if prefer_local and "local-native" in family.runtime_modes:
                score += 0.15
                reasons.append("Prefers local-native execution")
            if inferred_task in family.tasks:
                score += 0.15
                reasons.append(f"Supports requested task {inferred_task}")
            if missing_lookup.get(family_id):
                score -= 0.25
                reasons.append("Some required assets still appear missing")
            else:
                score += 0.05
                reasons.append("Required assets appear available")

            if quality_priority == "high" and family.priority >= 95:
                score += 0.05
            if speed_priority == "high" and family_id in {"sd15", "sdxl", "flux1"}:
                score += 0.05

            candidates.append({
                "strategy_id": f"local-{family_id}-{inferred_task}",
                "type": "family",
                "runtime": "local-native",
                "family": family_id,
                "display_name": family.display_name,
                "task": inferred_task,
                "score": round(score, 3),
                "why": reasons,
                "builder_compatible": family_id in BUILDER_COMPATIBLE_FAMILIES,
                "builder_template": TASK_TEMPLATE_MAP.get(inferred_task) if family_id in BUILDER_COMPATIBLE_FAMILIES else None,
                "template_hint": family_summaries[family_id].get("id"),
                "missing_assets": missing_lookup.get(family_id, []),
            })

        if allow_providers:
            for provider in awareness.get("provider_details", []):
                if not _task_supported(inferred_task, provider.get("tasks", [])):
                    continue
                score = 0.35 + min(provider.get("priority", 0) / 400.0, 0.2)
                reasons = [f"Detected provider {provider['display_name']} via nodes or auth"]
                if provider.get("configured"):
                    score += 0.15
                    reasons.append("Credentials appear configured")
                if prefer_local:
                    score -= 0.05
                    reasons.append("Local-first preference lowers provider ranking")
                if inferred_task in provider.get("tasks", []):
                    score += 0.1
                    reasons.append(f"Provider supports requested task {inferred_task}")

                candidates.append({
                    "strategy_id": f"provider-{provider['id']}-{inferred_task}",
                    "type": "provider",
                    "runtime": "partner-nodes",
                    "provider": provider["id"],
                    "display_name": provider["display_name"],
                    "task": inferred_task,
                    "score": round(score, 3),
                    "why": reasons,
                    "configured": provider.get("configured", False),
                })

        if template_index is not None:
            scorer = TemplateScorer(
                snapshot.get("node_classes", set()),
                snapshot.get("models", {}),
            )
            scored = scorer.score(goal or inferred_task, template_index.list_all(), limit=min(limit, 3))
            for entry in scored:
                if entry["score"] < 0.4:
                    continue
                score = 0.3 + entry["score"] * 0.4
                reasons = [f"Template search found {entry['name']}"]
                if not entry["warnings"]:
                    score += 0.1
                    reasons.append("Template looks compatible with the current install")
                candidates.append({
                    "strategy_id": f"template-{entry['id']}",
                    "type": "template",
                    "runtime": "template-index",
                    "template_id": entry["id"],
                    "display_name": entry["name"],
                    "task": inferred_task,
                    "score": round(score, 3),
                    "why": reasons,
                    "warnings": entry["warnings"],
                })

        candidates.sort(key=lambda item: item["score"], reverse=True)
        top = candidates[:limit]
        return {
            "goal": goal,
            "task": inferred_task,
            "prefer_local": prefer_local,
            "allow_providers": allow_providers,
            "environment": {
                "architectures": awareness.get("detected_architectures", []),
                "providers": awareness.get("detected_providers", []),
                "capabilities": awareness.get("available_capabilities", []),
                "runtimes": awareness.get("available_runtimes", []),
            },
            "recommendations": top,
            "default_recommendation": top[0] if top else None,
        }

    def recommend_for_common_tasks(
        self,
        snapshot: dict[str, Any] | None,
        capabilities: dict[str, Any] | None = None,
        template_index: Any | None = None,
    ) -> dict[str, Any]:
        tasks = ["t2i", "edit", "t2v", "i2v", "upscale"]
        return {
            task: self.recommend(
                snapshot,
                capabilities=capabilities,
                task=task,
                template_index=template_index,
                limit=3,
            )["recommendations"]
            for task in tasks
        }

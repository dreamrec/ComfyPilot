"""TemplateIndex -- unified template index with disk cache.

Maintains a merged index of all template sources at ~/.comfypilot/templates/.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from comfy_mcp.knowledge.store import atomic_write
from comfy_mcp.workflow_formats import describe_workflow

logger = logging.getLogger("comfypilot.templates")


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class TemplateIndex:
    """Unified template index across all sources."""

    def __init__(self, storage_dir: str | None = None, discovery: Any | None = None):
        self._dir = Path(storage_dir or Path.home() / ".comfypilot" / "templates")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._templates: list[dict[str, Any]] = []
        self._manifest: dict[str, Any] = {}
        self._discovery = discovery
        self._load()

    def _index_path(self) -> Path:
        return self._dir / "index.json"

    def _manifest_path(self) -> Path:
        return self._dir / "manifest.json"

    def _workflow_cache_path(self, template_id: str) -> Path:
        return self._dir / "workflows" / f"{template_id}.json"

    def _load(self) -> None:
        idx_path = self._index_path()
        if idx_path.exists():
            try:
                self._templates = json.loads(idx_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._templates = []
        mfst_path = self._manifest_path()
        if mfst_path.exists():
            try:
                self._manifest = json.loads(mfst_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._manifest = {}

    def rebuild(self, templates: list[dict[str, Any]]) -> None:
        """Replace the index with a new list of templates."""
        # Assign stable IDs based on source + name
        for t in templates:
            if "id" not in t:
                t["id"] = f"{t.get('source', 'unknown')}_{t.get('name', 'unnamed')}"
        self._templates = templates
        self._dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self._index_path(), json.dumps(templates, indent=2))
        self._manifest = {
            "last_updated": time.time(),
            "template_count": len(templates),
            "content_hash": _content_hash(json.dumps(templates, sort_keys=True)),
            "source_counts": self._count_sources(templates),
        }
        atomic_write(self._manifest_path(), json.dumps(self._manifest, indent=2))

    def _count_sources(self, templates: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in templates:
            src = t.get("source", "unknown")
            counts[src] = counts.get(src, 0) + 1
        return counts

    def get(self, template_id: str) -> dict | None:
        """Get a template by ID."""
        for t in self._templates:
            if t.get("id") == template_id:
                return t
        return None

    def _load_cached_workflow(self, template_id: str) -> Any | None:
        cache_path = self._workflow_cache_path(template_id)
        if not cache_path.exists():
            return None
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    async def _fetch_remote_workflow(self, template_id: str, workflow_url: str) -> Any | None:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(workflow_url)
            response.raise_for_status()
            payload = response.json()
        atomic_write(self._workflow_cache_path(template_id), json.dumps(payload, indent=2))
        return payload

    async def hydrate_template(
        self,
        template_id: str,
        *,
        include_workflow: bool = False,
        refresh_remote: bool = False,
        object_info: dict[str, Any] | None = None,
        assess_translation: bool = False,
    ) -> dict[str, Any] | None:
        """Return a template with remote workflow metadata hydrated when available."""
        template = self.get(template_id)
        if template is None:
            return None

        hydrated = dict(template)
        workflow_payload = hydrated.get("workflow")
        workflow_source = "embedded" if workflow_payload is not None else None

        if workflow_payload is None and hydrated.get("workflow_url"):
            if not refresh_remote:
                workflow_payload = self._load_cached_workflow(template_id)
                if workflow_payload is not None:
                    workflow_source = "cache"
            if workflow_payload is None:
                try:
                    workflow_payload = await self._fetch_remote_workflow(
                        template_id,
                        hydrated["workflow_url"],
                    )
                    workflow_source = "remote"
                except Exception as exc:
                    logger.debug("Failed to fetch workflow for template %s: %s", template_id, exc)
                    hydrated["workflow_fetch_error"] = str(exc)

        description = describe_workflow(workflow_payload)
        hydrated["workflow_format"] = description["format"]
        hydrated["workflow_summary"] = description["summary"]
        hydrated["workflow_source"] = workflow_source
        hydrated["supports_instantiation"] = bool(
            hydrated.get("supports_instantiation", False) or description["format"] == "api-prompt"
        )

        if assess_translation and workflow_payload is not None:
            if description["format"] == "comfyui-ui" and not object_info:
                hydrated["translation_status"] = "needs_object_info"
                hydrated["translation_assessment"] = {
                    "mode": "unknown",
                    "confidence": "unscored",
                    "score": None,
                    "ready_for_queue": False,
                    "recommended_action": "refresh-install-graph",
                    "reasons": [
                        "Installed node schema was not available, so this UI workflow could not be assessed safely."
                    ],
                }
            else:
                from comfy_mcp.workflow_translation import translate_workflow

                translation_report = translate_workflow(workflow_payload, object_info or {})
                hydrated["translation_status"] = translation_report["status"]
                hydrated["translation_assessment"] = translation_report.get("translation_assessment", {})

        if workflow_payload is not None:
            if include_workflow or "workflow" in template:
                hydrated["workflow"] = workflow_payload
            else:
                hydrated.pop("workflow", None)

        return hydrated

    def list_all(self) -> list[dict]:
        """Return all templates (metadata only, no workflow bodies)."""
        return [
            {k: v for k, v in t.items() if k != "workflow"}
            for t in self._templates
        ]

    def categories(self) -> list[str]:
        """Return all unique categories."""
        cats = set()
        for t in self._templates:
            cat = t.get("category", "")
            if cat:
                cats.add(cat)
        return sorted(cats)

    def is_stale(self, max_age: float = 300) -> bool:
        last = self._manifest.get("last_updated")
        if last is None:
            return True
        return (time.time() - last) >= max_age

    def content_hash(self) -> str:
        return self._manifest.get("content_hash", "")

    def clear(self) -> None:
        """Clear all cached templates and manifest."""
        self._templates = []
        self._manifest = {}
        idx_path = self._index_path()
        if idx_path.exists():
            idx_path.unlink()
        mfst_path = self._manifest_path()
        if mfst_path.exists():
            mfst_path.unlink()

    async def refresh(self) -> None:
        """Re-discover templates from all sources and rebuild the index."""
        if self._discovery is None:
            logger.warning("TemplateIndex.refresh() called without discovery instance, skipping")
            return
        templates = await self._discovery.discover_all()
        self.rebuild(templates)

    def summary(self) -> dict:
        return {
            "template_count": len(self._templates),
            "categories": self.categories(),
            "source_counts": self._manifest.get("source_counts", {}),
            "stale": self.is_stale(),
            "last_updated": self._manifest.get("last_updated"),
            "content_hash": self.content_hash(),
        }

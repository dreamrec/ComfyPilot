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
        self._index_path().write_text(json.dumps(templates, indent=2), encoding="utf-8")
        self._manifest = {
            "last_updated": time.time(),
            "template_count": len(templates),
            "content_hash": _content_hash(json.dumps(templates, sort_keys=True)),
            "source_counts": self._count_sources(templates),
        }
        self._manifest_path().write_text(json.dumps(self._manifest, indent=2), encoding="utf-8")

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

"""TechniqueStore — persistent workflow technique library.

Stores reusable workflow patterns (techniques) with search, favorites, and ratings.
Persists to JSON files in a configurable directory.
"""
from __future__ import annotations

import copy
import json
import time
import uuid
from pathlib import Path
from typing import Any

from comfy_mcp.knowledge.store import atomic_write

_TECHNIQUE_SCHEMA_VERSION = 1


class TechniqueStore:
    """Stores and retrieves workflow techniques (reusable patterns)."""

    def __init__(self, storage_dir: str | None = None):
        self._dir = Path(storage_dir or Path.home() / ".comfypilot" / "techniques")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._techniques: dict[str, dict] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all technique JSON files from storage directory."""
        for path in self._dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if "schema_version" not in data:
                    data["schema_version"] = _TECHNIQUE_SCHEMA_VERSION
                self._techniques[data["id"]] = data
            except (json.JSONDecodeError, KeyError):
                continue

    def _persist(self, technique_id: str) -> None:
        """Write a single technique to disk atomically."""
        tech = self._techniques.get(technique_id)
        if tech:
            path = self._dir / f"{technique_id}.json"
            atomic_write(path, json.dumps(tech, indent=2))

    def save(self, workflow: dict, name: str, description: str = "", tags: list[str] | None = None, metadata: dict | None = None) -> dict:
        """Save a workflow as a reusable technique. Returns metadata."""
        tech_id = str(uuid.uuid4())[:8]
        technique = {
            "schema_version": _TECHNIQUE_SCHEMA_VERSION,
            "id": tech_id,
            "name": name,
            "description": description,
            "tags": tags or [],
            "workflow": copy.deepcopy(workflow),
            "timestamp": time.time(),
            "node_count": len(workflow),
            "favorite": False,
            "rating": -1,
            "use_count": 0,
        }
        # Store metadata if provided
        if metadata:
            technique["node_classes"] = metadata.get("node_classes", [])
            technique["model_references"] = metadata.get("model_references", [])

        self._techniques[tech_id] = technique
        self._persist(tech_id)

        result = {
            "id": tech_id,
            "name": name,
            "description": description,
            "tags": technique["tags"],
            "timestamp": technique["timestamp"],
            "node_count": technique["node_count"],
        }

        # Include metadata in result if available
        if metadata:
            result["node_classes"] = metadata.get("node_classes", [])
            result["model_references"] = metadata.get("model_references", [])

        return result

    def search(self, query: str = "", tags: list[str] | None = None, limit: int = 20) -> list[dict]:
        """Search techniques by text query and/or tags. Returns metadata (no workflow)."""
        results = []
        query_lower = query.lower()
        for tech in self._techniques.values():
            # Tag filter
            if tags:
                if not any(t in tech.get("tags", []) for t in tags):
                    continue
            # Text filter
            if query_lower:
                searchable = f"{tech['name']} {tech.get('description', '')} {' '.join(tech.get('tags', []))}".lower()
                if query_lower not in searchable:
                    continue
            results.append({
                "id": tech["id"],
                "name": tech["name"],
                "description": tech.get("description", ""),
                "tags": tech.get("tags", []),
                "timestamp": tech["timestamp"],
                "node_count": tech["node_count"],
                "favorite": tech.get("favorite", False),
                "rating": tech.get("rating", -1),
                "use_count": tech.get("use_count", 0),
            })
        # Sort newest first
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results[:limit]

    def list(self, limit: int = 50) -> list[dict]:
        """List all techniques metadata (newest first)."""
        return self.search(query="", limit=limit)

    def get(self, technique_id: str) -> dict | None:
        """Get full technique including workflow data."""
        tech = self._techniques.get(technique_id)
        if tech:
            return copy.deepcopy(tech)
        return None

    def record_use(self, technique_id: str) -> dict | None:
        """Increment use_count and return full technique. Returns None if not found."""
        tech = self._techniques.get(technique_id)
        if not tech:
            return None
        tech["use_count"] = tech.get("use_count", 0) + 1
        self._persist(technique_id)
        return copy.deepcopy(tech)

    def favorite(self, technique_id: str, favorite: bool = True, rating: int = -1) -> dict:
        """Set favorite status and/or rating for a technique."""
        tech = self._techniques.get(technique_id)
        if not tech:
            return {"error": f"Technique {technique_id} not found"}
        tech["favorite"] = favorite
        if rating >= 0:
            tech["rating"] = min(rating, 5)
        self._persist(technique_id)
        return {
            "id": tech["id"],
            "name": tech["name"],
            "favorite": tech["favorite"],
            "rating": tech["rating"],
        }

    def delete(self, technique_id: str) -> bool:
        """Delete a technique. Returns True if found and deleted."""
        if technique_id in self._techniques:
            del self._techniques[technique_id]
            path = self._dir / f"{technique_id}.json"
            if path.exists():
                path.unlink()
            return True
        return False

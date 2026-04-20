"""Subgraph blueprint store.

Blueprints are named, reusable bundles of nodes. Two sources:
1. User-published (writable): COMFY_BLUEPRINT_DIR or ~/.comfypilot/blueprints
2. Bundled (read-only): the blueprints/ directory inside the package repo

Insert-time overrides let callers patch widget values per instance
(inputs = {node_id: {input_name: value}}).
"""
from __future__ import annotations

import copy
import json
import time
import uuid
from pathlib import Path


class BlueprintStore:
    def __init__(self, user_dir: Path | str | None = None, bundled_dir: Path | str | None = None):
        self._user_dir = Path(user_dir) if user_dir else None
        self._bundled_dir = Path(bundled_dir) if bundled_dir else None
        if self._user_dir is not None:
            self._user_dir.mkdir(parents=True, exist_ok=True)

    # ---------- publish ----------

    def publish(self, name: str, nodes: dict, description: str = "", tags: list[str] | None = None) -> dict:
        if self._user_dir is None:
            raise RuntimeError("BlueprintStore has no writable user directory configured")
        # Reject path separators on every platform. Windows treats '\' as a
        # separator and our manifest advertises win32 support, so names like
        # 'foo\bar' would escape the intended single-file layout. Also reject
        # NUL, control characters, and leading dots (hidden files).
        if (
            not name
            or "/" in name
            or "\\" in name
            or ".." in name
            or "\x00" in name
            or name.startswith(".")
            or any(ord(c) < 0x20 for c in name)
        ):
            raise ValueError(f"Invalid blueprint name: {name!r}")

        record = {
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "description": description,
            "tags": tags or [],
            "nodes": copy.deepcopy(nodes),
            "node_count": len(nodes),
            "timestamp": time.time(),
        }
        path = self._user_dir / f"{name}.json"
        path.write_text(json.dumps(record, indent=2))
        return {"id": record["id"], "name": name, "node_count": len(nodes), "source": "user"}

    # ---------- list ----------

    def list(self) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()

        # User blueprints take precedence
        if self._user_dir is not None and self._user_dir.exists():
            for p in sorted(self._user_dir.glob("*.json")):
                data = self._safe_read(p)
                if not data:
                    continue
                name = data.get("name", p.stem)
                if name in seen:
                    continue
                seen.add(name)
                out.append(self._summary(data, source="user"))

        # Bundled fall back
        if self._bundled_dir is not None and self._bundled_dir.exists():
            for p in sorted(self._bundled_dir.glob("*.json")):
                data = self._safe_read(p)
                if not data:
                    continue
                name = data.get("name", p.stem)
                if name in seen:
                    continue
                seen.add(name)
                out.append(self._summary(data, source="bundled"))

        return out

    # ---------- insert ----------

    def insert(self, name: str, inputs: dict | None = None) -> dict:
        """Materialize a blueprint into a workflow dict. Applies node-level input overrides."""
        data = self._load_named(name)
        if data is None:
            raise FileNotFoundError(f"Blueprint {name!r} not found")
        nodes = copy.deepcopy(data["nodes"])

        for node_id, overrides in (inputs or {}).items():
            if node_id in nodes and isinstance(overrides, dict):
                nodes[node_id].setdefault("inputs", {}).update(overrides)

        return {
            "name": name,
            "node_count": len(nodes),
            "workflow": nodes,
            "source": data.get("_source", "unknown"),
        }

    # ---------- helpers ----------

    def _load_named(self, name: str) -> dict | None:
        if self._user_dir is not None:
            candidate = self._user_dir / f"{name}.json"
            if candidate.exists():
                data = self._safe_read(candidate)
                if data:
                    data["_source"] = "user"
                    return data
        if self._bundled_dir is not None:
            candidate = self._bundled_dir / f"{name}.json"
            if candidate.exists():
                data = self._safe_read(candidate)
                if data:
                    data["_source"] = "bundled"
                    return data
        return None

    @staticmethod
    def _safe_read(path: Path) -> dict | None:
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _summary(data: dict, source: str) -> dict:
        return {
            "name": data.get("name", "unknown"),
            "id": data.get("id"),
            "description": data.get("description", ""),
            "tags": data.get("tags", []),
            "node_count": data.get("node_count", 0),
            "source": source,
        }

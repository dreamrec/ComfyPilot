"""RegistryIndex -- reverse lookup cache mapping node class names to registry packages.

Supports both positive entries (class -> package) and negative entries
(class -> not-in-registry) with configurable TTL for negative entries.
Persists to ~/.comfypilot/cache/registry/node_class_index.json.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("comfypilot.registry")

NEGATIVE_TTL_DEFAULT = 86400  # 24 hours


class RegistryIndex:
    """Cached reverse lookup from node class name to registry package."""

    def __init__(self, cache_dir: str | None = None, negative_ttl: float = NEGATIVE_TTL_DEFAULT):
        self._dir = Path(cache_dir or Path.home() / ".comfypilot" / "cache" / "registry")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._negative_ttl = negative_ttl
        self._cache: dict[str, dict[str, Any]] = {}
        self._load()

    def _index_path(self) -> Path:
        return self._dir / "node_class_index.json"

    def _load(self) -> None:
        path = self._index_path()
        if not path.exists():
            return
        try:
            self._cache = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Registry index corrupted, starting fresh: %s", exc)
            self._cache = {}

    def lookup(self, class_name: str) -> dict[str, Any] | None:
        """Look up a node class in the cache.

        Returns the cached entry if found and valid, None if not cached.
        For negative entries, returns None if expired (TTL exceeded).
        """
        entry = self._cache.get(class_name)
        if entry is None:
            return None

        # Check negative entry TTL
        if entry.get("package") is None:
            age = time.time() - entry.get("cached_at", 0)
            if age >= self._negative_ttl:
                del self._cache[class_name]
                self.save()
                return None

        return entry

    def cache_positive(self, class_name: str, package_id: str, version: str) -> None:
        """Cache a positive lookup result."""
        self._cache[class_name] = {
            "class": class_name,
            "package": package_id,
            "version": version,
            "cached_at": time.time(),
        }

    def cache_negative(self, class_name: str) -> None:
        """Cache a negative lookup result (not found in registry)."""
        self._cache[class_name] = {
            "class": class_name,
            "package": None,
            "cached_at": time.time(),
        }

    def save(self) -> None:
        """Persist cache to disk using atomic_write."""
        from comfy_mcp.knowledge.store import atomic_write
        atomic_write(self._index_path(), json.dumps(self._cache, indent=2))

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache = {}
        path = self._index_path()
        if path.exists():
            path.unlink()

    def is_stale(self, max_age: float = 86400) -> bool:
        """Check if cache is empty or all entries are older than max_age seconds."""
        if len(self._cache) == 0:
            return True
        oldest = min(e.get("cached_at", 0) for e in self._cache.values())
        return (time.time() - oldest) >= max_age

    def content_hash(self) -> str:
        """Hash of all cached entries (keys and values)."""
        import hashlib
        content = json.dumps(self._cache, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def summary(self) -> dict[str, Any]:
        positive = sum(1 for e in self._cache.values() if e.get("package") is not None)
        negative = sum(1 for e in self._cache.values() if e.get("package") is None)
        return {
            "total_entries": len(self._cache),
            "positive_entries": positive,
            "negative_entries": negative,
        }

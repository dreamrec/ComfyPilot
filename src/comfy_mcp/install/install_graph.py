"""InstallGraph — canonical snapshot of the connected ComfyUI machine state.

Queries object_info, models, features, extensions, embeddings, and system stats,
then caches a structured snapshot for use by the Compatibility Engine and tools.

Knowledge pipeline integration: tracks content hashes for change detection so
consumers can know when the graph is stale without re-querying every endpoint.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("comfypilot.install")

MODEL_FOLDERS = (
    "checkpoints",
    "diffusion_models",
    "text_encoders",
    "vae",
    "loras",
    "controlnet",
    "model_patches",
    "latent_upscale_models",
    "clip",
    "clip_vision",
    "upscale_models",
    "diffusers",
    "hypernetworks",
)


def _hash(obj: Any) -> str:
    """Deterministic SHA-256 prefix for change detection."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


class InstallGraph:
    """Canonical machine state snapshot."""

    def __init__(self, client, cache_dir: str | None = None):
        self._client = client
        self._snapshot: dict[str, Any] | None = None
        self._hashes: dict[str, str] = {}
        self._cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".comfypilot" / "cache"

    @property
    def snapshot(self) -> dict[str, Any] | None:
        return self._snapshot

    @property
    def hashes(self) -> dict[str, str]:
        return dict(self._hashes)

    async def refresh(self) -> dict[str, Any]:
        """Query ComfyUI and rebuild the snapshot."""
        client = self._client

        # System info
        stats = await client.get_system_stats()
        system = stats.get("system", {})
        devices = stats.get("devices", [])

        # Node catalog
        object_info = await client.get_object_info()
        node_classes = set(object_info.keys())
        categories = set()
        for info in object_info.values():
            cat = info.get("category", "")
            if cat:
                categories.add(cat)

        # Models per folder
        models: dict[str, list[str]] = {}
        for folder in MODEL_FOLDERS:
            try:
                models[folder] = await client.get_models(folder)
            except Exception:
                logger.debug("Skipping model folder %s (not available)", folder)

        # Features, extensions, embeddings
        try:
            features = await client.get_features()
        except Exception:
            features = []

        try:
            extensions = await client.get_extensions()
        except Exception:
            extensions = []

        try:
            embeddings = await client.get_embeddings()
        except Exception:
            embeddings = []

        # Build change detection hashes
        self._hashes = {
            "nodes": _hash(sorted(node_classes)),
            "models": _hash(models),
            "extensions": _hash(extensions),
            "embeddings": _hash(embeddings),
            "version": _hash(system.get("comfyui_version", "")),
        }

        self._snapshot = {
            "version": system.get("comfyui_version") or client.capabilities.get("version"),
            "profile": client.capabilities.get("profile", "unknown"),
            "python_version": system.get("python_version"),
            "pytorch_version": system.get("pytorch_version"),
            "os": system.get("os"),
            "gpu_devices": devices,
            "node_classes": node_classes,  # set for O(1) lookup
            "node_count": len(node_classes),
            "categories": sorted(categories),
            "object_info": object_info,
            "models": models,
            "features": features if features is not None else [],
            "extensions": extensions,
            "embeddings": embeddings,
            "refreshed_at": time.time(),
            "hashes": dict(self._hashes),
        }
        logger.info("Install graph refreshed: %d nodes, %d extensions, %d embeddings",
                     len(node_classes), len(extensions), len(embeddings))
        return self._snapshot

    def is_stale(self, max_age: float = 300) -> bool:
        """Check if the snapshot is missing or older than max_age seconds."""
        if not self._snapshot:
            return True
        age = time.time() - self._snapshot["refreshed_at"]
        return age >= max_age

    def summary(self) -> dict[str, Any]:
        """Return a compact summary of the install graph."""
        if not self._snapshot:
            return {"status": "not_refreshed"}
        s = self._snapshot
        return {
            "version": s["version"],
            "profile": s["profile"],
            "node_count": s["node_count"],
            "category_count": len(s["categories"]),
            "extension_count": len(s["extensions"]),
            "embedding_count": len(s["embeddings"]),
            "model_counts": {folder: len(files) for folder, files in s["models"].items()},
            "gpu_count": len(s["gpu_devices"]),
            "refreshed_at": s["refreshed_at"],
            "hashes": dict(self._hashes),
        }

    def has_node(self, node_type: str) -> bool:
        """Check if a node type is installed. O(1) set lookup."""
        if not self._snapshot:
            return False
        return node_type in self._snapshot["node_classes"]

    def get_node_schema(self, node_type: str) -> dict | None:
        """Get the object_info schema for a specific node type."""
        if not self._snapshot:
            return None
        return self._snapshot["object_info"].get(node_type)

    def find_models(self, query: str, folder: str | None = None) -> dict[str, list[str]]:
        """Search installed models by substring match."""
        if not self._snapshot:
            return {}
        q = query.lower()
        results = {}
        folders = [folder] if folder else self._snapshot["models"].keys()
        for f in folders:
            files = self._snapshot["models"].get(f, [])
            matches = [m for m in files if q in m.lower()]
            if matches:
                results[f] = matches
        return results

    # --- KnowledgeStore protocol methods ---

    def content_hash(self) -> str:
        """SHA-256 prefix of the combined hashes dict for change detection."""
        raw = json.dumps(self._hashes, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def clear(self) -> None:
        """Remove all cached data (in-memory and on disk)."""
        self._snapshot = None
        self._hashes = {}
        path = self._cache_dir / "install_graph.json"
        if path.exists():
            path.unlink()

    # --- Disk cache methods ---

    def save_to_disk(self) -> None:
        """Persist current snapshot to disk cache."""
        if not self._snapshot:
            return
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        # Convert set to sorted list for JSON serialization
        serializable = dict(self._snapshot)
        serializable["node_classes"] = sorted(serializable["node_classes"])
        path = self._cache_dir / "install_graph.json"
        from comfy_mcp.knowledge.store import atomic_write
        atomic_write(path, json.dumps(serializable, indent=2))

    def load_from_disk(self) -> bool:
        """Load snapshot from disk cache. Returns True if loaded successfully."""
        path = self._cache_dir / "install_graph.json"
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Restore node_classes as set
            data["node_classes"] = set(data.get("node_classes", []))
            self._snapshot = data
            self._hashes = data.get("hashes", {})
            return True
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            logger.warning("Failed to load install graph cache: %s", exc)
            return False

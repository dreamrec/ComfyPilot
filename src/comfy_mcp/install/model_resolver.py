"""ModelResolver — resolves model references against the install graph snapshot."""

from __future__ import annotations

from typing import Any


class ModelResolver:
    """Resolves model file references against installed models."""

    def __init__(self, snapshot: dict[str, Any]):
        self._models = snapshot.get("models", {})
        self._embeddings = snapshot.get("embeddings", [])

    def resolve(self, name: str, folder: str | None = None) -> dict[str, Any]:
        """Resolve a model reference.

        Args:
            name: Model filename or partial name to find
            folder: Specific folder to search. If None, searches all.

        Returns:
            Dict with found, exact, match/candidates, folder
        """
        folders = [folder] if folder else list(self._models.keys())
        name_lower = name.lower()

        for f in folders:
            files = self._models.get(f, [])
            # Exact match
            if name in files:
                return {"found": True, "exact": True, "match": name, "folder": f}
            # Substring match
            candidates = [m for m in files if name_lower in m.lower()]
            if candidates:
                return {"found": True, "exact": False, "candidates": candidates, "folder": f}

        return {"found": False, "name": name, "folder": folder}

    def resolve_embedding(self, name: str) -> dict[str, Any]:
        """Resolve an embedding reference."""
        if name in self._embeddings:
            return {"found": True, "exact": True, "match": name}
        candidates = [e for e in self._embeddings if name.lower() in e.lower()]
        if candidates:
            return {"found": True, "exact": False, "candidates": candidates}
        return {"found": False, "name": name}

    def resolve_all(self, refs: list[dict[str, str]]) -> dict[str, Any]:
        """Resolve a batch of model references.

        Args:
            refs: List of {"name": "...", "folder": "..."} dicts.

        Returns:
            Report with resolved/missing counts and details.
        """
        resolved_refs = []
        missing_refs = []
        for ref in refs:
            result = self.resolve(ref["name"], ref.get("folder"))
            if result["found"]:
                resolved_refs.append({**ref, **result})
            else:
                missing_refs.append(ref)
        return {
            "resolved": len(resolved_refs),
            "missing": len(missing_refs),
            "total": len(refs),
            "resolved_refs": resolved_refs,
            "missing_refs": missing_refs,
        }

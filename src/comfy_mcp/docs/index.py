"""DocsIndex — documentation lookup and search."""

from __future__ import annotations

from typing import Any

from comfy_mcp.docs.store import DocsStore


class DocsIndex:
    """Search and lookup interface for cached documentation."""

    def __init__(self, store: DocsStore, object_info: dict[str, Any] | None = None):
        self._store = store
        self._object_info = object_info or {}

    def get_node_doc(self, class_name: str) -> dict | None:
        embedded = self._store.get_embedded(class_name)
        schema = self._object_info.get(class_name)
        if embedded is None and schema is None:
            return None
        result: dict[str, Any] = {"class_name": class_name}
        if embedded is not None:
            result["description"] = embedded
        if schema is not None:
            result["schema"] = schema
        return result

    def search(self, query: str, limit: int = 10) -> list[dict]:
        query_lower = query.lower()
        results = []
        for class_name in self._store.list_embedded_classes():
            content = self._store.get_embedded(class_name)
            if content is None:
                continue
            if query_lower and query_lower not in content.lower():
                continue
            lines = content.strip().split("\n")
            snippet = lines[0] if lines else ""
            results.append({
                "class_name": class_name,
                "snippet": snippet[:200],
            })
        return results[:limit]

    def get_guide(self, topic: str) -> dict | None:
        return self._store.get_section(topic)

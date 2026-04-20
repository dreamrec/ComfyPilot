"""Thin HuggingFace model-search client.

Uses the public https://huggingface.co/api/models endpoint. No auth needed
for public model listings. Returns normalized hits: {id, name, url, downloads,
likes, last_modified, tags, library}.
"""
from __future__ import annotations

from typing import Any

import httpx


_HF_ENDPOINT = "https://huggingface.co/api/models"


async def search_huggingface(query: str, limit: int = 10, timeout: float = 10.0) -> list[dict[str, Any]]:
    """Search HuggingFace models by substring.

    Args:
        query: Free-text query matched against model id/name.
        limit: Max hits to return.
        timeout: HTTP timeout in seconds (short by default - discovery is interactive).
    """
    params: dict[str, str | int] = {
        "search": query,
        "limit": limit,
        "full": "1",  # includes tags, likes, downloads
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(_HF_ENDPOINT, params=params)
        resp.raise_for_status()
        raw = resp.json() or []

    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id") or item.get("modelId") or ""
        out.append({
            "source": "huggingface",
            "id": model_id,
            "name": model_id.rsplit("/", 1)[-1],
            "url": f"https://huggingface.co/{model_id}" if model_id else "",
            "downloads": item.get("downloads", 0),
            "likes": item.get("likes", 0),
            "last_modified": item.get("lastModified", ""),
            "tags": item.get("tags", []) or [],
            "library": item.get("library_name", ""),
        })
    return out

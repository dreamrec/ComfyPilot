"""Thin CivitAI model-search client.

Uses the public https://civitai.com/api/v1/models endpoint. Returns
normalized hits: {id, name, url, type, nsfw, downloads, rating, tags,
primary_file_name, sha256}.
"""
from __future__ import annotations

from typing import Any

import httpx


_CIVITAI_ENDPOINT = "https://civitai.com/api/v1/models"


async def search_civitai(query: str, limit: int = 10, timeout: float = 10.0) -> list[dict[str, Any]]:
    """Search CivitAI models by substring.

    Args:
        query: Free-text query matched against model name/description.
        limit: Max hits to return.
        timeout: HTTP timeout in seconds.
    """
    params: dict[str, str | int] = {
        "query": query,
        "limit": limit,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(_CIVITAI_ENDPOINT, params=params)
        resp.raise_for_status()
        body = resp.json() or {}

    items = body.get("items", []) if isinstance(body, dict) else []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        stats = item.get("stats", {}) or {}
        # Primary file info comes from the first modelVersion[0].files[0] entry
        primary_file = ""
        primary_sha256 = ""
        versions = item.get("modelVersions", []) or []
        if versions and isinstance(versions[0], dict):
            files = versions[0].get("files", []) or []
            if files and isinstance(files[0], dict):
                primary_file = files[0].get("name", "")
                hashes = files[0].get("hashes", {}) or {}
                primary_sha256 = hashes.get("SHA256", "") or ""
        out.append({
            "source": "civitai",
            "id": model_id,
            "name": item.get("name", ""),
            "url": f"https://civitai.com/models/{model_id}" if model_id else "",
            "type": item.get("type", ""),
            "nsfw": bool(item.get("nsfw", False)),
            "downloads": stats.get("downloadCount", 0),
            "rating": stats.get("rating", 0),
            "tags": item.get("tags", []) or [],
            "primary_file_name": primary_file,
            "sha256": primary_sha256,
        })
    return out

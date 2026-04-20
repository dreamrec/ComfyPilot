"""Hub search tool - 1 tool for HuggingFace + CivitAI model discovery."""
from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.hub import search_civitai, search_huggingface
from comfy_mcp.server import mcp


@mcp.tool(
    annotations={
        "title": "Search Model Hub",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def comfy_search_hub(
    query: str,
    source: str = "huggingface",
    limit: int = 10,
    ctx: Context = None,
) -> str:
    """Search a public model hub for models matching a query.

    Args:
        query: Free-text search, e.g. "flux2 klein" or "sdxl anime".
        source: "huggingface" or "civitai". Default huggingface.
        limit: Max results (1-50). Default 10.
    """
    source_norm = (source or "huggingface").strip().lower()
    if source_norm not in {"huggingface", "civitai"}:
        return json.dumps({
            "error": f"Unknown source {source!r}. Use 'huggingface' or 'civitai'.",
        })
    limit = max(1, min(int(limit), 50))

    try:
        if source_norm == "huggingface":
            hits = await search_huggingface(query, limit=limit)
        else:
            hits = await search_civitai(query, limit=limit)
    except Exception as e:
        return json.dumps({
            "error": f"{source_norm} search failed: {e}",
            "source": source_norm,
            "query": query,
        })

    return json.dumps({
        "source": source_norm,
        "query": query,
        "count": len(hits),
        "hits": hits,
    }, indent=2)

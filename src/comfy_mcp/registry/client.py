"""RegistryClient -- async HTTP client for the ComfyUI Registry API.

Base URL: https://api.comfy.org
All read endpoints are public (no auth required).
Includes rate limiting, retry logic, and User-Agent header.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from urllib.parse import quote

logger = logging.getLogger("comfypilot.registry")

BASE_URL = "https://api.comfy.org"
USER_AGENT = "ComfyPilot/0.7.1"
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 30.0
REQUEST_THROTTLE = 0.1  # minimum seconds between requests


class RegistryClient:
    """Async HTTP client for the ComfyUI Registry."""

    def __init__(self, base_url: str = BASE_URL, timeout: float = 30.0):
        self._base = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )
        self._last_request_time = 0.0

    async def _throttle(self) -> None:
        """Enforce minimum delay between requests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < REQUEST_THROTTLE:
            await asyncio.sleep(REQUEST_THROTTLE - elapsed)
        self._last_request_time = time.time()

    async def _throttled_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """HTTP request with rate limiting and retry."""
        last_response = None
        for attempt in range(MAX_RETRIES):
            await self._throttle()
            try:
                response = await self._http.request(method, url, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    try:
                        retry_after = float(response.headers.get("Retry-After", INITIAL_BACKOFF * (2 ** attempt)))
                    except (ValueError, TypeError):
                        retry_after = INITIAL_BACKOFF * (2 ** attempt)
                    wait = min(retry_after, MAX_BACKOFF)
                    logger.debug("Rate limited or server error (%d), retrying in %.1fs", response.status_code, wait)
                    await asyncio.sleep(wait)
                    last_response = response
                    continue
                return response
            except httpx.HTTPError as exc:
                if attempt < MAX_RETRIES - 1:
                    wait = min(INITIAL_BACKOFF * (2 ** attempt), MAX_BACKOFF)
                    logger.debug("Request failed (%s), retrying in %.1fs", exc, wait)
                    await asyncio.sleep(wait)
                else:
                    raise
        # All retries exhausted — return last error response instead of unprotected request
        return last_response

    async def _throttled_get(self, url: str, params: dict | None = None) -> httpx.Response:
        """GET with rate limiting and retry."""
        return await self._throttled_request("GET", url, params=params)

    async def search_nodes(self, query: str, page: int = 1, limit: int = 10, **filters) -> dict[str, Any]:
        """Search registry packages."""
        params = {"page": page, "limit": limit}
        if query:
            # The API uses node_id filter or general search
            params["node_id"] = query
        params.update(filters)
        try:
            response = await self._throttled_get(f"{self._base}/nodes", params=params)
            if response.status_code == 200:
                return response.json()
            return {"nodes": [], "total": 0, "page": page}
        except Exception as exc:
            logger.debug("search_nodes failed: %s", exc)
            return {"nodes": [], "total": 0, "page": page}

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Get full package metadata by ID."""
        try:
            response = await self._throttled_get(f"{self._base}/nodes/{quote(node_id, safe='')}")
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as exc:
            logger.debug("get_node failed for %s: %s", node_id, exc)
            return None

    async def get_versions(self, node_id: str) -> list[dict[str, Any]]:
        """List all versions of a package."""
        try:
            response = await self._throttled_get(f"{self._base}/nodes/{quote(node_id, safe='')}/versions")
            if response.status_code == 200:
                return response.json()
            return []
        except Exception:
            return []

    async def get_comfy_nodes(self, node_id: str, version: str) -> list[dict[str, Any]]:
        """List all node classes in a specific package version."""
        try:
            response = await self._throttled_get(f"{self._base}/nodes/{quote(node_id, safe='')}/versions/{quote(version, safe='')}/comfy-nodes")
            if response.status_code == 200:
                return response.json()
            return []
        except Exception:
            return []

    async def reverse_lookup(self, class_name: str) -> dict[str, Any] | None:
        """Map a node class name back to its registry package."""
        try:
            response = await self._throttled_get(f"{self._base}/comfy-nodes/{quote(class_name, safe='')}/node")
            if response.status_code == 200:
                return response.json()
            if response.status_code in (404, 410):
                return None
            return None
        except Exception as exc:
            logger.debug("reverse_lookup failed for %s: %s", class_name, exc)
            return None

    async def bulk_resolve(self, pairs: list[dict[str, str]]) -> dict[str, Any]:
        """Batch resolve multiple node class lookups."""
        try:
            response = await self._throttled_request(
                "POST",
                f"{self._base}/bulk/nodes/versions",
                json=pairs,
            )
            if response and response.status_code == 200:
                return response.json()
            return {}
        except Exception:
            return {}

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()

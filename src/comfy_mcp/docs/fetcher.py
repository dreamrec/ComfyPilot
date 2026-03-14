"""DocsFetcher — HTTP fetch for ComfyUI documentation sources."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("comfypilot.docs")

DEFAULT_EMBEDDED_BASE = "https://raw.githubusercontent.com/Comfy-Org/embedded-docs/main/docs"
DEFAULT_LLMS_URL = "https://docs.comfy.org/llms-full.txt"


class DocsFetcher:
    """Fetches documentation from remote sources with graceful degradation."""

    def __init__(
        self,
        embedded_base_url: str = DEFAULT_EMBEDDED_BASE,
        llms_url: str = DEFAULT_LLMS_URL,
        timeout: float = 30.0,
    ):
        self._embedded_base = embedded_base_url.rstrip("/")
        self._llms_url = llms_url
        self._client = httpx.AsyncClient(timeout=timeout)

    async def fetch_embedded_doc(self, class_name: str) -> str | None:
        url = f"{self._embedded_base}/{class_name}.md"
        try:
            response = await self._client.get(url)
            if response.status_code == 200:
                return response.text
            logger.debug("Embedded doc fetch %s returned %d", class_name, response.status_code)
            return None
        except Exception as exc:
            logger.debug("Embedded doc fetch failed for %s: %s", class_name, exc)
            return None

    async def fetch_llms_full(self) -> str | None:
        try:
            response = await self._client.get(self._llms_url)
            if response.status_code == 200:
                return response.text
            logger.debug("llms-full.txt fetch returned %d", response.status_code)
            return None
        except Exception as exc:
            logger.debug("llms-full.txt fetch failed: %s", exc)
            return None

    async def close(self) -> None:
        await self._client.aclose()

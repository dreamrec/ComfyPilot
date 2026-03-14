"""Tests for DocsFetcher — HTTP fetch with graceful degradation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestFetchEmbeddedDoc:
    @pytest.mark.asyncio
    async def test_fetch_returns_content_on_success(self):
        from comfy_mcp.docs.fetcher import DocsFetcher
        fetcher = DocsFetcher()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# KSampler\nSamples latents."
        with patch.object(fetcher, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            result = await fetcher.fetch_embedded_doc("KSampler")
            assert result == "# KSampler\nSamples latents."

    @pytest.mark.asyncio
    async def test_fetch_returns_none_on_404(self):
        from comfy_mcp.docs.fetcher import DocsFetcher
        fetcher = DocsFetcher()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        with patch.object(fetcher, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            result = await fetcher.fetch_embedded_doc("FakeNode")
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_returns_none_on_network_error(self):
        from comfy_mcp.docs.fetcher import DocsFetcher
        import httpx
        fetcher = DocsFetcher()
        with patch.object(fetcher, "_client") as mock_client:
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("offline"))
            result = await fetcher.fetch_embedded_doc("KSampler")
            assert result is None


class TestFetchLlmsFull:
    @pytest.mark.asyncio
    async def test_fetch_llms_returns_content(self):
        from comfy_mcp.docs.fetcher import DocsFetcher
        fetcher = DocsFetcher()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# Full Docs\nContent here."
        with patch.object(fetcher, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            result = await fetcher.fetch_llms_full()
            assert result == "# Full Docs\nContent here."

    @pytest.mark.asyncio
    async def test_fetch_llms_returns_none_on_error(self):
        from comfy_mcp.docs.fetcher import DocsFetcher
        import httpx
        fetcher = DocsFetcher()
        with patch.object(fetcher, "_client") as mock_client:
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("offline"))
            result = await fetcher.fetch_llms_full()
            assert result is None


class TestFetcherClose:
    @pytest.mark.asyncio
    async def test_close_is_safe_to_call(self):
        from comfy_mcp.docs.fetcher import DocsFetcher
        fetcher = DocsFetcher()
        await fetcher.close()  # should not raise

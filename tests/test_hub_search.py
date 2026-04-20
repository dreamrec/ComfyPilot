"""Tests for HuggingFace + CivitAI hub search."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comfy_mcp.hub.civitai import search_civitai
from comfy_mcp.hub.huggingface import search_huggingface
from comfy_mcp.tools.hub import comfy_search_hub


class TestHuggingFace:
    @pytest.mark.asyncio
    async def test_normalizes_hf_response(self):
        raw = [
            {
                "id": "black-forest-labs/FLUX.2-klein",
                "downloads": 12345,
                "likes": 42,
                "lastModified": "2026-04-01",
                "tags": ["diffusers", "flux"],
                "library_name": "diffusers",
            },
        ]
        mock_client = MagicMock()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=raw)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("comfy_mcp.hub.huggingface.httpx.AsyncClient", return_value=mock_client):
            hits = await search_huggingface("flux2", limit=5)

        assert len(hits) == 1
        assert hits[0]["source"] == "huggingface"
        assert hits[0]["name"] == "FLUX.2-klein"
        assert hits[0]["url"] == "https://huggingface.co/black-forest-labs/FLUX.2-klein"
        assert hits[0]["downloads"] == 12345

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty(self):
        mock_client = MagicMock()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=[])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("comfy_mcp.hub.huggingface.httpx.AsyncClient", return_value=mock_client):
            hits = await search_huggingface("nonexistent", limit=10)
        assert hits == []


class TestCivitAI:
    @pytest.mark.asyncio
    async def test_normalizes_civitai_response(self):
        raw = {
            "items": [
                {
                    "id": 12345,
                    "name": "Anime Style SDXL",
                    "type": "Checkpoint",
                    "nsfw": False,
                    "stats": {"downloadCount": 1000, "rating": 4.5},
                    "tags": ["anime", "sdxl"],
                    "modelVersions": [
                        {
                            "files": [
                                {
                                    "name": "anime-sdxl.safetensors",
                                    "hashes": {"SHA256": "abc123"},
                                },
                            ],
                        },
                    ],
                },
            ],
        }
        mock_client = MagicMock()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=raw)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("comfy_mcp.hub.civitai.httpx.AsyncClient", return_value=mock_client):
            hits = await search_civitai("anime sdxl", limit=5)

        assert len(hits) == 1
        h = hits[0]
        assert h["source"] == "civitai"
        assert h["id"] == 12345
        assert h["name"] == "Anime Style SDXL"
        assert h["url"] == "https://civitai.com/models/12345"
        assert h["primary_file_name"] == "anime-sdxl.safetensors"
        assert h["sha256"] == "abc123"
        assert h["downloads"] == 1000


class TestHubTool:
    @pytest.mark.asyncio
    async def test_default_source_is_huggingface(self):
        with patch("comfy_mcp.tools.hub.search_huggingface", AsyncMock(return_value=[])) as mock_hf:
            result = json.loads(await comfy_search_hub(query="flux"))
        assert result["source"] == "huggingface"
        assert result["count"] == 0
        mock_hf.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_explicit_civitai_source(self):
        with patch("comfy_mcp.tools.hub.search_civitai", AsyncMock(return_value=[])) as mock_cv:
            result = json.loads(await comfy_search_hub(query="anime", source="civitai"))
        assert result["source"] == "civitai"
        mock_cv.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_source_returns_error(self):
        result = json.loads(await comfy_search_hub(query="x", source="wikipedia"))
        assert "error" in result

    @pytest.mark.asyncio
    async def test_limit_clamped(self):
        with patch("comfy_mcp.tools.hub.search_huggingface", AsyncMock(return_value=[])) as mock_hf:
            await comfy_search_hub(query="x", limit=999)
        call_kwargs = mock_hf.call_args.kwargs
        assert call_kwargs["limit"] == 50

    @pytest.mark.asyncio
    async def test_http_failure_returns_error(self):
        with patch("comfy_mcp.tools.hub.search_huggingface",
                   AsyncMock(side_effect=Exception("rate limited"))):
            result = json.loads(await comfy_search_hub(query="x"))
        assert "error" in result
        assert "rate limited" in result["error"]

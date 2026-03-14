"""Tests for RegistryClient -- async HTTP client for api.comfy.org."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSearchNodes:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        from comfy_mcp.registry.client import RegistryClient
        client = RegistryClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={
            "nodes": [{"id": "comfyui-animatediff", "name": "AnimateDiff Evolved"}],
            "total": 1, "page": 1, "totalPages": 1,
        })
        with patch.object(client, "_http", AsyncMock()) as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)
            result = await client.search_nodes("animatediff")
            assert len(result["nodes"]) == 1

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self):
        from comfy_mcp.registry.client import RegistryClient
        import httpx
        client = RegistryClient()
        with patch.object(client, "_http", AsyncMock()) as mock_http:
            mock_http.get = AsyncMock(side_effect=httpx.ConnectError("offline"))
            result = await client.search_nodes("test")
            assert result["nodes"] == []


class TestReverseLookup:
    @pytest.mark.asyncio
    async def test_returns_package_info(self):
        from comfy_mcp.registry.client import RegistryClient
        client = RegistryClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={
            "comfy_node_name": "ADE_AnimateDiffLoaderWithContext",
            "node": {"id": "comfyui-animatediff-evolved", "name": "AnimateDiff Evolved"},
        })
        with patch.object(client, "_http", AsyncMock()) as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)
            result = await client.reverse_lookup("ADE_AnimateDiffLoaderWithContext")
            assert result is not None
            assert result["node"]["id"] == "comfyui-animatediff-evolved"

    @pytest.mark.asyncio
    async def test_returns_none_on_404(self):
        from comfy_mcp.registry.client import RegistryClient
        client = RegistryClient()
        mock_response = MagicMock()
        mock_response.status_code = 404
        with patch.object(client, "_http", AsyncMock()) as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)
            result = await client.reverse_lookup("FakeNode")
            assert result is None


class TestGetNode:
    @pytest.mark.asyncio
    async def test_returns_node_details(self):
        from comfy_mcp.registry.client import RegistryClient
        client = RegistryClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={
            "id": "comfyui-animatediff", "name": "AnimateDiff", "description": "Motion",
            "latest_version": {"version": "1.2.3"},
        })
        with patch.object(client, "_http", AsyncMock()) as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)
            result = await client.get_node("comfyui-animatediff")
            assert result["id"] == "comfyui-animatediff"


class TestClose:
    @pytest.mark.asyncio
    async def test_close_is_safe(self):
        from comfy_mcp.registry.client import RegistryClient
        client = RegistryClient()
        await client.close()

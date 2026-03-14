"""Tests for TemplateDiscovery -- fetching template sources."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_comfy_client():
    client = AsyncMock()
    client.base_url = "http://localhost:8188"
    # Official templates endpoint
    client.get = AsyncMock()
    return client


class TestDiscoverOfficial:
    @pytest.mark.asyncio
    async def test_discovers_official_templates(self, mock_comfy_client):
        from comfy_mcp.templates.discovery import TemplateDiscovery
        index_data = [
            {"name": "txt2img_basic", "category": "text-to-image", "description": "Basic txt2img", "file": "txt2img_basic.json"},
            {"name": "img2img_simple", "category": "image-to-image", "description": "Simple img2img", "file": "img2img_simple.json"},
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=index_data)
        mock_comfy_client.get = AsyncMock(return_value=mock_response)

        discovery = TemplateDiscovery(mock_comfy_client)
        templates = await discovery.discover_official()
        assert len(templates) == 2
        assert templates[0]["name"] == "txt2img_basic"
        assert templates[0]["source"] == "official"

    @pytest.mark.asyncio
    async def test_returns_empty_on_failure(self, mock_comfy_client):
        from comfy_mcp.templates.discovery import TemplateDiscovery
        mock_comfy_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        discovery = TemplateDiscovery(mock_comfy_client)
        templates = await discovery.discover_official()
        assert templates == []


class TestDiscoverCustomNode:
    @pytest.mark.asyncio
    async def test_discovers_custom_node_templates(self, mock_comfy_client):
        from comfy_mcp.templates.discovery import TemplateDiscovery
        wf_data = [
            {"name": "animatediff_example", "node_pack": "comfyui-animatediff", "file": "example.json"},
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=wf_data)
        mock_comfy_client.get = AsyncMock(return_value=mock_response)

        discovery = TemplateDiscovery(mock_comfy_client)
        templates = await discovery.discover_custom_node()
        assert len(templates) == 1
        assert templates[0]["source"] == "custom_node"


class TestDiscoverOfficialDictReturn:
    @pytest.mark.asyncio
    async def test_handles_dict_returning_client(self, mock_comfy_client):
        """ComfyClient.get() may return a dict/list directly instead of a response object."""
        from comfy_mcp.templates.discovery import TemplateDiscovery
        index_data = [
            {"name": "txt2img_basic", "category": "text-to-image", "description": "Basic txt2img", "file": "txt2img_basic.json"},
        ]
        mock_comfy_client.get = AsyncMock(return_value=index_data)
        discovery = TemplateDiscovery(mock_comfy_client)
        templates = await discovery.discover_official()
        assert len(templates) == 1
        assert templates[0]["source"] == "official"


class TestDiscoverBuiltin:
    def test_builtin_templates_always_available(self):
        from comfy_mcp.templates.discovery import TemplateDiscovery
        discovery = TemplateDiscovery(None)
        templates = discovery.discover_builtin()
        assert len(templates) >= 1
        assert all(t["source"] == "builtin" for t in templates)

    def test_builtin_templates_have_workflow(self):
        from comfy_mcp.templates.discovery import TemplateDiscovery
        discovery = TemplateDiscovery(None)
        templates = discovery.discover_builtin()
        assert all("workflow" in t for t in templates)


class TestDiscoverAll:
    @pytest.mark.asyncio
    async def test_discover_all_combines_sources(self, mock_comfy_client):
        from comfy_mcp.templates.discovery import TemplateDiscovery
        mock_comfy_client.get = AsyncMock(side_effect=Exception("offline"))
        discovery = TemplateDiscovery(mock_comfy_client)
        templates = await discovery.discover_all()
        # Should at least have builtins
        assert len(templates) >= 1

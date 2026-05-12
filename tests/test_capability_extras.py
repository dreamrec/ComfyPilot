"""Tests for v1.7.0 capability extras: frontend_version + cache_provider + openapi_version."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from comfy_mcp.comfy_client import ComfyClient


@pytest.mark.asyncio
async def test_frontend_version_surfaced():
    """ComfyUI v0.3.46+ exposes comfyui_frontend_version in system_stats."""
    client = ComfyClient("http://localhost:8188")

    async def get_side_effect(path: str):
        if "system_stats" in path:
            return {
                "system": {
                    "comfyui_version": "0.20.1",
                    "comfyui_frontend_version": "1.42.15",
                },
            }
        if "openapi" in path:
            raise Exception("404")
        if path.endswith("/features"):
            return {}
        return {}

    with patch.object(client, "get", new_callable=AsyncMock) as mock_get, \
         patch.object(client, "_probe_ws_available", new_callable=AsyncMock) as ws:
        mock_get.side_effect = get_side_effect
        ws.return_value = True
        await client.connect()
        await client.probe_capabilities()
        assert client.capabilities["frontend_version"] == "1.42.15"
    await client.close()


@pytest.mark.asyncio
async def test_cache_provider_surfaced_from_features_string():
    """When /features returns cache_provider as a string, capture it directly."""
    client = ComfyClient("http://localhost:8188")

    async def get_side_effect(path: str):
        if "system_stats" in path:
            return {"system": {"comfyui_version": "0.20.0"}}
        if path.endswith("/features"):
            return {"cache_provider": "redis"}
        if "openapi" in path:
            raise Exception("404")
        return {}

    with patch.object(client, "get", new_callable=AsyncMock) as mock_get, \
         patch.object(client, "_probe_ws_available", new_callable=AsyncMock) as ws:
        mock_get.side_effect = get_side_effect
        ws.return_value = True
        await client.connect()
        await client.probe_capabilities()
        assert client.capabilities["cache_provider"] == "redis"
    await client.close()


@pytest.mark.asyncio
async def test_cache_provider_surfaced_from_features_dict():
    """When /features returns cache as a dict, extract the provider name."""
    client = ComfyClient("http://localhost:8188")

    async def get_side_effect(path: str):
        if "system_stats" in path:
            return {"system": {"comfyui_version": "0.20.0"}}
        if path.endswith("/features"):
            return {"cache": {"provider": "memcached", "ttl": 300}}
        if "openapi" in path:
            raise Exception("404")
        return {}

    with patch.object(client, "get", new_callable=AsyncMock) as mock_get, \
         patch.object(client, "_probe_ws_available", new_callable=AsyncMock) as ws:
        mock_get.side_effect = get_side_effect
        ws.return_value = True
        await client.connect()
        await client.probe_capabilities()
        assert client.capabilities["cache_provider"] == "memcached"
    await client.close()


@pytest.mark.asyncio
async def test_cache_provider_none_when_absent():
    """Older ComfyUI builds without CacheProvider API report None."""
    client = ComfyClient("http://localhost:8188")

    async def get_side_effect(path: str):
        if "system_stats" in path:
            return {"system": {"comfyui_version": "0.17.0"}}
        if path.endswith("/features"):
            return {}
        if "openapi" in path:
            raise Exception("404")
        return {}

    with patch.object(client, "get", new_callable=AsyncMock) as mock_get, \
         patch.object(client, "_probe_ws_available", new_callable=AsyncMock) as ws:
        mock_get.side_effect = get_side_effect
        ws.return_value = True
        await client.connect()
        await client.probe_capabilities()
        assert client.capabilities["cache_provider"] is None
    await client.close()

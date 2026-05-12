"""Tests for OpenAPI 3.1 spec ingestion (ComfyUI v0.20.0+)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from comfy_mcp.comfy_client import ComfyClient


@pytest.mark.asyncio
async def test_get_openapi_spec_returns_dict_on_success():
    client = ComfyClient("http://localhost:8188")
    fake_spec = {
        "openapi": "3.1.0",
        "info": {"title": "ComfyUI API", "version": "0.20.0"},
        "paths": {"/prompt": {"post": {}}},
    }
    with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = fake_spec
        await client.connect()
        spec = await client.get_openapi_spec()
        assert spec == fake_spec
    await client.close()


@pytest.mark.asyncio
async def test_get_openapi_spec_returns_none_when_unavailable():
    """When ComfyUI returns 404 on both /openapi.json and /openapi, get None."""
    client = ComfyClient("http://localhost:8188")
    with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("404")
        await client.connect()
        spec = await client.get_openapi_spec()
        assert spec is None
    await client.close()


@pytest.mark.asyncio
async def test_probe_capabilities_records_openapi_version():
    """When the spec is fetchable, capabilities should expose openapi_version."""
    client = ComfyClient("http://localhost:8188")
    fake_spec = {"openapi": "3.1.0", "info": {"title": "ComfyUI", "version": "0.20.1"}}

    async def get_side_effect(path: str):
        if "openapi" in path:
            return fake_spec
        if "system_stats" in path:
            return {"system": {"comfyui_version": "0.20.1"}}
        if path.endswith("/features"):
            return {}
        return {}

    with patch.object(client, "get", new_callable=AsyncMock) as mock_get, \
         patch.object(client, "_probe_ws_available", new_callable=AsyncMock) as ws:
        mock_get.side_effect = get_side_effect
        ws.return_value = True
        await client.connect()
        await client.probe_capabilities()
        assert client.capabilities["openapi_version"] == "3.1.0"
    await client.close()


@pytest.mark.asyncio
async def test_probe_capabilities_sets_openapi_version_none_when_absent():
    """When /openapi.json 404s, openapi_version is None."""
    client = ComfyClient("http://localhost:8188")

    async def get_side_effect(path: str):
        if "openapi" in path:
            raise Exception("404")
        if "system_stats" in path:
            return {"system": {"comfyui_version": "0.17.0"}}
        if path.endswith("/features"):
            return {}
        return {}

    with patch.object(client, "get", new_callable=AsyncMock) as mock_get, \
         patch.object(client, "_probe_ws_available", new_callable=AsyncMock) as ws:
        mock_get.side_effect = get_side_effect
        ws.return_value = True
        await client.connect()
        await client.probe_capabilities()
        assert client.capabilities["openapi_version"] is None
    await client.close()

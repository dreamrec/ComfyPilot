"""Test capability probing during connect."""
import pytest
from unittest.mock import AsyncMock, patch

from comfy_mcp.comfy_client import ComfyClient


@pytest.mark.asyncio
async def test_probe_detects_local_profile():
    """Client should detect local ComfyUI profile on connect."""
    client = ComfyClient("http://localhost:8188")
    with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"system": {"comfyui_version": "0.17.1"}}
        await client.connect()
        await client.probe_capabilities()
        assert client.capabilities["profile"] == "local"
        assert client.capabilities["version"] is not None
    await client.close()


@pytest.mark.asyncio
async def test_probe_detects_ws_availability():
    client = ComfyClient("http://localhost:8188")
    with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"system": {"comfyui_version": "0.17.0"}}
        await client.connect()
        await client.probe_capabilities()
        assert "ws_available" in client.capabilities
    await client.close()

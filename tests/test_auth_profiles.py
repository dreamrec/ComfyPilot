"""Test auth header selection."""
import pytest
from comfy_mcp.comfy_client import ComfyClient


@pytest.mark.asyncio
async def test_bearer_auth_for_local():
    client = ComfyClient("http://localhost:8188", api_key="my-key", auth_method="bearer")
    await client.connect()
    assert client._http.headers.get("Authorization") == "Bearer my-key"
    await client.close()


@pytest.mark.asyncio
async def test_api_key_auth_for_cloud():
    client = ComfyClient("https://api.comfy.org", api_key="my-key", auth_method="x-api-key")
    await client.connect()
    assert client._http.headers.get("X-API-Key") == "my-key"
    assert "Authorization" not in client._http.headers
    await client.close()


@pytest.mark.asyncio
async def test_auto_auth_detection():
    """If auth_method='auto', detect from URL."""
    client = ComfyClient("https://api.comfy.org", api_key="key", auth_method="auto")
    await client.connect()
    assert client._http.headers.get("X-API-Key") == "key"
    await client.close()


@pytest.mark.asyncio
async def test_auto_auth_detection_for_cloud_host():
    client = ComfyClient("https://cloud.comfy.org", api_key="key", auth_method="auto")
    await client.connect()
    assert client._http.headers.get("X-API-Key") == "key"
    await client.close()

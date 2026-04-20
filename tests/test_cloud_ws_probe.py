"""Tests for cloud-mode WebSocket reachability probing."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comfy_mcp.comfy_client import ComfyClient


@pytest.fixture
def client():
    c = ComfyClient("http://127.0.0.1:8188")
    # Seed HTTP mock for probe_capabilities
    c._http = MagicMock()
    resp = MagicMock(is_success=True, status_code=200)
    resp.json = MagicMock(return_value={"system": {"comfyui_version": "0.19.3"}})
    c._http.get = AsyncMock(return_value=resp)
    return c


@pytest.mark.asyncio
async def test_ws_available_when_probe_succeeds(client):
    """ws_available flips True when the WS handshake succeeds."""
    fake_ws = MagicMock()
    fake_ws.close = AsyncMock()

    async def fake_connect_coro(*args, **kwargs):
        return fake_ws

    # websockets.connect returns an awaitable; mock it at the module level
    with patch("websockets.connect", return_value=fake_connect_coro()):
        caps = await client.probe_capabilities()
    assert caps["ws_available"] is True


@pytest.mark.asyncio
async def test_ws_unavailable_when_probe_fails(client):
    """ws_available stays False when the WS handshake errors."""
    async def fake_connect_coro(*args, **kwargs):
        raise ConnectionRefusedError("offline")

    with patch("websockets.connect", return_value=fake_connect_coro()):
        caps = await client.probe_capabilities()
    assert caps["ws_available"] is False


@pytest.mark.asyncio
async def test_ws_probe_respects_timeout(client):
    """A hung handshake times out and reports False."""
    import asyncio as _asyncio

    async def never_completes(*args, **kwargs):
        await _asyncio.sleep(60)

    with patch("websockets.connect", return_value=never_completes()):
        caps = await client.probe_capabilities()
    assert caps["ws_available"] is False


@pytest.mark.asyncio
async def test_capability_preserves_dict_features(client):
    """Modern ComfyUI returns `/features` as a dict of flags (not a list).
    The capability snapshot must preserve that shape."""
    resp = MagicMock(is_success=True, status_code=200)
    resp.json = MagicMock(side_effect=[
        {"system": {"comfyui_version": "0.19.3"}},        # /system_stats
        {"progress_text": "binary", "preview": True},      # /features dict
    ])
    client._http.get = AsyncMock(return_value=resp)

    fake_ws = MagicMock()
    fake_ws.close = AsyncMock()
    async def fake_connect(*args, **kwargs):
        return fake_ws
    with patch("websockets.connect", return_value=fake_connect()):
        caps = await client.probe_capabilities()

    assert caps["features"] == {"progress_text": "binary", "preview": True}


@pytest.mark.asyncio
async def test_capability_resolves_auth_method_for_local_bearer():
    """When api_key is set and auth_method='auto' on a local URL, the
    snapshot must report 'bearer' (the resolved choice) not 'auto'."""
    c = ComfyClient("http://127.0.0.1:8188", api_key="sk-local", auth_method="auto")
    c._http = MagicMock()
    resp = MagicMock(is_success=True, status_code=200)
    resp.json = MagicMock(return_value={"system": {"comfyui_version": "0.19.3"}})
    c._http.get = AsyncMock(return_value=resp)

    async def fake_connect(*args, **kwargs):
        raise ConnectionRefusedError("offline")
    with patch("websockets.connect", return_value=fake_connect()):
        caps = await c.probe_capabilities()

    assert caps["auth_method"] == "bearer"


@pytest.mark.asyncio
async def test_capability_resolves_auth_method_for_cloud_x_api_key():
    c = ComfyClient("https://cloud.comfy.org", api_key="sk-cloud", auth_method="auto")
    c._http = MagicMock()
    resp = MagicMock(is_success=True, status_code=200)
    resp.json = MagicMock(return_value={"system": {"comfyui_version": "0.19.3"}})
    c._http.get = AsyncMock(return_value=resp)

    async def fake_connect(*args, **kwargs):
        raise ConnectionRefusedError("offline")
    with patch("websockets.connect", return_value=fake_connect()):
        caps = await c.probe_capabilities()

    assert caps["auth_method"] == "x-api-key"


@pytest.mark.asyncio
async def test_capability_auth_method_none_when_no_api_key():
    c = ComfyClient("http://127.0.0.1:8188")  # no api_key
    c._http = MagicMock()
    resp = MagicMock(is_success=True, status_code=200)
    resp.json = MagicMock(return_value={"system": {"comfyui_version": "0.19.3"}})
    c._http.get = AsyncMock(return_value=resp)

    async def fake_connect(*args, **kwargs):
        raise ConnectionRefusedError("offline")
    with patch("websockets.connect", return_value=fake_connect()):
        caps = await c.probe_capabilities()

    assert caps["auth_method"] == "none"


@pytest.mark.asyncio
async def test_ws_url_uses_wss_for_https_base():
    """Cloud (https://...) base must derive a wss:// URL for the probe."""
    c = ComfyClient("https://cloud.comfy.org", api_key="sk-test")
    c._http = MagicMock()
    resp = MagicMock(is_success=True, status_code=200)
    resp.json = MagicMock(return_value={"system": {"comfyui_version": "0.19.3"}})
    c._http.get = AsyncMock(return_value=resp)

    fake_ws = MagicMock()
    fake_ws.close = AsyncMock()

    captured_url = {}

    async def fake_connect(url, **kwargs):
        captured_url["url"] = url
        captured_url["headers"] = kwargs.get("additional_headers")
        return fake_ws

    with patch("websockets.connect", side_effect=fake_connect):
        await c.probe_capabilities()
    assert captured_url["url"].startswith("wss://cloud.comfy.org/ws?clientId=")
    # Auth headers flow through to the WS probe
    assert captured_url["headers"] == {"X-API-Key": "sk-test"}

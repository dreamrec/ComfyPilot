"""Tests for cloud-tier detection in capabilities probe."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from comfy_mcp.comfy_client import ComfyClient


def _make_get_handler(routes):
    """Build a get-side-effect that returns / raises per path prefix."""
    async def handler(path):
        for prefix, resp in routes.items():
            if path.startswith(prefix):
                if isinstance(resp, Exception):
                    raise resp
                return resp
        return {}
    return handler


@pytest.mark.asyncio
async def test_local_profile_has_tier_none():
    client = ComfyClient("http://127.0.0.1:8188")
    routes = {
        "/system_stats": {"system": {"comfyui_version": "0.20.1"}},
        "/features": {},
    }
    with patch.object(client, "get", new=_make_get_handler(routes)), \
         patch.object(client, "_probe_ws_available", new_callable=AsyncMock) as ws:
        ws.return_value = True
        await client.connect()
        await client.probe_capabilities()
        assert client.capabilities["profile"] == "local"
        assert client.capabilities["tier"] is None
    await client.close()


@pytest.mark.asyncio
async def test_cloud_tier_from_user_endpoint():
    client = ComfyClient("https://cloud.comfy.org", api_key="ck-test")
    routes = {
        "/system_stats": Exception("404"),
        "/api/system_stats": {"system": {"comfyui_version": "0.20.1"}},
        "/features": Exception("404"),
        "/api/features": {},
        "/api/user": {"tier": "creator", "email": "x@y.z"},
    }
    with patch.object(client, "get", new=_make_get_handler(routes)), \
         patch.object(client, "_probe_ws_available", new_callable=AsyncMock) as ws:
        ws.return_value = True
        await client.connect()
        await client.probe_capabilities()
        assert client.capabilities["profile"] == "cloud"
        assert client.capabilities["tier"] == "creator"
    await client.close()


@pytest.mark.asyncio
async def test_cloud_tier_nested_subscription_object():
    client = ComfyClient("https://cloud.comfy.org", api_key="ck-test")
    routes = {
        "/system_stats": Exception("404"),
        "/api/system_stats": {"system": {"comfyui_version": "0.20.1"}},
        "/features": Exception("404"),
        "/api/features": {},
        "/api/user": {"subscription": {"name": "Pro"}},
    }
    with patch.object(client, "get", new=_make_get_handler(routes)), \
         patch.object(client, "_probe_ws_available", new_callable=AsyncMock) as ws:
        ws.return_value = True
        await client.connect()
        await client.probe_capabilities()
        assert client.capabilities["tier"] == "pro"
    await client.close()


@pytest.mark.asyncio
async def test_cloud_tier_falls_back_to_object_info_probe():
    """No user endpoint: infer from /api/object_info 200 == paid."""
    client = ComfyClient("https://cloud.comfy.org", api_key="ck-test")
    routes = {
        "/system_stats": Exception("404"),
        "/api/system_stats": {"system": {"comfyui_version": "0.20.1"}},
        "/features": Exception("404"),
        "/api/features": {},
        "/api/user": Exception("404"),
        "/user": Exception("404"),
        "/api/account": Exception("404"),
        "/api/me": Exception("404"),
        "/api/object_info": {"KSampler": {}},  # paid-tier success
    }
    with patch.object(client, "get", new=_make_get_handler(routes)), \
         patch.object(client, "_probe_ws_available", new_callable=AsyncMock) as ws:
        ws.return_value = True
        await client.connect()
        await client.probe_capabilities()
        assert client.capabilities["tier"] == "paid"
    await client.close()


@pytest.mark.asyncio
async def test_cloud_tier_403_classified_as_free():
    """A typed HTTP_403 from /api/object_info classifies the tier as free.

    Note (v1.8.0 audit-driven tightening): only error_code == 'HTTP_403'
    counts as 'free' now. Generic exceptions (network errors, 404s) return
    None / unknown so transient blips don't silently downgrade paid users.
    """
    from comfy_mcp.errors import ComfyAPIError

    client = ComfyClient("https://cloud.comfy.org", api_key="ck-test")
    routes = {
        "/system_stats": Exception("404"),
        "/api/system_stats": {"system": {"comfyui_version": "0.20.1"}},
        "/features": Exception("404"),
        "/api/features": {},
        "/api/user": Exception("404"),
        "/user": Exception("404"),
        "/api/account": Exception("404"),
        "/api/me": Exception("404"),
        "/api/object_info": ComfyAPIError(error_code="HTTP_403", message="forbidden", suggestion=""),
    }
    with patch.object(client, "get", new=_make_get_handler(routes)), \
         patch.object(client, "_probe_ws_available", new_callable=AsyncMock) as ws:
        ws.return_value = True
        await client.connect()
        await client.probe_capabilities()
        assert client.capabilities["tier"] == "free"
    await client.close()

"""Tests for ComfyClient HTTP layer."""

from __future__ import annotations

import httpx
import pytest

from comfy_mcp.comfy_client import ComfyClient
from comfy_mcp.errors import ComfyAPIError, ComfyConnectionError


def _mock_transport(responses: dict[str, tuple[int, dict]]):
    """Create httpx.MockTransport from path->(status, body) mapping."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in responses:
            status, body = responses[path]
            return httpx.Response(status, json=body)
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.fixture
def client_with_transport():
    """Factory: create ComfyClient with mock transport."""

    def _make(responses: dict[str, tuple[int, dict]], **kwargs):
        transport = _mock_transport(responses)
        c = ComfyClient("http://test:8188", **kwargs)
        c._http = httpx.AsyncClient(transport=transport, base_url="http://test:8188")
        return c

    return _make


class TestComfyClientInit:
    def test_base_url_strips_trailing_slash(self):
        c = ComfyClient("http://localhost:8188/")
        assert c.base_url == "http://localhost:8188"

    def test_defaults(self):
        c = ComfyClient("http://localhost:8188")
        assert c.api_key == ""
        assert c.ws_reconnect_max == 5

    def test_api_key_stored(self):
        c = ComfyClient("http://x:8188", api_key="secret123")
        assert c.api_key == "secret123"

    def test_detects_cloud_host(self):
        c = ComfyClient("https://cloud.comfy.org")
        assert c._is_cloud() is True


class TestComfyClientGet:
    @pytest.mark.asyncio
    async def test_get_success(self, client_with_transport):
        client = client_with_transport({
            "/system_stats": (200, {"system": {"os": "nt"}}),
        })
        result = await client.get("/system_stats")
        assert result["system"]["os"] == "nt"

    @pytest.mark.asyncio
    async def test_get_404_raises_api_error(self, client_with_transport):
        client = client_with_transport({})
        with pytest.raises(ComfyAPIError) as exc_info:
            await client.get("/nonexistent")
        assert exc_info.value.error_code == "HTTP_404"

    @pytest.mark.asyncio
    async def test_get_500_raises_api_error(self, client_with_transport):
        client = client_with_transport({
            "/broken": (500, {"error": "internal"}),
        })
        with pytest.raises(ComfyAPIError) as exc_info:
            await client.get("/broken")
        assert exc_info.value.error_code == "HTTP_500"
        assert exc_info.value.retry_possible is True


class TestComfyClientPost:
    @pytest.mark.asyncio
    async def test_post_success(self, client_with_transport):
        client = client_with_transport({
            "/prompt": (200, {"prompt_id": "abc123", "number": 1}),
        })
        result = await client.post("/prompt", {"prompt": {}})
        assert result["prompt_id"] == "abc123"


class TestComfyClientHighLevel:
    @pytest.mark.asyncio
    async def test_get_system_stats(self, client_with_transport):
        client = client_with_transport({
            "/system_stats": (200, {
                "system": {"os": "nt", "comfyui_version": "0.17.0"},
                "devices": [],
            }),
        })
        result = await client.get_system_stats()
        assert result["system"]["comfyui_version"] == "0.17.0"

    @pytest.mark.asyncio
    async def test_get_queue(self, client_with_transport):
        client = client_with_transport({
            "/queue": (200, {"queue_running": [], "queue_pending": []}),
        })
        result = await client.get_queue()
        assert result["queue_running"] == []

    @pytest.mark.asyncio
    async def test_queue_prompt(self, client_with_transport):
        client = client_with_transport({
            "/prompt": (200, {"prompt_id": "p1", "number": 3}),
        })
        result = await client.queue_prompt({"1": {"class_type": "KSampler"}})
        assert result["prompt_id"] == "p1"

    @pytest.mark.asyncio
    async def test_interrupt(self, client_with_transport):
        client = client_with_transport({
            "/interrupt": (200, {}),
        })
        result = await client.interrupt()
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_image_returns_bytes(self, client_with_transport):
        # Special case: get_image returns raw bytes, not JSON
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, content=b"\x89PNG\r\n", headers={"content-type": "image/png"})
        )
        c = ComfyClient("http://test:8188")
        c._http = httpx.AsyncClient(transport=transport, base_url="http://test:8188")
        result = await c.get_image("test.png")
        assert result == b"\x89PNG\r\n"

    @pytest.mark.asyncio
    async def test_close(self, client_with_transport):
        client = client_with_transport({})
        await client.close()
        assert client._http is None

    @pytest.mark.asyncio
    async def test_get_features_prefers_local_route(self, client_with_transport):
        client = client_with_transport({
            "/features": (200, {"feature1": True}),
        })
        result = await client.get_features()
        assert result["feature1"] is True

    @pytest.mark.asyncio
    async def test_get_features_uses_cloud_route_for_cloud_hosts(self):
        transport = _mock_transport({
            "/api/features": (200, {"feature1": True}),
        })
        client = ComfyClient("https://cloud.comfy.org")
        client._http = httpx.AsyncClient(transport=transport, base_url="https://cloud.comfy.org")
        result = await client.get_features()
        assert result["feature1"] is True

    @pytest.mark.asyncio
    async def test_get_extensions_prefers_local_route(self, client_with_transport):
        client = client_with_transport({
            "/extensions": (200, {"extensions": ["ext1"]}),
        })
        result = await client.get_extensions()
        assert result == ["ext1"]

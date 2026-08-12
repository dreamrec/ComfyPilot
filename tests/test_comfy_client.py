"""Tests for ComfyClient HTTP layer."""

from __future__ import annotations

import httpx
import pytest

from comfy_mcp.comfy_client import ComfyClient
from comfy_mcp.errors import ComfyAPIError, ComfyConnectionError


class AsyncNoop:
    async def __call__(self, *args, **kwargs):
        return None


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

    @pytest.mark.asyncio
    async def test_get_retries_transient_server_error(self, monkeypatch):
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                return httpx.Response(503, json={"error": "busy"})
            return httpx.Response(200, json={"ok": True})

        monkeypatch.setattr("comfy_mcp.comfy_client.asyncio.sleep", AsyncNoop())
        client = ComfyClient("http://test:8188", max_retries=2)
        client._http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://test:8188"
        )
        assert await client.get("/status") == {"ok": True}
        assert attempts == 3


class TestComfyClientPost:
    @pytest.mark.asyncio
    async def test_post_success(self, client_with_transport):
        client = client_with_transport({
            "/prompt": (200, {"prompt_id": "abc123", "number": 1}),
        })
        result = await client.post("/prompt", {"prompt": {}})
        assert result["prompt_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_post_accepts_empty_success_body(self):
        client = ComfyClient("http://test:8188")
        client._http = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200)),
            base_url="http://test:8188",
        )
        assert await client.post("/interrupt", idempotent=True) == {}

    @pytest.mark.asyncio
    async def test_post_accepts_plain_text_success_body(self):
        client = ComfyClient("http://test:8188")
        client._http = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text="restarting")
            ),
            base_url="http://test:8188",
        )
        assert await client.post("/manager/reboot", idempotent=True) == "restarting"

    @pytest.mark.asyncio
    async def test_non_idempotent_post_is_never_replayed(self, monkeypatch):
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(503, json={"error": "busy"})

        monkeypatch.setattr("comfy_mcp.comfy_client.asyncio.sleep", AsyncNoop())
        client = ComfyClient("http://test:8188", max_retries=5)
        client._http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://test:8188"
        )
        with pytest.raises(ComfyAPIError):
            await client.post("/prompt", {"prompt": {}})
        assert attempts == 1

    @pytest.mark.asyncio
    async def test_idempotent_post_retries(self, monkeypatch):
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(503, json={"error": "busy"})
            return httpx.Response(200)

        monkeypatch.setattr("comfy_mcp.comfy_client.asyncio.sleep", AsyncNoop())
        client = ComfyClient("http://test:8188", max_retries=2)
        client._http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://test:8188"
        )
        assert await client.post("/interrupt", idempotent=True) == {}
        assert attempts == 2


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
    async def test_queue_prompt_sends_modern_metadata(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(__import__("json").loads(request.content))
            return httpx.Response(200, json={"prompt_id": "p-modern", "number": 0})

        client = ComfyClient("http://test:8188")
        client._http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://test:8188"
        )
        await client.queue_prompt(
            {"1": {"class_type": "SaveImage"}},
            workflow_id="wf-1",
            workflow_version_id="wfv-2",
            partial_execution_targets=["1"],
            extra_data={"source": "test"},
        )
        assert captured["workflow_id"] == "wf-1"
        assert captured["workflow_version_id"] == "wfv-2"
        assert captured["partial_execution_targets"] == ["1"]
        assert captured["extra_data"] == {"source": "test"}

    @pytest.mark.asyncio
    async def test_embedded_markdown_docs(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/docs/KSampler/en.md":
                return httpx.Response(200, text="# KSampler\nSamples a latent.")
            return httpx.Response(404, text="missing")

        client = ComfyClient("http://test:8188")
        client._http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://test:8188"
        )
        result = await client.get_node_docs("KSampler")
        assert result["format"] == "markdown"
        assert result["source"] == "/docs/KSampler/en.md"
        assert "Samples a latent" in result["description"]

    @pytest.mark.asyncio
    async def test_global_subgraphs_id_map_normalized(self, client_with_transport):
        client = client_with_transport({
            "/global_subgraphs": (200, {"sha256-id": {"name": "Reusable Detailer"}}),
        })
        result = await client.get_published_subgraphs()
        assert result == [{"name": "Reusable Detailer", "id": "sha256-id"}]

    @pytest.mark.asyncio
    async def test_list_jobs_uses_local_sort_alias_and_offset(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(dict(request.url.params))
            return httpx.Response(200, json={"jobs": [], "pagination": {}})

        client = ComfyClient("http://test:8188")
        client._http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://test:8188"
        )
        await client.get_jobs(sort_by="create_time", offset=7, after="cloud-cursor")
        assert seen["sort_by"] == "created_at"
        assert seen["offset"] == "7"
        assert "after" not in seen

    @pytest.mark.asyncio
    async def test_cancel_prompt_prefers_modern_jobs_api(self, client_with_transport):
        client = client_with_transport({
            "/api/jobs/job-1/cancel": (200, {"cancelled": True}),
        })
        result = await client.cancel_prompt("job-1")
        assert result == {"cancelled": True, "method": "jobs_api"}

    @pytest.mark.asyncio
    async def test_cancel_prompt_legacy_queue_fallback(self, client_with_transport):
        client = client_with_transport({
            "/queue": (200, {"queue_running": [], "queue_pending": []}),
        })
        result = await client.cancel_prompt("job-old")
        assert result["cancelled"] is True
        assert result["method"] == "legacy_queue_delete"

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

    @pytest.mark.asyncio
    async def test_get_model_folders_returns_live_list(self, client_with_transport):
        """GET /models returns ['checkpoints', 'diffusion_models', ...] directly."""
        client = client_with_transport({
            "/models": (200, [
                "checkpoints", "diffusion_models", "loras", "vae", "text_encoders",
                "clip_vision", "controlnet", "upscale_models", "style_models",
                "embeddings", "gligen",
            ]),
        })
        result = await client.get_model_folders()
        assert "diffusion_models" in result
        assert "text_encoders" in result
        assert len(result) == 11

    @pytest.mark.asyncio
    async def test_get_model_folders_accepts_dict_shape(self, client_with_transport):
        """Some wrappers return {'folders': [...]} or {'models': [...]}."""
        client = client_with_transport({
            "/models": (200, {"folders": ["checkpoints", "loras"]}),
        })
        result = await client.get_model_folders()
        assert result == ["checkpoints", "loras"]

    @pytest.mark.asyncio
    async def test_get_model_folders_empty_on_error(self, client_with_transport):
        """Unreachable endpoint -> empty list (callers do fallback)."""
        client = client_with_transport({})  # no /models registered -> 404
        result = await client.get_model_folders()
        assert result == []

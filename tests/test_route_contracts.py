"""Route contract tests — verify local vs cloud route selection.

These tests ensure that route paths match the official ComfyUI API contracts:
- Local ComfyUI: /features, /extensions, /system_stats
- Cloud ComfyUI: /api/features, /api/extensions, /api/system_stats
"""
import httpx
import pytest

from comfy_mcp.comfy_client import ComfyClient


def _recording_transport(recorded: list):
    """Transport that records request paths and returns 200 with empty JSON."""

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request.url.path)
        return httpx.Response(200, json={})

    return httpx.MockTransport(handler)


@pytest.fixture
def local_client():
    """Client with local profile pre-set."""
    c = ComfyClient("http://localhost:8188")
    c.capabilities["profile"] = "local"
    recorded = []
    c._http = httpx.AsyncClient(
        transport=_recording_transport(recorded),
        base_url="http://localhost:8188",
    )
    return c, recorded


@pytest.fixture
def cloud_client():
    """Client with cloud profile pre-set."""
    c = ComfyClient("https://api.comfy.org", api_key="test-key")
    c.capabilities["profile"] = "cloud"
    recorded = []
    c._http = httpx.AsyncClient(
        transport=_recording_transport(recorded),
        base_url="https://api.comfy.org",
    )
    return c, recorded


class TestLocalRoutes:
    """Local ComfyUI should use unprefixed routes per official docs."""

    @pytest.mark.asyncio
    async def test_features_uses_local_route(self, local_client):
        client, recorded = local_client
        await client.get_features()
        assert "/features" in recorded
        assert "/api/features" not in recorded

    @pytest.mark.asyncio
    async def test_extensions_uses_local_route(self, local_client):
        client, recorded = local_client
        await client.get_extensions()
        assert "/extensions" in recorded
        assert "/api/extensions" not in recorded

    @pytest.mark.asyncio
    async def test_system_stats_uses_local_route(self, local_client):
        client, recorded = local_client
        await client.get_system_stats()
        assert "/system_stats" in recorded

    @pytest.mark.asyncio
    async def test_queue_uses_local_route(self, local_client):
        client, recorded = local_client
        await client.get_queue()
        assert "/queue" in recorded

    @pytest.mark.asyncio
    async def test_object_info_uses_local_route(self, local_client):
        client, recorded = local_client
        await client.get_object_info()
        assert "/object_info" in recorded


class TestCloudRoutes:
    """Cloud ComfyUI should use /api/ prefixed routes for features/extensions."""

    @pytest.mark.asyncio
    async def test_features_uses_cloud_route(self, cloud_client):
        client, recorded = cloud_client
        await client.get_features()
        assert "/api/features" in recorded

    @pytest.mark.asyncio
    async def test_extensions_uses_cloud_route(self, cloud_client):
        client, recorded = cloud_client
        await client.get_extensions()
        assert "/api/extensions" in recorded


class TestFeaturePayloadPreservation:
    """Feature probing must preserve the response shape regardless of type."""

    @pytest.mark.asyncio
    async def test_list_features_preserved(self):
        c = ComfyClient("http://localhost:8188")
        c.capabilities["profile"] = "local"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/system_stats":
                return httpx.Response(200, json={"system": {"comfyui_version": "0.17.0"}})
            if request.url.path == "/features":
                return httpx.Response(200, json=["feature_a", "feature_b"])
            return httpx.Response(200, json={})

        c._http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://localhost:8188",
        )
        await c.probe_capabilities()
        assert c.capabilities["features"] == ["feature_a", "feature_b"]

    @pytest.mark.asyncio
    async def test_object_features_preserved(self):
        """Object-shaped features must NOT be collapsed to []."""
        c = ComfyClient("http://localhost:8188")
        c.capabilities["profile"] = "local"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/system_stats":
                return httpx.Response(200, json={"system": {"comfyui_version": "0.17.0"}})
            if request.url.path == "/features":
                return httpx.Response(200, json={"experimental": True, "version": 2})
            return httpx.Response(200, json={})

        c._http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://localhost:8188",
        )
        await c.probe_capabilities()
        assert c.capabilities["features"] == {"experimental": True, "version": 2}


class TestInterruptMarksJobs:
    """comfy_interrupt must only mark running jobs as interrupted, not queued."""

    @pytest.mark.asyncio
    async def test_interrupt_only_marks_running_jobs(self, mock_ctx, mock_client):
        from comfy_mcp.tools.workflow import comfy_interrupt
        import json

        mock_client.interrupt.return_value = {}
        job_tracker = mock_ctx.request_context.lifespan_context["job_tracker"]
        job_tracker.list_active.return_value = [
            {"prompt_id": "p1", "status": "running"},
            {"prompt_id": "p2", "status": "queued"},
        ]

        result = await comfy_interrupt(ctx=mock_ctx)
        data = json.loads(result)

        assert data["status"] == "interrupted"
        assert data["interrupted_prompt_ids"] == ["p1"]
        assert data["queued_prompt_ids_unchanged"] == ["p2"]
        job_tracker.mark_interrupted.assert_awaited_once_with("p1")

    @pytest.mark.asyncio
    async def test_interrupt_with_no_active_jobs(self, mock_ctx, mock_client):
        from comfy_mcp.tools.workflow import comfy_interrupt
        import json

        mock_client.interrupt.return_value = {}
        job_tracker = mock_ctx.request_context.lifespan_context["job_tracker"]
        job_tracker.list_active.return_value = []

        result = await comfy_interrupt(ctx=mock_ctx)
        data = json.loads(result)

        assert data["interrupted_prompt_ids"] == []
        job_tracker.mark_interrupted.assert_not_awaited()

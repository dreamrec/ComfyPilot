"""Tests for system tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from comfy_mcp.tools.system import (
    comfy_free_vram,
    comfy_get_features,
    comfy_get_gpu_info,
    comfy_get_system_stats,
    comfy_list_extensions,
    comfy_restart,
)


class TestGetSystemStats:
    @pytest.mark.asyncio
    async def test_returns_system_info(self, mock_ctx, mock_client):
        result = await comfy_get_system_stats(ctx=mock_ctx)
        assert result.system.comfyui_version == "0.17.0"
        mock_client.get_system_stats.assert_awaited_once()

class TestGetGpuInfo:
    @pytest.mark.asyncio
    async def test_returns_gpu_details(self, mock_ctx, mock_client):
        result = await comfy_get_gpu_info(ctx=mock_ctx)
        data = json.loads(result)
        assert len(data["devices"]) == 1
        assert "vram_total" in data["devices"][0]

class TestGetFeatures:
    @pytest.mark.asyncio
    async def test_returns_features(self, mock_ctx, mock_client):
        mock_client.get_features.return_value = {"feature1": True}
        result = await comfy_get_features(ctx=mock_ctx)
        data = json.loads(result)
        assert data["feature1"] is True

class TestListExtensions:
    @pytest.mark.asyncio
    async def test_returns_extensions(self, mock_ctx, mock_client):
        mock_client.get_extensions.return_value = ["ext1", "ext2"]
        result = await comfy_list_extensions(ctx=mock_ctx)
        data = json.loads(result)
        assert data["extensions"] == ["ext1", "ext2"]
        assert data["count"] == 2

class TestFreeVram:
    @pytest.mark.asyncio
    async def test_free_vram(self, mock_ctx, mock_client):
        mock_client.free_vram.return_value = {}
        result = await comfy_free_vram(unload_models=True, free_memory=True, ctx=mock_ctx)
        data = json.loads(result)
        assert data["status"] == "ok"
        mock_client.free_vram.assert_awaited_once_with(unload_models=True, free_memory=True)


def _desktop_instance(manager_available: bool = True):
    return {
        "status": "ok",
        "base_url": "http://127.0.0.1:8000",
        "local": True,
        "instance_id": "inst-selected",
        "listener": {"pid": 123, "port": 8000},
        "owner_type": "comfy_desktop",
        "supervisor": {"name": "Comfy Desktop.exe", "pid": 999},
        "manager": {
            "available": manager_available,
            "api_generation": "v2" if manager_available else None,
            "restart_route": "/v2/manager/reboot",
            "error": None if manager_available else "not installed",
        },
    }


class TestRestart:
    @pytest.mark.asyncio
    async def test_requires_exact_instance_selector(self, mock_ctx):
        with patch(
            "comfy_mcp.tools.system.inspect_instance",
            new=AsyncMock(return_value=_desktop_instance()),
        ):
            data = json.loads(await comfy_restart(ctx=mock_ctx))
        assert data["status"] == "selection_required"
        assert data["selector"] == {"expected_instance_id": "inst-selected"}

    @pytest.mark.asyncio
    async def test_mismatched_selector_never_posts(self, mock_ctx, mock_client):
        with patch(
            "comfy_mcp.tools.system.inspect_instance",
            new=AsyncMock(return_value=_desktop_instance()),
        ):
            data = json.loads(await comfy_restart(
                expected_instance_id="wrong", confirm=True, ctx=mock_ctx
            ))
        assert data["status"] == "selection_mismatch"
        mock_client.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_manager_v2_restart_can_return_without_waiting(self, mock_ctx, mock_client):
        mock_client.post = AsyncMock(return_value={})
        with patch(
            "comfy_mcp.tools.system.inspect_instance",
            new=AsyncMock(return_value=_desktop_instance()),
        ):
            data = json.loads(await comfy_restart(
                expected_instance_id="inst-selected",
                confirm=True,
                wait_for_health=False,
                ctx=mock_ctx,
            ))
        assert data["status"] == "restart_requested"
        mock_client.post.assert_awaited_once_with("/v2/manager/reboot", {})

    @pytest.mark.asyncio
    async def test_manager_absence_returns_controlled_fallback(self, mock_ctx, mock_client):
        with patch(
            "comfy_mcp.tools.system.inspect_instance",
            new=AsyncMock(return_value=_desktop_instance(False)),
        ):
            data = json.loads(await comfy_restart(
                expected_instance_id="inst-selected", confirm=True, ctx=mock_ctx
            ))
        assert data["status"] == "controlled_fallback"
        assert data["supervisor"]["name"] == "Comfy Desktop.exe"
        mock_client.post.assert_not_awaited()

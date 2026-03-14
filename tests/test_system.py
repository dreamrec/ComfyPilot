"""Tests for system tools."""

from __future__ import annotations

import json

import pytest

from comfy_mcp.tools.system import (
    comfy_free_vram,
    comfy_get_features,
    comfy_get_gpu_info,
    comfy_get_system_stats,
    comfy_list_extensions,
)


class TestGetSystemStats:
    @pytest.mark.asyncio
    async def test_returns_system_info(self, mock_ctx, mock_client):
        result = await comfy_get_system_stats(ctx=mock_ctx)
        data = json.loads(result)
        assert data["system"]["comfyui_version"] == "0.17.0"
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

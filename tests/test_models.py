"""Tests for model tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from comfy_mcp.tools.models import (
    comfy_get_model_info,
    comfy_list_models,
    comfy_list_model_folders,
    comfy_search_models,
    comfy_refresh_models,
)


class TestListModels:
    @pytest.mark.asyncio
    async def test_list_models_basic(self, mock_ctx, mock_client):
        mock_client.get_models = AsyncMock(
            return_value=["model_a.safetensors", "model_b.safetensors"]
        )
        result = await comfy_list_models("checkpoints", ctx=mock_ctx)
        data = json.loads(result)
        assert data["total_count"] == 2
        assert data["folder"] == "checkpoints"
        assert data["has_more"] is False
        assert data["next_offset"] is None
        assert len(data["models"]) == 2

    @pytest.mark.asyncio
    async def test_list_models_pagination_has_more(self, mock_ctx, mock_client):
        models = [f"model_{i}.safetensors" for i in range(100)]
        mock_client.get_models = AsyncMock(return_value=models)
        result = await comfy_list_models("checkpoints", limit=50, offset=0, ctx=mock_ctx)
        data = json.loads(result)
        assert data["total_count"] == 100
        assert data["has_more"] is True
        assert data["next_offset"] == 50
        assert len(data["models"]) == 50

    @pytest.mark.asyncio
    async def test_list_models_pagination_offset(self, mock_ctx, mock_client):
        models = [f"model_{i}.safetensors" for i in range(150)]
        mock_client.get_models = AsyncMock(return_value=models)
        result = await comfy_list_models("checkpoints", limit=50, offset=50, ctx=mock_ctx)
        data = json.loads(result)
        assert data["total_count"] == 150
        assert data["has_more"] is True
        assert data["next_offset"] == 100
        assert len(data["models"]) == 50
        assert data["models"][0] == "model_50.safetensors"

    @pytest.mark.asyncio
    async def test_list_models_pagination_last_page(self, mock_ctx, mock_client):
        models = [f"model_{i}.safetensors" for i in range(100)]
        mock_client.get_models = AsyncMock(return_value=models)
        result = await comfy_list_models("checkpoints", limit=50, offset=75, ctx=mock_ctx)
        data = json.loads(result)
        assert data["total_count"] == 100
        assert data["has_more"] is False
        assert data["next_offset"] is None
        assert len(data["models"]) == 25


class TestGetModelInfo:
    @pytest.mark.asyncio
    async def test_get_model_info(self, mock_ctx, mock_client):
        expected_info = {
            "inputs": {"model": ["MODEL"]},
            "outputs": ["MODEL"],
            "output_names": ["MODEL"],
        }
        mock_client.get_object_info = AsyncMock(return_value=expected_info)
        result = await comfy_get_model_info("CheckpointLoader", ctx=mock_ctx)
        data = json.loads(result)
        assert data == expected_info
        mock_client.get_object_info.assert_awaited_once_with("CheckpointLoader")


class TestListModelFolders:
    @pytest.mark.asyncio
    async def test_list_model_folders(self, mock_ctx, mock_client):
        result = await comfy_list_model_folders(ctx=mock_ctx)
        data = json.loads(result)
        assert "folders" in data
        assert "checkpoints" in data["folders"]
        assert "loras" in data["folders"]
        assert "vae" in data["folders"]
        assert "clip" in data["folders"]
        assert "diffusers" in data["folders"]
        assert "controlnet" in data["folders"]
        assert "upscale_models" in data["folders"]
        assert "embeddings" in data["folders"]
        assert "hypernetworks" in data["folders"]
        assert data["count"] == 9


class TestSearchModels:
    @pytest.mark.asyncio
    async def test_search_models_single_folder(self, mock_ctx, mock_client):
        mock_client.get_models = AsyncMock(
            return_value=[
                "sd_v1.safetensors",
                "sd_v2.safetensors",
                "anime_model.safetensors",
            ]
        )
        result = await comfy_search_models("sd", folders=["checkpoints"], ctx=mock_ctx)
        data = json.loads(result)
        assert data["query"] == "sd"
        assert "checkpoints" in data["matches"]
        assert len(data["matches"]["checkpoints"]) == 2
        assert data["total_matches"] == 2

    @pytest.mark.asyncio
    async def test_search_models_multiple_folders(self, mock_ctx, mock_client):
        async def mock_get_models(folder):
            if folder == "checkpoints":
                return ["sd_v1.safetensors", "flux_model.safetensors"]
            elif folder == "loras":
                return ["lora_style.safetensors", "lora_detail.safetensors"]
            return []

        mock_client.get_models = AsyncMock(side_effect=mock_get_models)
        result = await comfy_search_models(
            "lora", folders=["checkpoints", "loras"], ctx=mock_ctx
        )
        data = json.loads(result)
        assert data["query"] == "lora"
        assert "checkpoints" not in data["matches"]
        assert "loras" in data["matches"]
        assert len(data["matches"]["loras"]) == 2
        assert data["total_matches"] == 2

    @pytest.mark.asyncio
    async def test_search_models_case_insensitive(self, mock_ctx, mock_client):
        mock_client.get_models = AsyncMock(
            return_value=["SD_V1.safetensors", "Model_SD.safetensors", "Other.safetensors"]
        )
        result = await comfy_search_models("SD", folders=["checkpoints"], ctx=mock_ctx)
        data = json.loads(result)
        assert len(data["matches"]["checkpoints"]) == 2
        assert data["total_matches"] == 2

    @pytest.mark.asyncio
    async def test_search_models_default_folders(self, mock_ctx, mock_client):
        async def mock_get_models(folder):
            return [f"model_in_{folder}.safetensors"]

        mock_client.get_models = AsyncMock(side_effect=mock_get_models)
        result = await comfy_search_models("model", ctx=mock_ctx)
        data = json.loads(result)
        # Should search checkpoints, loras, vae, controlnet, upscale_models
        assert data["total_matches"] == 5

    @pytest.mark.asyncio
    async def test_search_models_no_matches(self, mock_ctx, mock_client):
        mock_client.get_models = AsyncMock(return_value=["model_a.safetensors"])
        result = await comfy_search_models("nonexistent", folders=["checkpoints"], ctx=mock_ctx)
        data = json.loads(result)
        assert data["matches"] == {}
        assert data["total_matches"] == 0

    @pytest.mark.asyncio
    async def test_search_models_folder_error_handling(self, mock_ctx, mock_client):
        async def mock_get_models(folder):
            if folder == "missing_folder":
                raise Exception("Folder not found")
            return ["model.safetensors"]

        mock_client.get_models = AsyncMock(side_effect=mock_get_models)
        result = await comfy_search_models(
            "model", folders=["checkpoints", "missing_folder"], ctx=mock_ctx
        )
        data = json.loads(result)
        # Should skip the error and only return checkpoints
        assert "checkpoints" in data["matches"]
        assert "missing_folder" not in data["matches"]


class TestRefreshModels:
    @pytest.mark.asyncio
    async def test_refresh_models(self, mock_ctx, mock_client):
        mock_client.get_models = AsyncMock(return_value=["model.safetensors"])
        result = await comfy_refresh_models(ctx=mock_ctx)
        data = json.loads(result)
        assert data["status"] == "ok"
        assert "refreshed" in data["message"].lower()
        mock_client.get_models.assert_awaited_once_with("checkpoints")

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
        assert result.total_count == 2
        assert result.folder == "checkpoints"
        assert result.has_more is False
        assert result.next_offset is None
        assert len(result.models) == 2

    @pytest.mark.asyncio
    async def test_list_models_pagination_has_more(self, mock_ctx, mock_client):
        models = [f"model_{i}.safetensors" for i in range(100)]
        mock_client.get_models = AsyncMock(return_value=models)
        result = await comfy_list_models("checkpoints", limit=50, offset=0, ctx=mock_ctx)
        assert result.total_count == 100
        assert result.has_more is True
        assert result.next_offset == 50
        assert len(result.models) == 50

    @pytest.mark.asyncio
    async def test_list_models_pagination_offset(self, mock_ctx, mock_client):
        models = [f"model_{i}.safetensors" for i in range(150)]
        mock_client.get_models = AsyncMock(return_value=models)
        result = await comfy_list_models("checkpoints", limit=50, offset=50, ctx=mock_ctx)
        assert result.total_count == 150
        assert result.has_more is True
        assert result.next_offset == 100
        assert len(result.models) == 50
        assert result.models[0] == "model_50.safetensors"

    @pytest.mark.asyncio
    async def test_list_models_pagination_last_page(self, mock_ctx, mock_client):
        models = [f"model_{i}.safetensors" for i in range(100)]
        mock_client.get_models = AsyncMock(return_value=models)
        result = await comfy_list_models("checkpoints", limit=50, offset=75, ctx=mock_ctx)
        assert result.total_count == 100
        assert result.has_more is False
        assert result.next_offset is None
        assert len(result.models) == 25

    @pytest.mark.asyncio
    async def test_filters_cache_locks_and_source_by_default(self, mock_ctx, mock_client):
        mock_client.get_models = AsyncMock(return_value=[
            "trellis2/model.safetensors",
            ".cache/huggingface/download/model.safetensors.lock",
            "nodes/loader.py",
            "__pycache__/loader.cpython-312.pyc",
            "wheelhouse/package.whl",
            "config.json",
        ])
        result = await comfy_list_models("trellis2", ctx=mock_ctx)
        assert result.models == ["trellis2/model.safetensors", "config.json"]
        assert result.total_count == 2

    @pytest.mark.asyncio
    async def test_raw_model_listing_is_opt_in(self, mock_ctx, mock_client):
        raw = ["model.safetensors", "nodes/loader.py", "artifact.lock"]
        mock_client.get_models = AsyncMock(return_value=raw)
        result = await comfy_list_models(
            "custom", include_non_model_files=True, ctx=mock_ctx
        )
        assert result.models == raw


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
    async def test_list_model_folders_uses_live_endpoint(self, mock_ctx, mock_client):
        """When ComfyUI's /models endpoint answers, use THAT list, not a hardcoded one.

        This is how modern installs surface folders like diffusion_models and
        text_encoders that the old hardcoded list never mentioned.
        """
        mock_client.get_model_folders = AsyncMock(return_value=[
            "checkpoints", "diffusion_models", "loras", "vae", "text_encoders",
            "clip_vision", "controlnet", "upscale_models", "style_models",
            "embeddings", "gligen",
        ])
        result = await comfy_list_model_folders(ctx=mock_ctx)
        data = json.loads(result)
        assert data["source"] == "live"
        assert "diffusion_models" in data["folders"]
        assert "text_encoders" in data["folders"]
        assert "clip_vision" in data["folders"]
        assert data["count"] == 11

    @pytest.mark.asyncio
    async def test_list_model_folders_falls_back_when_endpoint_errors(self, mock_ctx, mock_client):
        """Unreachable ComfyUI -> fallback list covers every modern family."""
        mock_client.get_model_folders = AsyncMock(side_effect=Exception("offline"))
        result = await comfy_list_model_folders(ctx=mock_ctx)
        data = json.loads(result)
        assert data["source"] == "fallback"
        assert "checkpoints" in data["folders"]
        assert "diffusion_models" in data["folders"]
        assert "text_encoders" in data["folders"]
        assert "clip_vision" in data["folders"]
        assert "style_models" in data["folders"]

    @pytest.mark.asyncio
    async def test_list_model_folders_falls_back_on_empty_live_list(self, mock_ctx, mock_client):
        """Some ComfyUI wrappers return [] - treat as unavailable and fall back."""
        mock_client.get_model_folders = AsyncMock(return_value=[])
        result = await comfy_list_model_folders(ctx=mock_ctx)
        data = json.loads(result)
        assert data["source"] == "fallback"
        assert len(data["folders"]) >= 10


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
    async def test_search_models_default_uses_live_folder_list(self, mock_ctx, mock_client):
        """Default search must discover folders live, not use a hardcoded subset.

        Regression: pre-1.6 the default folder list was
        ['checkpoints', 'loras', 'vae', 'controlnet', 'upscale_models'] - so
        a wan2.2 checkpoint stored under diffusion_models/ was invisible to
        the default search.
        """
        mock_client.get_model_folders = AsyncMock(return_value=[
            "checkpoints", "diffusion_models", "loras", "vae", "text_encoders",
        ])
        async def mock_get_models(folder):
            return {
                "diffusion_models": ["wan2.2-t2v-14b.safetensors"],
                "text_encoders": ["t5xxl_fp16.safetensors"],
            }.get(folder, [])
        mock_client.get_models = AsyncMock(side_effect=mock_get_models)

        # Query "wan" matches ONLY the diffusion_models entry - proving the
        # default now searches that folder.
        result = await comfy_search_models("wan", ctx=mock_ctx)
        data = json.loads(result)
        assert data["folders_source"] == "live"
        assert "diffusion_models" in data["folders_scanned"]
        assert data["matches"]["diffusion_models"] == ["wan2.2-t2v-14b.safetensors"]
        assert data["total_matches"] == 1

    @pytest.mark.asyncio
    async def test_search_models_empty_query_returns_all(self, mock_ctx, mock_client):
        """Empty query = full inventory across every discovered folder."""
        mock_client.get_model_folders = AsyncMock(return_value=["checkpoints", "diffusion_models"])
        async def mock_get_models(folder):
            return [f"file_in_{folder}.safetensors"]
        mock_client.get_models = AsyncMock(side_effect=mock_get_models)
        result = await comfy_search_models("", ctx=mock_ctx)
        data = json.loads(result)
        assert data["total_matches"] == 2

    @pytest.mark.asyncio
    async def test_search_models_reports_caller_source_when_folders_passed(self, mock_ctx, mock_client):
        """Explicit folders= means the caller chose the taxonomy; advertise that."""
        mock_client.get_model_folders = AsyncMock(return_value=["should_not_be_used"])
        mock_client.get_models = AsyncMock(return_value=["x.safetensors"])
        result = await comfy_search_models("x", folders=["loras"], ctx=mock_ctx)
        data = json.loads(result)
        assert data["folders_source"] == "caller"
        assert data["folders_scanned"] == ["loras"]

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

    @pytest.mark.asyncio
    async def test_search_ignores_source_and_huggingface_locks(self, mock_ctx, mock_client):
        mock_client.get_models = AsyncMock(return_value=[
            "trellis2/model.safetensors",
            "trellis2/__pycache__/model.pyc",
            "trellis2/source/trellis_loader.py",
            ".cache/huggingface/trellis2.lock",
        ])
        data = json.loads(await comfy_search_models(
            "trellis", folders=["trellis2"], ctx=mock_ctx
        ))
        assert data["matches"]["trellis2"] == ["trellis2/model.safetensors"]
        assert data["total_matches"] == 1

    @pytest.mark.asyncio
    async def test_query_matching_folder_name_returns_clean_inventory(self, mock_ctx, mock_client):
        mock_client.get_models = AsyncMock(return_value=[
            "ckpts/shape_model.safetensors",
            "ckpts/shape_model.json",
            ".cache/huggingface/trellis2.safetensors.lock",
        ])
        data = json.loads(await comfy_search_models(
            "trellis", folders=["trellis2"], ctx=mock_ctx
        ))
        assert data["matches"]["trellis2"] == [
            "ckpts/shape_model.safetensors", "ckpts/shape_model.json"
        ]


class TestRefreshModels:
    @pytest.mark.asyncio
    async def test_refresh_models_counts_every_folder(self, mock_ctx, mock_client):
        """Regression: pre-1.6 refresh only hit `checkpoints`. Modern installs
        store primary weights under `diffusion_models/` - that refresh ignored
        them entirely."""
        mock_client.get_model_folders = AsyncMock(return_value=[
            "checkpoints", "diffusion_models", "loras",
        ])

        async def mock_get_models(folder):
            return {
                "checkpoints": ["sd15.safetensors"],
                "diffusion_models": ["flux2.safetensors", "wan22.safetensors"],
                "loras": [],
            }.get(folder, [])
        mock_client.get_models = AsyncMock(side_effect=mock_get_models)

        result = await comfy_refresh_models(ctx=mock_ctx)
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["folders_source"] == "live"
        assert data["counts_by_folder"]["checkpoints"] == 1
        assert data["counts_by_folder"]["diffusion_models"] == 2
        assert data["counts_by_folder"]["loras"] == 0
        assert data["total_models"] == 3

    @pytest.mark.asyncio
    async def test_refresh_models_surfaces_per_folder_errors(self, mock_ctx, mock_client):
        mock_client.get_model_folders = AsyncMock(return_value=["checkpoints", "broken"])
        async def mock_get_models(folder):
            if folder == "broken":
                raise Exception("index corrupted")
            return ["ok.safetensors"]
        mock_client.get_models = AsyncMock(side_effect=mock_get_models)

        result = await comfy_refresh_models(ctx=mock_ctx)
        data = json.loads(result)
        assert data["counts_by_folder"]["checkpoints"] == 1
        assert data["errors"]
        assert data["errors"][0]["folder"] == "broken"

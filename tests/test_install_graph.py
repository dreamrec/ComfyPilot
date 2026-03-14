"""Tests for InstallGraph — canonical machine state snapshot."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.capabilities = {
        "profile": "local",
        "version": "0.17.0",
        "ws_available": True,
        "features": ["some-feature"],
    }
    client.get_system_stats = AsyncMock(return_value={
        "system": {
            "os": "nt",
            "comfyui_version": "0.17.0",
            "python_version": "3.12.0",
            "pytorch_version": "2.5.0",
        },
        "devices": [{"name": "RTX 5090", "type": "cuda", "vram_total": 34359738368, "vram_free": 30000000000}],
    })
    client.get_object_info = AsyncMock(return_value={
        "KSampler": {"input": {"required": {"seed": ["INT"]}}, "output": ["LATENT"], "category": "sampling"},
        "CLIPTextEncode": {"input": {"required": {"text": ["STRING"]}}, "output": ["CONDITIONING"], "category": "conditioning"},
        "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["model1.safetensors", "model2.safetensors"]]}}, "output": ["MODEL", "CLIP", "VAE"], "category": "loaders"},
    })
    client.get_models = AsyncMock(side_effect=lambda folder: {
        "checkpoints": ["model1.safetensors", "model2.safetensors"],
        "loras": ["detail.safetensors"],
        "vae": ["sdxl_vae.safetensors"],
        "controlnet": [],
        "upscale_models": ["4x_NMKD.pth"],
    }.get(folder, []))
    client.get_features = AsyncMock(return_value=["some-feature"])
    client.get_extensions = AsyncMock(return_value=["ext.core.nodes", "ext.custom.animatediff"])
    client.get_embeddings = AsyncMock(return_value=["EasyNegative", "badhandv4"])
    return client


class TestInstallGraphRefresh:
    @pytest.mark.asyncio
    async def test_refresh_populates_snapshot(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        snap = graph.snapshot
        assert snap is not None
        assert snap["version"] == "0.17.0"
        assert snap["profile"] == "local"
        assert "KSampler" in snap["node_classes"]
        assert "model1.safetensors" in snap["models"]["checkpoints"]
        assert "EasyNegative" in snap["embeddings"]
        assert "ext.custom.animatediff" in snap["extensions"]
        assert snap["refreshed_at"] > 0

    @pytest.mark.asyncio
    async def test_snapshot_is_none_before_refresh(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        assert graph.snapshot is None

    @pytest.mark.asyncio
    async def test_refresh_updates_timestamp(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        t1 = graph.snapshot["refreshed_at"]
        await graph.refresh()
        t2 = graph.snapshot["refreshed_at"]
        assert t2 >= t1

    @pytest.mark.asyncio
    async def test_node_count_and_categories(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        assert graph.snapshot["node_count"] == 3
        cats = graph.snapshot["categories"]
        assert "sampling" in cats
        assert "conditioning" in cats

    @pytest.mark.asyncio
    async def test_gpu_info_included(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        assert len(graph.snapshot["gpu_devices"]) == 1
        assert graph.snapshot["gpu_devices"][0]["name"] == "RTX 5090"

    @pytest.mark.asyncio
    async def test_model_folder_error_handled(self, mock_client):
        """If a model folder errors, it's skipped gracefully."""
        async def flaky_get_models(folder):
            if folder == "controlnet":
                raise Exception("folder not found")
            return {
                "checkpoints": ["model1.safetensors", "model2.safetensors"],
                "loras": ["detail.safetensors"],
                "vae": ["sdxl_vae.safetensors"],
                "upscale_models": ["4x_NMKD.pth"],
            }.get(folder, [])

        mock_client.get_models = AsyncMock(side_effect=flaky_get_models)
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        assert "checkpoints" in graph.snapshot["models"]
        assert "controlnet" not in graph.snapshot["models"]


class TestInstallGraphSummary:
    @pytest.mark.asyncio
    async def test_summary_returns_counts(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        summary = graph.summary()
        assert summary["node_count"] == 3
        assert summary["extension_count"] == 2
        assert summary["embedding_count"] == 2
        assert "checkpoints" in summary["model_counts"]
        assert summary["model_counts"]["checkpoints"] == 2

    @pytest.mark.asyncio
    async def test_summary_includes_hashes(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        summary = graph.summary()
        assert "hashes" in summary
        assert "nodes" in summary["hashes"]
        assert len(summary["hashes"]["nodes"]) == 16


class TestInstallGraphHasNode:
    @pytest.mark.asyncio
    async def test_has_node_true(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        assert graph.has_node("KSampler") is True

    @pytest.mark.asyncio
    async def test_has_node_false(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        assert graph.has_node("NonExistentNode") is False

    @pytest.mark.asyncio
    async def test_has_node_before_refresh_returns_false(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        assert graph.has_node("KSampler") is False


class TestInstallGraphStaleness:
    @pytest.mark.asyncio
    async def test_is_stale_before_refresh(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        assert graph.is_stale() is True

    @pytest.mark.asyncio
    async def test_not_stale_after_refresh(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        assert graph.is_stale() is False

    @pytest.mark.asyncio
    async def test_stale_with_zero_age(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        assert graph.is_stale(max_age_seconds=0) is True


class TestInstallGraphChangeDetection:
    @pytest.mark.asyncio
    async def test_hashes_populated_after_refresh(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        h = graph.hashes
        assert "nodes" in h
        assert "models" in h
        assert "extensions" in h
        assert "embeddings" in h
        assert "version" in h

    @pytest.mark.asyncio
    async def test_hashes_stable_on_same_data(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        h1 = graph.hashes
        await graph.refresh()
        h2 = graph.hashes
        assert h1 == h2

    @pytest.mark.asyncio
    async def test_hashes_change_on_new_data(self, mock_client):
        from comfy_mcp.install.install_graph import InstallGraph
        graph = InstallGraph(mock_client)
        await graph.refresh()
        h1 = graph.hashes["nodes"]
        # Add a new node
        orig = await mock_client.get_object_info()
        orig["NewNode"] = {"input": {}, "output": [], "category": "test"}
        mock_client.get_object_info = AsyncMock(return_value=orig)
        await graph.refresh()
        h2 = graph.hashes["nodes"]
        assert h1 != h2

"""Tests for install tools — MCP surface for InstallGraph."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def graph_mock():
    """Mock InstallGraph with a populated snapshot."""
    graph = MagicMock()
    graph.snapshot = {
        "version": "0.17.0",
        "profile": "local",
        "node_classes": {"KSampler", "CLIPTextEncode"},
        "node_count": 2,
        "categories": ["sampling", "conditioning"],
        "models": {"checkpoints": ["model.safetensors"], "loras": ["detail.safetensors"]},
        "extensions": ["ext.core"],
        "embeddings": ["EasyNeg"],
        "features": [],
        "gpu_devices": [{"name": "RTX 5090"}],
        "refreshed_at": 1710000000.0,
        "object_info": {},
        "hashes": {"nodes": "abc123", "models": "def456"},
    }
    graph.summary = MagicMock(return_value={
        "version": "0.17.0",
        "profile": "local",
        "node_count": 2,
        "category_count": 2,
        "extension_count": 1,
        "embedding_count": 1,
        "model_counts": {"checkpoints": 1, "loras": 1},
        "gpu_count": 1,
        "refreshed_at": 1710000000.0,
        "hashes": {"nodes": "abc123", "models": "def456"},
    })
    graph.refresh = AsyncMock(return_value=graph.snapshot)
    graph.has_node = MagicMock(side_effect=lambda n: n in {"KSampler", "CLIPTextEncode"})
    graph.find_models = MagicMock(return_value={"checkpoints": ["model.safetensors"]})
    return graph


@pytest.fixture
def install_ctx(mock_ctx, graph_mock):
    mock_ctx.request_context.lifespan_context["install_graph"] = graph_mock
    return mock_ctx


class TestRefreshInstallGraph:
    @pytest.mark.asyncio
    async def test_refresh_returns_summary(self, install_ctx, graph_mock):
        from comfy_mcp.tools.install import comfy_refresh_install_graph
        result = json.loads(await comfy_refresh_install_graph(ctx=install_ctx))
        graph_mock.refresh.assert_called_once()
        assert result["status"] == "ok"
        assert result["summary"]["node_count"] == 2


class TestGetInstallSummary:
    @pytest.mark.asyncio
    async def test_returns_summary(self, install_ctx, graph_mock):
        from comfy_mcp.tools.install import comfy_get_install_summary
        result = json.loads(await comfy_get_install_summary(ctx=install_ctx))
        assert result["node_count"] == 2
        assert result["version"] == "0.17.0"


class TestCheckModelResolution:
    @pytest.mark.asyncio
    async def test_resolves_model(self, install_ctx, graph_mock):
        from comfy_mcp.tools.install import comfy_check_model
        result = json.loads(await comfy_check_model(name="model", folder="checkpoints", ctx=install_ctx))
        assert result["found"] is True

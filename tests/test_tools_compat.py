"""Tests for compatibility MCP tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def compat_ctx(mock_ctx):
    graph = MagicMock()
    graph.snapshot = {
        "node_classes": {"KSampler", "SaveImage"},
        "models": {"checkpoints": ["model.safetensors"]},
        "embeddings": [],
        "object_info": {
            "KSampler": {
                "input": {"required": {"seed": ["INT"]}},
                "output": ["LATENT"],
            },
            "SaveImage": {
                "input": {"required": {"images": ["IMAGE"]}},
                "output": [],
                "output_node": True,
            },
        },
    }
    graph.refresh = AsyncMock(return_value=graph.snapshot)
    mock_ctx.request_context.lifespan_context["install_graph"] = graph
    return mock_ctx


class TestPreflightWorkflow:
    @pytest.mark.asyncio
    async def test_preflight_returns_report(self, compat_ctx):
        from comfy_mcp.tools.compat import comfy_preflight_workflow
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 42}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        result = json.loads(await comfy_preflight_workflow(workflow=wf, ctx=compat_ctx))
        assert "status" in result
        assert "confidence" in result

    @pytest.mark.asyncio
    async def test_preflight_missing_node(self, compat_ctx):
        from comfy_mcp.tools.compat import comfy_preflight_workflow
        wf = {"1": {"class_type": "FakeNode", "inputs": {}}}
        result = json.loads(await comfy_preflight_workflow(workflow=wf, ctx=compat_ctx))
        assert result["status"] == "blocked"

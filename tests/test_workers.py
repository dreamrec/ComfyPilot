from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from comfy_mcp.tools.workers import comfy_get_environment_status, comfy_list_workers


@pytest.mark.asyncio
async def test_environment_status_survives_broken_runtime(mock_ctx, mock_client):
    async def get(path):
        if path == "/env-manager/runtime":
            raise RuntimeError("comfy_env has no attribute RuntimeEnv")
        if path == "/env-manager/environments":
            return {"node_environments": [
                {"node_name": "TRELLIS2", "has_config": True, "has_env": True},
                {"node_name": "ordinary", "has_config": False, "has_env": False},
            ]}
        if path == "/env-manager/workers":
            return {"workers": [{"pid": 42, "alive": True, "env_dir": "C:/ce/env"}]}
        raise AssertionError(path)

    mock_client.get = AsyncMock(side_effect=get)
    data = json.loads(await comfy_get_environment_status(ctx=mock_ctx))
    assert data["status"] == "partial"
    assert data["runtime_available"] is False
    assert data["environment_count"] == 1
    assert data["environments"][0]["node_name"] == "TRELLIS2"
    assert data["alive_worker_count"] == 1
    assert "RuntimeEnv" in data["errors"]["runtime"]["message"]


@pytest.mark.asyncio
async def test_list_workers_reports_pool(mock_ctx, mock_client):
    mock_client.get = AsyncMock(return_value={
        "workers": [
            {"pid": 1, "alive": True},
            {"pid": 2, "alive": False},
        ]
    })
    data = json.loads(await comfy_list_workers(ctx=mock_ctx))
    assert data["count"] == 2
    assert data["alive_count"] == 1

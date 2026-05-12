"""Tests for native subgraph awareness in blueprints (ComfyUI v0.3.67+)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.comfy_client import ComfyClient
from comfy_mcp.tools.blueprints import comfy_list_blueprints


def _ctx_with_native_subgraphs(native: list[dict], tmp_path: Path):
    """Build a Context whose lifespan_context routes blueprints to tmp dirs."""
    client = MagicMock()
    client.get_published_subgraphs = AsyncMock(return_value=native)
    ctx = MagicMock()
    user_dir = tmp_path / "user"
    bundled_dir = tmp_path / "bundled"
    user_dir.mkdir(parents=True, exist_ok=True)
    bundled_dir.mkdir(parents=True, exist_ok=True)
    ctx.request_context.lifespan_context = {
        "comfy_client": client,
        "blueprint_user_dir": user_dir,
        "blueprint_bundled_dir": bundled_dir,
    }
    return ctx


@pytest.mark.asyncio
async def test_list_blueprints_native_only(tmp_path):
    native = [
        {"name": "custom-node-bigflow", "description": "Subgraph from a custom node"},
    ]
    ctx = _ctx_with_native_subgraphs(native, tmp_path)
    result = await comfy_list_blueprints(source="native", ctx=ctx)
    parsed = json.loads(result)
    names = [bp.get("name") for bp in parsed["blueprints"]]
    assert "custom-node-bigflow" in names


@pytest.mark.asyncio
async def test_list_blueprints_all_combines_sources(tmp_path):
    # Write one bundled blueprint
    bundled = {"id": "abc", "name": "shipped-bp", "nodes": {}, "node_count": 0}
    (tmp_path / "bundled").mkdir(parents=True, exist_ok=True)
    (tmp_path / "bundled" / "shipped-bp.json").write_text(json.dumps(bundled))

    native = [{"name": "native-bp"}]
    ctx = _ctx_with_native_subgraphs(native, tmp_path)
    result = await comfy_list_blueprints(source="all", ctx=ctx)
    parsed = json.loads(result)
    names = {bp.get("name") for bp in parsed["blueprints"]}
    assert "native-bp" in names
    assert "shipped-bp" in names


@pytest.mark.asyncio
async def test_list_blueprints_bundled_excludes_native(tmp_path):
    bundled = {"id": "abc", "name": "shipped-only", "nodes": {}, "node_count": 0}
    (tmp_path / "bundled").mkdir(parents=True, exist_ok=True)
    (tmp_path / "bundled" / "shipped-only.json").write_text(json.dumps(bundled))

    native = [{"name": "should-not-appear"}]
    ctx = _ctx_with_native_subgraphs(native, tmp_path)
    result = await comfy_list_blueprints(source="bundled", ctx=ctx)
    parsed = json.loads(result)
    names = {bp.get("name") for bp in parsed["blueprints"]}
    assert "shipped-only" in names
    assert "should-not-appear" not in names


@pytest.mark.asyncio
async def test_list_blueprints_rejects_bad_source(tmp_path):
    ctx = _ctx_with_native_subgraphs([], tmp_path)
    result = await comfy_list_blueprints(source="garbage", ctx=ctx)
    parsed = json.loads(result)
    assert "error" in parsed


@pytest.mark.asyncio
async def test_client_get_published_subgraphs_returns_empty_when_unavailable():
    """If every candidate path 404s, return [] so callers can fall back."""
    from unittest.mock import patch

    client = ComfyClient("http://localhost:8188")
    with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("404")
        await client.connect()
        result = await client.get_published_subgraphs()
        assert result == []
    await client.close()

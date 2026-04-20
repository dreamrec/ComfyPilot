"""Tests for subgraph blueprint tools."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import Context

from comfy_mcp.blueprints.store import BlueprintStore
from comfy_mcp.tools.blueprints import (
    comfy_insert_blueprint,
    comfy_list_blueprints,
    comfy_publish_subgraph,
)


def _ctx(user_dir, bundled_dir=None):
    ctx = MagicMock(spec=Context)
    ctx.request_context.lifespan_context = {
        "blueprint_user_dir": user_dir,
        "blueprint_bundled_dir": bundled_dir,
    }
    return ctx


SAMPLE_NODES = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "hi", "clip": ["1", 1]}},
}


class TestStoreDirect:
    def test_publish_and_load_roundtrip(self, tmp_path):
        store = BlueprintStore(user_dir=tmp_path)
        result = store.publish("my-test", SAMPLE_NODES, description="Test", tags=["demo"])
        assert result["name"] == "my-test"
        assert result["node_count"] == 2

        loaded = store.insert("my-test")
        assert loaded["name"] == "my-test"
        assert len(loaded["workflow"]) == 2

    def test_list_shows_user_and_bundled(self, tmp_path):
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        (bundled / "shipped.json").write_text(json.dumps({
            "name": "shipped", "nodes": {"1": {"class_type": "X", "inputs": {}}},
            "node_count": 1, "tags": [], "description": ""
        }))

        user = tmp_path / "user"
        store = BlueprintStore(user_dir=user, bundled_dir=bundled)
        store.publish("my-test", SAMPLE_NODES)

        listed = store.list()
        names = {b["name"] for b in listed}
        sources = {b["name"]: b["source"] for b in listed}
        assert "my-test" in names
        assert "shipped" in names
        assert sources["shipped"] == "bundled"
        assert sources["my-test"] == "user"

    def test_user_shadows_bundled_same_name(self, tmp_path):
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        (bundled / "collide.json").write_text(json.dumps({
            "name": "collide", "nodes": {"1": {"class_type": "Bundled"}},
            "node_count": 1, "tags": [], "description": "bundled version"
        }))

        user = tmp_path / "user"
        store = BlueprintStore(user_dir=user, bundled_dir=bundled)
        store.publish("collide", {"1": {"class_type": "User", "inputs": {}}})

        listed = store.list()
        entries = [b for b in listed if b["name"] == "collide"]
        assert len(entries) == 1
        assert entries[0]["source"] == "user"

        inserted = store.insert("collide")
        assert inserted["workflow"]["1"]["class_type"] == "User"

    def test_insert_applies_overrides(self, tmp_path):
        store = BlueprintStore(user_dir=tmp_path)
        store.publish("my-test", SAMPLE_NODES)
        result = store.insert("my-test", inputs={"2": {"text": "new prompt"}})
        assert result["workflow"]["2"]["inputs"]["text"] == "new prompt"

    def test_insert_missing_raises(self, tmp_path):
        store = BlueprintStore(user_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            store.insert("nope")

    def test_publish_rejects_path_traversal(self, tmp_path):
        store = BlueprintStore(user_dir=tmp_path)
        with pytest.raises(ValueError):
            store.publish("../evil", SAMPLE_NODES)
        with pytest.raises(ValueError):
            store.publish("nested/name", SAMPLE_NODES)


class TestTools:
    @pytest.mark.asyncio
    async def test_publish_then_list_then_insert_roundtrip(self, tmp_path):
        ctx = _ctx(tmp_path)
        pub = json.loads(await comfy_publish_subgraph(
            name="my-test", nodes=SAMPLE_NODES, description="Test", tags=["demo"], ctx=ctx,
        ))
        assert pub["name"] == "my-test"

        listed = json.loads(await comfy_list_blueprints(ctx=ctx))
        assert any(b["name"] == "my-test" for b in listed["blueprints"])

        inserted = json.loads(await comfy_insert_blueprint(name="my-test", inputs=None, ctx=ctx))
        assert inserted["workflow"]["1"]["class_type"] == "CheckpointLoaderSimple"

    @pytest.mark.asyncio
    async def test_insert_unknown_returns_error(self, tmp_path):
        ctx = _ctx(tmp_path)
        result = json.loads(await comfy_insert_blueprint(name="does-not-exist", ctx=ctx))
        assert "error" in result

    @pytest.mark.asyncio
    async def test_publish_bad_name_returns_error(self, tmp_path):
        ctx = _ctx(tmp_path)
        result = json.loads(await comfy_publish_subgraph(
            name="../bad", nodes=SAMPLE_NODES, ctx=ctx,
        ))
        assert "error" in result

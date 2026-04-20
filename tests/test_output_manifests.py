"""Tests for output manifest sidecar + atomic writes."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import Context

from comfy_mcp.tools.output_routing import (
    comfy_send_to_disk,
    comfy_send_to_td,
    comfy_send_to_blender,
)


def _ctx(client):
    ctx = MagicMock(spec=Context)
    ctx.request_context.lifespan_context = {"comfy_client": client}
    return ctx


@pytest.fixture
def fake_client():
    client = MagicMock()
    client.get_image = AsyncMock(return_value=b"pixels-go-here")
    client.get_history = AsyncMock(return_value={
        "test-prompt-id": {
            "prompt": [0, "test-prompt-id", {
                "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux2-klein.safetensors"}},
                "5": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20}},
                "6": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
            }, {}, "client-id"],
            "outputs": {},
        }
    })
    return client


class TestSendToDiskManifest:
    @pytest.mark.asyncio
    async def test_sidecar_written_alongside_image(self, tmp_path, fake_client):
        result = json.loads(await comfy_send_to_disk(
            filename="out.png", output_dir=str(tmp_path), ctx=_ctx(fake_client),
        ))
        assert result["status"] == "saved"
        img = tmp_path / "out.png"
        sidecar = tmp_path / "out.png.json"
        assert img.exists()
        assert img.read_bytes() == b"pixels-go-here"
        assert sidecar.exists()
        m = json.loads(sidecar.read_text())
        assert m["schema_version"] == "comfypilot/manifest/v1"
        assert m["filename"] == "out.png"
        assert m["size_bytes"] == 14

    @pytest.mark.asyncio
    async def test_manifest_without_prompt_id_skips_history(self, tmp_path, fake_client):
        result = json.loads(await comfy_send_to_disk(
            filename="out.png", output_dir=str(tmp_path), ctx=_ctx(fake_client),
        ))
        m = json.loads((tmp_path / "out.png.json").read_text())
        assert m["prompt_id"] is None
        # history was not consulted
        fake_client.get_history.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_manifest_with_prompt_id_pulls_history_metadata(self, tmp_path, fake_client):
        result = json.loads(await comfy_send_to_disk(
            filename="out.png", output_dir=str(tmp_path),
            prompt_id="test-prompt-id", ctx=_ctx(fake_client),
        ))
        m = json.loads((tmp_path / "out.png.json").read_text())
        assert m["prompt_id"] == "test-prompt-id"
        assert 42 in m["seeds"]
        assert "flux2-klein.safetensors" in m["model_refs"]
        assert {"width": 1024, "height": 1024} in m["dimensions"]

    @pytest.mark.asyncio
    async def test_manifest_degrades_gracefully_if_history_fails(self, tmp_path, fake_client):
        fake_client.get_history = AsyncMock(side_effect=Exception("offline"))
        result = json.loads(await comfy_send_to_disk(
            filename="out.png", output_dir=str(tmp_path),
            prompt_id="whatever", ctx=_ctx(fake_client),
        ))
        # Image written even if history fetch fails
        assert (tmp_path / "out.png").exists()
        m = json.loads((tmp_path / "out.png.json").read_text())
        assert m["prompt_id"] == "whatever"
        # No enriched fields - history fetch was skipped
        assert "seeds" not in m or m["seeds"] == []

    @pytest.mark.asyncio
    async def test_atomic_write_leaves_no_tmp_on_success(self, tmp_path, fake_client):
        await comfy_send_to_disk(filename="out.png", output_dir=str(tmp_path), ctx=_ctx(fake_client))
        tmp_files = list(tmp_path.glob("out.png.tmp.*"))
        assert tmp_files == []


class TestSendToTDManifest:
    @pytest.mark.asyncio
    async def test_td_writes_sidecar(self, tmp_path, fake_client, monkeypatch):
        monkeypatch.setenv("COMFY_TD_OUTPUT_DIR", str(tmp_path))
        result = json.loads(await comfy_send_to_td(
            filename="out.png", ctx=_ctx(fake_client),
        ))
        assert (tmp_path / "out.png").exists()
        assert (tmp_path / "out.png.json").exists()
        assert result["manifest_path"].endswith("out.png.json")


class TestSendToBlenderManifest:
    @pytest.mark.asyncio
    async def test_blender_writes_sidecar(self, tmp_path, fake_client, monkeypatch):
        monkeypatch.setenv("COMFY_BLENDER_OUTPUT_DIR", str(tmp_path))
        result = json.loads(await comfy_send_to_blender(
            filename="out.png", ctx=_ctx(fake_client),
        ))
        assert (tmp_path / "out.png").exists()
        assert (tmp_path / "out.png.json").exists()
        assert result["manifest_path"].endswith("out.png.json")

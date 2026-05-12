"""Tests for v0.19+ asset-manifest awareness in image listing.

ComfyUI v0.19 added an asset registration system for output files. /history
responses can now carry outputs under `assets: [...]` alongside (or instead
of) the legacy `images: [...]` key. The image tools should handle both.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from comfy_mcp.tools.images import _iter_node_outputs, comfy_list_output_images


class TestIterNodeOutputs:
    def test_legacy_images_key(self):
        records = _iter_node_outputs({
            "images": [{"filename": "a.png", "subfolder": "", "type": "output"}]
        })
        assert len(records) == 1
        assert records[0]["filename"] == "a.png"

    def test_v0_19_assets_key(self):
        records = _iter_node_outputs({
            "assets": [
                {"filename": "b.png", "subfolder": "", "type": "output", "asset_id": "asset-42"},
            ],
        })
        assert len(records) == 1
        assert records[0]["filename"] == "b.png"
        assert records[0]["asset_id"] == "asset-42"

    def test_both_keys_combined(self):
        records = _iter_node_outputs({
            "images": [{"filename": "old.png", "subfolder": "", "type": "output"}],
            "assets": [{"filename": "new.png", "subfolder": "", "type": "output"}],
        })
        names = {r["filename"] for r in records}
        assert names == {"old.png", "new.png"}

    def test_video_and_audio_outputs(self):
        records = _iter_node_outputs({
            "gifs": [{"filename": "anim.webp", "subfolder": "", "type": "output"}],
            "audio": [{"filename": "track.flac", "subfolder": "", "type": "output"}],
        })
        names = {r["filename"] for r in records}
        assert names == {"anim.webp", "track.flac"}

    def test_empty_node_output(self):
        assert _iter_node_outputs({}) == []


class TestListOutputImagesIntegration:
    @pytest.mark.asyncio
    async def test_lists_from_assets_manifest(self, mock_ctx, mock_client):
        mock_client.get_history = AsyncMock(return_value={
            "prompt_1": {
                "outputs": {
                    "9": {
                        "assets": [
                            {"filename": "v019.png", "subfolder": "", "type": "output", "asset_id": "abc"}
                        ]
                    }
                }
            }
        })
        result = await comfy_list_output_images(ctx=mock_ctx)
        data = json.loads(result)
        assert "v019.png" in data["images"]

    @pytest.mark.asyncio
    async def test_lists_from_legacy_images(self, mock_ctx, mock_client):
        mock_client.get_history = AsyncMock(return_value={
            "prompt_1": {
                "outputs": {
                    "9": {"images": [{"filename": "legacy.png", "subfolder": "", "type": "output"}]}
                }
            }
        })
        result = await comfy_list_output_images(ctx=mock_ctx)
        data = json.loads(result)
        assert "legacy.png" in data["images"]

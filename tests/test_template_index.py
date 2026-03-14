"""Tests for TemplateIndex -- unified index with disk cache."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


SAMPLE_TEMPLATES = [
    {"name": "txt2img_basic", "category": "text-to-image", "source": "official",
     "tags": ["txt2img", "basic"], "required_nodes": ["KSampler"], "required_models": {"checkpoints": 1}},
    {"name": "controlnet_basic", "category": "controlnet", "source": "builtin",
     "tags": ["controlnet"], "required_nodes": ["ControlNetLoader"], "required_models": {"controlnet": 1}},
]


class TestRebuild:
    def test_rebuild_assigns_ids(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex
        idx = TemplateIndex(storage_dir=str(tmp_path))
        idx.rebuild(SAMPLE_TEMPLATES)
        assert all("id" in t for t in idx.list_all())

    def test_rebuild_persists_to_disk(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex
        idx = TemplateIndex(storage_dir=str(tmp_path))
        idx.rebuild(SAMPLE_TEMPLATES)
        assert (tmp_path / "index.json").exists()
        assert (tmp_path / "manifest.json").exists()

    def test_rebuild_updates_manifest(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex
        idx = TemplateIndex(storage_dir=str(tmp_path))
        idx.rebuild(SAMPLE_TEMPLATES)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["template_count"] == 2
        assert "last_updated" in manifest


class TestGet:
    def test_get_existing(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex
        idx = TemplateIndex(storage_dir=str(tmp_path))
        idx.rebuild(SAMPLE_TEMPLATES)
        result = idx.get("official_txt2img_basic")
        assert result is not None
        assert result["name"] == "txt2img_basic"

    def test_get_missing(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex
        idx = TemplateIndex(storage_dir=str(tmp_path))
        idx.rebuild(SAMPLE_TEMPLATES)
        assert idx.get("nonexistent") is None


class TestListAll:
    def test_list_all_returns_all(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex
        idx = TemplateIndex(storage_dir=str(tmp_path))
        idx.rebuild(SAMPLE_TEMPLATES)
        assert len(idx.list_all()) == 2


class TestCategories:
    def test_categories_extracted(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex
        idx = TemplateIndex(storage_dir=str(tmp_path))
        idx.rebuild(SAMPLE_TEMPLATES)
        cats = idx.categories()
        assert "text-to-image" in cats
        assert "controlnet" in cats


class TestStaleness:
    def test_fresh_index_not_stale(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex
        idx = TemplateIndex(storage_dir=str(tmp_path))
        idx.rebuild(SAMPLE_TEMPLATES)
        assert not idx.is_stale(max_age=300)

    def test_stale_before_rebuild(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex
        idx = TemplateIndex(storage_dir=str(tmp_path))
        assert idx.is_stale()


class TestContentHash:
    def test_content_hash_present(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex
        idx = TemplateIndex(storage_dir=str(tmp_path))
        idx.rebuild(SAMPLE_TEMPLATES)
        assert len(idx.content_hash()) > 0

    def test_content_hash_empty_before_rebuild(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex
        idx = TemplateIndex(storage_dir=str(tmp_path))
        assert idx.content_hash() == ""


class TestClear:
    def test_clear_removes_templates(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex
        idx = TemplateIndex(storage_dir=str(tmp_path))
        idx.rebuild(SAMPLE_TEMPLATES)
        assert len(idx.list_all()) == 2
        idx.clear()
        assert len(idx.list_all()) == 0
        assert not (tmp_path / "index.json").exists()
        assert not (tmp_path / "manifest.json").exists()


class TestRefresh:
    @pytest.mark.asyncio
    async def test_refresh_without_discovery_is_safe(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex
        idx = TemplateIndex(storage_dir=str(tmp_path))
        # Should not raise, just log warning
        await idx.refresh()
        assert len(idx.list_all()) == 0

    @pytest.mark.asyncio
    async def test_refresh_with_discovery_rebuilds(self, tmp_path):
        from unittest.mock import AsyncMock
        from comfy_mcp.templates.index import TemplateIndex
        mock_discovery = AsyncMock()
        mock_discovery.discover_all = AsyncMock(return_value=SAMPLE_TEMPLATES.copy())
        idx = TemplateIndex(storage_dir=str(tmp_path), discovery=mock_discovery)
        await idx.refresh()
        assert len(idx.list_all()) == 2
        mock_discovery.discover_all.assert_awaited_once()


class TestDiskPersistence:
    def test_reload_from_disk(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex
        idx1 = TemplateIndex(storage_dir=str(tmp_path))
        idx1.rebuild(SAMPLE_TEMPLATES)
        # Create a new instance pointing at same dir -- should load from disk
        idx2 = TemplateIndex(storage_dir=str(tmp_path))
        assert len(idx2.list_all()) == 2
        assert idx2.content_hash() == idx1.content_hash()


class TestWorkflowHydration:
    @pytest.mark.asyncio
    async def test_hydrate_template_fetches_remote_workflow(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex

        idx = TemplateIndex(storage_dir=str(tmp_path))
        idx.rebuild([
            {
                "id": "official_qwen_image",
                "name": "image_qwen_image",
                "source": "official",
                "workflow_url": "https://example.com/qwen.json",
            }
        ])

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "nodes": [
                {"id": 1, "type": "QwenNode"},
                {"id": 2, "type": "SaveImage"},
            ],
            "links": [],
        })

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("comfy_mcp.templates.index.httpx.AsyncClient", return_value=mock_client):
            hydrated = await idx.hydrate_template("official_qwen_image")

        assert hydrated is not None
        assert hydrated["workflow_format"] == "comfyui-ui"
        assert hydrated["workflow_summary"]["node_count"] == 2
        assert hydrated["workflow_source"] == "remote"
        assert (tmp_path / "workflows" / "official_qwen_image.json").exists()

    @pytest.mark.asyncio
    async def test_hydrate_template_uses_cache(self, tmp_path):
        from comfy_mcp.templates.index import TemplateIndex

        idx = TemplateIndex(storage_dir=str(tmp_path))
        idx.rebuild([
            {
                "id": "official_qwen_image",
                "name": "image_qwen_image",
                "source": "official",
                "workflow_url": "https://example.com/qwen.json",
            }
        ])
        (tmp_path / "workflows").mkdir(parents=True, exist_ok=True)
        (tmp_path / "workflows" / "official_qwen_image.json").write_text(
            json.dumps({
                "nodes": [{"id": 1, "type": "SaveImage"}],
                "links": [],
            }),
            encoding="utf-8",
        )

        hydrated = await idx.hydrate_template("official_qwen_image")
        assert hydrated is not None
        assert hydrated["workflow_source"] == "cache"
        assert hydrated["workflow_format"] == "comfyui-ui"

"""Tests for ModelResolver — resolves model references against installed models."""

from __future__ import annotations

import pytest


def _make_graph_snapshot():
    """Create a minimal install graph snapshot for testing."""
    return {
        "node_classes": {"KSampler", "CheckpointLoaderSimple"},
        "models": {
            "checkpoints": ["sd_xl_base_1.0.safetensors", "dreamshaper_8.safetensors", "v1-5-pruned.safetensors"],
            "loras": ["detail_tweaker.safetensors", "add_detail.safetensors"],
            "vae": ["sdxl_vae.safetensors"],
            "controlnet": ["control_v11p_sd15_openpose.pth"],
            "upscale_models": [],
        },
        "embeddings": ["EasyNegative", "badhandv4", "verybadimagenegative_v1.3"],
    }


class TestModelResolver:
    def test_resolve_exact_match(self):
        from comfy_mcp.install.model_resolver import ModelResolver
        resolver = ModelResolver(_make_graph_snapshot())
        result = resolver.resolve("sd_xl_base_1.0.safetensors", "checkpoints")
        assert result["found"] is True
        assert result["exact"] is True
        assert result["match"] == "sd_xl_base_1.0.safetensors"

    def test_resolve_not_found(self):
        from comfy_mcp.install.model_resolver import ModelResolver
        resolver = ModelResolver(_make_graph_snapshot())
        result = resolver.resolve("nonexistent_model.safetensors", "checkpoints")
        assert result["found"] is False

    def test_resolve_partial_match(self):
        from comfy_mcp.install.model_resolver import ModelResolver
        resolver = ModelResolver(_make_graph_snapshot())
        result = resolver.resolve("dreamshaper", "checkpoints")
        assert result["found"] is True
        assert result["exact"] is False
        assert "dreamshaper_8.safetensors" in result["candidates"]

    def test_resolve_embedding(self):
        from comfy_mcp.install.model_resolver import ModelResolver
        resolver = ModelResolver(_make_graph_snapshot())
        result = resolver.resolve_embedding("EasyNegative")
        assert result["found"] is True

    def test_resolve_embedding_not_found(self):
        from comfy_mcp.install.model_resolver import ModelResolver
        resolver = ModelResolver(_make_graph_snapshot())
        result = resolver.resolve_embedding("UnknownEmbed")
        assert result["found"] is False

    def test_resolve_all_from_workflow(self):
        from comfy_mcp.install.model_resolver import ModelResolver
        resolver = ModelResolver(_make_graph_snapshot())
        refs = [
            {"name": "sd_xl_base_1.0.safetensors", "folder": "checkpoints"},
            {"name": "missing_lora.safetensors", "folder": "loras"},
            {"name": "detail_tweaker.safetensors", "folder": "loras"},
        ]
        report = resolver.resolve_all(refs)
        assert report["resolved"] == 2
        assert report["missing"] == 1
        assert report["missing_refs"][0]["name"] == "missing_lora.safetensors"

    def test_resolve_across_all_folders(self):
        from comfy_mcp.install.model_resolver import ModelResolver
        resolver = ModelResolver(_make_graph_snapshot())
        result = resolver.resolve("detail_tweaker.safetensors")
        assert result["found"] is True
        assert result["folder"] == "loras"

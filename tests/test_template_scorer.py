"""Tests for TemplateScorer -- relevance ranking."""

from __future__ import annotations

import pytest


INSTALLED_NODES = {"KSampler", "CheckpointLoaderSimple", "CLIPTextEncode", "VAEDecode", "SaveImage", "EmptyLatentImage"}
INSTALLED_MODELS = {"checkpoints": ["dreamshaper_8.safetensors"], "loras": [], "controlnet": []}

TEMPLATES = [
    {"id": "official_txt2img", "name": "txt2img_basic", "category": "text-to-image", "source": "official",
     "tags": ["txt2img", "basic"], "required_nodes": ["CheckpointLoaderSimple", "KSampler", "VAEDecode", "SaveImage"],
     "required_models": {"checkpoints": 1}},
    {"id": "official_controlnet", "name": "controlnet_basic", "category": "controlnet", "source": "official",
     "tags": ["controlnet", "guided"], "required_nodes": ["ControlNetLoader", "ControlNetApply"],
     "required_models": {"controlnet": 1}},
    {"id": "builtin_txt2img", "name": "txt2img_basic", "category": "text-to-image", "source": "builtin",
     "tags": ["txt2img", "basic"], "required_nodes": ["CheckpointLoaderSimple", "KSampler"],
     "required_models": {"checkpoints": 1}},
]


class TestScorerRanking:
    def test_matching_tags_ranked_higher(self):
        from comfy_mcp.templates.scorer import TemplateScorer
        scorer = TemplateScorer(INSTALLED_NODES, INSTALLED_MODELS)
        results = scorer.score("txt2img basic", TEMPLATES)
        assert results[0]["id"] in ("official_txt2img", "builtin_txt2img")

    def test_missing_nodes_penalized(self):
        from comfy_mcp.templates.scorer import TemplateScorer
        scorer = TemplateScorer(INSTALLED_NODES, INSTALLED_MODELS)
        results = scorer.score("controlnet", TEMPLATES)
        controlnet = next(r for r in results if r["id"] == "official_controlnet")
        assert controlnet["score"] < 1.0
        assert len(controlnet.get("warnings", [])) > 0

    def test_source_precedence_tiebreaker(self):
        from comfy_mcp.templates.scorer import TemplateScorer
        scorer = TemplateScorer(INSTALLED_NODES, INSTALLED_MODELS)
        results = scorer.score("txt2img basic", TEMPLATES)
        # Both txt2img templates match, but official should rank first
        txt2img_results = [r for r in results if "txt2img" in r["id"]]
        assert txt2img_results[0]["id"] == "official_txt2img"

    def test_empty_query_returns_all(self):
        from comfy_mcp.templates.scorer import TemplateScorer
        scorer = TemplateScorer(INSTALLED_NODES, INSTALLED_MODELS)
        results = scorer.score("", TEMPLATES)
        assert len(results) == len(TEMPLATES)

    def test_limit_respected(self):
        from comfy_mcp.templates.scorer import TemplateScorer
        scorer = TemplateScorer(INSTALLED_NODES, INSTALLED_MODELS)
        results = scorer.score("", TEMPLATES, limit=1)
        assert len(results) == 1

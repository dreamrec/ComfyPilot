"""Tests for comfy_extract_schema - workflow-level controllability summary."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.tools.diagnostics import comfy_extract_schema


def _ctx():
    client = MagicMock()
    client.get_history = AsyncMock(return_value={})
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"comfy_client": client}
    return ctx


SD15_TXT2IMG = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "v1-5.safetensors"}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "a sunset", "clip": ["1", 1]}},
    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly, blurry", "clip": ["1", 1]}},
    "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
    "5": {"class_type": "KSampler", "inputs": {
        "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
        "seed": 42, "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
    }},
    "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
    "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "test"}},
}


class TestSummary:
    @pytest.mark.asyncio
    async def test_summary_only_flags(self):
        result = await comfy_extract_schema(workflow=SD15_TXT2IMG, summary_only=True, ctx=_ctx())
        parsed = json.loads(result)
        assert parsed["has_seed"] is True
        assert parsed["has_negative_prompt"] is True
        assert parsed["node_count"] == 7
        assert parsed["model_count"] == 1
        assert parsed["output_node_count"] == 1
        assert "parameters" not in parsed  # summary_only excludes these

    @pytest.mark.asyncio
    async def test_full_extract_lists_parameters(self):
        result = await comfy_extract_schema(workflow=SD15_TXT2IMG, ctx=_ctx())
        parsed = json.loads(result)
        names = {p["name"] for p in parsed["parameters"]}
        assert "seed" in names
        assert "steps" in names
        assert "cfg" in names
        assert "ckpt_name" in names

    @pytest.mark.asyncio
    async def test_model_dependencies_reported(self):
        result = await comfy_extract_schema(workflow=SD15_TXT2IMG, ctx=_ctx())
        parsed = json.loads(result)
        assert len(parsed["model_dependencies"]) == 1
        dep = parsed["model_dependencies"][0]
        assert dep["class_type"] == "CheckpointLoaderSimple"
        assert dep["folder"] == "checkpoints"
        assert dep["value"] == "v1-5.safetensors"

    @pytest.mark.asyncio
    async def test_output_nodes_identified(self):
        result = await comfy_extract_schema(workflow=SD15_TXT2IMG, ctx=_ctx())
        parsed = json.loads(result)
        outputs = [o["class_type"] for o in parsed["output_nodes"]]
        assert "SaveImage" in outputs

    @pytest.mark.asyncio
    async def test_embedding_references_extracted(self):
        wf = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat embedding:lcm  embedding:negative", "clip": ["x", 1]}},
        }
        result = await comfy_extract_schema(workflow=wf, ctx=_ctx())
        parsed = json.loads(result)
        embs = set(parsed["embedding_references"])
        assert "lcm" in embs
        assert "negative" in embs

    @pytest.mark.asyncio
    async def test_editor_format_short_circuits(self):
        editor = {"nodes": [{"id": 1, "type": "X"}], "links": []}
        result = await comfy_extract_schema(workflow=editor, ctx=_ctx())
        parsed = json.loads(result)
        assert "error" in parsed
        assert "editor format" in parsed["error"].lower()

    @pytest.mark.asyncio
    async def test_empty_workflow_errors(self):
        result = await comfy_extract_schema(workflow={}, ctx=_ctx())
        parsed = json.loads(result)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_video_workflow_has_video_output_node(self):
        wf = {
            "1": {"class_type": "VHS_LoadVideo", "inputs": {"video": "input.mp4"}},
            "2": {"class_type": "SaveAnimatedWEBP", "inputs": {"images": ["1", 0], "filename_prefix": "out", "fps": 24}},
        }
        result = await comfy_extract_schema(workflow=wf, summary_only=True, ctx=_ctx())
        parsed = json.loads(result)
        assert parsed["output_node_count"] == 1
        assert parsed["has_seed"] is False

    @pytest.mark.asyncio
    async def test_no_negative_prompt_detected_in_pure_positive_wf(self):
        wf = {
            "1": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        result = await comfy_extract_schema(workflow=wf, summary_only=True, ctx=_ctx())
        parsed = json.loads(result)
        assert parsed["has_negative_prompt"] is False

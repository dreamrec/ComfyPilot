"""Tests for comfy_recommend_runtime and comfy_suggest_timeout."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.tools.diagnostics import comfy_recommend_runtime, comfy_suggest_timeout


def _ctx(stats_response):
    client = MagicMock()
    client.get_system_stats = AsyncMock(return_value=stats_response)
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"comfy_client": client}
    return ctx


class TestRecommendRuntime:
    @pytest.mark.asyncio
    async def test_nvidia_24gb_is_ok_full_support(self):
        """RTX 4090-class card should pass everything."""
        stats = {
            "system": {"os": "Linux"},
            "devices": [{"name": "NVIDIA GeForce RTX 4090", "type": "cuda", "vram_total": 24 * 1024**3, "vram_free": 20 * 1024**3}],
        }
        result = await comfy_recommend_runtime(ctx=_ctx(stats))
        parsed = json.loads(result)
        assert parsed["verdict"] == "ok"
        assert parsed["comfy_cli_flag"] == "--nvidia"
        assert parsed["supports"]["flux2"] is True
        assert parsed["supports"]["video"] is True
        assert parsed["route_to_cloud"] is False

    @pytest.mark.asyncio
    async def test_nvidia_8gb_is_ok_no_flux(self):
        """RTX 3070-class card: SDXL OK, Flux may OOM."""
        stats = {
            "system": {"os": "Linux"},
            "devices": [{"name": "NVIDIA GeForce RTX 3070", "type": "cuda", "vram_total": 8 * 1024**3, "vram_free": 7 * 1024**3}],
        }
        result = await comfy_recommend_runtime(ctx=_ctx(stats))
        parsed = json.loads(result)
        assert parsed["verdict"] == "ok"
        assert parsed["supports"]["sdxl"] is True
        assert parsed["supports"]["flux2"] is False

    @pytest.mark.asyncio
    async def test_nvidia_6gb_is_marginal(self):
        stats = {
            "system": {"os": "Linux"},
            "devices": [{"name": "NVIDIA GTX 1660 Ti", "type": "cuda", "vram_total": 6 * 1024**3, "vram_free": 5 * 1024**3}],
        }
        result = await comfy_recommend_runtime(ctx=_ctx(stats))
        parsed = json.loads(result)
        assert parsed["verdict"] == "marginal"
        assert parsed["supports"]["sd15"] is True
        assert parsed["supports"]["sdxl"] is False

    @pytest.mark.asyncio
    async def test_apple_silicon_64gb_is_ok(self):
        stats = {
            "system": {"os": "Darwin"},
            "devices": [{"name": "Apple M3 Max", "type": "mps", "vram_total": 64 * 1024**3, "vram_free": 50 * 1024**3}],
        }
        result = await comfy_recommend_runtime(ctx=_ctx(stats))
        parsed = json.loads(result)
        assert parsed["verdict"] == "ok"
        assert parsed["comfy_cli_flag"] == "--m-series"
        assert parsed["supports"]["video"] is True

    @pytest.mark.asyncio
    async def test_apple_silicon_16gb_is_marginal(self):
        stats = {
            "system": {"os": "Darwin"},
            "devices": [{"name": "Apple M2", "type": "mps", "vram_total": 16 * 1024**3, "vram_free": 12 * 1024**3}],
        }
        result = await comfy_recommend_runtime(ctx=_ctx(stats))
        parsed = json.loads(result)
        assert parsed["verdict"] == "marginal"
        assert parsed["supports"]["flux2"] is False

    @pytest.mark.asyncio
    async def test_apple_silicon_8gb_is_cloud(self):
        stats = {
            "system": {"os": "Darwin"},
            "devices": [{"name": "Apple M1", "type": "mps", "vram_total": 8 * 1024**3, "vram_free": 6 * 1024**3}],
        }
        result = await comfy_recommend_runtime(ctx=_ctx(stats))
        parsed = json.loads(result)
        assert parsed["verdict"] == "cloud"
        assert parsed["route_to_cloud"] is True

    @pytest.mark.asyncio
    async def test_no_gpu_is_cloud(self):
        stats = {"system": {"os": "Linux"}, "devices": []}
        result = await comfy_recommend_runtime(ctx=_ctx(stats))
        parsed = json.loads(result)
        assert parsed["verdict"] == "cloud"
        assert parsed["comfy_cli_flag"] == "--cpu"

    @pytest.mark.asyncio
    async def test_amd_gpu_picks_amd_flag(self):
        stats = {
            "system": {"os": "Linux"},
            "devices": [{"name": "AMD Radeon RX 7900 XTX", "type": "rocm", "vram_total": 24 * 1024**3, "vram_free": 20 * 1024**3}],
        }
        result = await comfy_recommend_runtime(ctx=_ctx(stats))
        parsed = json.loads(result)
        assert parsed["comfy_cli_flag"] == "--amd"
        assert parsed["verdict"] == "ok"

    @pytest.mark.asyncio
    async def test_reasons_explained(self):
        stats = {
            "system": {"os": "Linux"},
            "devices": [{"name": "RTX 4090", "type": "cuda", "vram_total": 24 * 1024**3, "vram_free": 20 * 1024**3}],
        }
        result = await comfy_recommend_runtime(ctx=_ctx(stats))
        parsed = json.loads(result)
        assert len(parsed["reasons"]) >= 1
        assert any("VRAM" in r or "headroom" in r.lower() for r in parsed["reasons"])

    @pytest.mark.asyncio
    async def test_system_stats_unreachable_falls_back_to_cloud(self):
        client = MagicMock()
        client.get_system_stats = AsyncMock(side_effect=Exception("connection refused"))
        ctx = MagicMock()
        ctx.request_context.lifespan_context = {"comfy_client": client}
        result = await comfy_recommend_runtime(ctx=ctx)
        parsed = json.loads(result)
        assert parsed["verdict"] == "cloud"


class TestSuggestTimeout:
    @pytest.mark.asyncio
    async def test_image_workflow_uses_default(self):
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
            "2": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
            "3": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20, "cfg": 7.0}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
        }
        result = await comfy_suggest_timeout(workflow=wf, ctx=None)
        parsed = json.loads(result)
        assert parsed["suggested_seconds"] == 300
        assert parsed["default_seconds"] == 300

    @pytest.mark.asyncio
    async def test_video_workflow_bumps_to_900(self):
        wf = {
            "1": {"class_type": "LoadVideo", "inputs": {"video": "in.mp4"}},
            "2": {"class_type": "VHS_VideoCombine", "inputs": {"images": ["1", 0]}},
        }
        result = await comfy_suggest_timeout(workflow=wf, ctx=None)
        parsed = json.loads(result)
        assert parsed["suggested_seconds"] == 900
        assert any(d["class_type"] == "VHS_VideoCombine" for d in parsed["drivers"])

    @pytest.mark.asyncio
    async def test_supir_super_resolution_bumps_to_600(self):
        wf = {
            "1": {"class_type": "LoadImage", "inputs": {"image": "in.png"}},
            "2": {"class_type": "SUPIRLoader", "inputs": {}},
            "3": {"class_type": "SUPIREncode", "inputs": {}},
            "4": {"class_type": "SUPIRSample", "inputs": {}},
            "5": {"class_type": "SUPIRDecode", "inputs": {}},
            "6": {"class_type": "SaveImage", "inputs": {}},
        }
        result = await comfy_suggest_timeout(workflow=wf, ctx=None)
        parsed = json.loads(result)
        assert parsed["suggested_seconds"] == 600

    @pytest.mark.asyncio
    async def test_lora_training_bumps_to_3600(self):
        wf = {
            "1": {"class_type": "TrainLoraDataLoader", "inputs": {}},
            "2": {"class_type": "TrainLora", "inputs": {}},
            "3": {"class_type": "SaveLora", "inputs": {}},
        }
        result = await comfy_suggest_timeout(workflow=wf, ctx=None)
        parsed = json.loads(result)
        assert parsed["suggested_seconds"] == 3600

    @pytest.mark.asyncio
    async def test_picks_largest_when_multiple_drivers(self):
        wf = {
            "1": {"class_type": "SaveAnimatedWEBP", "inputs": {}},  # 600
            "2": {"class_type": "VHS_VideoCombine", "inputs": {}},  # 900
        }
        result = await comfy_suggest_timeout(workflow=wf, ctx=None)
        parsed = json.loads(result)
        assert parsed["suggested_seconds"] == 900

    @pytest.mark.asyncio
    async def test_rationale_explains_bump(self):
        wf = {"1": {"class_type": "VHS_VideoCombine", "inputs": {}}}
        result = await comfy_suggest_timeout(workflow=wf, ctx=None)
        parsed = json.loads(result)
        assert "Bumped from 300s to 900s" in parsed["rationale"]

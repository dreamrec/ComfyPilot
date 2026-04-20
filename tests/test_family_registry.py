"""Tests for the family -> intent -> builder registry."""
from __future__ import annotations

import pytest

from comfy_mcp.families.detector import Family
from comfy_mcp.families.registry import build, has, list_families, list_intents


class TestRegistryBaseline:
    def test_sd15_txt2img_registered(self):
        assert has(Family.SD15, "txt2img")

    def test_sd15_intents_present(self):
        intents = set(list_intents(Family.SD15))
        assert {"txt2img", "img2img", "upscale", "inpaint", "controlnet"} <= intents

    def test_sd15_family_listed(self):
        assert Family.SD15 in list_families()


class TestBuild:
    def test_sd15_txt2img_returns_dict(self):
        workflow = build(Family.SD15, "txt2img", {"checkpoint": "v1-5-pruned-emaonly.safetensors"})
        assert isinstance(workflow, dict)
        assert len(workflow) >= 5

    def test_sd15_txt2img_uses_classic_nodes(self):
        workflow = build(Family.SD15, "txt2img", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "CheckpointLoaderSimple" in class_types
        assert "KSampler" in class_types
        assert "VAEDecode" in class_types
        assert "SaveImage" in class_types

    def test_sd15_inpaint_uses_set_latent_noise_mask(self):
        workflow = build(Family.SD15, "inpaint", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "SetLatentNoiseMask" in class_types

    def test_sd15_controlnet_uses_controlnet_apply(self):
        workflow = build(Family.SD15, "controlnet", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "ControlNetApply" in class_types

    def test_params_override(self):
        workflow = build(Family.SD15, "txt2img", {"width": 768, "height": 768, "steps": 30})
        latent = next(n for n in workflow.values() if n["class_type"] == "EmptyLatentImage")
        assert latent["inputs"]["width"] == 768
        assert latent["inputs"]["height"] == 768
        ksampler = next(n for n in workflow.values() if n["class_type"] == "KSampler")
        assert ksampler["inputs"]["steps"] == 30


class TestErrors:
    def test_unknown_intent_raises(self):
        with pytest.raises(KeyError):
            build(Family.SD15, "video2video", {})

    def test_unregistered_family_raises(self):
        # FLUX2 is not yet registered in Task 4 baseline
        with pytest.raises(KeyError):
            build(Family.FLUX2, "txt2img", {})

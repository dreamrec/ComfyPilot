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


class TestFlux2:
    def test_flux2_txt2img_uses_unet_loader(self):
        workflow = build(Family.FLUX2, "txt2img", {"checkpoint": "flux2-klein.safetensors"})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "UNETLoader" in class_types
        assert "DualCLIPLoader" in class_types
        assert "FluxGuidance" in class_types
        assert "SamplerCustomAdvanced" in class_types
        # Flux 2 must NOT use SD 1.5 loader
        assert "CheckpointLoaderSimple" not in class_types

    def test_flux2_uses_sd3_latent(self):
        workflow = build(Family.FLUX2, "txt2img", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "EmptySD3LatentImage" in class_types
        assert "EmptyLatentImage" not in class_types

    def test_flux2_defaults_to_1024px(self):
        workflow = build(Family.FLUX2, "txt2img", {})
        latent = next(n for n in workflow.values() if n["class_type"] == "EmptySD3LatentImage")
        assert latent["inputs"]["width"] == 1024
        assert latent["inputs"]["height"] == 1024

    def test_flux2_guidance_default(self):
        workflow = build(Family.FLUX2, "txt2img", {})
        guidance = next(n for n in workflow.values() if n["class_type"] == "FluxGuidance")
        assert guidance["inputs"]["guidance"] == 3.5


class TestSDXL:
    def test_sdxl_txt2img_defaults_to_1024(self):
        workflow = build(Family.SDXL, "txt2img", {})
        latent = next(n for n in workflow.values() if n["class_type"] == "EmptyLatentImage")
        assert latent["inputs"]["width"] == 1024


class TestSD35:
    def test_sd35_uses_model_sampling_sd3(self):
        workflow = build(Family.SD35, "txt2img", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "ModelSamplingSD3" in class_types
        assert "EmptySD3LatentImage" in class_types


class TestQwen:
    def test_qwen_uses_unet_loader_with_qwen_clip(self):
        workflow = build(Family.QWEN, "txt2img", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "UNETLoader" in class_types
        clip_loader = next(n for n in workflow.values() if n["class_type"] == "CLIPLoader")
        assert clip_loader["inputs"]["type"] == "qwen_image"


class TestWan22:
    def test_wan22_txt2video_is_video_output(self):
        workflow = build(Family.WAN22, "txt2video", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "SaveAnimatedWEBP" in class_types
        assert "EmptyHunyuanLatentVideo" in class_types  # Wan shares Hunyuan latent shape

    def test_wan22_img2video_uses_image_conditioning(self):
        workflow = build(Family.WAN22, "img2video", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "WanImageToVideo" in class_types
        assert "LoadImage" in class_types


class TestLTX2:
    def test_ltx2_uses_ltxv_nodes(self):
        workflow = build(Family.LTX2, "txt2video", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "LTXVConditioning" in class_types
        assert "LTXVScheduler" in class_types
        assert "EmptyLTXVLatentVideo" in class_types


class TestHunyuanVideo:
    def test_hunyuan_video_txt2video(self):
        workflow = build(Family.HUNYUAN_VIDEO, "txt2video", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "EmptyHunyuanLatentVideo" in class_types
        assert "DualCLIPLoader" in class_types
        dcl = next(n for n in workflow.values() if n["class_type"] == "DualCLIPLoader")
        assert dcl["inputs"]["type"] == "hunyuan_video"

    def test_hunyuan_video_img2video_uses_image_node(self):
        workflow = build(Family.HUNYUAN_VIDEO, "img2video", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "HunyuanImageToVideo" in class_types


class TestHunyuan3D:
    def test_hunyuan_3d_uses_3d_latent(self):
        workflow = build(Family.HUNYUAN_3D, "image2_3d", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "EmptyLatentHunyuan3Dv2" in class_types
        assert "VAEDecodeHunyuan3D" in class_types
        assert "SaveGLB" in class_types


class TestAceStep:
    def test_ace_step_uses_music_nodes(self):
        workflow = build(Family.ACE_STEP, "txt2music", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "EmptyAceStepLatentAudio" in class_types
        assert "TextEncodeAceStepAudio" in class_types
        assert "VAEDecodeAudio" in class_types
        assert "SaveAudio" in class_types


class TestAllFamiliesRegistered:
    def test_every_supported_family_has_at_least_one_intent(self):
        for family in [
            Family.SD15, Family.SDXL, Family.SD35, Family.FLUX2,
            Family.QWEN, Family.WAN22, Family.LTX2,
            Family.HUNYUAN_VIDEO, Family.HUNYUAN_3D, Family.ACE_STEP,
        ]:
            assert list_intents(family), f"{family} has no registered intents"


class TestErrors:
    def test_unknown_intent_raises(self):
        with pytest.raises(KeyError):
            build(Family.SD15, "video2video", {})

    def test_flux1_not_registered(self):
        # FLUX1 intentionally not registered - Flux.1 users should use community templates
        with pytest.raises(KeyError):
            build(Family.FLUX1, "txt2img", {})

    def test_sd3_not_registered(self):
        # SD 3 (not 3.5) is deprecated - users should upgrade to SD 3.5
        with pytest.raises(KeyError):
            build(Family.SD3, "txt2img", {})

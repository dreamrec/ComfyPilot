"""Tests for family-agnostic intent overrides (SUPIR, RIFE/FILM, SAM 3.1, train_lora, audio_t2a).

These intents dispatch through the intent-override map instead of family
detection. They take precedence over family routing.
"""
from __future__ import annotations

import pytest

from comfy_mcp.families.registry import (
    build_intent,
    has_intent_override,
    list_intent_overrides,
)


class TestSupir:
    def test_super_resolution_is_intent_override(self):
        assert has_intent_override("super_resolution")

    def test_super_resolution_uses_supir_nodes(self):
        workflow = build_intent("super_resolution", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "SUPIRLoader" in class_types
        assert "SUPIREncode" in class_types
        assert "SUPIRSample" in class_types
        assert "SUPIRDecode" in class_types
        assert "LoadImage" in class_types
        assert "SaveImage" in class_types

    def test_super_resolution_seed_override(self):
        workflow = build_intent("super_resolution", {"seed": 7777})
        sampler = next(n for n in workflow.values() if n["class_type"] == "SUPIRSample")
        assert sampler["inputs"]["seed"] == 7777

    def test_super_resolution_image_override(self):
        workflow = build_intent("super_resolution", {"image": "myphoto.png"})
        loader = next(n for n in workflow.values() if n["class_type"] == "LoadImage")
        assert loader["inputs"]["image"] == "myphoto.png"


class TestInterpolation:
    def test_interpolate_frames_is_intent_override(self):
        assert has_intent_override("interpolate_frames")

    def test_rife_default(self):
        workflow = build_intent("interpolate_frames", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "RIFE_VFI" in class_types
        assert "FILM_VFI" not in class_types
        assert "LoadVideo" in class_types
        assert "SaveAnimatedWEBP" in class_types

    def test_film_method(self):
        workflow = build_intent("interpolate_frames", {"method": "film"})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "FILM_VFI" in class_types
        assert "RIFE_VFI" not in class_types

    def test_multiplier_affects_output_fps(self):
        workflow = build_intent("interpolate_frames", {"fps": 30, "multiplier": 4})
        save = next(n for n in workflow.values() if n["class_type"] == "SaveAnimatedWEBP")
        assert save["inputs"]["fps"] == 120  # 30 * 4

    def test_video_param_override(self):
        workflow = build_intent("interpolate_frames", {"video": "myclip.mp4"})
        loader = next(n for n in workflow.values() if n["class_type"] == "LoadVideo")
        assert loader["inputs"]["video"] == "myclip.mp4"


class TestAudioT2A:
    def test_txt2audio_is_intent_override(self):
        assert has_intent_override("txt2audio")

    def test_txt2audio_uses_audio_nodes(self):
        workflow = build_intent("txt2audio", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "ConditioningStableAudio" in class_types
        assert "EmptyLatentAudio" in class_types
        assert "VAEDecodeAudio" in class_types
        assert "SaveAudio" in class_types

    def test_txt2audio_duration_override(self):
        workflow = build_intent("txt2audio", {"duration_s": 30.0})
        latent = next(n for n in workflow.values() if n["class_type"] == "EmptyLatentAudio")
        assert latent["inputs"]["seconds"] == 30.0


class TestTrainLora:
    def test_train_lora_is_intent_override(self):
        assert has_intent_override("train_lora")

    def test_train_lora_uses_native_trainer_nodes(self):
        workflow = build_intent("train_lora", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "TrainLoraDataLoader" in class_types
        assert "TrainLora" in class_types
        assert "SaveLora" in class_types

    def test_train_lora_rank_override(self):
        workflow = build_intent("train_lora", {"rank": 32})
        trainer = next(n for n in workflow.values() if n["class_type"] == "TrainLora")
        assert trainer["inputs"]["rank"] == 32

    def test_train_lora_steps_override(self):
        workflow = build_intent("train_lora", {"steps": 5000})
        trainer = next(n for n in workflow.values() if n["class_type"] == "TrainLora")
        assert trainer["inputs"]["steps"] == 5000


class TestSegment:
    def test_segment_is_intent_override(self):
        assert has_intent_override("segment")

    def test_segment_uses_sam3_nodes(self):
        workflow = build_intent("segment", {})
        class_types = {n["class_type"] for n in workflow.values()}
        assert "SAM3Loader" in class_types
        assert "SAM3Segment" in class_types
        assert "LoadImage" in class_types
        assert "MaskToImage" in class_types
        assert "SaveImage" in class_types

    def test_segment_prompt_override(self):
        workflow = build_intent("segment", {"prompt": "the red car"})
        seg = next(n for n in workflow.values() if n["class_type"] == "SAM3Segment")
        assert seg["inputs"]["text_prompt"] == "the red car"

    def test_segment_threshold_override(self):
        workflow = build_intent("segment", {"threshold": 0.75})
        seg = next(n for n in workflow.values() if n["class_type"] == "SAM3Segment")
        assert seg["inputs"]["threshold"] == 0.75


class TestErrors:
    def test_unknown_intent_override_raises(self):
        with pytest.raises(KeyError):
            build_intent("nonexistent_intent", {})


class TestRegistration:
    def test_super_resolution_is_listed(self):
        assert "super_resolution" in list_intent_overrides()

    def test_interpolate_frames_is_listed(self):
        assert "interpolate_frames" in list_intent_overrides()

    def test_segment_is_listed(self):
        assert "segment" in list_intent_overrides()

    def test_train_lora_is_listed(self):
        assert "train_lora" in list_intent_overrides()

    def test_txt2audio_is_listed(self):
        assert "txt2audio" in list_intent_overrides()

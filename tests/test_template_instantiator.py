"""Tests for TemplateInstantiator -- model substitution and workflow output."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


SNAPSHOT = {
    "node_classes": {"KSampler", "CheckpointLoaderSimple", "CLIPTextEncode", "VAEDecode", "SaveImage", "EmptyLatentImage"},
    "models": {"checkpoints": ["dreamshaper_8.safetensors"], "loras": [], "controlnet": []},
    "embeddings": [],
    "object_info": {
        "KSampler": {"input": {"required": {"seed": ["INT"]}}, "output": ["LATENT"]},
        "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["dreamshaper_8.safetensors"]]}}, "output": ["MODEL", "CLIP", "VAE"]},
        "SaveImage": {"input": {"required": {"images": ["IMAGE"]}}, "output": [], "output_node": True},
    },
}


TEMPLATE_WITH_WORKFLOW = {
    "id": "builtin_txt2img",
    "name": "txt2img_basic",
    "workflow": {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
        "2": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20, "cfg": 7.0,
              "sampler_name": "euler", "scheduler": "normal",
              "model": ["1", 0], "positive": ["1", 1], "negative": ["1", 2], "latent_image": ["3", 0]}},
        "3": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "4": {"class_type": "VAEDecode", "inputs": {"samples": ["2", 0], "vae": ["1", 2]}},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["4", 0]}},
    },
}


class TestInstantiation:
    def test_substitutes_checkpoint(self):
        from comfy_mcp.templates.instantiator import TemplateInstantiator
        inst = TemplateInstantiator(SNAPSHOT)
        result = inst.instantiate(TEMPLATE_WITH_WORKFLOW)
        wf = result["workflow"]
        assert wf["1"]["inputs"]["ckpt_name"] == "dreamshaper_8.safetensors"

    def test_applies_overrides(self):
        from comfy_mcp.templates.instantiator import TemplateInstantiator
        inst = TemplateInstantiator(SNAPSHOT)
        result = inst.instantiate(TEMPLATE_WITH_WORKFLOW, overrides={"width": 768, "height": 768})
        wf = result["workflow"]
        assert wf["3"]["inputs"]["width"] == 768

    def test_unknown_override_produces_warning(self):
        from comfy_mcp.templates.instantiator import TemplateInstantiator
        inst = TemplateInstantiator(SNAPSHOT)
        result = inst.instantiate(TEMPLATE_WITH_WORKFLOW, overrides={"nonexistent_param": 42})
        assert len(result.get("warnings", [])) > 0

    def test_returns_ready_status_for_valid_workflow(self):
        from comfy_mcp.templates.instantiator import TemplateInstantiator
        inst = TemplateInstantiator(SNAPSHOT)
        result = inst.instantiate(TEMPLATE_WITH_WORKFLOW)
        assert result["status"] in ("ready", "warnings")

    def test_missing_model_produces_warning(self):
        from comfy_mcp.templates.instantiator import TemplateInstantiator
        snapshot = dict(SNAPSHOT)
        snapshot["models"] = {"checkpoints": [], "loras": [], "controlnet": []}
        inst = TemplateInstantiator(snapshot)
        result = inst.instantiate(TEMPLATE_WITH_WORKFLOW)
        assert any("model" in w.lower() or "checkpoint" in w.lower() for w in result.get("warnings", []))

    def test_modern_inputs_prefer_modern_model_folders(self):
        from comfy_mcp.templates.instantiator import TemplateInstantiator

        snapshot = {
            "models": {
                "diffusion_models": ["qwen_image_fp8.safetensors"],
                "text_encoders": ["qwen_2.5_vl_7b_fp8_scaled.safetensors"],
                "vae": ["qwen_image_vae.safetensors"],
                "checkpoints": ["legacy.safetensors"],
                "clip": ["clip_l.safetensors"],
            }
        }
        template = {
            "id": "official_qwen",
            "name": "qwen",
            "workflow": {
                "1": {
                    "class_type": "LoadDiffusionModel",
                    "inputs": {
                        "unet_name": "missing_unet.safetensors",
                        "clip_name": "missing_text_encoder.safetensors",
                        "vae_name": "missing_vae.safetensors",
                    },
                }
            },
        }

        result = TemplateInstantiator(snapshot).instantiate(template)
        inputs = result["workflow"]["1"]["inputs"]
        assert inputs["unet_name"] == "qwen_image_fp8.safetensors"
        assert inputs["clip_name"] == "qwen_2.5_vl_7b_fp8_scaled.safetensors"
        assert inputs["vae_name"] == "qwen_image_vae.safetensors"

"""Tests for conservative UI workflow translation."""

from __future__ import annotations


OBJECT_INFO = {
    "CheckpointLoaderSimple": {
        "input": {"required": {"ckpt_name": [["model.safetensors"]]}},
        "output": ["MODEL", "CLIP", "VAE"],
        "category": "loaders",
    },
    "CLIPTextEncode": {
        "input": {"required": {"text": ["STRING"], "clip": ["CLIP"]}},
        "output": ["CONDITIONING"],
        "category": "conditioning",
    },
    "EmptyLatentImage": {
        "input": {"required": {"width": ["INT"], "height": ["INT"], "batch_size": ["INT"]}},
        "output": ["LATENT"],
        "category": "latent",
    },
    "KSampler": {
        "input": {
            "required": {
                "model": ["MODEL"],
                "seed": ["INT"],
                "steps": ["INT"],
                "cfg": ["FLOAT"],
                "sampler_name": [["euler"]],
                "scheduler": [["normal"]],
                "positive": ["CONDITIONING"],
                "negative": ["CONDITIONING"],
                "latent_image": ["LATENT"],
                "denoise": ["FLOAT"],
            }
        },
        "output": ["LATENT"],
        "category": "sampling",
    },
    "VAEDecode": {
        "input": {"required": {"samples": ["LATENT"], "vae": ["VAE"]}},
        "output": ["IMAGE"],
        "category": "latent",
    },
    "SaveImage": {
        "input": {"required": {"images": ["IMAGE"]}, "optional": {"filename_prefix": ["STRING"]}},
        "output": [],
        "output_node": True,
        "category": "image",
    },
}


UI_WORKFLOW = {
    "nodes": [
        {"id": 90, "type": "MarkdownNote", "inputs": [], "widgets_values": ["hello"]},
        {"id": 1, "type": "CheckpointLoaderSimple", "inputs": [], "widgets_values": ["model.safetensors"]},
        {"id": 2, "type": "CLIPTextEncode", "inputs": [{"name": "clip", "link": 10}], "widgets_values": ["a cat"]},
        {"id": 3, "type": "CLIPTextEncode", "inputs": [{"name": "clip", "link": 11}], "widgets_values": ["bad"]},
        {"id": 4, "type": "EmptyLatentImage", "inputs": [], "widgets_values": [512, 512, 1]},
        {
            "id": 5,
            "type": "KSampler",
            "inputs": [
                {"name": "model", "link": 12},
                {"name": "positive", "link": 13},
                {"name": "negative", "link": 14},
                {"name": "latent_image", "link": 15},
            ],
            "widgets_values": [42, "randomize", 20, 7.0, "euler", "normal", 1.0],
        },
        {"id": 6, "type": "VAEDecode", "inputs": [{"name": "samples", "link": 16}, {"name": "vae", "link": 17}], "widgets_values": []},
        {"id": 7, "type": "SaveImage", "inputs": [{"name": "images", "link": 18}], "widgets_values": ["ComfyPilot"]},
    ],
    "links": [
        [10, 1, 1, 2, 0, "CLIP"],
        [11, 1, 1, 3, 0, "CLIP"],
        [12, 1, 0, 5, 0, "MODEL"],
        [13, 2, 0, 5, 1, "CONDITIONING"],
        [14, 3, 0, 5, 2, "CONDITIONING"],
        [15, 4, 0, 5, 3, "LATENT"],
        [16, 5, 0, 6, 0, "LATENT"],
        [17, 1, 2, 6, 1, "VAE"],
        [18, 6, 0, 7, 0, "IMAGE"],
    ],
}


class TestTranslateWorkflow:
    def test_translate_ui_workflow(self):
        from comfy_mcp.workflow_translation import translate_workflow

        result = translate_workflow(UI_WORKFLOW, OBJECT_INFO)
        assert result["status"] == "translated"
        assert result["workflow"] is not None
        assert result["workflow"]["1"]["class_type"] == "CheckpointLoaderSimple"
        assert result["workflow"]["5"]["inputs"]["seed"] == 42
        assert result["workflow"]["5"]["inputs"]["steps"] == 20
        assert result["workflow"]["7"]["inputs"]["filename_prefix"] == "ComfyPilot"

    def test_translate_reports_unsupported_nodes(self):
        from comfy_mcp.workflow_translation import translate_workflow

        workflow = {
            "nodes": [
                {"id": 1, "type": "MysteryCustomNode", "inputs": [], "widgets_values": ["prompt"]},
                {"id": 2, "type": "SaveImage", "inputs": [{"name": "images", "link": 10}], "widgets_values": ["Out"]},
            ],
            "links": [[10, 1, 0, 2, 0, "IMAGE"]],
        }
        result = translate_workflow(workflow, OBJECT_INFO)
        assert result["status"] == "partial"
        assert result["unsupported_nodes"][0]["node_type"] == "MysteryCustomNode"

    def test_translate_inlines_primitive_node(self):
        from comfy_mcp.workflow_translation import translate_workflow

        workflow = {
            "nodes": [
                {"id": 1, "type": "PrimitiveNode", "inputs": [], "widgets_values": ["model.safetensors"]},
                {"id": 2, "type": "CheckpointLoaderSimple", "inputs": [{"name": "ckpt_name", "link": 10}], "widgets_values": []},
            ],
            "links": [[10, 1, 0, 2, 0, "STRING"]],
        }
        result = translate_workflow(workflow, OBJECT_INFO)
        assert result["status"] == "translated"
        assert result["workflow"]["2"]["inputs"]["ckpt_name"] == "model.safetensors"

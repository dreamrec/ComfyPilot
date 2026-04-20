"""SDXL family templates.

SDXL uses the same CheckpointLoaderSimple + KSampler topology as SD 1.5,
but with 1024x1024 default resolution and a CLIPTextEncodeSDXL node for
prompt encoding that bakes in the two CLIP encoders SDXL expects.

Reference: ComfyUI SDXL workflow templates.
"""
from __future__ import annotations


def txt2img(params: dict) -> dict:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": params.get("checkpoint", "sd_xl_base_1.0.safetensors")},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("positive", "cinematic portrait, sharp focus"), "clip": ["1", 1]},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("negative", "blurry, low quality"), "clip": ["1", 1]},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": params.get("width", 1024),
                "height": params.get("height", 1024),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 25),
                "cfg": params.get("cfg", 7.5),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "karras"),
                "denoise": params.get("denoise", 1.0),
            },
        },
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {
            "class_type": "SaveImage",
            "inputs": {"images": ["6", 0], "filename_prefix": params.get("filename_prefix", "ComfyPilot_sdxl")},
        },
    }


TEMPLATES = {"txt2img": txt2img}

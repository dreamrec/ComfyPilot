"""SD 3.5 family templates.

SD 3.5 uses the MMDiT architecture with triple-text-encoder conditioning
(CLIP-L + CLIP-G + T5XXL). It can be loaded as a combined checkpoint via
CheckpointLoaderSimple, and uses ModelSamplingSD3 to set the sigma shift
expected by SD3 sampling.

Reference: ComfyUI SD 3.5 workflow templates.
"""
from __future__ import annotations


def txt2img(params: dict) -> dict:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": params.get("checkpoint", "sd3.5_large.safetensors")},
        },
        "2": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"model": ["1", 0], "shift": params.get("shift", 3.0)},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("positive", "professional photograph, detailed"), "clip": ["1", 1]},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("negative", ""), "clip": ["1", 1]},
        },
        "5": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {
                "width": params.get("width", 1024),
                "height": params.get("height", 1024),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["2", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 28),
                "cfg": params.get("cfg", 4.5),
                "sampler_name": params.get("sampler", "dpmpp_2m"),
                "scheduler": params.get("scheduler", "sgm_uniform"),
                "denoise": params.get("denoise", 1.0),
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {
            "class_type": "SaveImage",
            "inputs": {"images": ["7", 0], "filename_prefix": params.get("filename_prefix", "ComfyPilot_sd35")},
        },
    }


TEMPLATES = {"txt2img": txt2img}

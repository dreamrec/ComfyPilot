"""Qwen-Image templates.

Qwen-Image-2.0 / Qwen-Image-2512 uses its own DiT with a Qwen text encoder.
ComfyUI exposes it via UNETLoader + CLIPLoader with clip_type=qwen_image,
its own VAELoader, and the same SamplerCustomAdvanced path as Flux.

Confirm node names against your live ComfyUI if this template 404s.
"""
from __future__ import annotations


def txt2img(params: dict) -> dict:
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": params.get("checkpoint", "qwen-image-2512.safetensors"),
                "weight_dtype": params.get("weight_dtype", "default"),
            },
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": params.get("clip_name", "qwen_2.5_vl_7b_fp8_scaled.safetensors"),
                "type": "qwen_image",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": params.get("vae", "qwen_image_vae.safetensors")},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("positive", "a detailed photograph of a quiet street at dusk"),
                "clip": ["2", 0],
            },
        },
        "5": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {
                "width": params.get("width", 1328),
                "height": params.get("height", 1328),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "6": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": params.get("sampler", "euler")},
        },
        "7": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": ["1", 0],
                "scheduler": params.get("scheduler", "simple"),
                "steps": params.get("steps", 20),
                "denoise": 1.0,
            },
        },
        "8": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": params.get("seed", 42)},
        },
        "9": {
            "class_type": "BasicGuider",
            "inputs": {"model": ["1", 0], "conditioning": ["4", 0]},
        },
        "10": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["8", 0],
                "guider": ["9", 0],
                "sampler": ["6", 0],
                "sigmas": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["3", 0]}},
        "12": {
            "class_type": "SaveImage",
            "inputs": {"images": ["11", 0], "filename_prefix": params.get("filename_prefix", "ComfyPilot_qwen")},
        },
    }


TEMPLATES = {"txt2img": txt2img}

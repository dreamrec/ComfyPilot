"""Ernie Image templates (ComfyUI v0.19.0+).

Baidu's Ernie Image is a new image-generation family added to ComfyUI in
v0.19.0 (general support) and v0.19.1 (Ernie Image Text to Image). It loads
via UNETLoader (weights live in `diffusion_models/`) with a dedicated Ernie
text encoder. v0.19.2 fixed the class name to `ErnieTEModel_` with a
trailing underscore - the CLIPLoader `type="ernie_image"` is the public
selector that doesn't change.

Topology mirrors Qwen-Image / Flux 2: UNETLoader + CLIPLoader + VAELoader +
EmptySD3LatentImage + KSamplerSelect + BasicScheduler + RandomNoise +
BasicGuider + SamplerCustomAdvanced + VAEDecode + SaveImage.
"""
from __future__ import annotations


def txt2img(params: dict) -> dict:
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": params.get("checkpoint", "ernie_image_v1.safetensors"),
                "weight_dtype": params.get("weight_dtype", "default"),
            },
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": params.get("clip_name", "ernie_te_fp16.safetensors"),
                "type": "ernie_image",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": params.get("vae", "ernie_image_vae.safetensors")},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("positive", "a detailed photograph"),
                "clip": ["2", 0],
            },
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
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": params.get("sampler", "euler")},
        },
        "7": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": ["1", 0],
                "scheduler": params.get("scheduler", "simple"),
                "steps": params.get("steps", 20),
                "denoise": params.get("denoise", 1.0),
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
            "inputs": {
                "images": ["11", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_ernie"),
            },
        },
    }


TEMPLATES = {"txt2img": txt2img}

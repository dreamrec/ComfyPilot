"""Flux 2 / Flux 2 Klein templates.

Reference: ComfyUI v0.17+ Flux 2 workflow. Core difference from SD 1.5:
- UNETLoader instead of CheckpointLoaderSimple
- DualCLIPLoader (T5XXL + CLIP-L) for conditioning
- Separate VAELoader
- EmptySD3LatentImage (shared SD3/Flux latent shape)
- FluxGuidance node sets CFG-free guidance strength
- SamplerCustomAdvanced with RandomNoise + BasicGuider + BasicScheduler

Default checkpoint hint: 'flux2-klein.safetensors'. Callers should pass the
actual installed checkpoint name. Confirm CLIP/VAE filenames against the
local install - ComfyUI ships these separately from the UNET.
"""
from __future__ import annotations


def txt2img(params: dict) -> dict:
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": params.get("checkpoint", "flux2-klein.safetensors"),
                "weight_dtype": params.get("weight_dtype", "default"),
            },
        },
        "2": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": params.get("clip_name1", "t5xxl_fp16.safetensors"),
                "clip_name2": params.get("clip_name2", "clip_l.safetensors"),
                "type": "flux",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": params.get("vae", "ae.safetensors")},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("positive", "a cinematic landscape, golden hour"),
                "clip": ["2", 0],
            },
        },
        "5": {
            "class_type": "FluxGuidance",
            "inputs": {
                "conditioning": ["4", 0],
                "guidance": params.get("guidance", 3.5),
            },
        },
        "6": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {
                "width": params.get("width", 1024),
                "height": params.get("height", 1024),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "7": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": params.get("sampler", "euler")},
        },
        "8": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": ["1", 0],
                "scheduler": params.get("scheduler", "simple"),
                "steps": params.get("steps", 20),
                "denoise": params.get("denoise", 1.0),
            },
        },
        "9": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": params.get("seed", 42)},
        },
        "10": {
            "class_type": "BasicGuider",
            "inputs": {"model": ["1", 0], "conditioning": ["5", 0]},
        },
        "11": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["9", 0],
                "guider": ["10", 0],
                "sampler": ["7", 0],
                "sigmas": ["8", 0],
                "latent_image": ["6", 0],
            },
        },
        "12": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["11", 0], "vae": ["3", 0]},
        },
        "13": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["12", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_flux2"),
            },
        },
    }


TEMPLATES = {
    "txt2img": txt2img,
}

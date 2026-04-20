"""Wan 2.2 templates (MoE text-to-video and image-to-video).

Wan 2.2 is an Apache-2.0 video DiT with a Mixture-of-Experts architecture.
ComfyUI v0.19+ exposes it via a UNETLoader for the diffusion transformer,
a CLIPLoader with type='wan', its VAE, and a KSampler variant tuned for
the model's sigma schedule.

Reference: https://docs.comfy.org/tutorials/video/wan/wan2_2

Node names below match the Comfy-Org/workflow_templates reference as of
2026-04. Verify against live object_info if the queue rejects them.
"""
from __future__ import annotations


def _common_wan_nodes(params: dict) -> dict:
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": params.get("checkpoint", "wan2.2-t2v-14b.safetensors"),
                "weight_dtype": params.get("weight_dtype", "default"),
            },
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": params.get("clip_name", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"),
                "type": "wan",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": params.get("vae", "wan_2.1_vae.safetensors")},
        },
    }


def txt2video(params: dict) -> dict:
    nodes = _common_wan_nodes(params)
    nodes.update({
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("positive", "a sweeping cinematic shot over a mountain lake"),
                "clip": ["2", 0],
            },
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("negative", "low quality, static"), "clip": ["2", 0]},
        },
        "6": {
            "class_type": "EmptyHunyuanLatentVideo",
            "inputs": {
                "width": params.get("width", 832),
                "height": params.get("height", 480),
                "length": params.get("length", 81),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["6", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 30),
                "cfg": params.get("cfg", 6.0),
                "sampler_name": params.get("sampler", "uni_pc"),
                "scheduler": params.get("scheduler", "simple"),
                "denoise": 1.0,
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {
            "class_type": "SaveAnimatedWEBP",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_wan22"),
                "fps": params.get("fps", 16),
                "quality": 80,
            },
        },
    })
    return nodes


def img2video(params: dict) -> dict:
    nodes = _common_wan_nodes(params)
    nodes.update({
        "4": {"class_type": "LoadImage", "inputs": {"image": params.get("image", "input.png")}},
        "5": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": params.get("clip_vision", "clip_vision_h.safetensors")}},
        "6": {"class_type": "CLIPVisionEncode", "inputs": {"clip_vision": ["5", 0], "image": ["4", 0]}},
        "7": {
            "class_type": "WanImageToVideo",
            "inputs": {
                "positive": params.get("positive", "smooth cinematic motion"),
                "negative": params.get("negative", "low quality"),
                "clip_vision_output": ["6", 0],
                "start_image": ["4", 0],
                "vae": ["3", 0],
                "length": params.get("length", 81),
                "width": params.get("width", 832),
                "height": params.get("height", 480),
                "batch_size": params.get("batch_size", 1),
                "clip": ["2", 0],
            },
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["7", 0],
                "negative": ["7", 1],
                "latent_image": ["7", 2],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 30),
                "cfg": params.get("cfg", 6.0),
                "sampler_name": params.get("sampler", "uni_pc"),
                "scheduler": params.get("scheduler", "simple"),
                "denoise": 1.0,
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {
            "class_type": "SaveAnimatedWEBP",
            "inputs": {
                "images": ["9", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_wan22_i2v"),
                "fps": params.get("fps", 16),
                "quality": 80,
            },
        },
    })
    return nodes


TEMPLATES = {"txt2video": txt2video, "img2video": img2video}

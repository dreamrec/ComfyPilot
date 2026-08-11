"""LTX-Video / LTX-2 templates.

LTX-2 is the fastest class of open video model (5-sec clip in ~4s on
RTX 4090). ComfyUI exposes it via a CheckpointLoaderSimple that bundles
the UNET + text encoder + VAE, plus LTXVConditioning and LTXVScheduler
nodes for the model-specific denoising curve.
"""
from __future__ import annotations


def txt2video(params: dict) -> dict:
    if params.get("model_folder") == "diffusion_models":
        return _txt2video_separate_models(params)

    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": params.get("checkpoint", "ltx-video-2b-v0.9.safetensors")},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("positive", "a time-lapse of clouds over a mountain"), "clip": ["1", 1]},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("negative", "low quality, flicker"), "clip": ["1", 1]},
        },
        "4": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["2", 0],
                "negative": ["3", 0],
                "frame_rate": params.get("fps", 25),
            },
        },
        "5": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": params.get("width", 768),
                "height": params.get("height", 512),
                "length": params.get("length", 121),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "6": {
            "class_type": "LTXVScheduler",
            "inputs": {
                "steps": params.get("steps", 30),
                "max_shift": 2.05,
                "base_shift": 0.95,
                "stretch": True,
                "terminal": 0.1,
                "latent": ["5", 0],
            },
        },
        "7": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": params.get("sampler", "euler")},
        },
        "8": {
            "class_type": "SamplerCustom",
            "inputs": {
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["4", 1],
                "sampler": ["7", 0],
                "sigmas": ["6", 0],
                "latent_image": ["5", 0],
                "add_noise": True,
                "noise_seed": params.get("seed", 42),
                "cfg": params.get("cfg", 3.0),
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
        "10": {
            "class_type": "SaveAnimatedWEBP",
            "inputs": {
                "images": ["9", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_ltx2"),
                "fps": params.get("fps", 25),
                "quality": 80,
            },
        },
    }


TEMPLATES = {"txt2video": txt2video}


def _txt2video_separate_models(params: dict) -> dict:
    """LTX transformer-only layout for models stored in diffusion_models/."""
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": params["checkpoint"],
                "weight_dtype": params.get("weight_dtype", "default"),
            },
        },
        "2": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": params.get("clip_name1", "gemma_3_12B_it_fpmixed.safetensors"),
                "clip_name2": params.get("clip_name2", "ltx-2.3_text_projection_bf16.safetensors"),
                "type": "ltxv",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": params.get("vae", "LTX23_video_vae_bf16_KJ.safetensors")},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("positive", "a time-lapse of clouds over a mountain"),
                "clip": ["2", 0],
            },
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("negative", "low quality, flicker"), "clip": ["2", 0]},
        },
        "6": {
            "class_type": "LTXVConditioning",
            "inputs": {"positive": ["4", 0], "negative": ["5", 0], "frame_rate": params.get("fps", 25)},
        },
        "7": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": params.get("width", 768), "height": params.get("height", 512),
                "length": params.get("length", 97), "batch_size": params.get("batch_size", 1),
            },
        },
        "8": {
            "class_type": "LTXVScheduler",
            "inputs": {
                "steps": params.get("steps", 20), "max_shift": params.get("max_shift", 2.05),
                "base_shift": params.get("base_shift", 0.95), "stretch": True,
                "terminal": 0.1, "latent": ["7", 0],
            },
        },
        "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": params.get("sampler", "euler")}},
        "10": {
            "class_type": "SamplerCustom",
            "inputs": {
                "model": ["1", 0], "positive": ["6", 0], "negative": ["6", 1],
                "sampler": ["9", 0], "sigmas": ["8", 0], "latent_image": ["7", 0],
                "add_noise": True, "noise_seed": params.get("seed", 42), "cfg": params.get("cfg", 3.0),
            },
        },
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["3", 0]}},
        "12": {
            "class_type": "SaveAnimatedWEBP",
            "inputs": {
                "images": ["11", 0], "filename_prefix": params.get("filename_prefix", "ComfyPilot_ltx2"),
                "fps": params.get("fps", 25), "quality": 80,
            },
        },
    }

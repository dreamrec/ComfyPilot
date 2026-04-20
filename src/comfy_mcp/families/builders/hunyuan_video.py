"""HunyuanVideo 1.5 templates (txt2video + img2video).

Hunyuan Video is a 13B DiT with strong face rendering. ComfyUI v0.19
exposes it via UNETLoader + DualCLIPLoader (LLaMA + CLIP) + VAELoader,
and uses EmptyHunyuanLatentVideo as the latent primitive.
"""
from __future__ import annotations


def _common(params: dict) -> dict:
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": params.get("checkpoint", "hunyuan-video-t2v-720p.safetensors"),
                "weight_dtype": params.get("weight_dtype", "default"),
            },
        },
        "2": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": params.get("clip_name1", "llava_llama3_fp16.safetensors"),
                "clip_name2": params.get("clip_name2", "clip_l.safetensors"),
                "type": "hunyuan_video",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": params.get("vae", "hunyuan_video_vae_bf16.safetensors")},
        },
    }


def txt2video(params: dict) -> dict:
    nodes = _common(params)
    nodes.update({
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": params.get("positive", "a character walking through a neon-lit alley at night"),
                "clip": ["2", 0],
            },
        },
        "5": {
            "class_type": "EmptyHunyuanLatentVideo",
            "inputs": {
                "width": params.get("width", 720),
                "height": params.get("height", 480),
                "length": params.get("length", 73),
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
                "steps": params.get("steps", 30),
                "denoise": 1.0,
            },
        },
        "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": params.get("seed", 42)}},
        "9": {"class_type": "BasicGuider", "inputs": {"model": ["1", 0], "conditioning": ["4", 0]}},
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
            "class_type": "SaveAnimatedWEBP",
            "inputs": {
                "images": ["11", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_hyv"),
                "fps": params.get("fps", 24),
                "quality": 80,
            },
        },
    })
    return nodes


def img2video(params: dict) -> dict:
    """Hunyuan I2V adds an image-conditioning encoder and HunyuanImageToVideo node."""
    nodes = _common(params)
    nodes.update({
        "4": {"class_type": "LoadImage", "inputs": {"image": params.get("image", "input.png")}},
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("positive", "subtle motion, cinematic"), "clip": ["2", 0]},
        },
        "6": {
            "class_type": "HunyuanImageToVideo",
            "inputs": {
                "positive": ["5", 0],
                "vae": ["3", 0],
                "start_image": ["4", 0],
                "width": params.get("width", 720),
                "height": params.get("height", 480),
                "length": params.get("length", 73),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "7": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": params.get("sampler", "euler")}},
        "8": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": ["1", 0],
                "scheduler": params.get("scheduler", "simple"),
                "steps": params.get("steps", 30),
                "denoise": 1.0,
            },
        },
        "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": params.get("seed", 42)}},
        "10": {"class_type": "BasicGuider", "inputs": {"model": ["1", 0], "conditioning": ["6", 0]}},
        "11": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["9", 0],
                "guider": ["10", 0],
                "sampler": ["7", 0],
                "sigmas": ["8", 0],
                "latent_image": ["6", 1],
            },
        },
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "13": {
            "class_type": "SaveAnimatedWEBP",
            "inputs": {
                "images": ["12", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_hyv_i2v"),
                "fps": params.get("fps", 24),
                "quality": 80,
            },
        },
    })
    return nodes


TEMPLATES = {"txt2video": txt2video, "img2video": img2video}

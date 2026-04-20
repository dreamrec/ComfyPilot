"""SD 1.5 family templates - the ComfyPilot baseline.

These mirror the original ComfyPilot templates (CheckpointLoaderSimple +
CLIPTextEncode + EmptyLatentImage + KSampler + VAEDecode + SaveImage).
They are the fallback when the family detector cannot identify the checkpoint.
"""
from __future__ import annotations


def txt2img(params: dict) -> dict:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": params.get("checkpoint", "v1-5-pruned-emaonly.safetensors")},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("positive", "beautiful landscape"), "clip": ["1", 1]},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("negative", "ugly, blurry"), "clip": ["1", 1]},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": params.get("width", 512),
                "height": params.get("height", 512),
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
                "steps": params.get("steps", 20),
                "cfg": params.get("cfg", 7.0),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "normal"),
                "denoise": params.get("denoise", 1.0),
            },
        },
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {
            "class_type": "SaveImage",
            "inputs": {"images": ["6", 0], "filename_prefix": params.get("filename_prefix", "ComfyPilot")},
        },
    }


def img2img(params: dict) -> dict:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": params.get("checkpoint", "v1-5-pruned-emaonly.safetensors")},
        },
        "2": {"class_type": "LoadImage", "inputs": {"image": params.get("image", "input.png")}},
        "3": {"class_type": "VAEEncode", "inputs": {"pixels": ["2", 0], "vae": ["1", 2]}},
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("positive", "beautiful landscape"), "clip": ["1", 1]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("negative", "ugly, blurry"), "clip": ["1", 1]},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["3", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 20),
                "cfg": params.get("cfg", 7.0),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "normal"),
                "denoise": params.get("denoise", 0.75),
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {
            "class_type": "SaveImage",
            "inputs": {"images": ["7", 0], "filename_prefix": params.get("filename_prefix", "ComfyPilot_img2img")},
        },
    }


def upscale(params: dict) -> dict:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": params.get("checkpoint", "v1-5-pruned-emaonly.safetensors")},
        },
        "2": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": params.get("width", 512),
                "height": params.get("height", 512),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("positive", "beautiful landscape"), "clip": ["1", 1]},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("negative", "ugly, blurry"), "clip": ["1", 1]},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["2", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 20),
                "cfg": params.get("cfg", 7.0),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "normal"),
                "denoise": params.get("denoise", 1.0),
            },
        },
        "6": {
            "class_type": "LatentUpscale",
            "inputs": {
                "samples": ["5", 0],
                "upscale_method": params.get("upscale_method", "nearest-exact"),
                "width": params.get("upscale_width", 1024),
                "height": params.get("upscale_height", 1024),
                "crop": params.get("crop", "disabled"),
            },
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["6", 0],
                "seed": params.get("upscale_seed", 43),
                "steps": params.get("upscale_steps", 10),
                "cfg": params.get("cfg", 7.0),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "normal"),
                "denoise": params.get("upscale_denoise", 0.5),
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["8", 0], "filename_prefix": params.get("filename_prefix", "ComfyPilot_upscale")},
        },
    }


def inpaint(params: dict) -> dict:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": params.get("checkpoint", "v1-5-pruned-emaonly.safetensors")},
        },
        "2": {"class_type": "LoadImage", "inputs": {"image": params.get("image", "input.png")}},
        "3": {"class_type": "LoadImage", "inputs": {"image": params.get("mask", "mask.png")}},
        "4": {"class_type": "VAEEncode", "inputs": {"pixels": ["2", 0], "vae": ["1", 2]}},
        "5": {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["4", 0], "mask": ["3", 0]}},
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("positive", "beautiful landscape"), "clip": ["1", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("negative", "ugly, blurry"), "clip": ["1", 1]},
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 20),
                "cfg": params.get("cfg", 7.0),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "normal"),
                "denoise": params.get("denoise", 0.75),
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
        "10": {
            "class_type": "SaveImage",
            "inputs": {"images": ["9", 0], "filename_prefix": params.get("filename_prefix", "ComfyPilot_inpaint")},
        },
    }


def controlnet(params: dict) -> dict:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": params.get("checkpoint", "v1-5-pruned-emaonly.safetensors")},
        },
        "2": {
            "class_type": "ControlNetLoader",
            "inputs": {"control_net_name": params.get("controlnet_name", "control_v11p_sd15_canny.pth")},
        },
        "3": {"class_type": "LoadImage", "inputs": {"image": params.get("control_image", "control.png")}},
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("positive", "beautiful landscape"), "clip": ["1", 1]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("negative", "ugly, blurry"), "clip": ["1", 1]},
        },
        "6": {
            "class_type": "ControlNetApply",
            "inputs": {
                "conditioning": ["4", 0],
                "control_net": ["2", 0],
                "image": ["3", 0],
                "strength": params.get("controlnet_strength", 1.0),
            },
        },
        "7": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": params.get("width", 512),
                "height": params.get("height", 512),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["6", 0],
                "negative": ["5", 0],
                "latent_image": ["7", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 20),
                "cfg": params.get("cfg", 7.0),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "normal"),
                "denoise": params.get("denoise", 1.0),
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
        "10": {
            "class_type": "SaveImage",
            "inputs": {"images": ["9", 0], "filename_prefix": params.get("filename_prefix", "ComfyPilot_controlnet")},
        },
    }


TEMPLATES = {
    "txt2img": txt2img,
    "img2img": img2img,
    "upscale": upscale,
    "inpaint": inpaint,
    "controlnet": controlnet,
}

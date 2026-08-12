"""Hunyuan3D 2.1 templates (image-to-3D mesh with textures).

Pipeline: input image -> Hunyuan3D diffusion -> mesh -> VAE decode to
textured GLB. Distinct from video: node set is Hunyuan3D* not HunyuanVideo*.
"""
from __future__ import annotations


def image2_3d(params: dict) -> dict:
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": params.get("image", "input.png")},
        },
        "2": {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": params.get("clip_vision", "clip_vision_h.safetensors")},
        },
        "3": {
            "class_type": "CLIPVisionEncode",
            "inputs": {"clip_vision": ["2", 0], "image": ["1", 0], "crop": "center"},
        },
        "4": {
            "class_type": "Hunyuan3Dv2Conditioning",
            "inputs": {"clip_vision_output": ["3", 0]},
        },
        "5": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": params.get("checkpoint", "hunyuan3d-dit-v2-1.safetensors"),
                "weight_dtype": params.get("weight_dtype", "default"),
            },
        },
        "6": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": params.get("vae", "hunyuan3d-vae-v2-1.safetensors")},
        },
        "7": {
            "class_type": "EmptyLatentHunyuan3Dv2",
            "inputs": {
                "resolution": params.get("resolution", 3072),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["5", 0],
                "positive": ["4", 0],
                "negative": ["4", 1],
                "latent_image": ["7", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 30),
                "cfg": params.get("cfg", 5.5),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "simple"),
                "denoise": 1.0,
            },
        },
        "9": {
            "class_type": "VAEDecodeHunyuan3D",
            "inputs": {"samples": ["8", 0], "vae": ["6", 0]},
        },
        "10": {
            "class_type": "VoxelToMesh",
            "inputs": {
                "voxel": ["9", 0],
                "algorithm": params.get("mesh_algorithm", "surface net"),
                "threshold": params.get("mesh_threshold", 0.6),
            },
        },
        "11": {
            "class_type": "SaveGLB",
            "inputs": {
                "mesh": ["10", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_hy3d"),
            },
        },
    }


TEMPLATES = {"image2_3d": image2_3d}

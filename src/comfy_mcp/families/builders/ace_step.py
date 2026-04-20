"""ACE-Step 1.5 XL templates (text-to-music).

ACE-Step is a 4B-parameter music DiT (released 2026-04). ComfyUI exposes
it via CheckpointLoaderSimple and EmptyAceStepLatentAudio as the latent
primitive. Output is saved as SaveAudio (FLAC by default).

Typical generation: <2s per song on A100, <10s on RTX 3090.
"""
from __future__ import annotations


def txt2music(params: dict) -> dict:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": params.get("checkpoint", "ace-step-1.5-xl.safetensors")},
        },
        "2": {
            "class_type": "EmptyAceStepLatentAudio",
            "inputs": {
                "seconds": params.get("seconds", 30.0),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "3": {
            "class_type": "TextEncodeAceStepAudio",
            "inputs": {
                "clip": ["1", 1],
                "tags": params.get("tags", "electronic, ambient, cinematic"),
                "lyrics": params.get("lyrics", ""),
                "lyrics_strength": params.get("lyrics_strength", 1.0),
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": params.get("negative", "low quality, distorted"), "clip": ["1", 1]},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["2", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 50),
                "cfg": params.get("cfg", 5.0),
                "sampler_name": params.get("sampler", "euler"),
                "scheduler": params.get("scheduler", "simple"),
                "denoise": 1.0,
            },
        },
        "6": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {
            "class_type": "SaveAudio",
            "inputs": {
                "audio": ["6", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_acestep"),
            },
        },
    }


TEMPLATES = {"txt2music": txt2music}

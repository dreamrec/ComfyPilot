"""General text-to-audio templates.

Distinct from the ACE-Step family (which targets music). This builder
handles general audio: ambience, sfx, soundscapes, voice via Stable Audio
2.5 (v0.3.58) or other native audio diffusion models. Uses the v0.3.53
AudioEncoders directory + wav2vec2 + LTXV Audio VAE primitives.

Intent: `txt2audio`. Family-agnostic.
"""
from __future__ import annotations


def txt2audio(params: dict) -> dict:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": params.get("checkpoint", "stable-audio-2.5.safetensors")},
        },
        "2": {
            "class_type": "ConditioningStableAudio",
            "inputs": {
                "model": ["1", 0],
                "positive": params.get("positive", "warm ambient pad, slow attack"),
                "negative": params.get("negative", "harsh, distorted, clipping"),
                "seconds_start": params.get("seconds_start", 0.0),
                "seconds_total": params.get("duration_s", 10.0),
            },
        },
        "3": {
            "class_type": "EmptyLatentAudio",
            "inputs": {
                "seconds": params.get("duration_s", 10.0),
                "batch_size": params.get("batch_size", 1),
            },
        },
        "4": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["2", 1],
                "latent_image": ["3", 0],
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 50),
                "cfg": params.get("cfg", 7.0),
                "sampler_name": params.get("sampler", "dpmpp_3m_sde"),
                "scheduler": params.get("scheduler", "exponential"),
                "denoise": 1.0,
            },
        },
        "5": {
            "class_type": "VAEDecodeAudio",
            "inputs": {"samples": ["4", 0], "vae": ["1", 2]},
        },
        "6": {
            "class_type": "SaveAudio",
            "inputs": {
                "audio": ["5", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_audio"),
            },
        },
    }


TEMPLATES = {"txt2audio": txt2audio}

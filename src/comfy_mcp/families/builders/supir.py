"""SUPIR super-resolution templates (ComfyUI v0.20.0+).

SUPIR is an image super-resolution / restoration pipeline whose ComfyUI
nodes landed natively in v0.20.0. It is family-agnostic - a SUPIR pipeline
takes any image as input regardless of which model produced it, so we
register it under the intent-override map (not a checkpoint family).

Topology:
  LoadImage -> SUPIRLoader (model + first_stage_model + ckpt encoder) ->
  SUPIREncode -> SUPIRSample (with prompt conditioning) -> SUPIRDecode ->
  SaveImage.

Class names follow ComfyUI's naming convention. Confirm against the live
object_info catalog if these 404 on your install - the SUPIR native nodes
were still settling at v0.20.0.
"""
from __future__ import annotations


def super_resolution(params: dict) -> dict:
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": params.get("image", "input.png")},
        },
        "2": {
            "class_type": "SUPIRLoader",
            "inputs": {
                "supir_model": params.get("supir_model", "SUPIR-v0Q.safetensors"),
                "sdxl_model": params.get("sdxl_model", "sd_xl_base_1.0.safetensors"),
                "fp8_unet": params.get("fp8_unet", False),
                "diffusion_dtype": params.get("diffusion_dtype", "fp16"),
            },
        },
        "3": {
            "class_type": "SUPIREncode",
            "inputs": {
                "SUPIR_VAE": ["2", 0],
                "image": ["1", 0],
                "use_tiled_vae": params.get("use_tiled_vae", True),
                "encoder_tile_size": params.get("encoder_tile_size", 1024),
                "encoder_dtype": params.get("encoder_dtype", "auto"),
            },
        },
        "4": {
            "class_type": "SUPIRSample",
            "inputs": {
                "SUPIR_model": ["2", 1],
                "latents": ["3", 0],
                "positive_prompt": params.get(
                    "positive", "cinematic photograph, ultra-detailed, sharp focus"
                ),
                "negative_prompt": params.get(
                    "negative",
                    "painting, oil painting, illustration, drawing, art, sketch, anime, "
                    "cartoon, CG style, 3D render, blurry, out of focus, low quality",
                ),
                "seed": params.get("seed", 42),
                "steps": params.get("steps", 45),
                "cfg_scale_start": params.get("cfg_scale_start", 4.0),
                "cfg_scale_end": params.get("cfg_scale_end", 4.0),
                "EDM_s_churn": params.get("edm_s_churn", 5),
                "s_noise": params.get("s_noise", 1.003),
                "DPMPP_eta": params.get("dpmpp_eta", 1.0),
                "control_scale_start": params.get("control_scale_start", 1.0),
                "control_scale_end": params.get("control_scale_end", 1.0),
                "restore_cfg": params.get("restore_cfg", -1.0),
                "keep_model_loaded": params.get("keep_model_loaded", True),
                "sampler": params.get("sampler", "RestoreEDMSampler"),
            },
        },
        "5": {
            "class_type": "SUPIRDecode",
            "inputs": {
                "SUPIR_VAE": ["2", 0],
                "latents": ["4", 0],
                "use_tiled_vae": params.get("use_tiled_vae", True),
                "decoder_tile_size": params.get("decoder_tile_size", 512),
            },
        },
        "6": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["5", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_supir"),
            },
        },
    }


TEMPLATES = {"super_resolution": super_resolution}

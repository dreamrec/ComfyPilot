"""SAM 3.1 segmentation templates (ComfyUI v0.20.0+).

Meta's SAM 3.1 (Segment Anything Model 3.1) gained native ComfyUI support
in v0.20.0. It accepts an image plus optional point/box/text prompts and
returns one or more masks.

Topology:
  LoadImage -> SAM3Loader (model load) -> SAM3Segment (prompt + masking) ->
  MaskToImage (visualization) -> SaveImage.

Intent: `segment`. Family-agnostic - operates on any input image. Useful
as a pre-processing step for downstream inpaint / controlnet / compositing.
"""
from __future__ import annotations


def segment(params: dict) -> dict:
    workflow: dict = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": params.get("image", "input.png")},
        },
        "2": {
            "class_type": "SAM3Loader",
            "inputs": {
                "model_name": params.get("model_name", "sam3.1_hiera_large.pt"),
                "device": params.get("device", "AUTO"),
            },
        },
        "3": {
            "class_type": "SAM3Segment",
            "inputs": {
                "sam_model": ["2", 0],
                "image": ["1", 0],
                "text_prompt": params.get("prompt", "the main subject"),
                "threshold": params.get("threshold", 0.5),
                "multimask_output": params.get("multimask_output", False),
            },
        },
        "4": {
            "class_type": "MaskToImage",
            "inputs": {"mask": ["3", 0]},
        },
        "5": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["4", 0],
                "filename_prefix": params.get("filename_prefix", "ComfyPilot_sam31_mask"),
            },
        },
    }
    return workflow


TEMPLATES = {"segment": segment}

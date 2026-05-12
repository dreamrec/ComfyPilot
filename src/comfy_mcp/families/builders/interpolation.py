"""Frame interpolation templates (ComfyUI v0.20.0+).

RIFE (Real-Time Intermediate Flow Estimation) and FILM (Frame Interpolation
for Large Motion) interpolation models gained native support in ComfyUI
v0.20.0. Both produce intermediate frames between consecutive video frames
to smooth motion or increase frame rate.

Topology:
  LoadVideo / image batch -> RIFE_VFI or FILM_VFI -> SaveAnimatedWEBP /
  SaveVideo.

Intent: `interpolate_frames`. Family-agnostic - operates on any video
regardless of how it was produced (Wan, LTX, HunyuanVideo, direct upload).
Method controlled via params['method'] = "rife" | "film" (default rife).
"""
from __future__ import annotations


def _rife_node(multiplier: int) -> dict:
    return {
        "class_type": "RIFE_VFI",
        "inputs": {
            "frames": ["1", 0],
            "ckpt_name": "rife49.pth",
            "clear_cache_after_n_frames": 10,
            "multiplier": multiplier,
            "fast_mode": True,
            "ensemble": True,
            "scale_factor": 1.0,
        },
    }


def _film_node(multiplier: int) -> dict:
    return {
        "class_type": "FILM_VFI",
        "inputs": {
            "frames": ["1", 0],
            "ckpt_name": "film_net_fp32.pt",
            "clear_cache_after_n_frames": 10,
            "multiplier": multiplier,
        },
    }


def interpolate_frames(params: dict) -> dict:
    method = (params.get("method") or "rife").lower()
    multiplier = int(params.get("multiplier", 2))
    fps = int(params.get("fps", 24))

    # Source can be a video file or an image batch directory. LoadVideo handles
    # both single-file and ComfyUI image batches in v0.20+.
    source: dict = {
        "class_type": "LoadVideo",
        "inputs": {
            "video": params.get("video", "input.mp4"),
            "force_rate": 0,
            "force_size": "Disabled",
            "custom_width": 0,
            "custom_height": 0,
            "frame_load_cap": 0,
            "skip_first_frames": 0,
            "select_every_nth": 1,
        },
    }

    interp = _film_node(multiplier) if method == "film" else _rife_node(multiplier)

    workflow: dict = {
        "1": source,
        "2": interp,
        "3": {
            "class_type": "SaveAnimatedWEBP",
            "inputs": {
                "images": ["2", 0],
                "filename_prefix": params.get(
                    "filename_prefix", f"ComfyPilot_{method}_x{multiplier}"
                ),
                "fps": fps * multiplier,
                "lossless": False,
                "quality": 90,
                "method": "default",
            },
        },
    }
    return workflow


TEMPLATES = {"interpolate_frames": interpolate_frames}

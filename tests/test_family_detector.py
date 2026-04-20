"""Tests for model family detection from checkpoint filenames."""
from __future__ import annotations

import pytest

from comfy_mcp.families.detector import Family, detect_family


@pytest.mark.parametrize("name,expected", [
    # SD 1.5 variants
    ("v1-5-pruned-emaonly.safetensors", Family.SD15),
    ("sd15_anything_v5.safetensors", Family.SD15),
    ("SD1.5-realisticVisionV60B1.safetensors", Family.SD15),
    # SDXL
    ("sd_xl_base_1.0.safetensors", Family.SDXL),
    ("sdxl_lightning_8step.safetensors", Family.SDXL),
    ("SDXL-Turbo.safetensors", Family.SDXL),
    # SD 3
    ("sd3_medium.safetensors", Family.SD3),
    ("sd3_medium_incl_clips_t5xxlfp8.safetensors", Family.SD3),
    # SD 3.5
    ("sd3.5_large.safetensors", Family.SD35),
    ("sd3_5_large_turbo.safetensors", Family.SD35),
    # Flux 1
    ("flux1-dev.safetensors", Family.FLUX1),
    ("flux1-schnell-fp8.safetensors", Family.FLUX1),
    ("flux_1_krea_dev.safetensors", Family.FLUX1),
    # Flux 2
    ("flux2-klein.safetensors", Family.FLUX2),
    ("flux_2_dev.safetensors", Family.FLUX2),
    # Qwen-Image
    ("qwen-image-2512.safetensors", Family.QWEN),
    ("qwen_image_2.0.safetensors", Family.QWEN),
    # Wan 2.2
    ("wan2.2-t2v-14b.safetensors", Family.WAN22),
    ("wan_2_2_i2v_14B_fp8.safetensors", Family.WAN22),
    ("wan22-t2v.safetensors", Family.WAN22),
    # LTX-Video / LTX-2
    ("ltx-video-2b-v0.9.safetensors", Family.LTX2),
    ("ltx_2_dev.safetensors", Family.LTX2),
    # Hunyuan video
    ("hunyuan-video-t2v-720p.safetensors", Family.HUNYUAN_VIDEO),
    ("hunyuanvideo_i2v.safetensors", Family.HUNYUAN_VIDEO),
    # Hunyuan 3D
    ("hunyuan3d-dit-v2-1.safetensors", Family.HUNYUAN_3D),
    ("hunyuan_3d_2.0.safetensors", Family.HUNYUAN_3D),
    # ACE-Step
    ("ace-step-1.5-xl.safetensors", Family.ACE_STEP),
    ("ace_step_v1.5.safetensors", Family.ACE_STEP),
    # Unknown
    ("custom-checkpoint.safetensors", Family.UNKNOWN),
    ("", Family.UNKNOWN),
])
def test_detects_family_from_filename(name, expected):
    assert detect_family(name) == expected


def test_empty_string_is_unknown():
    assert detect_family("") == Family.UNKNOWN


def test_path_with_subfolder_still_works():
    assert detect_family("folder/subfolder/flux2-klein.safetensors") == Family.FLUX2

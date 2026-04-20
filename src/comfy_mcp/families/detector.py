"""Detect ComfyUI model family from a checkpoint filename.

Why this exists: different families (SD 1.5 vs Flux 2 vs Wan 2.2 vs LTX-2 vs
HunyuanVideo vs ACE-Step) demand different graph topologies. A builder that
auto-detects an installed Flux 2 checkpoint and drops it into an SD 1.5
CheckpointLoaderSimple/KSampler graph produces a workflow that cannot execute.
Detecting the family is step one of capability-aware graph synthesis.

Detection is filename-first because filenames are what ComfyUI's model lists
return. Future improvements can cross-check against object_info hints or
probe the checkpoint header for signatures.
"""
from __future__ import annotations

import re
from enum import Enum


class Family(str, Enum):
    SD15 = "sd15"
    SDXL = "sdxl"
    SD3 = "sd3"
    SD35 = "sd35"
    FLUX1 = "flux1"
    FLUX2 = "flux2"
    QWEN = "qwen"
    WAN22 = "wan22"
    LTX2 = "ltx2"
    HUNYUAN_VIDEO = "hunyuan_video"
    HUNYUAN_3D = "hunyuan_3d"
    ACE_STEP = "ace_step"
    UNKNOWN = "unknown"


# Patterns are evaluated in order — more specific before general.
# SD3.5 must match before SD3; Flux2 before Flux1; Hunyuan3D and HunyuanVideo
# disambiguated explicitly. Patterns match anywhere in the basename (filenames
# may carry prefix like "folder/file.safetensors").
_PATTERNS: list[tuple[re.Pattern[str], Family]] = [
    # Product-specific patterns go FIRST so they claim version-like suffixes
    # (e.g. "ace_step_v1.5" should not be misread as SD 1.5)
    (re.compile(r"ace[._\-]?step", re.I), Family.ACE_STEP),

    # Hunyuan variants (3d must beat video to avoid 'hunyuan_3d_video_xyz' edge cases)
    (re.compile(r"hunyuan[._\-]?3d|hunyuan3d", re.I), Family.HUNYUAN_3D),
    (re.compile(r"hunyuan[._\-]?video|hunyuanvideo", re.I), Family.HUNYUAN_VIDEO),

    # Flux 2 must beat Flux 1
    (re.compile(r"flux[._\-]?2|flux2", re.I), Family.FLUX2),
    (re.compile(r"flux[._\-]?1|flux\.?1|flux(?!\d)", re.I), Family.FLUX1),

    # Qwen-Image (before SD patterns in case something like "qwen_sd_compatible" exists)
    (re.compile(r"qwen[._\-]?image|qwen", re.I), Family.QWEN),

    # Wan 2.2
    (re.compile(r"wan[._\-]?2[._\-]?2|wan22", re.I), Family.WAN22),

    # LTX-Video / LTX-2
    (re.compile(r"ltx[._\-]?(?:video|2)|ltx2", re.I), Family.LTX2),

    # SD 3.5 must beat SD 3
    (re.compile(r"sd[._\-]?3[._\-]?5|sd3\.5|sd3_5", re.I), Family.SD35),
    (re.compile(r"sd[._\-]?3(?![._\-]?5)", re.I), Family.SD3),

    # SDXL must beat plain SD
    (re.compile(r"sd[._\-]?xl|sdxl", re.I), Family.SDXL),

    # SD 1.5 - "v1-5" only matches at start of basename to avoid clashing with
    # version suffixes like "ace_step_v1.5" or "some_model_v1.5.safetensors".
    (re.compile(r"^v1[._\-]5|sd[._\-]?1[._\-]?5|sd15", re.I), Family.SD15),
]


def detect_family(checkpoint_name: str, catalog: dict | None = None) -> Family:
    """Identify model family from filename.

    Args:
        checkpoint_name: Filename like 'flux2-klein.safetensors' or a path.
        catalog: Optional object_info (reserved for future schema-based hints).

    Returns:
        Family enum; Family.UNKNOWN if no pattern matches.
    """
    if not checkpoint_name:
        return Family.UNKNOWN
    # Strip any path prefix - match on basename only
    name = checkpoint_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    for pattern, family in _PATTERNS:
        if pattern.search(name):
            return family
    return Family.UNKNOWN

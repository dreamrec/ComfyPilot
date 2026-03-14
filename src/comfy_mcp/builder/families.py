"""Model family detection — infer checkpoint family from name patterns."""
from __future__ import annotations

import re
from dataclasses import dataclass

@dataclass(frozen=True)
class ModelFamily:
    name: str
    default_width: int
    default_height: int
    default_cfg: float
    default_steps: int
    default_sampler: str
    default_scheduler: str

# Known families with their defaults
FAMILIES: dict[str, ModelFamily] = {
    "sd1.5": ModelFamily(
        name="sd1.5",
        default_width=512,
        default_height=512,
        default_cfg=7.0,
        default_steps=20,
        default_sampler="euler",
        default_scheduler="normal",
    ),
    "sdxl": ModelFamily(
        name="sdxl",
        default_width=1024,
        default_height=1024,
        default_cfg=7.0,
        default_steps=25,
        default_sampler="euler",
        default_scheduler="normal",
    ),
    "flux": ModelFamily(
        name="flux",
        default_width=1024,
        default_height=1024,
        default_cfg=1.0,
        default_steps=20,
        default_sampler="euler",
        default_scheduler="simple",
    ),
}

# Patterns to match checkpoint filenames to families (checked in order)
_FAMILY_PATTERNS: list[tuple[str, str]] = [
    # FLUX patterns (check first — most specific)
    (r"flux", "flux"),
    # SDXL patterns
    (r"sdxl|sd_xl|juggernaut.*xl|dreamshaperxl|realvis.*xl|animagine.*xl|pony", "sdxl"),
    # SD1.5 patterns (broadest — default fallback)
    (r"v1[._-]5|sd1[._]5|sd15|deliberate|dreamshaper(?!.*xl)|realistic.?vision(?!.*xl)|anything.?v[345]|rev.?animated|counterfeit|abyssorange", "sd1.5"),
]

def detect_family(checkpoint_name: str) -> ModelFamily:
    """Detect model family from checkpoint filename.

    Returns the matching ModelFamily, defaulting to sd1.5 if no pattern matches.
    """
    lower = checkpoint_name.lower()
    for pattern, family_name in _FAMILY_PATTERNS:
        if re.search(pattern, lower):
            return FAMILIES[family_name]
    # Default to SD1.5 for unknown checkpoints
    return FAMILIES["sd1.5"]

def family_defaults(checkpoint_name: str) -> dict:
    """Return a dict of recommended defaults for the given checkpoint.

    Useful for merging into workflow parameters.
    """
    family = detect_family(checkpoint_name)
    return {
        "family": family.name,
        "width": family.default_width,
        "height": family.default_height,
        "cfg": family.default_cfg,
        "steps": family.default_steps,
        "sampler_name": family.default_sampler,
        "scheduler": family.default_scheduler,
    }

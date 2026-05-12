"""Deprecated-model catalog.

ComfyUI marks specific partner / API models as deprecated across releases.
The validator's environment pass lints referenced model filenames against
this list and emits a warning (not an error) when a deprecated model is
used. Errors are reserved for missing files; deprecation is advisory.

Keep this list ordered alphabetically and add new entries as upstream
deprecates them. Each entry maps a substring pattern (lowercased, matched
against the lowercased filename basename) to a human-readable reason.
"""
from __future__ import annotations


# pattern (substring, case-insensitive) -> (reason, suggested_replacement | None)
DEPRECATED_MODELS: dict[str, tuple[str, str | None]] = {
    "seedream-3-0-t2i": (
        "ByteDance Seedream 3.0 t2i was deprecated in ComfyUI v0.18.0",
        "seedream-5-t2i",
    ),
    "seedance-1-0-lite": (
        "ByteDance Seedance 1.0 Lite was deprecated in ComfyUI v0.18.0",
        "seedance-2-0",
    ),
    "seededit": (
        "OpenAI seededit was deprecated in ComfyUI v0.7.0",
        "Seedream image-edit pipeline",
    ),
    "gpt-image-1": (
        "GPT-Image-1 was superseded by GPT-Image-1.5 (v0.5.1) and GPT-Image-2 (v0.20)",
        "gpt-image-2",
    ),
    "kling-2-1-master": (
        "Kling v2-1-master was rolled into Kling v2.5 turbo (v0.3.66+)",
        "kling-2.5-turbo",
    ),
    "veo-3-0": (
        "Veo 3.0 was extended to 4K resolution and a Lite variant; check for v3.1+ paths",
        "veo-3.1 or veo-3-lite",
    ),
}


def lint_model_name(name: str) -> tuple[str, str | None] | None:
    """Return (reason, replacement) when `name` matches a deprecated entry, else None."""
    if not name:
        return None
    base = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    for pattern, info in DEPRECATED_MODELS.items():
        if pattern.lower() in base:
            return info
    return None

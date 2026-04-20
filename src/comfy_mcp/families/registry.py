"""Family -> intent -> builder function registry.

Glue between detect_family() and the per-family template modules. Each
family registers its supported intents (txt2img, img2img, inpaint,
controlnet, txt2video, img2video, image2_3d, txt2music, upscale, etc.)
by calling register(family, intent, fn).

The builder tool resolves a high-level intent against the registry once
the family has been detected.
"""
from __future__ import annotations

from typing import Callable

from comfy_mcp.families.detector import Family

BuilderFn = Callable[[dict], dict]

_REGISTRY: dict[Family, dict[str, BuilderFn]] = {}


def register(family: Family, intent: str, fn: BuilderFn) -> None:
    _REGISTRY.setdefault(family, {})[intent] = fn


def has(family: Family, intent: str) -> bool:
    return intent in _REGISTRY.get(family, {})


def build(family: Family, intent: str, params: dict) -> dict:
    if family not in _REGISTRY or intent not in _REGISTRY[family]:
        raise KeyError(f"No builder for family={family.value} intent={intent!r}")
    return _REGISTRY[family][intent](params)


def list_intents(family: Family) -> list[str]:
    return list(_REGISTRY.get(family, {}).keys())


def list_families() -> list[Family]:
    return list(_REGISTRY.keys())


# --- Wire up built-in family templates ---

from comfy_mcp.families.builders import sd15 as _sd15  # noqa: E402

for _intent, _fn in _sd15.TEMPLATES.items():
    register(Family.SD15, _intent, _fn)

"""Family -> intent -> builder function registry.

Glue between detect_family() and the per-family template modules. Each
family registers its supported intents (txt2img, img2img, inpaint,
controlnet, txt2video, img2video, image2_3d, txt2music, upscale, etc.)
by calling register(family, intent, fn).

The builder tool resolves a high-level intent against the registry once
the family has been detected.

Some intents are family-agnostic (e.g. super_resolution via SUPIR, frame
interpolation via RIFE/FILM, segmentation via SAM 3.1) and dispatch from
an intent-first override map instead of going through family detection.
"""
from __future__ import annotations

from typing import Callable

from comfy_mcp.families.detector import Family

BuilderFn = Callable[[dict], dict]

_REGISTRY: dict[Family, dict[str, BuilderFn]] = {}
_INTENT_OVERRIDES: dict[str, BuilderFn] = {}


def register(family: Family, intent: str, fn: BuilderFn) -> None:
    _REGISTRY.setdefault(family, {})[intent] = fn


def register_intent(intent: str, fn: BuilderFn) -> None:
    """Register a family-agnostic intent (takes precedence over family routing).

    Use for capabilities that operate on any image/video regardless of the
    upstream model family - SUPIR super-resolution, RIFE/FILM frame
    interpolation, SAM 3.1 segmentation, training/LoRA, audio t2a, etc.
    """
    _INTENT_OVERRIDES[intent] = fn


def has(family: Family, intent: str) -> bool:
    return intent in _REGISTRY.get(family, {})


def has_intent_override(intent: str) -> bool:
    return intent in _INTENT_OVERRIDES


def build_intent(intent: str, params: dict) -> dict:
    if intent not in _INTENT_OVERRIDES:
        raise KeyError(f"No intent override for {intent!r}")
    return _INTENT_OVERRIDES[intent](params)


def build(family: Family, intent: str, params: dict) -> dict:
    if family not in _REGISTRY or intent not in _REGISTRY[family]:
        raise KeyError(f"No builder for family={family.value} intent={intent!r}")
    return _REGISTRY[family][intent](params)


def list_intents(family: Family) -> list[str]:
    return list(_REGISTRY.get(family, {}).keys())


def list_intent_overrides() -> list[str]:
    return list(_INTENT_OVERRIDES.keys())


def list_families() -> list[Family]:
    return list(_REGISTRY.keys())


# --- Wire up built-in family templates ---

from comfy_mcp.families.builders import ace_step as _ace_step  # noqa: E402
from comfy_mcp.families.builders import audio_t2a as _audio_t2a  # noqa: E402
from comfy_mcp.families.builders import ernie as _ernie  # noqa: E402
from comfy_mcp.families.builders import flux2 as _flux2  # noqa: E402
from comfy_mcp.families.builders import hunyuan_3d as _hunyuan_3d  # noqa: E402
from comfy_mcp.families.builders import hunyuan_video as _hunyuan_video  # noqa: E402
from comfy_mcp.families.builders import interpolation as _interpolation  # noqa: E402
from comfy_mcp.families.builders import ltx2 as _ltx2  # noqa: E402
from comfy_mcp.families.builders import qwen as _qwen  # noqa: E402
from comfy_mcp.families.builders import sd15 as _sd15  # noqa: E402
from comfy_mcp.families.builders import sd35 as _sd35  # noqa: E402
from comfy_mcp.families.builders import sdxl as _sdxl  # noqa: E402
from comfy_mcp.families.builders import segment as _segment  # noqa: E402
from comfy_mcp.families.builders import supir as _supir  # noqa: E402
from comfy_mcp.families.builders import training as _training  # noqa: E402
from comfy_mcp.families.builders import wan22 as _wan22  # noqa: E402


def _register_module(family: Family, module) -> None:
    for intent, fn in module.TEMPLATES.items():
        register(family, intent, fn)


def _register_intent_module(module) -> None:
    for intent, fn in module.TEMPLATES.items():
        register_intent(intent, fn)


_register_module(Family.SD15, _sd15)
_register_module(Family.SDXL, _sdxl)
_register_module(Family.SD35, _sd35)
_register_module(Family.FLUX2, _flux2)
_register_module(Family.QWEN, _qwen)
_register_module(Family.WAN22, _wan22)
_register_module(Family.LTX2, _ltx2)
_register_module(Family.HUNYUAN_VIDEO, _hunyuan_video)
_register_module(Family.HUNYUAN_3D, _hunyuan_3d)
_register_module(Family.ACE_STEP, _ace_step)
_register_module(Family.ERNIE_IMAGE, _ernie)

# Family-agnostic intents (intent-first dispatch)
_register_intent_module(_supir)
_register_intent_module(_interpolation)
_register_intent_module(_segment)
_register_intent_module(_training)
_register_intent_module(_audio_t2a)

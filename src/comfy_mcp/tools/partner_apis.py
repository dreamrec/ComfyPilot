"""Partner-API listing tool.

ComfyUI ships an ever-expanding ecosystem of partner / API custom nodes:
Veo, Kling, ByteDance Seedance/Seedream, GPT-Image, Topaz, Tripo3D, Rodin,
Recraft, Ideogram, NanoBanana, Ernie, ElevenLabs, Sonilo, and so on. Each
node bundles a vendor-hosted model behind a familiar ComfyUI node surface.

`comfy_list_partner_apis` walks the installed extensions list and reports
which known partner APIs are wired up, plus their vendor / category /
homepage so agents can suggest workflows that match what's actually
available on the local server.
"""
from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


# Curated catalog of partner/API custom nodes ComfyUI core or community ship.
# Key is a substring matched against installed-extension names (lowercased).
# Values: human-readable metadata. Update as new partners land.
KNOWN_PARTNER_APIS: dict[str, dict] = {
    # Video
    "veo": {
        "vendor": "Google",
        "category": "video",
        "models": ["veo-3.0", "veo-3-lite", "veo-3.1"],
        "homepage": "https://deepmind.google/technologies/veo/",
    },
    "kling": {
        "vendor": "Kuaishou",
        "category": "video",
        "models": ["kling-2.5-turbo", "kling-3.0", "kling-v2-1"],
        "homepage": "https://klingai.com/",
    },
    "seedance": {
        "vendor": "ByteDance",
        "category": "video",
        "models": ["seedance-2.0", "seedance-pro"],
        "homepage": "https://www.volcengine.com/product/seedance",
    },
    "sora": {
        "vendor": "OpenAI",
        "category": "video",
        "models": ["sora2"],
        "homepage": "https://openai.com/sora",
    },
    "minimax": {
        "vendor": "MiniMax",
        "category": "video",
        "models": ["hailuo-video"],
        "homepage": "https://www.minimax.io/",
    },
    "vidu": {
        "vendor": "Vidu",
        "category": "video",
        "models": ["viduq3-turbo"],
        "homepage": "https://www.vidu.com/",
    },
    "moonvalley": {
        "vendor": "Moonvalley",
        "category": "video",
        "models": ["moonvalley-v2v"],
        "homepage": "https://moonvalley.ai/",
    },
    "sonilo": {
        "vendor": "Sonilo",
        "category": "audio_for_video",
        "models": ["sonilo-music"],
        "homepage": "https://sonilo.ai/",
    },
    # Image
    "seedream": {
        "vendor": "ByteDance",
        "category": "image",
        "models": ["seedream-5", "seedream-4"],
        "homepage": "https://www.volcengine.com/product/seedream",
    },
    "gpt-image": {
        "vendor": "OpenAI",
        "category": "image",
        "models": ["gpt-image-2", "gpt-image-1.5"],
        "homepage": "https://platform.openai.com/docs/guides/images",
    },
    "recraft": {
        "vendor": "Recraft",
        "category": "image",
        "models": ["recraft-v4"],
        "homepage": "https://www.recraft.ai/",
    },
    "ideogram": {
        "vendor": "Ideogram",
        "category": "image",
        "models": ["ideogram-v3"],
        "homepage": "https://ideogram.ai/",
    },
    "nanobanana": {
        "vendor": "Google",
        "category": "image",
        "models": ["nanobanana-2", "nano-banana-pro"],
        "homepage": "https://deepmind.google/technologies/imagen/",
    },
    "topaz": {
        "vendor": "Topaz Labs",
        "category": "upscale",
        "models": ["topaz-4k-video"],
        "homepage": "https://www.topazlabs.com/",
    },
    "bfl": {
        "vendor": "Black Forest Labs",
        "category": "image",
        "models": ["flux1-dev-api", "flux1-pro"],
        "homepage": "https://blackforestlabs.ai/",
    },
    "quiver": {
        "vendor": "Quiver",
        "category": "vector",
        "models": ["arrow-1.1", "arrow-1.1-max"],
        "homepage": "https://quiver.ai/",
    },
    # 3D
    "tripo": {
        "vendor": "VAST",
        "category": "3d",
        "models": ["tripo-3.0"],
        "homepage": "https://www.tripo3d.ai/",
    },
    "rodin": {
        "vendor": "Hyper3D",
        "category": "3d",
        "models": ["rodin-gen-2"],
        "homepage": "https://hyper3d.ai/",
    },
    "tencent3d": {
        "vendor": "Tencent",
        "category": "3d",
        "models": ["tencent-smart-topology"],
        "homepage": "https://hunyuan.tencent.com/",
    },
    # Audio
    "elevenlabs": {
        "vendor": "ElevenLabs",
        "category": "audio",
        "models": ["elevenlabs-tts"],
        "homepage": "https://elevenlabs.io/",
    },
    "stableaudio": {
        "vendor": "Stability AI",
        "category": "audio",
        "models": ["stable-audio-2.5"],
        "homepage": "https://stability.ai/stable-audio",
    },
    # LLM / multimodal
    "gemini": {
        "vendor": "Google",
        "category": "llm",
        "models": ["gemini-3.1-flash-lite"],
        "homepage": "https://ai.google.dev/",
    },
    "grok": {
        "vendor": "xAI",
        "category": "video_llm",
        "models": ["grok-reference-to-video", "grok-video-extend"],
        "homepage": "https://x.ai/",
    },
    "ministral": {
        "vendor": "Mistral",
        "category": "llm",
        "models": ["ministral"],
        "homepage": "https://mistral.ai/",
    },
}


@mcp.tool(
    annotations={
        "title": "List Partner APIs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def comfy_list_partner_apis(ctx: Context = None) -> str:
    """List partner-API custom nodes installed on the connected ComfyUI.

    Intersects the installed extensions list (from ComfyUI's /extensions
    endpoint) with ComfyPilot's curated KNOWN_PARTNER_APIS catalog. Useful
    before suggesting workflows that depend on cloud-backed nodes - tells
    the agent which vendors (Veo, Kling, Seedream, GPT-Image, etc.) are
    actually wired up on this server.

    Returns:
        JSON with `installed` (list of detected partners) and `available`
        (full catalog) so the agent can suggest installs when needed.
    """
    client = ctx.request_context.lifespan_context["comfy_client"]
    try:
        extensions = await client.get_extensions()
    except Exception as e:
        return json.dumps({
            "error": f"Could not fetch /extensions: {e}",
            "installed": [],
            "available": [
                {"key": k, **v} for k, v in KNOWN_PARTNER_APIS.items()
            ],
        }, indent=2)

    ext_lower = [str(e).lower() for e in (extensions or [])]
    installed: list[dict] = []
    for key, meta in KNOWN_PARTNER_APIS.items():
        if any(key in e for e in ext_lower):
            installed.append({"key": key, **meta})

    return json.dumps({
        "installed_count": len(installed),
        "installed": installed,
        "catalog_size": len(KNOWN_PARTNER_APIS),
        "extension_count": len(ext_lower),
    }, indent=2)

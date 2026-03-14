"""TemplateDiscovery -- fetch template sources from ComfyUI and built-in library.

Sources:
1. Official ComfyUI templates (GET /templates/index.json)
2. Custom node example workflows (GET /workflow_templates or /api/workflow_templates)
3. Built-in templates (hardcoded fallbacks for basic workflows)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_OFFICIAL_CATEGORY_HINTS = {
    "text to image": "text-to-image",
    "text-to-image": "text-to-image",
    "txt2img": "text-to-image",
    "image edit": "image-to-image",
    "edit": "image-to-image",
    "img2img": "image-to-image",
    "image to image": "image-to-image",
    "inpaint": "inpaint",
    "inpainting": "inpaint",
    "controlnet": "controlnet",
    "text to video": "text-to-video",
    "t2v": "text-to-video",
    "image to video": "image-to-video",
    "i2v": "image-to-video",
    "flf2v": "first-last-frame-to-video",
    "audio to video": "audio-to-video",
    "audio": "audio",
    "image upscale": "upscale",
    "upscale": "upscale",
    "video upscale": "video-upscale",
}


class TemplateDiscovery:
    """Discovers workflow templates from multiple sources."""

    def __init__(self, client: Any | None):
        self._client = client

    async def discover_official(self) -> list[dict[str, Any]]:
        """Fetch official ComfyUI templates from the server.

        ComfyClient.get() returns parsed JSON directly (dict/list). If the mock returns an object with
        .status_code/.json(), it is unwrapped first.
        """
        if self._client is None:
            return []
        try:
            response = await self._client.get("/templates/index.json")
            data = self._unwrap_response(response)
            if data is None:
                return []
            templates = []
            for item in self._normalize_official_payload(data):
                item["source"] = "official"
                if "tags" not in item:
                    item["tags"] = []
                templates.append(item)
            return templates
        except Exception as exc:
            logger.debug("Official template discovery failed: %s", exc)
            return []

    async def discover_custom_node(self) -> list[dict[str, Any]]:
        """Fetch custom node example workflows from ComfyUI server."""
        if self._client is None:
            return []
        profile = getattr(self._client, "capabilities", {}).get("profile", "unknown")
        if profile == "cloud":
            candidate_paths = ["/api/workflow_templates", "/workflow_templates"]
        else:
            candidate_paths = ["/workflow_templates", "/api/workflow_templates"]
        last_exc: Exception | None = None
        try:
            data = None
            for path in candidate_paths:
                try:
                    response = await self._client.get(path)
                    data = self._unwrap_response(response)
                    if data is not None:
                        break
                except Exception as exc:
                    last_exc = exc
            if data is None:
                return []
            templates = []
            for item in data:
                item["source"] = "custom_node"
                if "tags" not in item:
                    item["tags"] = []
                item.setdefault("supports_instantiation", "workflow" in item)
                templates.append(item)
            return templates
        except Exception as exc:
            logger.debug(
                "Custom node template discovery failed: %s",
                exc if last_exc is None else last_exc,
            )
            return []

    @staticmethod
    def _unwrap_response(response: Any) -> list[dict[str, Any]] | None:
        """Handle both dict-returning and response-object-returning client.get() patterns.

        Real ComfyClient.get() returns parsed JSON (list/dict).
        Some test mocks return objects with .status_code and .json().
        """
        if isinstance(response, list):
            return response
        if isinstance(response, dict):
            if "error" in response:
                return None
            return [response]
        # Response-like object
        if hasattr(response, "status_code"):
            if response.status_code != 200:
                return None
            return response.json()
        return None

    @staticmethod
    def _slugify(value: str) -> str:
        return "-".join(part for part in value.lower().replace("_", " ").split() if part)

    def _infer_official_category(self, item: dict[str, Any], module: dict[str, Any]) -> str:
        raw_category = item.get("category")
        if raw_category:
            return raw_category

        lower_tags = [tag.lower() for tag in item.get("tags", []) if isinstance(tag, str)]
        for tag in lower_tags:
            if tag in _OFFICIAL_CATEGORY_HINTS:
                return _OFFICIAL_CATEGORY_HINTS[tag]

        haystacks = [
            item.get("title", ""),
            item.get("description", ""),
            module.get("title", ""),
        ]
        for text in haystacks:
            lower = text.lower()
            for hint, category in _OFFICIAL_CATEGORY_HINTS.items():
                if hint in lower:
                    return category

        module_title = module.get("title", "")
        return self._slugify(module_title) if module_title else "official"

    def _normalize_official_entry(
        self,
        item: dict[str, Any],
        module: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        module = module or {}
        template = dict(item)
        workflow_file = template.get("file")
        if not workflow_file and template.get("name"):
            workflow_file = f"{template['name']}.json"

        template["title"] = template.get("title", template.get("name", ""))
        template["category"] = self._infer_official_category(template, module)
        template["module_name"] = module.get("moduleName", template.get("module_name", ""))
        template["module_title"] = module.get("title", template.get("module_title", ""))
        template["template_type"] = module.get("type", template.get("template_type", ""))
        template["model_names"] = list(template.get("models", []))
        template["required_custom_nodes"] = list(template.get("requiresCustomNodes", []))
        template["distribution_targets"] = list(template.get("includeOnDistributions", []))
        template["tutorial_url"] = template.get("tutorialUrl", "")
        template["media_type"] = template.get("mediaType", template.get("template_type", ""))
        template["media_subtype"] = template.get("mediaSubtype", "")
        template["open_source"] = bool(template.get("openSource", False))
        template["usage"] = int(template.get("usage", 0) or 0)
        template["vram"] = int(template.get("vram", 0) or 0)
        template["size"] = int(template.get("size", 0) or 0)
        template["workflow_file"] = workflow_file
        if workflow_file:
            template["workflow_url"] = (
                "https://raw.githubusercontent.com/Comfy-Org/workflow_templates/"
                f"refs/heads/main/templates/{workflow_file}"
            )
        template["supports_instantiation"] = bool(template.get("workflow"))
        io = template.get("io", {})
        template["input_count"] = len(io.get("inputs", []))
        template["output_count"] = len(io.get("outputs", []))
        return template

    def _normalize_official_payload(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return []

        templates: list[dict[str, Any]] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            nested_templates = entry.get("templates")
            if isinstance(nested_templates, list):
                for template in nested_templates:
                    if isinstance(template, dict):
                        templates.append(self._normalize_official_entry(template, module=entry))
                continue
            templates.append(self._normalize_official_entry(entry))
        return templates

    def discover_builtin(self) -> list[dict[str, Any]]:
        """Return hardcoded built-in templates (8 templates) that are always available."""
        return [
            {
                "name": "txt2img_basic",
                "category": "text-to-image",
                "source": "builtin",
                "description": "Basic text-to-image workflow with checkpoint, sampler, and save.",
                "tags": ["txt2img", "basic", "generation"],
                "required_nodes": ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler",
                                   "EmptyLatentImage", "VAEDecode", "SaveImage"],
                "required_models": {"checkpoints": 1},
                "supports_instantiation": True,
                "workflow": {
                    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
                    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "beautiful landscape", "clip": ["1", 1]}},
                    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly, blurry", "clip": ["1", 1]}},
                    "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
                    "5": {"class_type": "KSampler", "inputs": {
                        "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                        "latent_image": ["4", 0], "seed": 42, "steps": 20, "cfg": 7.0,
                        "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                    }},
                    "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
                    "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "ComfyPilot"}},
                },
            },
            {
                "name": "img2img_basic",
                "category": "image-to-image",
                "source": "builtin",
                "description": "Basic image-to-image workflow.",
                "tags": ["img2img", "basic"],
                "required_nodes": ["CheckpointLoaderSimple", "LoadImage", "VAEEncode",
                                   "CLIPTextEncode", "KSampler", "VAEDecode", "SaveImage"],
                "required_models": {"checkpoints": 1},
                "supports_instantiation": True,
                "workflow": {
                    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
                    "2": {"class_type": "LoadImage", "inputs": {"image": "input.png"}},
                    "3": {"class_type": "VAEEncode", "inputs": {"pixels": ["2", 0], "vae": ["1", 2]}},
                    "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "beautiful landscape", "clip": ["1", 1]}},
                    "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly, blurry", "clip": ["1", 1]}},
                    "6": {"class_type": "KSampler", "inputs": {
                        "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0],
                        "latent_image": ["3", 0], "seed": 42, "steps": 20, "cfg": 7.0,
                        "sampler_name": "euler", "scheduler": "normal", "denoise": 0.75,
                    }},
                    "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
                    "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "ComfyPilot_img2img"}},
                },
            },
            {
                "name": "sdxl_txt2img",
                "category": "text-to-image",
                "source": "builtin",
                "description": "SDXL text-to-image workflow with 1024x1024 defaults",
                "tags": ["txt2img", "sdxl", "generation", "1024"],
                "required_nodes": ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler",
                                   "EmptyLatentImage", "VAEDecode", "SaveImage"],
                "required_models": {"checkpoints": 1},
                "supports_instantiation": True,
                "workflow": {
                    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
                    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "beautiful landscape", "clip": ["1", 1]}},
                    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly, blurry", "clip": ["1", 1]}},
                    "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
                    "5": {"class_type": "KSampler", "inputs": {
                        "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                        "latent_image": ["4", 0], "seed": 42, "steps": 25, "cfg": 7.0,
                        "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                    }},
                    "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
                    "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "ComfyPilot"}},
                },
            },
            {
                "name": "sdxl_img2img",
                "category": "image-to-image",
                "source": "builtin",
                "description": "SDXL image-to-image workflow with 1024x1024 defaults",
                "tags": ["img2img", "sdxl", "refine", "1024"],
                "required_nodes": ["CheckpointLoaderSimple", "CLIPTextEncode", "LoadImage",
                                   "VAEEncode", "KSampler", "VAEDecode", "SaveImage"],
                "required_models": {"checkpoints": 1},
                "supports_instantiation": True,
                "workflow": {
                    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
                    "2": {"class_type": "LoadImage", "inputs": {"image": "input.png"}},
                    "3": {"class_type": "VAEEncode", "inputs": {"pixels": ["2", 0], "vae": ["1", 2]}},
                    "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "beautiful landscape", "clip": ["1", 1]}},
                    "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly, blurry", "clip": ["1", 1]}},
                    "6": {"class_type": "KSampler", "inputs": {
                        "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0],
                        "latent_image": ["3", 0], "seed": 42, "steps": 25, "cfg": 7.0,
                        "sampler_name": "euler", "scheduler": "normal", "denoise": 0.75,
                    }},
                    "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
                    "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "ComfyPilot_img2img"}},
                },
            },
            {
                "name": "flux_txt2img",
                "category": "text-to-image",
                "source": "builtin",
                "description": "FLUX text-to-image workflow with 1024x1024 defaults and low CFG",
                "tags": ["txt2img", "flux", "generation", "1024"],
                "required_nodes": ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler",
                                   "EmptyLatentImage", "VAEDecode", "SaveImage"],
                "required_models": {"checkpoints": 1},
                "supports_instantiation": True,
                "workflow": {
                    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
                    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "beautiful landscape", "clip": ["1", 1]}},
                    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly, blurry", "clip": ["1", 1]}},
                    "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
                    "5": {"class_type": "KSampler", "inputs": {
                        "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                        "latent_image": ["4", 0], "seed": 42, "steps": 20, "cfg": 1.0,
                        "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
                    }},
                    "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
                    "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "ComfyPilot"}},
                },
            },
            {
                "name": "upscale_basic",
                "category": "upscale",
                "source": "builtin",
                "description": "Two-pass upscale workflow: generate at 512x512 then upscale to 1024x1024",
                "tags": ["upscale", "enhance", "hires", "two-pass"],
                "required_nodes": ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler",
                                   "EmptyLatentImage", "LatentUpscale", "VAEDecode", "SaveImage"],
                "required_models": {"checkpoints": 1},
                "supports_instantiation": True,
                "workflow": {
                    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
                    "2": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
                    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "beautiful landscape", "clip": ["1", 1]}},
                    "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly, blurry", "clip": ["1", 1]}},
                    "5": {"class_type": "KSampler", "inputs": {
                        "model": ["1", 0], "positive": ["3", 0], "negative": ["4", 0],
                        "latent_image": ["2", 0], "seed": 42, "steps": 20, "cfg": 7.0,
                        "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                    }},
                    "6": {"class_type": "LatentUpscale", "inputs": {
                        "samples": ["5", 0], "upscale_method": "nearest-exact",
                        "width": 1024, "height": 1024, "crop": "disabled",
                    }},
                    "7": {"class_type": "KSampler", "inputs": {
                        "model": ["1", 0], "positive": ["3", 0], "negative": ["4", 0],
                        "latent_image": ["6", 0], "seed": 43, "steps": 10, "cfg": 7.0,
                        "sampler_name": "euler", "scheduler": "normal", "denoise": 0.5,
                    }},
                    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
                    "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "ComfyPilot_upscale"}},
                },
            },
            {
                "name": "inpaint_basic",
                "category": "inpaint",
                "source": "builtin",
                "description": "Inpainting workflow with mask-based generation",
                "tags": ["inpaint", "mask", "edit", "repair"],
                "required_nodes": ["CheckpointLoaderSimple", "CLIPTextEncode", "LoadImage",
                                   "VAEEncode", "SetLatentNoiseMask", "KSampler", "VAEDecode", "SaveImage"],
                "required_models": {"checkpoints": 1},
                "supports_instantiation": True,
                "workflow": {
                    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
                    "2": {"class_type": "LoadImage", "inputs": {"image": "input.png"}},
                    "3": {"class_type": "LoadImage", "inputs": {"image": "mask.png"}},
                    "4": {"class_type": "VAEEncode", "inputs": {"pixels": ["2", 0], "vae": ["1", 2]}},
                    "5": {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["4", 0], "mask": ["3", 0]}},
                    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "beautiful landscape", "clip": ["1", 1]}},
                    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly, blurry", "clip": ["1", 1]}},
                    "8": {"class_type": "KSampler", "inputs": {
                        "model": ["1", 0], "positive": ["6", 0], "negative": ["7", 0],
                        "latent_image": ["5", 0], "seed": 42, "steps": 20, "cfg": 7.0,
                        "sampler_name": "euler", "scheduler": "normal", "denoise": 0.75,
                    }},
                    "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
                    "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "ComfyPilot_inpaint"}},
                },
            },
            {
                "name": "controlnet_basic",
                "category": "controlnet",
                "source": "builtin",
                "description": "ControlNet-guided generation workflow",
                "tags": ["controlnet", "guided", "control", "conditional"],
                "required_nodes": ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler",
                                   "EmptyLatentImage", "ControlNetLoader", "ControlNetApply",
                                   "LoadImage", "VAEDecode", "SaveImage"],
                "required_models": {"checkpoints": 1, "controlnet": 1},
                "supports_instantiation": True,
                "workflow": {
                    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
                    "2": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "control_v11p_sd15_canny.pth"}},
                    "3": {"class_type": "LoadImage", "inputs": {"image": "control.png"}},
                    "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "beautiful landscape", "clip": ["1", 1]}},
                    "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly, blurry", "clip": ["1", 1]}},
                    "6": {"class_type": "ControlNetApply", "inputs": {
                        "conditioning": ["4", 0], "control_net": ["2", 0],
                        "image": ["3", 0], "strength": 1.0,
                    }},
                    "7": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
                    "8": {"class_type": "KSampler", "inputs": {
                        "model": ["1", 0], "positive": ["6", 0], "negative": ["5", 0],
                        "latent_image": ["7", 0], "seed": 42, "steps": 20, "cfg": 7.0,
                        "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                    }},
                    "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
                    "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "ComfyPilot_controlnet"}},
                },
            },
        ]

    async def discover_all(self) -> list[dict[str, Any]]:
        """Discover templates from all sources and merge."""
        official = await self.discover_official()
        custom = await self.discover_custom_node()
        builtin = self.discover_builtin()
        return official + custom + builtin

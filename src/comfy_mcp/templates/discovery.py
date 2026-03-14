"""TemplateDiscovery -- fetch template sources from ComfyUI and built-in library.

Sources:
1. Official ComfyUI templates (GET /templates/index.json)
2. Custom node example workflows (GET /workflow_templates)
3. Built-in templates (hardcoded fallbacks for basic workflows)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


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
            for item in data:
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
        try:
            response = await self._client.get("/workflow_templates")
            data = self._unwrap_response(response)
            if data is None:
                return []
            templates = []
            for item in data:
                item["source"] = "custom_node"
                if "tags" not in item:
                    item["tags"] = []
                templates.append(item)
            return templates
        except Exception as exc:
            logger.debug("Custom node template discovery failed: %s", exc)
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
            return [response]
        # Response-like object
        if hasattr(response, "status_code"):
            if response.status_code != 200:
                return None
            return response.json()
        return None

    def discover_builtin(self) -> list[dict[str, Any]]:
        """Return hardcoded built-in templates that are always available."""
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
        ]

    async def discover_all(self) -> list[dict[str, Any]]:
        """Discover templates from all sources and merge."""
        official = await self.discover_official()
        custom = await self.discover_custom_node()
        builtin = self.discover_builtin()
        return official + custom + builtin

"""TemplateInstantiator -- model substitution and workflow preparation.

Takes a template, substitutes model references with installed models,
applies user overrides, and returns a ready-to-queue workflow.
"""

from __future__ import annotations

import copy
from typing import Any

# Input names that reference models, mapped to model folder
MODEL_INPUT_HINTS = {
    "ckpt_name": "checkpoints",
    "lora_name": "loras",
    "vae_name": "vae",
    "control_net_name": "controlnet",
    "unet_name": "checkpoints",
    "clip_name": "clip",
    "upscale_model": "upscale_models",
}

# Input names that are common override targets
OVERRIDE_TARGETS = {
    "width", "height", "batch_size", "seed", "steps", "cfg",
    "sampler_name", "scheduler", "denoise",
    "positive_prompt", "negative_prompt",
    "ckpt_name", "lora_name", "vae_name",
}


class TemplateInstantiator:
    """Substitutes model references and applies overrides to template workflows."""

    def __init__(self, snapshot: dict[str, Any]):
        self._models = snapshot.get("models", {})
        self._nodes = snapshot.get("node_classes", set())

    def instantiate(
        self,
        template: dict[str, Any],
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Instantiate a template into a ready-to-queue workflow.

        Returns: {"status": "ready"|"warnings", "workflow": {...}, "warnings": [...]}
        """
        if "workflow" not in template:
            return {"status": "error", "workflow": {}, "warnings": ["Template has no workflow body"]}

        workflow = copy.deepcopy(template["workflow"])
        warnings: list[str] = []

        # Phase 1: Model substitution
        for node_id, node in workflow.items():
            inputs = node.get("inputs", {})
            for input_name, value in list(inputs.items()):
                if input_name in MODEL_INPUT_HINTS and isinstance(value, str):
                    folder = MODEL_INPUT_HINTS[input_name]
                    installed = self._models.get(folder, [])
                    if value not in installed:
                        if installed:
                            # Pick first alphabetically (deterministic default)
                            replacement = sorted(installed)[0]
                            inputs[input_name] = replacement
                            warnings.append(f"Substituted {input_name}: '{value}' -> '{replacement}' (first available {folder})")
                        else:
                            warnings.append(f"No {folder} models installed for {input_name} (template needs '{value}')")

        # Phase 2: Apply overrides
        if overrides:
            applied = set()
            for node_id, node in workflow.items():
                inputs = node.get("inputs", {})
                for key, new_value in overrides.items():
                    if key in inputs:
                        inputs[key] = new_value
                        applied.add(key)

            unapplied = set(overrides.keys()) - applied
            for key in unapplied:
                warnings.append(f"Override '{key}' did not match any workflow input (ignored)")

        status = "ready" if not warnings else "warnings"
        return {
            "status": status,
            "workflow": workflow,
            "warnings": warnings,
            "template_id": template.get("id", ""),
            "template_name": template.get("name", ""),
        }

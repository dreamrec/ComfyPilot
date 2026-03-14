"""TemplateInstantiator -- model substitution and workflow preparation.

Takes a template, substitutes model references with installed models,
applies user overrides, and returns a ready-to-queue workflow.
"""

from __future__ import annotations

import copy
from typing import Any

# Input names that reference models, mapped to preferred model folders
MODEL_INPUT_HINTS = {
    "ckpt_name": ("checkpoints",),
    "lora_name": ("loras",),
    "vae_name": ("vae",),
    "control_net_name": ("controlnet",),
    "unet_name": ("diffusion_models", "checkpoints"),
    "clip_name": ("text_encoders", "clip"),
    "upscale_model": ("latent_upscale_models", "upscale_models"),
}


class TemplateInstantiator:
    """Substitutes model references and applies overrides to template workflows."""

    def __init__(self, snapshot: dict[str, Any]):
        self._models = snapshot.get("models", {})

    def _resolve_model_folders(self, input_name: str) -> tuple[str, ...]:
        folders = MODEL_INPUT_HINTS[input_name]
        return folders if isinstance(folders, tuple) else (folders,)

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
                    folders = self._resolve_model_folders(input_name)
                    installed_by_folder = [
                        (folder, self._models.get(folder, []))
                        for folder in folders
                    ]
                    if any(value in installed for _, installed in installed_by_folder):
                        continue

                    replacement_pair = next(
                        (
                            (folder, sorted(installed)[0])
                            for folder, installed in installed_by_folder
                            if installed
                        ),
                        None,
                    )
                    if replacement_pair is not None:
                        folder, replacement = replacement_pair
                        inputs[input_name] = replacement
                        warnings.append(
                            f"Substituted {input_name}: '{value}' -> '{replacement}' "
                            f"(first available from {folder})"
                        )
                    else:
                        warnings.append(
                            f"No models installed in {', '.join(folders)} for {input_name} "
                            f"(template needs '{value}')"
                        )

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

"""Compatibility Pass 3: Environment validation.

Checks that everything the workflow references is actually available:
- All node types are installed
- All model references can be resolved
"""

from __future__ import annotations

from typing import Any

# Known input names that reference models by folder
MODEL_INPUT_HINTS = {
    "ckpt_name": "checkpoints",
    "lora_name": "loras",
    "vae_name": "vae",
    "control_net_name": "controlnet",
    "upscale_model": "upscale_models",
    "clip_name": "clip",
}


def check_environment(workflow: dict, snapshot: dict) -> dict[str, Any]:
    """Validate that workflow requirements exist on this machine."""
    errors: list[str] = []
    warnings: list[str] = []
    missing_nodes: list[str] = []
    missing_models: list[dict] = []
    installed_nodes = 0

    node_classes = snapshot.get("node_classes", set())
    # Support both set and list
    if isinstance(node_classes, list):
        node_classes = set(node_classes)
    models = snapshot.get("models", {})

    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        if not class_type:
            continue

        if class_type in node_classes:
            installed_nodes += 1
        else:
            missing_nodes.append(class_type)
            errors.append(f"Node {node_id}: '{class_type}' is not installed")

        # Check model references in inputs
        inputs = node.get("inputs", {})
        for input_name, value in inputs.items():
            if isinstance(value, (list, dict)):
                continue  # link or complex input
            folder = MODEL_INPUT_HINTS.get(input_name)
            if folder and isinstance(value, str):
                folder_models = models.get(folder, [])
                if value not in folder_models:
                    missing_models.append({"name": value, "folder": folder, "node_id": node_id})

    return {
        "pass": len(missing_nodes) == 0 and len(missing_models) == 0,
        "errors": errors,
        "warnings": warnings,
        "missing_nodes": sorted(set(missing_nodes)),
        "missing_models": missing_models,
        "installed_nodes": installed_nodes,
    }

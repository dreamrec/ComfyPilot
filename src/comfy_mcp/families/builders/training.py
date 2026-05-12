"""Native LoRA training templates (ComfyUI v0.3.41+, v0.3.45+, v0.3.76+).

ComfyUI added native LoRA training nodes in v0.3.41:
- v0.3.41: Initial LoRA Training Integration (TrainLoraDataLoader, TrainLora, SaveLora)
- v0.3.45: Multi-image-caption dataset support + training loop improvements
- v0.3.76: Multi-resolution bucketing + Z-Image LoRA training

Intent: `train_lora`. Family-agnostic - the trainer takes any compatible
base model (SD 1.5, SDXL, Flux, Qwen, Z-Image, etc.). The base model and
dataset directory are supplied via params.
"""
from __future__ import annotations


def train_lora(params: dict) -> dict:
    """Build a LoRA-training workflow.

    Params:
        base_model: Filename in checkpoints/ or diffusion_models/.
        dataset_dir: Path to the training image/caption directory.
        rank: LoRA rank (default 16).
        alpha: LoRA alpha (default 16).
        steps: Total training steps (default 1000).
        learning_rate: Default 1e-4.
        batch_size: Default 1.
        output_name: Resulting LoRA filename prefix.
        resolution: Bucket resolution (default 512). v0.3.76+ supports
            multi-resolution buckets via dataset metadata.
    """
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": params.get("base_model", "v1-5-pruned-emaonly.safetensors")},
        },
        "2": {
            "class_type": "TrainLoraDataLoader",
            "inputs": {
                "dataset_dir": params.get("dataset_dir", "datasets/my_lora"),
                "resolution": params.get("resolution", 512),
                "batch_size": params.get("batch_size", 1),
                "shuffle": params.get("shuffle", True),
                "caption_extension": params.get("caption_extension", ".txt"),
                "multi_resolution": params.get("multi_resolution", True),
            },
        },
        "3": {
            "class_type": "TrainLora",
            "inputs": {
                "model": ["1", 0],
                "clip": ["1", 1],
                "dataset": ["2", 0],
                "rank": params.get("rank", 16),
                "alpha": params.get("alpha", 16),
                "steps": params.get("steps", 1000),
                "learning_rate": params.get("learning_rate", 1e-4),
                "optimizer": params.get("optimizer", "AdamW"),
                "training_dtype": params.get("training_dtype", "bf16"),
                "lora_dtype": params.get("lora_dtype", "bf16"),
                "save_every": params.get("save_every", 250),
            },
        },
        "4": {
            "class_type": "SaveLora",
            "inputs": {
                "lora": ["3", 0],
                "filename_prefix": params.get("output_name", "ComfyPilot_trained_lora"),
            },
        },
    }


TEMPLATES = {"train_lora": train_lora}

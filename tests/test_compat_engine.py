"""Tests for the Compatibility Engine orchestrator."""

from __future__ import annotations

import pytest


OBJECT_INFO = {
    "KSampler": {
        "input": {"required": {
            "model": ["MODEL"], "seed": ["INT"], "steps": ["INT"],
            "cfg": ["FLOAT"], "sampler_name": [["euler"]], "scheduler": [["normal"]],
            "positive": ["CONDITIONING"], "negative": ["CONDITIONING"],
            "latent_image": ["LATENT"],
        }},
        "output": ["LATENT"],
        "category": "sampling",
    },
    "CheckpointLoaderSimple": {
        "input": {"required": {"ckpt_name": [["model.safetensors"]]}},
        "output": ["MODEL", "CLIP", "VAE"],
        "category": "loaders",
    },
    "SaveImage": {
        "input": {"required": {"images": ["IMAGE"]}},
        "output": [],
        "output_node": True,
        "category": "image",
    },
}

SNAPSHOT = {
    "node_classes": {"KSampler", "CheckpointLoaderSimple", "SaveImage"},
    "models": {"checkpoints": ["model.safetensors"]},
    "embeddings": [],
    "object_info": OBJECT_INFO,
}


class TestCompatEngine:
    def test_valid_workflow_verified(self):
        from comfy_mcp.compat.engine import run_preflight
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0], "seed": 42, "steps": 20, "cfg": 7.0,
                "sampler_name": "euler", "scheduler": "normal",
                "positive": ["1", 1], "negative": ["1", 2], "latent_image": ["1", 3],
            }},
            "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0]}},
        }
        result = run_preflight(wf, SNAPSHOT)
        assert result["status"] == "verified"
        assert result["confidence"] >= 0.9

    def test_missing_node_blocks(self):
        from comfy_mcp.compat.engine import run_preflight
        wf = {
            "1": {"class_type": "UnknownNode", "inputs": {}},
        }
        result = run_preflight(wf, SNAPSHOT)
        assert result["status"] == "blocked"
        assert "UnknownNode" in str(result["errors"])

    def test_schema_warning_reduces_confidence(self):
        from comfy_mcp.compat.engine import run_preflight
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0], "seed": 42, "steps": 20, "cfg": 7.0,
                "sampler_name": "bad_sampler", "scheduler": "normal",
                "positive": ["1", 1], "negative": ["1", 2], "latent_image": ["1", 3],
            }},
        }
        result = run_preflight(wf, SNAPSHOT)
        assert result["status"] == "likely"
        assert len(result["warnings"]) > 0

    def test_empty_workflow_blocked(self):
        from comfy_mcp.compat.engine import run_preflight
        result = run_preflight({}, SNAPSHOT)
        assert result["status"] == "blocked"

    def test_result_includes_all_sections(self):
        from comfy_mcp.compat.engine import run_preflight
        wf = {"1": {"class_type": "KSampler", "inputs": {"seed": 42}}}
        result = run_preflight(wf, SNAPSHOT)
        assert "status" in result
        assert "errors" in result
        assert "warnings" in result
        assert "missing_nodes" in result
        assert "missing_models" in result
        assert "confidence" in result

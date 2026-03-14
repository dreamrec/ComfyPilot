"""Tests for compatibility Pass 3: environment validation."""

from __future__ import annotations

import pytest


SNAPSHOT = {
    "node_classes": {"KSampler", "CheckpointLoaderSimple", "CLIPTextEncode", "VAEDecode", "SaveImage"},
    "models": {
        "checkpoints": ["sd_xl_base_1.0.safetensors", "dreamshaper_8.safetensors"],
        "loras": ["detail.safetensors"],
        "vae": [],
        "controlnet": [],
    },
    "embeddings": ["EasyNegative"],
    "object_info": {
        "CheckpointLoaderSimple": {
            "input": {"required": {"ckpt_name": [["sd_xl_base_1.0.safetensors", "dreamshaper_8.safetensors"]]}},
        },
    },
}


class TestEnvironmentPass:
    def test_all_nodes_installed(self):
        from comfy_mcp.compat.environment import check_environment
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}},
        }
        result = check_environment(wf, SNAPSHOT)
        assert result["pass"] is True
        assert result["missing_nodes"] == []

    def test_missing_node_detected(self):
        from comfy_mcp.compat.environment import check_environment
        wf = {
            "1": {"class_type": "IPAdapterAdvanced", "inputs": {}},
        }
        result = check_environment(wf, SNAPSHOT)
        assert result["pass"] is False
        assert "IPAdapterAdvanced" in result["missing_nodes"]

    def test_model_reference_resolved(self):
        from comfy_mcp.compat.environment import check_environment
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
        }
        result = check_environment(wf, SNAPSHOT)
        assert result["missing_models"] == []

    def test_missing_model_detected(self):
        from comfy_mcp.compat.environment import check_environment
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "nonexistent.safetensors"}},
        }
        result = check_environment(wf, SNAPSHOT)
        assert len(result["missing_models"]) == 1
        assert result["missing_models"][0]["name"] == "nonexistent.safetensors"

    def test_mixed_installed_and_missing(self):
        from comfy_mcp.compat.environment import check_environment
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
            "2": {"class_type": "IPAdapterAdvanced", "inputs": {}},
            "3": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}},
        }
        result = check_environment(wf, SNAPSHOT)
        assert result["pass"] is False
        assert "IPAdapterAdvanced" in result["missing_nodes"]
        assert result["installed_nodes"] == 2

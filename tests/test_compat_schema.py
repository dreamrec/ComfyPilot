"""Tests for compatibility Pass 2: schema validation against object_info."""

from __future__ import annotations

import pytest


OBJECT_INFO = {
    "KSampler": {
        "input": {
            "required": {
                "model": ["MODEL"],
                "seed": ["INT", {"default": 0, "min": 0, "max": 2**32}],
                "steps": ["INT", {"default": 20, "min": 1, "max": 10000}],
                "cfg": ["FLOAT", {"default": 7.0}],
                "sampler_name": [["euler", "euler_ancestral", "dpmpp_2m"]],
                "scheduler": [["normal", "karras"]],
                "positive": ["CONDITIONING"],
                "negative": ["CONDITIONING"],
                "latent_image": ["LATENT"],
            },
        },
        "output": ["LATENT"],
        "category": "sampling",
    },
    "CheckpointLoaderSimple": {
        "input": {
            "required": {
                "ckpt_name": [["model1.safetensors", "model2.safetensors"]],
            },
        },
        "output": ["MODEL", "CLIP", "VAE"],
        "category": "loaders",
    },
    "SaveImage": {
        "input": {
            "required": {
                "images": ["IMAGE"],
            },
        },
        "output": [],
        "output_node": True,
        "category": "image",
    },
}


class TestSchemaPass:
    def test_valid_inputs_pass(self):
        from comfy_mcp.compat.schema import check_schema
        wf = {
            "1": {"class_type": "KSampler", "inputs": {
                "model": ["0", 0], "seed": 42, "steps": 20, "cfg": 7.0,
                "sampler_name": "euler", "scheduler": "normal",
                "positive": ["0", 1], "negative": ["0", 2], "latent_image": ["0", 3],
            }},
        }
        result = check_schema(wf, OBJECT_INFO)
        assert result["pass"] is True

    def test_unknown_node_type_flagged(self):
        from comfy_mcp.compat.schema import check_schema
        wf = {"1": {"class_type": "NonExistentNode", "inputs": {}}}
        result = check_schema(wf, OBJECT_INFO)
        assert result["pass"] is False
        assert any("NonExistentNode" in e for e in result["errors"])

    def test_missing_required_input_flagged(self):
        from comfy_mcp.compat.schema import check_schema
        wf = {"1": {"class_type": "KSampler", "inputs": {"seed": 42}}}
        result = check_schema(wf, OBJECT_INFO)
        assert result["pass"] is False
        assert any("model" in e for e in result["errors"])

    def test_invalid_enum_value_flagged(self):
        from comfy_mcp.compat.schema import check_schema
        wf = {"1": {"class_type": "KSampler", "inputs": {
            "model": ["0", 0], "seed": 42, "steps": 20, "cfg": 7.0,
            "sampler_name": "invalid_sampler", "scheduler": "normal",
            "positive": ["0", 1], "negative": ["0", 2], "latent_image": ["0", 3],
        }}}
        result = check_schema(wf, OBJECT_INFO)
        assert any("invalid_sampler" in w or "sampler_name" in w for w in result["warnings"])

    def test_link_inputs_not_validated_as_missing(self):
        """Inputs provided via links should not be flagged as missing."""
        from comfy_mcp.compat.schema import check_schema
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model1.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0], "seed": 42, "steps": 20, "cfg": 7.0,
                "sampler_name": "euler", "scheduler": "normal",
                "positive": ["1", 1], "negative": ["1", 2], "latent_image": ["1", 3],
            }},
        }
        result = check_schema(wf, OBJECT_INFO)
        assert result["pass"] is True

    def test_schema_reports_checked_count(self):
        from comfy_mcp.compat.schema import check_schema
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model1.safetensors"}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        result = check_schema(wf, OBJECT_INFO)
        assert result["nodes_checked"] == 2

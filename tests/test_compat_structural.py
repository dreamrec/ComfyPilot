"""Tests for compatibility Pass 1: structural validation."""

from __future__ import annotations

import pytest


# Minimal valid API-format workflow
VALID_WORKFLOW = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
    "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": 42}},
    "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0]}},
}


class TestStructuralPass:
    def test_valid_workflow_passes(self):
        from comfy_mcp.compat.structural import check_structural
        result = check_structural(VALID_WORKFLOW)
        assert result["pass"] is True
        assert result["errors"] == []

    def test_empty_workflow_fails(self):
        from comfy_mcp.compat.structural import check_structural
        result = check_structural({})
        assert result["pass"] is False
        assert any("empty" in e.lower() for e in result["errors"])

    def test_not_dict_fails(self):
        from comfy_mcp.compat.structural import check_structural
        result = check_structural("not a dict")
        assert result["pass"] is False

    def test_missing_class_type_fails(self):
        from comfy_mcp.compat.structural import check_structural
        wf = {"1": {"inputs": {"seed": 42}}}
        result = check_structural(wf)
        assert result["pass"] is False
        assert any("class_type" in e for e in result["errors"])

    def test_broken_link_detected(self):
        from comfy_mcp.compat.structural import check_structural
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"model": ["999", 0]}},
        }
        result = check_structural(wf)
        assert result["pass"] is False
        assert any("999" in e for e in result["errors"])

    def test_valid_link_format(self):
        from comfy_mcp.compat.structural import check_structural
        wf = {
            "1": {"class_type": "LoadModel", "inputs": {}},
            "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}},
        }
        result = check_structural(wf)
        assert result["pass"] is True

    def test_no_output_node_warning(self):
        from comfy_mcp.compat.structural import check_structural
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 42}},
        }
        result = check_structural(wf)
        # Should pass structurally but warn about no output node
        assert any("output" in w.lower() for w in result["warnings"])

    def test_node_count_reported(self):
        from comfy_mcp.compat.structural import check_structural
        result = check_structural(VALID_WORKFLOW)
        assert result["node_count"] == 3

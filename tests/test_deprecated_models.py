"""Tests for deprecated-model lint pass.

ComfyUI deprecates partner / API models over time. The validator emits
advisory warnings (not errors) for referenced model names that match the
deprecated list, so workflows continue to validate but the agent gets a
nudge toward the modern replacement.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import Context

from comfy_mcp.safety.deprecated_models import (
    DEPRECATED_MODELS,
    lint_model_name,
)
from comfy_mcp.tools.workflow import comfy_validate_workflow


def _ctx(client):
    ctx = MagicMock(spec=Context)
    ctx.request_context.lifespan_context = {"comfy_client": client, "vram_guard": None}
    return ctx


class TestLintHelper:
    def test_seedream_3_0_t2i_is_deprecated(self):
        info = lint_model_name("seedream-3-0-t2i.safetensors")
        assert info is not None
        reason, replacement = info
        assert "deprecated" in reason.lower()
        assert replacement is not None

    def test_clean_model_name_passes(self):
        assert lint_model_name("flux2-klein.safetensors") is None

    def test_case_insensitive_match(self):
        assert lint_model_name("SeeDream-3-0-T2i.safetensors") is not None

    def test_path_prefix_handled(self):
        assert lint_model_name("partners/seedance-1-0-lite.safetensors") is not None

    def test_empty_name_returns_none(self):
        assert lint_model_name("") is None


class TestValidatorIntegration:
    @pytest.mark.asyncio
    async def test_workflow_with_deprecated_model_warns_but_passes(self):
        """Deprecated models emit warnings, not errors - workflow still validates."""
        client = MagicMock()
        client.get_object_info = AsyncMock(return_value={"CheckpointLoaderSimple": {}})
        # Pretend the deprecated file IS installed - we want the lint, not the
        # missing-file error.
        client.get_models = AsyncMock(return_value=["seedream-3-0-t2i.safetensors"])

        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "seedream-3-0-t2i.safetensors"},
            },
        }
        report = await comfy_validate_workflow(workflow=workflow, ctx=_ctx(client))
        assert any("deprecated" in w.lower() for w in report.warnings)

    @pytest.mark.asyncio
    async def test_clean_workflow_no_deprecation_warnings(self):
        client = MagicMock()
        client.get_object_info = AsyncMock(return_value={"CheckpointLoaderSimple": {}})
        client.get_models = AsyncMock(return_value=["v1-5-pruned-emaonly.safetensors"])

        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
            },
        }
        report = await comfy_validate_workflow(workflow=workflow, ctx=_ctx(client))
        assert not any("deprecated" in w.lower() for w in report.warnings)


class TestCatalog:
    def test_at_least_three_deprecated_entries(self):
        """Sanity check the catalog is populated."""
        assert len(DEPRECATED_MODELS) >= 3

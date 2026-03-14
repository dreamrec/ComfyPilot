"""Tests for the bundled ecosystem registry and model-awareness resources."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from comfy_mcp.ecosystem import EcosystemRegistry, ModelAwarenessScanner


class TestEcosystemRegistry:
    def test_summary_reports_counts(self):
        registry = EcosystemRegistry()
        summary = registry.summary()
        assert summary["family_count"] >= 9
        assert summary["provider_count"] >= 7
        assert summary["latest_verified_at"] == "2026-03-14"

    def test_classifies_qwen_image(self):
        registry = EcosystemRegistry()
        result = registry.classify_model("qwen_image_fp8.safetensors", "diffusion_models")
        assert result["family"] == "qwen-image"

    def test_classifies_omnigen2(self):
        registry = EcosystemRegistry()
        result = registry.classify_model("omnigen2_fp8_e4m3fn.safetensors", "diffusion_models")
        assert result["family"] == "omnigen2"

    def test_classifies_pony_as_sdxl_with_ecosystem_tag(self):
        registry = EcosystemRegistry()
        result = registry.classify_model("ponyDiffusionV6XL.safetensors", "checkpoints")
        assert result["family"] == "sdxl"
        assert "pony" in result["ecosystems"]

    def test_detects_provider_from_node_names(self):
        registry = EcosystemRegistry()
        providers = registry.detect_providers({"GoogleNanoBananaNode", "RunwayVideoGeneration"})
        ids = {provider["id"] for provider in providers}
        assert "google" in ids
        assert "runway" in ids


class TestModelAwarenessScanner:
    def test_scan_summarizes_current_install(self):
        registry = EcosystemRegistry()
        scanner = ModelAwarenessScanner(registry)
        snapshot = {
            "models": {
                "checkpoints": ["ponyDiffusionV6XL.safetensors"],
                "diffusion_models": ["qwen_image_fp8.safetensors", "wan2.2_t2v.safetensors"],
                "text_encoders": ["qwen_2.5_vl_7b_fp8_scaled.safetensors", "umt5_xxl_fp8.safetensors"],
                "vae": ["qwen_image_vae.safetensors", "wan_2.2_vae.safetensors"],
            },
            "node_classes": {"GoogleNanoBananaNode"},
        }
        result = scanner.scan(snapshot, capabilities={"profile": "local", "version": "0.17.0"})
        assert "qwen-image" in result["detected_architectures"]
        assert "wan22" in result["detected_architectures"]
        assert "pony" in result["detected_ecosystems"]
        assert "google" in result["detected_providers"]
        assert "t2v" in result["available_capabilities"]


class TestModelAwarenessResources:
    @pytest.mark.asyncio
    async def test_ecosystem_registry_resource(self):
        import comfy_mcp.server as srv

        srv._shared_ecosystem_registry = EcosystemRegistry()
        try:
            result = json.loads(await srv.ecosystem_registry_resource())
            assert result["summary"]["family_count"] >= 9
            assert any(entry["id"] == "qwen-image" for entry in result["families"])
        finally:
            srv._shared_ecosystem_registry = None

    @pytest.mark.asyncio
    async def test_model_awareness_resource(self):
        import comfy_mcp.server as srv

        registry = EcosystemRegistry()
        srv._shared_ecosystem_registry = registry
        srv._shared_model_awareness_scanner = ModelAwarenessScanner(registry)
        srv._shared_client = MagicMock(capabilities={"profile": "local", "version": "0.17.0"})
        srv._shared_install_graph = MagicMock(snapshot={
            "models": {
                "checkpoints": ["ponyDiffusionV6XL.safetensors"],
                "diffusion_models": ["qwen_image_fp8.safetensors"],
                "text_encoders": ["qwen_2.5_vl_7b_fp8_scaled.safetensors"],
                "vae": ["qwen_image_vae.safetensors"],
            },
            "node_classes": {"GoogleNanoBananaNode"},
        })
        try:
            result = json.loads(await srv.model_awareness_resource())
            assert "qwen-image" in result["detected_architectures"]
            assert "pony" in result["detected_ecosystems"]
            assert "google" in result["detected_providers"]
        finally:
            srv._shared_ecosystem_registry = None
            srv._shared_model_awareness_scanner = None
            srv._shared_client = None
            srv._shared_install_graph = None

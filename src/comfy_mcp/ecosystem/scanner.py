"""Environment scanner that combines the install graph with bundled ecosystem data."""

from __future__ import annotations

import os
from typing import Any

from comfy_mcp.ecosystem.registry import EcosystemRegistry


class ModelAwarenessScanner:
    """Derive model and provider capabilities from a ComfyUI install snapshot."""

    def __init__(self, registry: EcosystemRegistry) -> None:
        self._registry = registry

    def scan(
        self,
        snapshot: dict[str, Any] | None,
        capabilities: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot = snapshot or {}
        capabilities = capabilities or {}
        models = snapshot.get("models", {})
        node_classes = snapshot.get("node_classes", set())

        matched_models: list[dict[str, Any]] = []
        detected_architectures: set[str] = set()
        detected_ecosystems: set[str] = set()
        available_capabilities: set[str] = set()
        available_modalities: set[str] = set()
        required_families: list[str] = []

        for folder, files in models.items():
            for filename in files:
                result = self._registry.classify_model(filename, folder)
                if result["family"]:
                    detected_architectures.add(result["family"])
                    required_families.append(result["family"])
                detected_ecosystems.update(result["ecosystems"])
                available_capabilities.update(result["tasks"])
                available_modalities.update(result["modality"])
                if result["family"] or result["ecosystems"]:
                    matched_models.append(result)

        provider_matches = self._registry.detect_providers(node_classes=node_classes, env=os.environ)
        for provider in provider_matches:
            available_capabilities.update(provider["tasks"])
            available_modalities.update(provider["modality"])

        missing_assets: list[dict[str, Any]] = []
        for family_id in sorted(set(required_families)):
            entry = self._registry.family_by_id(family_id)
            if entry is None:
                continue
            missing = entry.missing_assets(models)
            if missing:
                missing_assets.append({
                    "family": family_id,
                    "missing": missing,
                })

        available_runtimes = set()
        if detected_architectures:
            available_runtimes.add("local-native")
        if provider_matches:
            available_runtimes.add("partner-nodes")
        profile = capabilities.get("profile")
        if profile:
            available_runtimes.add(profile)

        return {
            "profile": profile or "unknown",
            "version": capabilities.get("version"),
            "detected_architectures": sorted(detected_architectures),
            "detected_ecosystems": sorted(detected_ecosystems),
            "detected_providers": sorted(provider["id"] for provider in provider_matches),
            "provider_details": provider_matches,
            "available_capabilities": sorted(available_capabilities),
            "available_modalities": sorted(available_modalities),
            "available_runtimes": sorted(available_runtimes),
            "available_model_folders": sorted(folder for folder, files in models.items() if files),
            "matched_models": matched_models[:50],
            "matched_model_count": len(matched_models),
            "missing_assets": missing_assets,
            "registry_summary": self._registry.summary(),
        }

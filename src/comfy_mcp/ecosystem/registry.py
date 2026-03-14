"""Bundled ecosystem registry for modern ComfyUI model and provider awareness."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _load_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_datasets() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    data_dir = Path(__file__).resolve().parent.parent / "data" / "ecosystem"
    if not (data_dir / "registry.json").exists():
        repo_data_dir = Path.cwd() / "src" / "comfy_mcp" / "data" / "ecosystem"
        if (repo_data_dir / "registry.json").exists():
            data_dir = repo_data_dir
    families = _load_json(data_dir / "registry.json")
    ecosystems = _load_json(data_dir / "community_ecosystems.json")
    providers = _load_json(data_dir / "providers.json")
    return families, ecosystems, providers


@dataclass(frozen=True)
class RegistryEntry:
    """Typed view over one ecosystem entry."""

    raw: dict[str, Any]

    @property
    def id(self) -> str:
        return self.raw["id"]

    @property
    def display_name(self) -> str:
        return self.raw["display_name"]

    @property
    def kind(self) -> str:
        return self.raw.get("kind", "family")

    @property
    def priority(self) -> int:
        return int(self.raw.get("priority", 0))

    @property
    def tasks(self) -> list[str]:
        return list(self.raw.get("tasks", []))

    @property
    def modalities(self) -> list[str]:
        return list(self.raw.get("modality", []))

    @property
    def runtime_modes(self) -> list[str]:
        return list(self.raw.get("runtime_modes", []))

    @property
    def required_folders(self) -> list[str]:
        return list(self.raw.get("required_folders", []))

    @property
    def optional_folders(self) -> list[str]:
        return list(self.raw.get("optional_folders", []))

    @property
    def community_tags(self) -> list[str]:
        return list(self.raw.get("community_tags", []))

    @property
    def source_urls(self) -> list[str]:
        return list(self.raw.get("source_urls", []))

    @property
    def last_verified_at(self) -> str:
        return self.raw.get("last_verified_at", "")

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "kind": self.kind,
            "priority": self.priority,
            "tasks": self.tasks,
            "modality": self.modalities,
            "runtime_modes": self.runtime_modes,
            "required_folders": self.required_folders,
            "community_tags": self.community_tags,
            "last_verified_at": self.last_verified_at,
        }

    def matches_model(self, filename: str, folder: str) -> bool:
        lower_name = filename.lower()
        normalized_name = _normalize(filename)
        for matcher in self.raw.get("matchers", []):
            matcher_folder = matcher.get("folder")
            if matcher_folder and matcher_folder != folder:
                continue
            for term in matcher.get("terms", []):
                if _normalize(term) in normalized_name:
                    return True
            for pattern in matcher.get("patterns", []):
                regex = re.compile(pattern, re.IGNORECASE)
                if regex.search(lower_name):
                    return True
        return False

    def missing_assets(self, models: dict[str, list[str]]) -> list[str]:
        missing: list[str] = []
        for requirement in self.raw.get("asset_requirements", []):
            folder = requirement["folder"]
            files = [item.lower() for item in models.get(folder, [])]
            patterns = requirement.get("patterns", [])
            if not any(any(re.search(pattern, filename, flags=re.IGNORECASE) for filename in files) for pattern in patterns):
                missing.extend(f"{folder}/{pattern}" for pattern in patterns)
        return missing


class EcosystemRegistry:
    """Curated registry of model families, ecosystems, and providers."""

    def __init__(self) -> None:
        families, ecosystems, providers = _load_datasets()
        self._families = [RegistryEntry(item) for item in families]
        self._ecosystems = [RegistryEntry(item) for item in ecosystems]
        self._providers = [RegistryEntry(item) for item in providers]

        self._families.sort(key=lambda entry: entry.priority, reverse=True)
        self._ecosystems.sort(key=lambda entry: entry.priority, reverse=True)
        self._providers.sort(key=lambda entry: entry.priority, reverse=True)

    def summary(self) -> dict[str, Any]:
        verified_dates = sorted(
            {
                entry.last_verified_at
                for entry in [*self._families, *self._ecosystems, *self._providers]
                if entry.last_verified_at
            }
        )
        last_verified = verified_dates[-1] if verified_dates else None
        return {
            "family_count": len(self._families),
            "ecosystem_count": len(self._ecosystems),
            "provider_count": len(self._providers),
            "latest_verified_at": last_verified,
            "family_ids": [entry.id for entry in self._families],
            "ecosystem_ids": [entry.id for entry in self._ecosystems],
            "provider_ids": [entry.id for entry in self._providers],
        }

    def list_entries(
        self,
        kind: str = "family",
        modality: str = "",
        runtime_mode: str = "",
    ) -> list[dict[str, Any]]:
        entries = {
            "family": self._families,
            "ecosystem": self._ecosystems,
            "provider": self._providers,
        }.get(kind, self._families)
        results: list[dict[str, Any]] = []
        for entry in entries:
            if modality and modality not in entry.modalities:
                continue
            if runtime_mode and runtime_mode not in entry.runtime_modes:
                continue
            results.append(entry.summary())
        return results

    def family_by_id(self, family_id: str) -> RegistryEntry | None:
        for entry in self._families:
            if entry.id == family_id:
                return entry
        return None

    def classify_model(self, filename: str, folder: str) -> dict[str, Any]:
        family = next((entry for entry in self._families if entry.matches_model(filename, folder)), None)
        ecosystems = [entry for entry in self._ecosystems if entry.matches_model(filename, folder)]
        return {
            "filename": filename,
            "folder": folder,
            "family": family.id if family else None,
            "family_display_name": family.display_name if family else None,
            "ecosystems": [entry.id for entry in ecosystems],
            "tasks": family.tasks if family else [],
            "modality": family.modalities if family else [],
            "runtime_modes": family.runtime_modes if family else [],
        }

    def detect_providers(
        self,
        node_classes: Iterable[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        node_names = {_normalize(name) for name in (node_classes or [])}
        env = env or {}
        matches: list[dict[str, Any]] = []
        for provider in self._providers:
            matched_by_node = False
            for term in provider.raw.get("node_terms", []):
                normalized_term = _normalize(term)
                if any(normalized_term in node_name for node_name in node_names):
                    matched_by_node = True
                    break
            configured = any(env.get(name) for name in provider.raw.get("auth_envs", []))
            if not (matched_by_node or configured):
                continue
            info = provider.summary()
            info["configured"] = configured
            info["detected_from_nodes"] = matched_by_node
            matches.append(info)
        return matches

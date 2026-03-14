"""Tests for RegistryIndex -- reverse lookup cache with negative caching."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestIndexLookup:
    def test_cache_hit_returns_instantly(self, tmp_path):
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path))
        # Pre-populate cache
        index._cache["KSampler"] = {
            "class": "KSampler", "package": "comfy-core", "cached_at": time.time(),
        }
        result = index.lookup("KSampler")
        assert result is not None
        assert result["package"] == "comfy-core"

    def test_cache_miss_returns_none(self, tmp_path):
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path))
        result = index.lookup("FakeNode")
        assert result is None


class TestNegativeCaching:
    def test_negative_entry_cached(self, tmp_path):
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path))
        index.cache_negative("FakeNode")
        result = index.lookup("FakeNode")
        assert result is not None
        assert result["package"] is None

    def test_negative_entry_expires(self, tmp_path):
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path), negative_ttl=0)
        index.cache_negative("FakeNode")
        result = index.lookup("FakeNode")
        # TTL=0 means it should be expired already
        assert result is None


class TestCachePositive:
    def test_cache_positive_stores_entry(self, tmp_path):
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path))
        index.cache_positive("ADE_Loader", "comfyui-animatediff-evolved", "1.2.3")
        result = index.lookup("ADE_Loader")
        assert result["package"] == "comfyui-animatediff-evolved"
        assert result["version"] == "1.2.3"


class TestDiskPersistence:
    def test_save_and_load(self, tmp_path):
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path))
        index.cache_positive("KSampler", "comfy-core", "0.17.0")
        index.save()
        assert (tmp_path / "node_class_index.json").exists()

        index2 = RegistryIndex(cache_dir=str(tmp_path))
        result = index2.lookup("KSampler")
        assert result is not None
        assert result["package"] == "comfy-core"

    def test_handles_corrupted_cache(self, tmp_path):
        (tmp_path / "node_class_index.json").write_text("{{invalid")
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path))
        # Should not crash, just start empty
        assert index.lookup("anything") is None


class TestIndexStats:
    def test_summary_reports_counts(self, tmp_path):
        from comfy_mcp.registry.index import RegistryIndex
        index = RegistryIndex(cache_dir=str(tmp_path))
        index.cache_positive("A", "pkg-a", "1.0")
        index.cache_positive("B", "pkg-b", "2.0")
        index.cache_negative("C")
        summary = index.summary()
        assert summary["total_entries"] == 3
        assert summary["positive_entries"] == 2
        assert summary["negative_entries"] == 1

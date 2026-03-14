"""Tests for ConfigManager — persistent user preferences."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


class TestConfigDefaults:
    def test_returns_defaults_when_no_file(self, tmp_path):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        assert config.get("safety.vram_warn_pct") == 80
        assert config.get("safety.vram_block_pct") == 95
        assert config.get("cache.max_age_seconds") == 300

    def test_returns_none_for_unknown_key(self, tmp_path):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        assert config.get("nonexistent.key") is None

    def test_get_all_returns_full_config(self, tmp_path):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        full = config.get_all()
        assert "safety" in full
        assert "cache" in full


class TestConfigReadWrite:
    def test_set_and_get(self, tmp_path):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        config.set("safety.vram_warn_pct", 90)
        assert config.get("safety.vram_warn_pct") == 90

    def test_persists_to_disk(self, tmp_path):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        config.set("safety.vram_warn_pct", 90)
        # Reload from disk
        config2 = ConfigManager(config_dir=str(tmp_path))
        assert config2.get("safety.vram_warn_pct") == 90

    def test_creates_config_file(self, tmp_path):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        config.set("safety.vram_warn_pct", 90)
        assert (tmp_path / "config.json").exists()


class TestConfigEnvOverride:
    def test_env_var_overrides_file(self, tmp_path, monkeypatch):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        config.set("safety.vram_warn_pct", 90)
        monkeypatch.setenv("COMFY_VRAM_WARN_PCT", "75")
        # Env var should override
        assert config.get("safety.vram_warn_pct") == 75

    def test_env_var_for_output_dir(self, tmp_path, monkeypatch):
        from comfy_mcp.knowledge.config import ConfigManager
        config = ConfigManager(config_dir=str(tmp_path))
        monkeypatch.setenv("COMFY_OUTPUT_DIR", "/custom/output")
        assert config.get("output.default_dir") == "/custom/output"

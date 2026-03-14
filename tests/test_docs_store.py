"""Tests for DocsStore — disk cache for ComfyUI documentation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestDocsStoreInit:
    def test_creates_storage_directory(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store_dir = tmp_path / "docs"
        store = DocsStore(storage_dir=str(store_dir))
        assert store_dir.exists()
        assert (store_dir / "embedded").exists()

    def test_defaults_to_home_comfypilot(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore()
        assert (tmp_path / ".comfypilot" / "docs").exists()


class TestFilenameSanitization:
    def test_simple_name_unchanged(self):
        from comfy_mcp.docs.store import _sanitize_filename
        assert _sanitize_filename("KSampler") == "KSampler"

    def test_plus_sign_replaced(self):
        from comfy_mcp.docs.store import _sanitize_filename
        assert _sanitize_filename("Node+Plus") == "Node_Plus"

    def test_parentheses_replaced(self):
        from comfy_mcp.docs.store import _sanitize_filename
        assert _sanitize_filename("Node(v2)") == "Node_v2_"

    def test_spaces_replaced(self):
        from comfy_mcp.docs.store import _sanitize_filename
        assert _sanitize_filename("My Custom Node") == "My_Custom_Node"

    def test_already_safe_with_dots(self):
        from comfy_mcp.docs.store import _sanitize_filename
        assert _sanitize_filename("ADE_AnimateDiff.v2") == "ADE_AnimateDiff.v2"

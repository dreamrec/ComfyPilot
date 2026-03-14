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


class TestEmbeddedDocCache:
    def test_save_and_get_embedded_doc(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_embedded("KSampler", "# KSampler\nSamples latents.")
        doc = store.get_embedded("KSampler")
        assert doc == "# KSampler\nSamples latents."

    def test_get_embedded_returns_none_for_missing(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        assert store.get_embedded("FakeNode") is None

    def test_save_embedded_updates_manifest(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_embedded("KSampler", "# KSampler\nSamples latents.")
        assert "KSampler" in store._manifest.get("embedded", {})

    def test_is_stale_returns_true_when_empty(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        assert store.is_stale() is True

    def test_is_stale_returns_false_when_fresh(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_embedded("KSampler", "doc")
        assert store.is_stale(max_age=300) is False

    def test_content_hash_changes_on_update(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_embedded("KSampler", "v1")
        hash1 = store.content_hash()
        store.save_embedded("KSampler", "v2")
        hash2 = store.content_hash()
        assert hash1 != hash2

    def test_unsafe_classname_stored_safely(self, tmp_path):
        from comfy_mcp.docs.store import DocsStore
        store = DocsStore(storage_dir=str(tmp_path / "docs"))
        store.save_embedded("Node(v2+)", "doc content")
        doc = store.get_embedded("Node(v2+)")
        assert doc == "doc content"
        files = list((tmp_path / "docs" / "embedded").glob("*"))
        for f in files:
            assert "(" not in f.name
            assert "+" not in f.name

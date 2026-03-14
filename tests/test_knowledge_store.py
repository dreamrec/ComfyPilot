"""Tests for KnowledgeStore protocol and atomic_write utility."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


class TestAtomicWrite:
    def test_happy_path_writes_file(self, tmp_path):
        from comfy_mcp.knowledge.store import atomic_write
        target = tmp_path / "test.json"
        atomic_write(target, '{"hello": "world"}')
        assert target.exists()
        assert target.read_text() == '{"hello": "world"}'

    def test_creates_parent_directories(self, tmp_path):
        from comfy_mcp.knowledge.store import atomic_write
        target = tmp_path / "a" / "b" / "test.json"
        atomic_write(target, "content")
        assert target.exists()
        assert target.read_text() == "content"

    def test_cleanup_on_failure(self, tmp_path, monkeypatch):
        from comfy_mcp.knowledge.store import atomic_write

        # Force os.rename to fail to simulate write failure
        def failing_rename(src, dst):
            raise OSError("simulated rename failure")
        monkeypatch.setattr(os, "rename", failing_rename)

        target = tmp_path / "test.json"
        with pytest.raises(OSError, match="simulated rename failure"):
            atomic_write(target, "content")

        # Temp file should be cleaned up
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_overwrites_existing_file(self, tmp_path):
        from comfy_mcp.knowledge.store import atomic_write
        target = tmp_path / "test.json"
        target.write_text("old content")
        atomic_write(target, "new content")
        assert target.read_text() == "new content"


class TestKnowledgeStoreProtocol:
    def test_protocol_is_runtime_checkable(self):
        from comfy_mcp.knowledge.store import KnowledgeStore
        from typing import Protocol
        assert issubclass(KnowledgeStore, Protocol)

    def test_compliant_class_passes_isinstance(self):
        from comfy_mcp.knowledge.store import KnowledgeStore

        class FakeStore:
            def is_stale(self, max_age: float = 300) -> bool:
                return False
            def content_hash(self) -> str:
                return "abc123"
            def summary(self) -> dict:
                return {}
            def clear(self) -> None:
                pass

        assert isinstance(FakeStore(), KnowledgeStore)

    def test_non_compliant_class_fails_isinstance(self):
        from comfy_mcp.knowledge.store import KnowledgeStore

        class BadStore:
            pass

        assert not isinstance(BadStore(), KnowledgeStore)

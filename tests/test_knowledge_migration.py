"""Tests for manifest.json -> state.json migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestManifestMigration:
    def test_migrates_manifest_to_state(self, tmp_path):
        from comfy_mcp.knowledge.migration import migrate_manifest_to_state
        manifest = {"version": 1, "docs": {"count": 5}}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        migrate_manifest_to_state(tmp_path)

        assert (tmp_path / "state.json").exists()
        state = json.loads((tmp_path / "state.json").read_text())
        assert "docs" in state or "migrated_from" in state

    def test_creates_backup_of_manifest(self, tmp_path):
        from comfy_mcp.knowledge.migration import migrate_manifest_to_state
        manifest = {"version": 1, "docs": {"count": 5}}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        migrate_manifest_to_state(tmp_path)

        assert (tmp_path / "manifest.json.bak").exists()
        backup = json.loads((tmp_path / "manifest.json.bak").read_text())
        assert backup == manifest

    def test_idempotent_rerun_does_not_overwrite(self, tmp_path):
        from comfy_mcp.knowledge.migration import migrate_manifest_to_state
        manifest = {"version": 1, "docs": {"count": 5}}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        migrate_manifest_to_state(tmp_path)
        first_state = (tmp_path / "state.json").read_text()

        # Run again -- should be idempotent
        migrate_manifest_to_state(tmp_path)
        second_state = (tmp_path / "state.json").read_text()
        assert first_state == second_state

    def test_noop_when_no_manifest(self, tmp_path):
        from comfy_mcp.knowledge.migration import migrate_manifest_to_state
        migrate_manifest_to_state(tmp_path)
        # No crash, no state.json created from nothing
        assert not (tmp_path / "state.json").exists()

    def test_noop_when_state_already_exists(self, tmp_path):
        from comfy_mcp.knowledge.migration import migrate_manifest_to_state
        (tmp_path / "manifest.json").write_text('{"old": true}')
        (tmp_path / "state.json").write_text('{"already": "migrated"}')

        migrate_manifest_to_state(tmp_path)
        state = json.loads((tmp_path / "state.json").read_text())
        assert state == {"already": "migrated"}  # Not overwritten

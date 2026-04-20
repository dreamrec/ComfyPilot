"""Tests for persistent snapshots (disk-backed storage)."""
from __future__ import annotations

import json

import pytest

from comfy_mcp.memory.snapshot_manager import SnapshotManager


WORKFLOW = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
    "2": {"class_type": "SaveImage", "inputs": {"filename_prefix": "out"}},
}


class TestInMemoryStillWorks:
    def test_no_storage_dir_keeps_old_behavior(self):
        mgr = SnapshotManager(max_snapshots=10)
        r = mgr.add(WORKFLOW, name="first")
        assert r["name"] == "first"
        assert len(mgr.list()) == 1


class TestPersistence:
    def test_snapshot_written_to_disk(self, tmp_path):
        mgr = SnapshotManager(max_snapshots=10, storage_dir=tmp_path)
        r = mgr.add(WORKFLOW, name="persisted")
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["name"] == "persisted"
        assert len(data["workflow"]) == 2

    def test_restart_reloads_snapshots(self, tmp_path):
        mgr1 = SnapshotManager(max_snapshots=10, storage_dir=tmp_path)
        mgr1.add(WORKFLOW, name="one")
        mgr1.add(WORKFLOW, name="two")
        mgr1.add(WORKFLOW, name="three")
        assert len(mgr1.list()) == 3

        # Fresh manager pointing at same dir
        mgr2 = SnapshotManager(max_snapshots=10, storage_dir=tmp_path)
        names = {s["name"] for s in mgr2.list()}
        assert names == {"one", "two", "three"}

    def test_delete_unpersists_file(self, tmp_path):
        mgr = SnapshotManager(max_snapshots=10, storage_dir=tmp_path)
        r = mgr.add(WORKFLOW, name="will-delete")
        sid = r["id"]
        assert (tmp_path / f"{sid}.json").exists()
        assert mgr.delete(sid) is True
        assert not (tmp_path / f"{sid}.json").exists()

    def test_lru_eviction_also_removes_file(self, tmp_path):
        mgr = SnapshotManager(max_snapshots=2, storage_dir=tmp_path)
        r1 = mgr.add(WORKFLOW, name="first")
        r2 = mgr.add(WORKFLOW, name="second")
        r3 = mgr.add(WORKFLOW, name="third")
        # first got evicted
        assert r1["id"] not in {s["id"] for s in mgr.list()}
        assert not (tmp_path / f"{r1['id']}.json").exists()
        # Second and third remain on disk
        assert (tmp_path / f"{r2['id']}.json").exists()
        assert (tmp_path / f"{r3['id']}.json").exists()

    def test_corrupted_file_is_skipped_on_load(self, tmp_path):
        # Write a valid one
        mgr1 = SnapshotManager(max_snapshots=10, storage_dir=tmp_path)
        mgr1.add(WORKFLOW, name="valid")
        # Write a corrupt one
        (tmp_path / "bad.json").write_text("{{{ not json")
        # Fresh manager should skip the bad file
        mgr2 = SnapshotManager(max_snapshots=10, storage_dir=tmp_path)
        assert len(mgr2.list()) == 1

    def test_max_snapshots_enforced_on_reload(self, tmp_path):
        # Add 5 to disk via a manager that allows 5
        mgr1 = SnapshotManager(max_snapshots=10, storage_dir=tmp_path)
        for i in range(5):
            mgr1.add(WORKFLOW, name=f"s{i}")
        # New manager with smaller cap trims to cap on load
        mgr2 = SnapshotManager(max_snapshots=2, storage_dir=tmp_path)
        assert len(mgr2.list()) == 2
        assert len(list(tmp_path.glob("*.json"))) == 2

"""Tests for SnapshotManager."""

from __future__ import annotations

import pytest

from comfy_mcp.memory.snapshot_manager import SnapshotManager


SAMPLE_WORKFLOW = {
    "1": {"class_type": "KSampler", "inputs": {"seed": 42}},
    "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl.safetensors"}},
}


class TestSnapshotAdd:
    def test_add_returns_metadata(self):
        mgr = SnapshotManager()
        meta = mgr.add(SAMPLE_WORKFLOW, "test snapshot")
        assert "id" in meta
        assert meta["name"] == "test snapshot"
        assert meta["node_count"] == 2

    def test_add_default_name(self):
        mgr = SnapshotManager()
        meta = mgr.add(SAMPLE_WORKFLOW)
        assert meta["name"].startswith("snapshot-")

    def test_add_deep_copies(self):
        mgr = SnapshotManager()
        workflow = {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}
        meta = mgr.add(workflow)
        workflow["1"]["inputs"]["seed"] = 999
        snap = mgr.get(meta["id"])
        assert snap["workflow"]["1"]["inputs"]["seed"] == 1  # unchanged


class TestSnapshotList:
    def test_list_newest_first(self):
        mgr = SnapshotManager()
        mgr.add({"1": {}}, "first")
        mgr.add({"2": {}}, "second")
        result = mgr.list()
        assert result[0]["name"] == "second"

    def test_list_with_limit(self):
        mgr = SnapshotManager()
        for i in range(10):
            mgr.add({str(i): {}}, f"snap-{i}")
        result = mgr.list(limit=3)
        assert len(result) == 3


class TestSnapshotGet:
    def test_get_existing(self):
        mgr = SnapshotManager()
        meta = mgr.add(SAMPLE_WORKFLOW)
        snap = mgr.get(meta["id"])
        assert snap is not None
        assert snap["workflow"] == SAMPLE_WORKFLOW

    def test_get_nonexistent(self):
        mgr = SnapshotManager()
        assert mgr.get("nonexistent") is None


class TestSnapshotDiff:
    def test_diff_no_changes(self):
        mgr = SnapshotManager()
        m1 = mgr.add(SAMPLE_WORKFLOW)
        m2 = mgr.add(SAMPLE_WORKFLOW)
        diff = mgr.diff(m1["id"], m2["id"])
        assert diff["total_changes"] == 0

    def test_diff_added_node(self):
        mgr = SnapshotManager()
        m1 = mgr.add({"1": {"class_type": "A"}})
        m2 = mgr.add({"1": {"class_type": "A"}, "2": {"class_type": "B"}})
        diff = mgr.diff(m1["id"], m2["id"])
        assert "2" in diff["added_nodes"]

    def test_diff_removed_node(self):
        mgr = SnapshotManager()
        m1 = mgr.add({"1": {}, "2": {}})
        m2 = mgr.add({"1": {}})
        diff = mgr.diff(m1["id"], m2["id"])
        assert "2" in diff["removed_nodes"]

    def test_diff_modified_node(self):
        mgr = SnapshotManager()
        m1 = mgr.add({"1": {"class_type": "A", "inputs": {"seed": 1}}})
        m2 = mgr.add({"1": {"class_type": "A", "inputs": {"seed": 999}}})
        diff = mgr.diff(m1["id"], m2["id"])
        assert "1" in diff["modified_nodes"]

    def test_diff_vs_current(self):
        mgr = SnapshotManager()
        m1 = mgr.add({"1": {}})
        diff = mgr.diff(m1["id"], current={"1": {}, "2": {}})
        assert "2" in diff["added_nodes"]

    def test_diff_not_found(self):
        mgr = SnapshotManager()
        diff = mgr.diff("nonexistent")
        assert "error" in diff


class TestSnapshotDelete:
    def test_delete_existing(self):
        mgr = SnapshotManager()
        meta = mgr.add(SAMPLE_WORKFLOW)
        assert mgr.delete(meta["id"]) is True
        assert mgr.get(meta["id"]) is None

    def test_delete_nonexistent(self):
        mgr = SnapshotManager()
        assert mgr.delete("nonexistent") is False


class TestSnapshotLRU:
    def test_eviction_at_limit(self):
        mgr = SnapshotManager(max_snapshots=3)
        ids = []
        for i in range(5):
            meta = mgr.add({str(i): {}}, f"snap-{i}")
            ids.append(meta["id"])
        # First two should be evicted
        assert mgr.get(ids[0]) is None
        assert mgr.get(ids[1]) is None
        # Last three should survive
        assert mgr.get(ids[2]) is not None
        assert mgr.get(ids[3]) is not None
        assert mgr.get(ids[4]) is not None

    def test_list_count_after_eviction(self):
        mgr = SnapshotManager(max_snapshots=3)
        for i in range(5):
            mgr.add({str(i): {}})
        assert len(mgr.list()) == 3

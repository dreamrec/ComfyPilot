"""Tests for snapshot tools."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest

from comfy_mcp.memory.snapshot_manager import SnapshotManager
from comfy_mcp.tools.snapshots import (
    comfy_auto_snapshot,
    comfy_delete_snapshot,
    comfy_diff_snapshots,
    comfy_list_snapshots,
    comfy_restore_snapshot,
    comfy_snapshot_workflow,
)


@pytest.fixture
def snap_ctx():
    """Context with real SnapshotManager."""
    mgr = SnapshotManager()
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {
        "snapshot_manager": mgr,
    }
    return ctx


class TestSnapshotWorkflow:
    @pytest.mark.asyncio
    async def test_snapshot_workflow_creates_snapshot(self, snap_ctx):
        """Test creating a snapshot returns metadata."""
        workflow = {"node_1": {"class_type": "KSampler"}, "node_2": {"class_type": "VAEDecode"}}
        result = await comfy_snapshot_workflow(workflow, name="test_snapshot", ctx=snap_ctx)
        data = json.loads(result)

        assert "id" in data
        assert data["name"] == "test_snapshot"
        assert "timestamp" in data
        assert data["node_count"] == 2

    @pytest.mark.asyncio
    async def test_snapshot_workflow_default_name(self, snap_ctx):
        """Test snapshot with no name gets auto-generated name."""
        workflow = {"node_1": {"class_type": "KSampler"}}
        result = await comfy_snapshot_workflow(workflow, ctx=snap_ctx)
        data = json.loads(result)

        assert "id" in data
        assert data["name"].startswith("snapshot-")
        assert data["node_count"] == 1

    @pytest.mark.asyncio
    async def test_snapshot_workflow_empty_workflow(self, snap_ctx):
        """Test snapshot with empty workflow."""
        workflow = {}
        result = await comfy_snapshot_workflow(workflow, name="empty", ctx=snap_ctx)
        data = json.loads(result)

        assert data["name"] == "empty"
        assert data["node_count"] == 0


class TestListSnapshots:
    @pytest.mark.asyncio
    async def test_list_snapshots_returns_list(self, snap_ctx):
        """Test listing snapshots returns list with metadata."""
        workflow1 = {"node_1": {"class_type": "KSampler"}}
        workflow2 = {"node_2": {"class_type": "VAEDecode"}}

        await comfy_snapshot_workflow(workflow1, name="snap1", ctx=snap_ctx)
        await comfy_snapshot_workflow(workflow2, name="snap2", ctx=snap_ctx)

        result = await comfy_list_snapshots(limit=20, ctx=snap_ctx)
        data = json.loads(result)

        assert data["total_count"] == 2
        assert len(data["snapshots"]) == 2
        # Newest first
        assert data["snapshots"][0]["name"] == "snap2"
        assert data["snapshots"][1]["name"] == "snap1"

    @pytest.mark.asyncio
    async def test_list_snapshots_respects_limit(self, snap_ctx):
        """Test that list respects limit parameter."""
        for i in range(5):
            workflow = {f"node_{i}": {"class_type": "KSampler"}}
            await comfy_snapshot_workflow(workflow, name=f"snap{i}", ctx=snap_ctx)

        result = await comfy_list_snapshots(limit=2, ctx=snap_ctx)
        data = json.loads(result)

        assert data["total_count"] == 2
        assert len(data["snapshots"]) == 2

    @pytest.mark.asyncio
    async def test_list_snapshots_empty(self, snap_ctx):
        """Test listing when no snapshots exist."""
        result = await comfy_list_snapshots(ctx=snap_ctx)
        data = json.loads(result)

        assert data["total_count"] == 0
        assert len(data["snapshots"]) == 0

    @pytest.mark.asyncio
    async def test_list_snapshots_newest_first(self, snap_ctx):
        """Test that snapshots are returned newest first."""
        for i in range(3):
            workflow = {f"node_{i}": {"class_type": "KSampler"}}
            await comfy_snapshot_workflow(workflow, name=f"snap{i}", ctx=snap_ctx)
            time.sleep(0.01)  # Small delay to ensure order

        result = await comfy_list_snapshots(ctx=snap_ctx)
        data = json.loads(result)

        assert data["snapshots"][0]["name"] == "snap2"
        assert data["snapshots"][1]["name"] == "snap1"
        assert data["snapshots"][2]["name"] == "snap0"


class TestDiffSnapshots:
    @pytest.mark.asyncio
    async def test_diff_two_snapshots(self, snap_ctx):
        """Test diffing two snapshots."""
        workflow1 = {"node_1": {"class_type": "KSampler"}, "node_2": {"class_type": "VAEDecode"}}
        workflow2 = {"node_1": {"class_type": "KSampler"}, "node_3": {"class_type": "VAEEncode"}}

        snap1_result = await comfy_snapshot_workflow(workflow1, name="snap1", ctx=snap_ctx)
        snap1_data = json.loads(snap1_result)
        snap1_id = snap1_data["id"]

        snap2_result = await comfy_snapshot_workflow(workflow2, name="snap2", ctx=snap_ctx)
        snap2_data = json.loads(snap2_result)
        snap2_id = snap2_data["id"]

        result = await comfy_diff_snapshots(snap1_id, snap2_id, ctx=snap_ctx)
        diff_data = json.loads(result)

        assert "node_3" in diff_data["added_nodes"]
        assert "node_2" in diff_data["removed_nodes"]
        assert "node_1" not in diff_data["modified_nodes"]
        assert diff_data["total_changes"] == 2

    @pytest.mark.asyncio
    async def test_diff_snapshot_vs_current(self, snap_ctx):
        """Test diffing snapshot vs current workflow."""
        old_workflow = {"node_1": {"class_type": "KSampler"}}
        current_workflow = {"node_1": {"class_type": "KSampler"}, "node_2": {"class_type": "VAEDecode"}}

        snap_result = await comfy_snapshot_workflow(old_workflow, name="old", ctx=snap_ctx)
        snap_data = json.loads(snap_result)
        snap_id = snap_data["id"]

        result = await comfy_diff_snapshots(snap_id, current_workflow=current_workflow, ctx=snap_ctx)
        diff_data = json.loads(result)

        assert "node_2" in diff_data["added_nodes"]
        assert len(diff_data["removed_nodes"]) == 0
        assert diff_data["total_changes"] == 1

    @pytest.mark.asyncio
    async def test_diff_nonexistent_snapshot(self, snap_ctx):
        """Test diffing with non-existent snapshot ID."""
        result = await comfy_diff_snapshots("nonexistent_id", ctx=snap_ctx)
        diff_data = json.loads(result)

        assert "error" in diff_data
        assert "not found" in diff_data["error"].lower()

    @pytest.mark.asyncio
    async def test_diff_missing_comparison(self, snap_ctx):
        """Test diff when neither id_b nor current_workflow provided."""
        workflow = {"node_1": {"class_type": "KSampler"}}
        snap_result = await comfy_snapshot_workflow(workflow, ctx=snap_ctx)
        snap_data = json.loads(snap_result)
        snap_id = snap_data["id"]

        result = await comfy_diff_snapshots(snap_id, ctx=snap_ctx)
        diff_data = json.loads(result)

        assert "error" in diff_data


class TestRestoreSnapshot:
    @pytest.mark.asyncio
    async def test_restore_snapshot_returns_workflow(self, snap_ctx):
        """Test restoring a snapshot returns full workflow data."""
        workflow = {"node_1": {"class_type": "KSampler", "inputs": {"seed": 42}}}
        snap_result = await comfy_snapshot_workflow(workflow, name="restore_test", ctx=snap_ctx)
        snap_data = json.loads(snap_result)
        snap_id = snap_data["id"]

        result = await comfy_restore_snapshot(snap_id, ctx=snap_ctx)
        restored = json.loads(result)

        assert restored["workflow"]["node_1"]["class_type"] == "KSampler"
        assert restored["workflow"]["node_1"]["inputs"]["seed"] == 42
        assert restored["name"] == "restore_test"

    @pytest.mark.asyncio
    async def test_restore_nonexistent_snapshot(self, snap_ctx):
        """Test restoring non-existent snapshot returns error."""
        result = await comfy_restore_snapshot("nonexistent_id", ctx=snap_ctx)
        data = json.loads(result)

        assert "error" in data
        assert data["snapshot_id"] == "nonexistent_id"

    @pytest.mark.asyncio
    async def test_restore_snapshot_deep_copy(self, snap_ctx):
        """Test that restored snapshot is a deep copy."""
        workflow = {"node_1": {"class_type": "KSampler", "nested": {"value": 42}}}
        snap_result = await comfy_snapshot_workflow(workflow, ctx=snap_ctx)
        snap_data = json.loads(snap_result)
        snap_id = snap_data["id"]

        result = await comfy_restore_snapshot(snap_id, ctx=snap_ctx)
        restored = json.loads(result)

        # Verify the data is correct
        assert restored["workflow"]["node_1"]["nested"]["value"] == 42


class TestDeleteSnapshot:
    @pytest.mark.asyncio
    async def test_delete_snapshot_succeeds(self, snap_ctx):
        """Test deleting a snapshot."""
        workflow = {"node_1": {"class_type": "KSampler"}}
        snap_result = await comfy_snapshot_workflow(workflow, ctx=snap_ctx)
        snap_data = json.loads(snap_result)
        snap_id = snap_data["id"]

        result = await comfy_delete_snapshot(snap_id, ctx=snap_ctx)
        data = json.loads(result)

        assert data["status"] == "deleted"
        assert data["snapshot_id"] == snap_id

        # Verify it's actually deleted
        list_result = await comfy_list_snapshots(ctx=snap_ctx)
        list_data = json.loads(list_result)
        assert list_data["total_count"] == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_snapshot(self, snap_ctx):
        """Test deleting non-existent snapshot returns error."""
        result = await comfy_delete_snapshot("nonexistent_id", ctx=snap_ctx)
        data = json.loads(result)

        assert "error" in data
        assert data["snapshot_id"] == "nonexistent_id"

    @pytest.mark.asyncio
    async def test_delete_snapshot_preserves_others(self, snap_ctx):
        """Test that deleting one snapshot doesn't affect others."""
        snap_ids = []
        for i in range(3):
            workflow = {f"node_{i}": {"class_type": "KSampler"}}
            snap_result = await comfy_snapshot_workflow(workflow, name=f"snap{i}", ctx=snap_ctx)
            snap_data = json.loads(snap_result)
            snap_ids.append(snap_data["id"])

        # Delete the middle one
        await comfy_delete_snapshot(snap_ids[1], ctx=snap_ctx)

        # Verify other snapshots still exist
        list_result = await comfy_list_snapshots(ctx=snap_ctx)
        list_data = json.loads(list_result)
        assert list_data["total_count"] == 2

        remaining_ids = [s["id"] for s in list_data["snapshots"]]
        assert snap_ids[0] in remaining_ids
        assert snap_ids[2] in remaining_ids
        assert snap_ids[1] not in remaining_ids


class TestAutoSnapshot:
    @pytest.mark.asyncio
    async def test_auto_snapshot_toggle_on(self, snap_ctx):
        """Test toggling auto_snapshot on."""
        result = await comfy_auto_snapshot(True, ctx=snap_ctx)
        data = json.loads(result)

        assert data["auto_snapshot"] is True
        assert data["status"] == "enabled"

    @pytest.mark.asyncio
    async def test_auto_snapshot_toggle_off(self, snap_ctx):
        """Test toggling auto_snapshot off."""
        result = await comfy_auto_snapshot(False, ctx=snap_ctx)
        data = json.loads(result)

        assert data["auto_snapshot"] is False
        assert data["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_auto_snapshot_flag_persists(self, snap_ctx):
        """Test that auto_snapshot flag persists on context."""
        await comfy_auto_snapshot(True, ctx=snap_ctx)

        mgr = snap_ctx.request_context.lifespan_context["snapshot_manager"]
        assert mgr.auto_snapshot is True

        await comfy_auto_snapshot(False, ctx=snap_ctx)
        assert mgr.auto_snapshot is False


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_full_roundtrip_snapshot_restore(self, snap_ctx):
        """Test full roundtrip: snapshot -> list -> restore -> verify."""
        original_workflow = {
            "node_1": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20}},
            "node_2": {"class_type": "VAEDecode", "inputs": {"samples": "1"}},
            "node_3": {"class_type": "SaveImage", "inputs": {"filename_prefix": "output"}},
        }

        # Create snapshot
        snap_result = await comfy_snapshot_workflow(original_workflow, name="complete_test", ctx=snap_ctx)
        snap_data = json.loads(snap_result)
        snap_id = snap_data["id"]

        # List snapshots
        list_result = await comfy_list_snapshots(ctx=snap_ctx)
        list_data = json.loads(list_result)
        assert list_data["total_count"] == 1
        assert list_data["snapshots"][0]["id"] == snap_id
        assert list_data["snapshots"][0]["name"] == "complete_test"

        # Restore snapshot
        restore_result = await comfy_restore_snapshot(snap_id, ctx=snap_ctx)
        restore_data = json.loads(restore_result)

        # Verify workflow matches
        assert restore_data["workflow"] == original_workflow
        assert restore_data["name"] == "complete_test"

        # Delete snapshot
        delete_result = await comfy_delete_snapshot(snap_id, ctx=snap_ctx)
        delete_data = json.loads(delete_result)
        assert delete_data["status"] == "deleted"

        # Verify deletion
        final_list = await comfy_list_snapshots(ctx=snap_ctx)
        final_data = json.loads(final_list)
        assert final_data["total_count"] == 0

    @pytest.mark.asyncio
    async def test_multiple_snapshots_lifecycle(self, snap_ctx):
        """Test managing multiple snapshots through their lifecycle."""
        snap_ids = []

        # Create 3 snapshots
        for i in range(3):
            workflow = {f"node_{i}_1": {"class_type": "KSampler"}, f"node_{i}_2": {"class_type": "VAEDecode"}}
            snap_result = await comfy_snapshot_workflow(workflow, name=f"snapshot_{i}", ctx=snap_ctx)
            snap_data = json.loads(snap_result)
            snap_ids.append(snap_data["id"])

        # Verify all exist
        list_result = await comfy_list_snapshots(ctx=snap_ctx)
        list_data = json.loads(list_result)
        assert list_data["total_count"] == 3

        # Diff snapshots
        diff_result = await comfy_diff_snapshots(snap_ids[0], snap_ids[1], ctx=snap_ctx)
        diff_data = json.loads(diff_result)
        assert "added_nodes" in diff_data
        assert "removed_nodes" in diff_data

        # Delete first snapshot
        await comfy_delete_snapshot(snap_ids[0], ctx=snap_ctx)

        # Verify count decreased
        list_result = await comfy_list_snapshots(ctx=snap_ctx)
        list_data = json.loads(list_result)
        assert list_data["total_count"] == 2

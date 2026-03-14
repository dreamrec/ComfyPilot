"""SnapshotManager — in-memory workflow snapshots with LRU eviction.

Stores workflow state snapshots for undo/restore capability.
Snapshots are ordered by creation time; oldest evicted when limit reached.
"""

from __future__ import annotations

import copy
import time
import uuid
from typing import Any


class SnapshotManager:
    """Manages workflow snapshots with bounded storage."""

    def __init__(self, max_snapshots: int = 50):
        """Initialize snapshot manager.

        Args:
            max_snapshots: Maximum number of snapshots to retain.
        """
        self._max = max_snapshots
        self._snapshots: dict[str, dict] = {}  # id → snapshot data
        self._order: list[str] = []  # oldest first
        self.auto_snapshot = False  # Toggle for automatic snapshot creation

    def add(self, workflow: dict, name: str = "") -> dict:
        """Create a new snapshot. Returns snapshot metadata (id, name, timestamp, node_count).

        Args:
            workflow: The workflow dictionary to snapshot.
            name: Optional name for the snapshot.

        Returns:
            Dictionary with id, name, timestamp, and node_count.
        """
        snapshot_id = str(uuid.uuid4())[:8]
        snapshot = {
            "id": snapshot_id,
            "name": name or f"snapshot-{snapshot_id}",
            "workflow": copy.deepcopy(workflow),
            "timestamp": time.time(),
            "node_count": len(workflow),
        }
        self._snapshots[snapshot_id] = snapshot
        self._order.append(snapshot_id)
        self._trim()
        return {
            "id": snapshot_id,
            "name": snapshot["name"],
            "timestamp": snapshot["timestamp"],
            "node_count": snapshot["node_count"],
        }

    def list(self, limit: int = 20) -> list[dict]:
        """List snapshot metadata (newest first), no workflow data.

        Args:
            limit: Maximum number of snapshots to return.

        Returns:
            List of snapshot metadata dictionaries, newest first.
        """
        result = []
        for sid in reversed(self._order):
            if len(result) >= limit:
                break
            snap = self._snapshots.get(sid)
            if snap:
                result.append({
                    "id": snap["id"],
                    "name": snap["name"],
                    "timestamp": snap["timestamp"],
                    "node_count": snap["node_count"],
                })
        return result

    def get(self, snapshot_id: str) -> dict | None:
        """Get a full snapshot including workflow data.

        Args:
            snapshot_id: The snapshot ID to retrieve.

        Returns:
            Full snapshot dictionary or None if not found.
        """
        snap = self._snapshots.get(snapshot_id)
        if snap:
            return copy.deepcopy(snap)
        return None

    def diff(self, id_a: str, id_b: str | None = None, current: dict | None = None) -> dict:
        """Diff two snapshots or a snapshot vs current workflow.

        Returns dict with: added_nodes, removed_nodes, modified_nodes.

        Args:
            id_a: First snapshot ID.
            id_b: Optional second snapshot ID.
            current: Optional current workflow to diff against.

        Returns:
            Dictionary with added_nodes, removed_nodes, modified_nodes, total_changes.
        """
        snap_a = self._snapshots.get(id_a)
        if not snap_a:
            return {"error": f"Snapshot {id_a} not found"}

        workflow_a = snap_a["workflow"]

        if id_b:
            snap_b = self._snapshots.get(id_b)
            if not snap_b:
                return {"error": f"Snapshot {id_b} not found"}
            workflow_b = snap_b["workflow"]
        elif current is not None:
            workflow_b = current
        else:
            return {"error": "Provide either id_b or current workflow"}

        keys_a = set(workflow_a.keys())
        keys_b = set(workflow_b.keys())

        added = list(keys_b - keys_a)
        removed = list(keys_a - keys_b)
        modified = []
        for key in keys_a & keys_b:
            if workflow_a[key] != workflow_b[key]:
                modified.append(key)

        return {
            "added_nodes": sorted(added),
            "removed_nodes": sorted(removed),
            "modified_nodes": sorted(modified),
            "total_changes": len(added) + len(removed) + len(modified),
        }

    def delete(self, snapshot_id: str) -> bool:
        """Delete a snapshot. Returns True if found and deleted.

        Args:
            snapshot_id: The snapshot ID to delete.

        Returns:
            True if snapshot was found and deleted, False otherwise.
        """
        if snapshot_id in self._snapshots:
            del self._snapshots[snapshot_id]
            self._order = [s for s in self._order if s != snapshot_id]
            return True
        return False

    def _trim(self) -> None:
        """Evict oldest snapshots when over limit."""
        while len(self._snapshots) > self._max:
            oldest_id = self._order.pop(0)
            self._snapshots.pop(oldest_id, None)

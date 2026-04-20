"""SnapshotManager - workflow snapshots with optional disk persistence.

Stores workflow state snapshots for undo/restore capability. When
storage_dir is set, snapshots persist as JSON files and survive restart;
otherwise they live purely in memory. Eviction is LRU by creation time.
"""

from __future__ import annotations

import copy
import json
import time
import uuid
from pathlib import Path
from typing import Any


class SnapshotManager:
    """Manages workflow snapshots with bounded storage, optionally persisted to disk."""

    def __init__(self, max_snapshots: int = 50, storage_dir: Path | str | None = None):
        """Initialize snapshot manager.

        Args:
            max_snapshots: Maximum number of snapshots to retain.
            storage_dir: If set, snapshots persist as JSON files in this
                directory and survive restart. If None, snapshots are
                in-memory only (backward-compatible with pre-1.3 behavior).
        """
        self._max = max_snapshots
        self._snapshots: dict[str, dict] = {}
        self._order: list[str] = []
        self.auto_snapshot = False
        self._dir: Path | None = Path(storage_dir) if storage_dir else None
        if self._dir is not None:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Populate _snapshots and _order from persisted files (oldest first)."""
        if self._dir is None:
            return
        files = sorted(self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for p in files:
            try:
                data = json.loads(p.read_text())
                sid = data.get("id") or p.stem
                data["id"] = sid
                self._snapshots[sid] = data
                self._order.append(sid)
            except (json.JSONDecodeError, OSError):
                continue
        # Respect max_snapshots after load
        self._trim()

    def _persist(self, snapshot_id: str) -> None:
        if self._dir is None:
            return
        snap = self._snapshots.get(snapshot_id)
        if snap is None:
            return
        try:
            (self._dir / f"{snapshot_id}.json").write_text(json.dumps(snap, indent=2))
        except OSError:
            pass

    def _unpersist(self, snapshot_id: str) -> None:
        if self._dir is None:
            return
        try:
            (self._dir / f"{snapshot_id}.json").unlink(missing_ok=True)
        except OSError:
            pass

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
        self._persist(snapshot_id)
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
            self._unpersist(snapshot_id)
            return True
        return False

    def _trim(self) -> None:
        """Evict oldest snapshots when over limit."""
        while len(self._snapshots) > self._max:
            oldest_id = self._order.pop(0)
            self._snapshots.pop(oldest_id, None)
            self._unpersist(oldest_id)

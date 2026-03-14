"""Snapshot manager — stub for Task 14."""
from __future__ import annotations


class SnapshotManager:
    """Manages workflow state snapshots for undo/redo and comparison."""

    def __init__(self, max_snapshots: int = 50):
        """Initialize snapshot manager.

        Args:
            max_snapshots: Maximum number of snapshots to retain.
        """
        self._max = max_snapshots

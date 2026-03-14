"""Job tracker — stub for Task 12."""
from __future__ import annotations

from typing import Any


class JobTracker:
    """Tracks workflow job execution state and progress."""

    def __init__(self, client: Any, event_mgr: Any):
        """Initialize job tracker.

        Args:
            client: ComfyClient instance for queue operations.
            event_mgr: EventManager instance for event subscriptions.
        """
        self._client = client
        self._event_mgr = event_mgr

"""VRAM guard — stub for Task 17."""
from __future__ import annotations

from typing import Any


class VRAMGuard:
    """Monitors and enforces VRAM safety thresholds."""

    def __init__(self, client: Any):
        """Initialize VRAM guard.

        Args:
            client: ComfyClient instance for system stats queries.
        """
        self._client = client

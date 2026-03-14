"""WebSocket event manager — stub for Task 10."""
from __future__ import annotations

from typing import Any


class EventManager:
    """Manages WebSocket event subscriptions and dispatching."""

    def __init__(self, client: Any):
        """Initialize event manager with a ComfyClient reference.

        Args:
            client: ComfyClient instance for websocket operations.
        """
        self._client = client

    async def shutdown(self) -> None:
        """Shutdown event manager and close any active connections."""
        pass

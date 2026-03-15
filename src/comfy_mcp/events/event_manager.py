"""EventManager - WebSocket listener for ComfyUI execution events.

Connects to ComfyUI's /ws endpoint, buffers events, supports subscriptions,
and provides auto-reconnect with exponential backoff.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Any, Callable

logger = logging.getLogger("comfypilot.events")


class EventManager:
    """Manages WebSocket connection to ComfyUI for real-time events."""

    def __init__(self, client):
        self._client = client
        self._subscriptions: dict[str, list[Callable]] = {}
        self._event_buffer: deque[dict] = deque(maxlen=1000)
        self._ws = None
        self._ws_task: asyncio.Task | None = None
        self._reconnect_count = 0
        self._running = False
        self._progress_cache: dict[str, dict] = {}  # prompt_id -> latest progress

    async def start(self) -> None:
        """Launch the WebSocket listener task."""
        if self._running:
            return
        self._running = True
        self._ws_task = asyncio.create_task(self._ws_loop())

    async def shutdown(self) -> None:
        """Cancel listener task and close WebSocket."""
        self._running = False
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        self._ws_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def _ws_loop(self) -> None:
        """Connect, listen, dispatch events, reconnect on failure."""
        import websockets

        base = self._client.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{base}/ws?clientId={self._client._client_id}"

        while self._running:
            try:
                async with websockets.connect(ws_url, **self._ws_connect_kwargs()) as ws:
                    self._ws = ws
                    self._reconnect_count = 0
                    logger.info("WebSocket connected to %s", ws_url)

                    async for raw_msg in ws:
                        if not self._running:
                            break
                        if isinstance(raw_msg, bytes):
                            # ComfyUI may send binary preview frames; ignore them for now.
                            continue
                        try:
                            msg = json.loads(raw_msg)
                            self._dispatch(msg)
                        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
                            continue

            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                self._reconnect_count += 1
                if self._reconnect_count > self._client.ws_reconnect_max:
                    logger.error("Max reconnect attempts (%d) reached", self._client.ws_reconnect_max)
                    break
                delay = min(2 ** (self._reconnect_count - 1), 16)
                logger.warning("WS disconnected (%s), reconnecting in %ds (attempt %d/%d)",
                               e, delay, self._reconnect_count, self._client.ws_reconnect_max)
                await asyncio.sleep(delay)

        self._ws = None

    def _ws_connect_kwargs(self) -> dict[str, Any]:
        """Pass through auth headers so WS monitoring matches HTTP auth."""
        headers = self._client.get_auth_headers() if hasattr(self._client, "get_auth_headers") else {}
        if headers:
            return {"additional_headers": headers}
        return {}

    def _dispatch(self, msg: dict) -> None:
        """Buffer event and notify subscribers."""
        event_type = msg.get("type", "unknown")
        event = {
            "type": event_type,
            "data": msg.get("data", {}),
            "timestamp": time.time(),
        }
        self._event_buffer.append(event)

        # Cache progress events
        if event_type == "progress":
            prompt_id = msg.get("data", {}).get("prompt_id", "")
            if prompt_id:
                self._progress_cache[prompt_id] = event

        # Notify subscribers
        for callback in self._subscriptions.get(event_type, []):
            try:
                callback(event)
            except Exception:
                logger.exception("Subscriber callback error for %s", event_type)

    def subscribe(self, event_type: str, callback: Callable | None = None) -> None:
        """Register interest in an event type."""
        if event_type not in self._subscriptions:
            self._subscriptions[event_type] = []
        if callback and callback not in self._subscriptions[event_type]:
            self._subscriptions[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable | None = None) -> None:
        """Remove subscription."""
        if callback and event_type in self._subscriptions:
            self._subscriptions[event_type] = [
                cb for cb in self._subscriptions[event_type] if cb != callback
            ]
        elif not callback and event_type in self._subscriptions:
            del self._subscriptions[event_type]

    def drain_events(self, event_type: str | None = None, limit: int = 100) -> list[dict]:
        """Return and remove buffered events, optionally filtered by type."""
        if event_type is None:
            events = list(self._event_buffer)[:limit]
            # Remove only the returned events from the front
            for _ in range(len(events)):
                self._event_buffer.popleft()
            return events

        matched = []
        remaining = deque(maxlen=self._event_buffer.maxlen)
        for ev in self._event_buffer:
            if ev["type"] == event_type and len(matched) < limit:
                matched.append(ev)
            else:
                remaining.append(ev)
        self._event_buffer = remaining
        return matched

    def peek_events(self, event_type: str | None = None, limit: int = 100) -> list[dict]:
        """Return buffered events without consuming them."""
        if event_type is None:
            return list(self._event_buffer)[:limit]

        matched = []
        for ev in self._event_buffer:
            if ev["type"] == event_type:
                matched.append(ev)
            if len(matched) >= limit:
                break
        return matched

    def get_latest_progress(self, prompt_id: str) -> dict | None:
        """Get cached progress for a prompt_id."""
        return self._progress_cache.get(prompt_id)

    def health(self) -> dict:
        """Return health status of the event system."""
        return {
            "running": self._running,
            "connected": self._ws is not None,
            "reconnect_count": self._reconnect_count,
            "buffer_size": len(self._event_buffer),
            "buffer_capacity": self._event_buffer.maxlen,
            "subscription_count": sum(len(cbs) for cbs in self._subscriptions.values()),
            "subscribed_types": list(self._subscriptions.keys()),
        }

"""EventManager - WebSocket listener for ComfyUI execution events.

Connects to ComfyUI's /ws endpoint, buffers events, supports subscriptions,
and provides auto-reconnect with exponential backoff.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from collections import OrderedDict, deque
from typing import Any, Callable

logger = logging.getLogger("comfypilot.events")


class EventManager:
    """Manages WebSocket connection to ComfyUI for real-time events."""

    _HIGH_SIGNAL_TYPES = frozenset({
        "connection_restored",
        "execution_start",
        "execution_success",
        "execution_error",
        "execution_interrupted",
        "execution_cached",
        "executed",
    })
    _TERMINAL_TYPES = frozenset({
        "execution_success",
        "execution_error",
        "execution_interrupted",
    })
    _PROGRESS_CACHE_LIMIT = 512
    _PROGRESS_CACHE_TTL = 3600.0

    def __init__(self, client):
        self._client = client
        self._subscriptions: dict[str, list[Callable]] = {}
        self._event_buffer: deque[dict] = deque(maxlen=1000)
        self._ws = None
        self._ws_task: asyncio.Task | None = None
        self._reconnect_count = 0
        self._reconnect_total = 0
        self._connection_generation = 0
        self._last_error: str | None = None
        self._running = False
        self._progress_cache: OrderedDict[str, dict] = OrderedDict()
        self._subscriber_tasks: set[asyncio.Task] = set()
        self._capability_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Launch the WebSocket listener task."""
        if self._running and self._ws_task is not None and not self._ws_task.done():
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
        background_tasks = list(self._subscriber_tasks)
        if self._capability_task and not self._capability_task.done():
            background_tasks.append(self._capability_task)
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
        self._capability_task = None
        self._subscriber_tasks.clear()
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
                    attempts_before_connect = self._reconnect_count
                    self._reconnect_count = 0
                    self._last_error = None
                    self._connection_generation += 1
                    logger.info("WebSocket connected to %s", ws_url)

                    if self._connection_generation > 1 or attempts_before_connect:
                        self._dispatch({
                            "type": "connection_restored",
                            "data": {
                                "generation": self._connection_generation,
                                "attempts": attempts_before_connect,
                            },
                        })
                        self._schedule_capability_refresh()

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

                    if self._running:
                        raise ConnectionError("WebSocket closed by ComfyUI")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._ws = None
                if not self._running:
                    break
                self._reconnect_count += 1
                self._reconnect_total += 1
                self._last_error = str(e)
                # ws_reconnect_max now caps the exponential backoff exponent;
                # it does not permanently disable monitoring after a restart.
                exponent_cap = max(0, int(getattr(self._client, "ws_reconnect_max", 5)) - 1)
                exponent = min(self._reconnect_count - 1, exponent_cap)
                delay = min(2 ** exponent, 16)
                logger.warning(
                    "WS disconnected (%s), reconnecting in %ds (consecutive attempt %d)",
                    e,
                    delay,
                    self._reconnect_count,
                )
                await asyncio.sleep(delay)

        self._ws = None

    def _schedule_capability_refresh(self) -> None:
        """Refresh server capabilities after reconnect without blocking events."""
        probe = getattr(self._client, "probe_capabilities", None)
        if not callable(probe):
            return
        if self._capability_task is not None and not self._capability_task.done():
            return

        async def _refresh() -> None:
            try:
                result = probe()
                if inspect.isawaitable(result):
                    await result
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Capability refresh failed after WebSocket reconnect")

        self._capability_task = asyncio.create_task(_refresh())

    def _ws_connect_kwargs(self) -> dict[str, Any]:
        """Pass through auth headers so WS monitoring matches HTTP auth."""
        headers = self._client.get_auth_headers() if hasattr(self._client, "get_auth_headers") else {}
        if headers:
            return {"additional_headers": headers}
        return {}

    def _dispatch(self, msg: dict) -> None:
        """Buffer event and notify subscribers."""
        event_type = msg.get("type", "unknown")
        raw_data = msg.get("data", {})
        data = raw_data if isinstance(raw_data, dict) else {"value": raw_data}
        event = {
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
        }
        self._append_event(event)

        normalized_progress = self._normalize_progress(event)
        if normalized_progress is not None:
            prompt_id = str(normalized_progress["data"].get("prompt_id", ""))
            if prompt_id:
                self._cache_progress(prompt_id, normalized_progress)

        if event_type in self._TERMINAL_TYPES:
            prompt_id = str(data.get("prompt_id", ""))
            if prompt_id:
                self._progress_cache.pop(prompt_id, None)

        self._notify(event_type, event)
        # Consumers written for the legacy event continue to work when a new
        # ComfyUI server only emits progress_state.
        if event_type == "progress_state" and normalized_progress is not None:
            self._notify("progress", normalized_progress)

    def _notify(self, event_type: str, event: dict) -> None:
        """Notify synchronous or asynchronous subscribers safely."""
        for callback in tuple(self._subscriptions.get(event_type, [])):
            try:
                result = callback(event)
                if inspect.isawaitable(result):
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        close = getattr(result, "close", None)
                        if callable(close):
                            close()
                        logger.error("Cannot run async subscriber for %s without an event loop", event_type)
                        continue
                    task = loop.create_task(result)
                    self._subscriber_tasks.add(task)
                    task.add_done_callback(self._subscriber_done)
            except Exception:
                logger.exception("Subscriber callback error for %s", event_type)

    def _subscriber_done(self, task: asyncio.Task) -> None:
        self._subscriber_tasks.discard(task)
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Async subscriber callback failed")

    def _normalize_progress(self, event: dict) -> dict | None:
        """Normalize legacy progress and v0.31 progress_state payloads."""
        event_type = event.get("type")
        data = event.get("data", {})
        if event_type == "progress":
            normalized = dict(data)
            normalized["source_type"] = "progress"
        elif event_type == "progress_state":
            nodes = data.get("nodes", {})
            if not isinstance(nodes, dict) or not nodes:
                return None
            node_items = [
                (str(node_id), node)
                for node_id, node in nodes.items()
                if isinstance(node, dict)
            ]
            if not node_items:
                return None
            active = [
                item for item in node_items
                if str(item[1].get("state", "")).lower() in {"running", "executing"}
            ]
            node_id, node = (active or node_items)[-1]
            normalized = {
                "prompt_id": data.get("prompt_id") or node.get("prompt_id", ""),
                "node": node.get("node_id", node_id),
                "node_id": node.get("node_id", node_id),
                "value": node.get("value", 0),
                "max": node.get("max", 0),
                "state": node.get("state", ""),
                "nodes": nodes,
                "source_type": "progress_state",
            }
        else:
            return None
        return {"type": "progress", "data": normalized, "timestamp": event["timestamp"]}

    def _cache_progress(self, prompt_id: str, event: dict) -> None:
        self._cleanup_progress_cache()
        self._progress_cache.pop(prompt_id, None)
        self._progress_cache[prompt_id] = event
        while len(self._progress_cache) > self._PROGRESS_CACHE_LIMIT:
            self._progress_cache.popitem(last=False)

    def _cleanup_progress_cache(self) -> None:
        cutoff = time.time() - self._PROGRESS_CACHE_TTL
        expired = [
            prompt_id
            for prompt_id, event in self._progress_cache.items()
            if float(event.get("timestamp", 0.0) or 0.0) < cutoff
        ]
        for prompt_id in expired:
            self._progress_cache.pop(prompt_id, None)

    @staticmethod
    def _coalesce_key(event: dict) -> tuple[str, str] | None:
        event_type = str(event.get("type", "unknown"))
        data = event.get("data", {})
        if event_type in {"progress", "progress_state"}:
            prompt_id = str(data.get("prompt_id", ""))
            return ("progress", prompt_id) if prompt_id else None
        if event_type in {"status", "crystools.monitor"}:
            return (event_type, "global")
        return None

    def _append_event(self, event: dict) -> None:
        """Coalesce noisy state and preferentially retain terminal events."""
        key = self._coalesce_key(event)
        if key is not None:
            for index in range(len(self._event_buffer) - 1, -1, -1):
                if self._coalesce_key(self._event_buffer[index]) == key:
                    del self._event_buffer[index]
                    break

        if len(self._event_buffer) == self._event_buffer.maxlen:
            for index, existing in enumerate(self._event_buffer):
                if existing.get("type") not in self._HIGH_SIGNAL_TYPES:
                    del self._event_buffer[index]
                    break
        self._event_buffer.append(event)

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
        """Return the most recent buffered events without consuming them."""
        if limit <= 0:
            return []
        events = list(self._event_buffer)
        if event_type is not None:
            events = [event for event in events if event["type"] == event_type]
        return events[-limit:]

    def get_latest_progress(self, prompt_id: str) -> dict | None:
        """Get cached progress for a prompt_id."""
        self._cleanup_progress_cache()
        return self._progress_cache.get(prompt_id)

    def health(self) -> dict:
        """Return health status of the event system."""
        listener_alive = self._ws_task is not None and not self._ws_task.done()
        return {
            "running": self._running and listener_alive,
            "desired_running": self._running,
            "listener_alive": listener_alive,
            "connected": self._ws is not None,
            "reconnect_count": self._reconnect_count,
            "reconnect_total": self._reconnect_total,
            "connection_generation": self._connection_generation,
            "last_error": self._last_error,
            "buffer_size": len(self._event_buffer),
            "buffer_capacity": self._event_buffer.maxlen,
            "subscription_count": sum(len(cbs) for cbs in self._subscriptions.values()),
            "subscribed_types": list(self._subscriptions.keys()),
        }

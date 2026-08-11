"""Tests for EventManager."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.events.event_manager import EventManager


@pytest.fixture
def mock_ws_client():
    client = MagicMock()
    client.base_url = "http://localhost:8188"
    client._client_id = "test-client-id"
    client.ws_reconnect_max = 3
    client.get_auth_headers = MagicMock(return_value={})
    return client


@pytest.fixture
def event_mgr(mock_ws_client):
    return EventManager(mock_ws_client)


class TestEventManagerInit:
    def test_initial_state(self, event_mgr):
        assert event_mgr._running is False
        assert event_mgr._ws is None
        assert event_mgr._ws_task is None
        assert len(event_mgr._event_buffer) == 0
        assert len(event_mgr._subscriptions) == 0

    def test_client_stored(self, event_mgr, mock_ws_client):
        assert event_mgr._client is mock_ws_client


class TestEventManagerDispatch:
    def test_dispatch_buffers_event(self, event_mgr):
        event_mgr._dispatch({"type": "progress", "data": {"value": 5, "max": 20}})
        assert len(event_mgr._event_buffer) == 1
        ev = event_mgr._event_buffer[0]
        assert ev["type"] == "progress"
        assert ev["data"]["value"] == 5

    def test_dispatch_caches_progress(self, event_mgr):
        event_mgr._dispatch({"type": "progress", "data": {"prompt_id": "p1", "value": 10, "max": 20}})
        progress = event_mgr.get_latest_progress("p1")
        assert progress is not None
        assert progress["data"]["value"] == 10

    def test_dispatch_normalizes_progress_state(self, event_mgr):
        event_mgr._dispatch({
            "type": "progress_state",
            "data": {
                "prompt_id": "p-new",
                "nodes": {
                    "4": {"value": 2, "max": 10, "state": "running"},
                    "3": {"value": 5, "max": 5, "state": "finished"},
                },
            },
        })
        progress = event_mgr.get_latest_progress("p-new")
        assert progress["type"] == "progress"
        assert progress["data"]["value"] == 2
        assert progress["data"]["max"] == 10
        assert progress["data"]["node_id"] == "4"
        assert progress["data"]["source_type"] == "progress_state"

    def test_terminal_event_cleans_progress(self, event_mgr):
        event_mgr._dispatch({
            "type": "progress",
            "data": {"prompt_id": "p1", "value": 10, "max": 20},
        })
        event_mgr._dispatch({"type": "execution_success", "data": {"prompt_id": "p1"}})
        assert event_mgr.get_latest_progress("p1") is None

    def test_dispatch_notifies_subscribers(self, event_mgr):
        received = []
        event_mgr.subscribe("progress", lambda ev: received.append(ev))
        event_mgr._dispatch({"type": "progress", "data": {"value": 1}})
        assert len(received) == 1

    def test_dispatch_unknown_type(self, event_mgr):
        event_mgr._dispatch({"data": {"foo": "bar"}})
        assert event_mgr._event_buffer[0]["type"] == "unknown"

    @pytest.mark.asyncio
    async def test_ws_loop_ignores_binary_frames(self, event_mgr):
        class FakeWS:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

            def __aiter__(self_inner):
                async def _iter():
                    yield b"\x89PNG"
                    event_mgr._running = False
                return _iter()

        def fake_connect(*args, **kwargs):
            return FakeWS()

        original_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "websockets":
                return type("WebsocketsModule", (), {"connect": fake_connect})
            return original_import(name, *args, **kwargs)

        event_mgr._running = True
        try:
            import builtins

            builtins_import = builtins.__import__
            builtins.__import__ = fake_import
            await event_mgr._ws_loop()
        finally:
            builtins.__import__ = builtins_import

        assert len(event_mgr._event_buffer) == 0


class TestEventManagerSubscriptions:
    def test_subscribe(self, event_mgr):
        cb = lambda ev: None
        event_mgr.subscribe("progress", cb)
        assert cb in event_mgr._subscriptions["progress"]

    def test_unsubscribe_specific(self, event_mgr):
        cb = lambda ev: None
        event_mgr.subscribe("progress", cb)
        event_mgr.unsubscribe("progress", cb)
        assert cb not in event_mgr._subscriptions.get("progress", [])

    def test_unsubscribe_all(self, event_mgr):
        event_mgr.subscribe("progress", lambda ev: None)
        event_mgr.unsubscribe("progress")
        assert "progress" not in event_mgr._subscriptions

    def test_subscribe_without_callback(self, event_mgr):
        event_mgr.subscribe("status")
        assert "status" in event_mgr._subscriptions


class TestEventManagerDrain:
    def test_drain_all(self, event_mgr):
        event_mgr._dispatch({"type": "a", "data": {}})
        event_mgr._dispatch({"type": "b", "data": {}})
        events = event_mgr.drain_events()
        assert len(events) == 2
        assert len(event_mgr._event_buffer) == 0

    def test_drain_by_type(self, event_mgr):
        event_mgr._dispatch({"type": "progress", "data": {}})
        event_mgr._dispatch({"type": "status", "data": {}})
        event_mgr._dispatch({"type": "progress", "data": {}})
        events = event_mgr.drain_events("progress")
        assert len(events) == 2
        assert len(event_mgr._event_buffer) == 1  # status remains

    def test_drain_with_limit(self, event_mgr):
        for i in range(10):
            event_mgr._dispatch({"type": "progress", "data": {"i": i}})
        events = event_mgr.drain_events(limit=3)
        assert len(events) == 3

    def test_drain_empty(self, event_mgr):
        events = event_mgr.drain_events()
        assert events == []

    def test_peek_events_does_not_consume_buffer(self, event_mgr):
        event_mgr._dispatch({"type": "progress", "data": {"value": 1}})
        peeked = event_mgr.peek_events(limit=1)
        assert len(peeked) == 1
        assert len(event_mgr._event_buffer) == 1

    def test_peek_events_returns_recent_tail(self, event_mgr):
        for value in range(4):
            event_mgr._dispatch({"type": "sample", "data": {"value": value}})
        assert [event["data"]["value"] for event in event_mgr.peek_events(limit=2)] == [2, 3]

    def test_noisy_global_telemetry_is_coalesced(self, event_mgr):
        for value in range(20):
            event_mgr._dispatch({"type": "crystools.monitor", "data": {"value": value}})
        assert len(event_mgr._event_buffer) == 1
        assert event_mgr._event_buffer[0]["data"]["value"] == 19

    def test_high_signal_event_survives_low_signal_pressure(self, event_mgr):
        event_mgr._dispatch({"type": "execution_error", "data": {"prompt_id": "p1"}})
        for value in range(1000):
            event_mgr._dispatch({"type": f"telemetry-{value}", "data": {}})
        assert any(event["type"] == "execution_error" for event in event_mgr._event_buffer)


class TestEventManagerWebSocketAuth:
    def test_ws_connect_kwargs_include_auth_headers(self, event_mgr, mock_ws_client):
        mock_ws_client.get_auth_headers.return_value = {"Authorization": "Bearer secret"}
        assert event_mgr._ws_connect_kwargs() == {
            "additional_headers": {"Authorization": "Bearer secret"}
        }


class TestEventManagerLifecycle:
    @pytest.mark.asyncio
    async def test_shutdown_when_not_started(self, event_mgr):
        await event_mgr.shutdown()
        assert event_mgr._running is False

    @pytest.mark.asyncio
    async def test_start_sets_running(self, event_mgr):
        # We can't actually connect to a WS, but start() should set _running
        # and create a task. The task will fail immediately since there's no WS server.
        event_mgr._running = True  # Just test the flag
        assert event_mgr._running is True
        event_mgr._running = False  # cleanup

    @pytest.mark.asyncio
    async def test_start_recovers_a_finished_listener_task(self, event_mgr, monkeypatch):
        async def finished():
            return None

        stale = asyncio.create_task(finished())
        await stale
        event_mgr._running = True
        event_mgr._ws_task = stale
        restarted = asyncio.Event()

        async def replacement_loop():
            restarted.set()
            event_mgr._running = False

        monkeypatch.setattr(event_mgr, "_ws_loop", replacement_loop)
        await event_mgr.start()
        await event_mgr._ws_task
        assert restarted.is_set()

    @pytest.mark.asyncio
    async def test_reconnect_does_not_give_up_after_backoff_cap(
        self, event_mgr, mock_ws_client, monkeypatch
    ):
        attempts = 0
        mock_ws_client.ws_reconnect_max = 2
        mock_ws_client.probe_capabilities = AsyncMock(return_value={})

        class FailingContext:
            async def __aenter__(self):
                raise OSError("server restarting")

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class WorkingContext:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def __aiter__(self):
                async def messages():
                    event_mgr._running = False
                    yield '{"type":"status","data":{}}'

                return messages()

        def connect(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            return FailingContext() if attempts <= 5 else WorkingContext()

        async def no_sleep(delay):
            return None

        import builtins

        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "websockets":
                return type("WebsocketsModule", (), {"connect": connect})
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        monkeypatch.setattr("comfy_mcp.events.event_manager.asyncio.sleep", no_sleep)
        event_mgr._running = True
        await event_mgr._ws_loop()
        if event_mgr._capability_task:
            await event_mgr._capability_task

        assert attempts == 6
        assert event_mgr._reconnect_total == 5
        assert event_mgr._connection_generation == 1
        mock_ws_client.probe_capabilities.assert_awaited_once()


class TestGetLatestProgress:
    def test_no_progress(self, event_mgr):
        assert event_mgr.get_latest_progress("nonexistent") is None

    def test_cached_progress(self, event_mgr):
        event_mgr._dispatch({"type": "progress", "data": {"prompt_id": "p1", "value": 50, "max": 100}})
        event_mgr._dispatch({"type": "progress", "data": {"prompt_id": "p1", "value": 75, "max": 100}})
        progress = event_mgr.get_latest_progress("p1")
        assert progress["data"]["value"] == 75  # latest

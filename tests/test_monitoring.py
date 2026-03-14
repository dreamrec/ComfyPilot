"""Tests for monitoring tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.tools.monitoring import (
    comfy_describe_dynamics,
    comfy_get_events,
    comfy_get_status,
    comfy_subscribe,
    comfy_unsubscribe,
    comfy_watch_progress,
)


class TestWatchProgress:
    @pytest.mark.asyncio
    async def test_with_progress(self, mock_ctx):
        mock_ctx.request_context.lifespan_context["event_manager"].get_latest_progress = MagicMock(
            return_value={"type": "progress", "data": {"prompt_id": "p1", "value": 50, "max": 100}}
        )
        result = json.loads(await comfy_watch_progress(prompt_id="p1", ctx=mock_ctx))
        assert result["status"] == "ok"
        assert result["progress"]["data"]["value"] == 50

    @pytest.mark.asyncio
    async def test_no_progress(self, mock_ctx):
        mock_ctx.request_context.lifespan_context["event_manager"].get_latest_progress = MagicMock(
            return_value=None
        )
        result = json.loads(await comfy_watch_progress(prompt_id="p1", ctx=mock_ctx))
        assert result["status"] == "no_progress"
        assert result["prompt_id"] == "p1"


class TestSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_event_type(self, mock_ctx):
        mock_ctx.request_context.lifespan_context["event_manager"].subscribe = MagicMock()
        result = json.loads(await comfy_subscribe(event_type="progress", ctx=mock_ctx))
        assert result["status"] == "subscribed"
        assert result["event_type"] == "progress"
        mock_ctx.request_context.lifespan_context["event_manager"].subscribe.assert_called_once_with("progress")


class TestUnsubscribe:
    @pytest.mark.asyncio
    async def test_unsubscribe_event_type(self, mock_ctx):
        mock_ctx.request_context.lifespan_context["event_manager"].unsubscribe = MagicMock()
        result = json.loads(await comfy_unsubscribe(event_type="progress", ctx=mock_ctx))
        assert result["status"] == "unsubscribed"
        assert result["event_type"] == "progress"
        mock_ctx.request_context.lifespan_context["event_manager"].unsubscribe.assert_called_once_with("progress")


class TestGetEvents:
    @pytest.mark.asyncio
    async def test_drain_events(self, mock_ctx):
        mock_ctx.request_context.lifespan_context["event_manager"].drain_events = MagicMock(
            return_value=[
                {"type": "progress", "data": {}, "timestamp": 1.0},
                {"type": "complete", "data": {}, "timestamp": 2.0},
            ]
        )
        result = json.loads(await comfy_get_events(ctx=mock_ctx))
        assert result["count"] == 2
        assert len(result["events"]) == 2

    @pytest.mark.asyncio
    async def test_drain_events_empty(self, mock_ctx):
        mock_ctx.request_context.lifespan_context["event_manager"].drain_events = MagicMock(return_value=None)
        result = json.loads(await comfy_get_events(ctx=mock_ctx))
        assert result["count"] == 0
        assert result["events"] == []

    @pytest.mark.asyncio
    async def test_drain_events_with_filter(self, mock_ctx):
        mock_ctx.request_context.lifespan_context["event_manager"].drain_events = MagicMock(
            return_value=[{"type": "progress", "data": {}, "timestamp": 1.0}]
        )
        result = json.loads(await comfy_get_events(event_type="progress", limit=50, ctx=mock_ctx))
        assert result["count"] == 1
        mock_ctx.request_context.lifespan_context["event_manager"].drain_events.assert_called_once_with(
            "progress", 50
        )


class TestDescribeDynamics:
    @pytest.mark.asyncio
    async def test_returns_combined(self, mock_ctx, mock_client):
        mock_ctx.request_context.lifespan_context["event_manager"].drain_events = MagicMock(
            return_value=[{"type": "progress", "data": {}, "timestamp": 1.0}]
        )
        mock_ctx.request_context.lifespan_context["job_tracker"].get_active_jobs = MagicMock(return_value=[])
        result = json.loads(await comfy_describe_dynamics(ctx=mock_ctx))
        assert "queue" in result
        assert "events" in result
        assert "jobs" in result
        assert result["queue"]["running"] == 0
        assert result["queue"]["pending"] == 0

    @pytest.mark.asyncio
    async def test_with_queue_items(self, mock_ctx, mock_client):
        mock_client.get_queue.return_value = {
            "queue_running": ["prompt1"],
            "queue_pending": ["prompt2", "prompt3"],
        }
        mock_ctx.request_context.lifespan_context["event_manager"].drain_events = MagicMock(return_value=None)
        mock_ctx.request_context.lifespan_context["job_tracker"].get_active_jobs = MagicMock(return_value=[])
        result = json.loads(await comfy_describe_dynamics(ctx=mock_ctx))
        assert result["queue"]["running"] == 1
        assert result["queue"]["pending"] == 2


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_returns_combined(self, mock_ctx, mock_client):
        result = json.loads(await comfy_get_status(ctx=mock_ctx))
        assert "queue" in result
        assert "system" in result
        assert "devices" in result["system"]

    @pytest.mark.asyncio
    async def test_with_running_queue(self, mock_ctx, mock_client):
        mock_client.get_queue.return_value = {
            "queue_running": ["prompt1"],
            "queue_pending": ["prompt2"],
        }
        result = json.loads(await comfy_get_status(ctx=mock_ctx))
        assert result["queue"]["running"] == 1
        assert result["queue"]["pending"] == 1

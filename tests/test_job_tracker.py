"""Tests for JobTracker."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.jobs.job_tracker import JobTracker


@pytest.fixture
def mock_jt_client():
    client = AsyncMock()
    client.get_history = AsyncMock(return_value={})
    return client


@pytest.fixture
def mock_event_mgr():
    mgr = MagicMock()
    mgr.get_latest_progress = MagicMock(return_value=None)
    return mgr


@pytest.fixture
def tracker(mock_jt_client, mock_event_mgr):
    return JobTracker(mock_jt_client, mock_event_mgr)


class TestJobTrackerTrack:
    @pytest.mark.asyncio
    async def test_track_creates_job(self, tracker):
        await tracker.track("p1")
        assert "p1" in tracker._active_jobs
        assert tracker._active_jobs["p1"]["status"] == "queued"

    @pytest.mark.asyncio
    async def test_track_records_timestamp(self, tracker):
        await tracker.track("p1")
        assert "submitted_at" in tracker._active_jobs["p1"]


class TestJobTrackerStatus:
    @pytest.mark.asyncio
    async def test_get_status_active(self, tracker):
        await tracker.track("p1")
        status = tracker.get_status("p1")
        assert status["status"] == "queued"

    @pytest.mark.asyncio
    async def test_get_status_with_progress(self, tracker, mock_event_mgr):
        await tracker.track("p1")
        mock_event_mgr.get_latest_progress.return_value = {
            "data": {"value": 50, "max": 100, "prompt_id": "p1"},
        }
        status = tracker.get_status("p1")
        assert status["status"] == "running"
        assert status["progress"] == 50

    @pytest.mark.asyncio
    async def test_get_status_completed(self, tracker):
        await tracker.track("p1")
        await tracker.mark_complete("p1", {"outputs": {}})
        status = tracker.get_status("p1")
        assert status["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_status_failed(self, tracker):
        await tracker.track("p1")
        await tracker.mark_failed("p1", "OOM error")
        status = tracker.get_status("p1")
        assert status["status"] == "failed"
        assert status["error"] == "OOM error"

    def test_get_status_unknown(self, tracker):
        assert tracker.get_status("nonexistent") is None


class TestJobTrackerCompletion:
    @pytest.mark.asyncio
    async def test_mark_complete_moves_to_completed(self, tracker):
        await tracker.track("p1")
        await tracker.mark_complete("p1")
        assert "p1" not in tracker._active_jobs
        assert len(tracker._completed) == 1

    @pytest.mark.asyncio
    async def test_mark_failed_moves_to_completed(self, tracker):
        await tracker.track("p1")
        await tracker.mark_failed("p1", "error msg")
        assert "p1" not in tracker._active_jobs
        assert tracker._completed[0]["error"] == "error msg"


class TestJobTrackerWait:
    @pytest.mark.asyncio
    async def test_wait_completes(self, tracker, mock_jt_client):
        await tracker.track("p1")
        mock_jt_client.get_history.return_value = {
            "p1": {
                "outputs": {"1": {"images": []}},
                "status": {"status_str": "success", "completed": True},
            }
        }
        result = await tracker.wait_for_completion("p1", timeout=5, poll_interval=0.1)
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_wait_timeout(self, tracker, mock_jt_client):
        await tracker.track("p1")
        mock_jt_client.get_history.return_value = {}  # Never appears in history
        result = await tracker.wait_for_completion("p1", timeout=0.3, poll_interval=0.1)
        assert result["status"] == "timeout"

    @pytest.mark.asyncio
    async def test_wait_detects_failure(self, tracker, mock_jt_client):
        await tracker.track("p1")
        mock_jt_client.get_history.return_value = {
            "p1": {
                "outputs": {},
                "status": {"status_str": "error", "completed": False, "messages": ["OOM"]},
            }
        }
        result = await tracker.wait_for_completion("p1", timeout=5, poll_interval=0.1)
        assert result["status"] == "failed"


class TestJobTrackerLists:
    @pytest.mark.asyncio
    async def test_list_active(self, tracker):
        await tracker.track("p1")
        await tracker.track("p2")
        active = tracker.list_active()
        assert len(active) == 2

    @pytest.mark.asyncio
    async def test_list_recent(self, tracker):
        await tracker.track("p1")
        await tracker.mark_complete("p1")
        await tracker.track("p2")
        await tracker.mark_complete("p2")
        recent = tracker.list_recent()
        assert len(recent) == 2
        assert recent[0]["prompt_id"] == "p2"  # most recent first

    @pytest.mark.asyncio
    async def test_list_recent_with_limit(self, tracker):
        for i in range(5):
            await tracker.track(f"p{i}")
            await tracker.mark_complete(f"p{i}")
        recent = tracker.list_recent(limit=2)
        assert len(recent) == 2

    @pytest.mark.asyncio
    async def test_completed_deque_maxlen(self, tracker):
        for i in range(110):
            await tracker.track(f"p{i}")
            await tracker.mark_complete(f"p{i}")
        assert len(tracker._completed) == 100  # maxlen enforced

"""Test JobTracker lifecycle state machine."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from comfy_mcp.jobs.job_tracker import JobTracker


@pytest.fixture
def tracker():
    client = AsyncMock()
    event_mgr = MagicMock()
    event_mgr.get_latest_progress = MagicMock(return_value=None)
    return JobTracker(client, event_mgr)


@pytest.mark.asyncio
async def test_track_creates_queued_job(tracker):
    await tracker.track("p1")
    status = tracker.get_status("p1")
    assert status["status"] == "queued"
    assert "submitted_at" in status


@pytest.mark.asyncio
async def test_mark_complete_moves_to_completed(tracker):
    await tracker.track("p1")
    await tracker.mark_complete("p1", {"outputs": {}})
    status = tracker.get_status("p1")
    assert status["status"] == "completed"
    assert "completed_at" in status
    assert status not in tracker._active_jobs.values()


@pytest.mark.asyncio
async def test_mark_failed_records_error(tracker):
    await tracker.track("p1")
    await tracker.mark_failed("p1", "OOM error")
    status = tracker.get_status("p1")
    assert status["status"] == "failed"
    assert status["error"] == "OOM error"


@pytest.mark.asyncio
async def test_mark_cancelled(tracker):
    await tracker.track("p1")
    await tracker.mark_cancelled("p1")
    status = tracker.get_status("p1")
    assert status["status"] == "cancelled"


@pytest.mark.asyncio
async def test_mark_interrupted(tracker):
    await tracker.track("p1")
    await tracker.mark_interrupted("p1")
    status = tracker.get_status("p1")
    assert status["status"] == "interrupted"


def test_list_active_returns_only_active(tracker):
    import asyncio
    asyncio.get_event_loop().run_until_complete(tracker.track("p1"))
    asyncio.get_event_loop().run_until_complete(tracker.track("p2"))
    asyncio.get_event_loop().run_until_complete(tracker.mark_complete("p1"))
    active = tracker.list_active()
    assert len(active) == 1
    assert active[0]["prompt_id"] == "p2"

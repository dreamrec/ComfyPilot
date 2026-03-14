"""Tests for the 4 findings from the final review (4e8ba46).

1. interrupt refreshes job state before marking
2. describe_dynamics is non-destructive (peek, not drain)
3. list_output_images preserves subfolder identity
4. get_output_image returns correct MIME type
"""

from __future__ import annotations

import json
from collections import deque
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fix 1: interrupt refreshes stale job state
# ---------------------------------------------------------------------------


class TestInterruptRefresh:
    """comfy_interrupt must refresh job state from progress cache."""

    @pytest.fixture
    def tracker_with_running_job(self, mock_ctx):
        jt = mock_ctx.request_context.lifespan_context["job_tracker"]
        jt.list_active = MagicMock(return_value=[
            {"prompt_id": "p-123", "status": "running"},
        ])
        jt.mark_interrupted = AsyncMock()
        jt.refresh_active_states = MagicMock()
        return jt

    @pytest.mark.asyncio
    async def test_interrupt_calls_refresh_before_marking(self, mock_ctx, tracker_with_running_job):
        from comfy_mcp.tools.workflow import comfy_interrupt
        mock_ctx.request_context.lifespan_context["comfy_client"].interrupt = AsyncMock()
        result = await comfy_interrupt(ctx=mock_ctx)
        data = json.loads(result)
        tracker_with_running_job.refresh_active_states.assert_called_once()
        tracker_with_running_job.mark_interrupted.assert_called_once_with("p-123")
        assert "p-123" in data["interrupted_prompt_ids"]

    @pytest.mark.asyncio
    async def test_interrupt_leaves_queued_jobs_unchanged(self, mock_ctx):
        jt = mock_ctx.request_context.lifespan_context["job_tracker"]
        jt.list_active = MagicMock(return_value=[
            {"prompt_id": "q-456", "status": "queued"},
        ])
        jt.mark_interrupted = AsyncMock()
        jt.refresh_active_states = MagicMock()
        mock_ctx.request_context.lifespan_context["comfy_client"].interrupt = AsyncMock()

        from comfy_mcp.tools.workflow import comfy_interrupt
        result = await comfy_interrupt(ctx=mock_ctx)
        data = json.loads(result)
        jt.mark_interrupted.assert_not_called()
        assert data.get("interrupted_prompt_ids") == []
        assert "q-456" in data["queued_prompt_ids_unchanged"]


# ---------------------------------------------------------------------------
# Fix 1 (unit): refresh_active_states on real JobTracker
# ---------------------------------------------------------------------------


class TestRefreshActiveStates:
    """JobTracker.refresh_active_states upgrades queued to running from progress."""

    @pytest.mark.asyncio
    async def test_upgrades_queued_with_progress(self):
        from comfy_mcp.jobs.job_tracker import JobTracker
        client = MagicMock()
        event_mgr = MagicMock()
        event_mgr.get_latest_progress = MagicMock(return_value={
            "type": "progress",
            "data": {"value": 5, "max": 20},
        })
        tracker = JobTracker(client, event_mgr)
        await tracker.track("p-1")
        assert tracker._active_jobs["p-1"]["status"] == "queued"
        tracker.refresh_active_states()
        assert tracker._active_jobs["p-1"]["status"] == "running"
        assert tracker._active_jobs["p-1"]["progress"] == 5

    @pytest.mark.asyncio
    async def test_leaves_queued_without_progress(self):
        from comfy_mcp.jobs.job_tracker import JobTracker
        client = MagicMock()
        event_mgr = MagicMock()
        event_mgr.get_latest_progress = MagicMock(return_value=None)
        tracker = JobTracker(client, event_mgr)
        await tracker.track("p-2")
        tracker.refresh_active_states()
        assert tracker._active_jobs["p-2"]["status"] == "queued"


# ---------------------------------------------------------------------------
# Fix 2: describe_dynamics is non-destructive
# ---------------------------------------------------------------------------


class TestDescribeDynamicsNonDestructive:
    """comfy_describe_dynamics must not drain events from the buffer."""

    def _make_event_mgr_with_events(self):
        from comfy_mcp.events.event_manager import EventManager
        mgr = EventManager.__new__(EventManager)
        mgr._event_buffer = deque(maxlen=1000)
        mgr._subscriptions = {}
        mgr._progress_cache = {}
        for i in range(5):
            mgr._event_buffer.append({"type": "progress", "data": {"i": i}, "timestamp": i})
        return mgr

    def test_peek_events_does_not_remove(self):
        mgr = self._make_event_mgr_with_events()
        before = len(mgr._event_buffer)
        peeked = mgr.peek_events(limit=3)
        assert len(peeked) == 3
        assert len(mgr._event_buffer) == before

    def test_drain_events_removes(self):
        mgr = self._make_event_mgr_with_events()
        before = len(mgr._event_buffer)
        drained = mgr.drain_events(limit=3)
        assert len(drained) == 3
        assert len(mgr._event_buffer) == before - 3

    @pytest.mark.asyncio
    async def test_describe_dynamics_preserves_buffer(self, mock_ctx):
        mgr = self._make_event_mgr_with_events()
        mock_ctx.request_context.lifespan_context["event_manager"] = mgr
        from comfy_mcp.tools.monitoring import comfy_describe_dynamics
        await comfy_describe_dynamics(ctx=mock_ctx)
        assert len(mgr._event_buffer) == 5

    def test_peek_events_filters_by_type(self):
        mgr = self._make_event_mgr_with_events()
        mgr._event_buffer.append({"type": "error", "data": {}, "timestamp": 99})
        peeked = mgr.peek_events(event_type="error")
        assert len(peeked) == 1
        assert peeked[0]["type"] == "error"


# ---------------------------------------------------------------------------
# Fix 3: list_output_images preserves subfolder
# ---------------------------------------------------------------------------


class TestListOutputImagesSubfolder:
    """comfy_list_output_images returns objects with subfolder, not bare names."""

    @pytest.mark.asyncio
    async def test_returns_subfolder_and_type(self, mock_ctx):
        mock_ctx.request_context.lifespan_context["comfy_client"].get_history = AsyncMock(return_value={
            "p1": {
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "img.png", "subfolder": "batch1", "type": "output"},
                        ]
                    }
                }
            }
        })
        from comfy_mcp.tools.images import comfy_list_output_images
        result = json.loads(await comfy_list_output_images(ctx=mock_ctx))
        entry = result["images"][0]
        assert entry["filename"] == "img.png"
        assert entry["subfolder"] == "batch1"
        assert entry["type"] == "output"

    @pytest.mark.asyncio
    async def test_duplicate_names_different_subfolders_stay_separate(self, mock_ctx):
        mock_ctx.request_context.lifespan_context["comfy_client"].get_history = AsyncMock(return_value={
            "p1": {
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "img.png", "subfolder": "a", "type": "output"},
                            {"filename": "img.png", "subfolder": "b", "type": "output"},
                        ]
                    }
                }
            }
        })
        from comfy_mcp.tools.images import comfy_list_output_images
        result = json.loads(await comfy_list_output_images(ctx=mock_ctx))
        assert result["count"] == 2
        subfolders = {e["subfolder"] for e in result["images"]}
        assert subfolders == {"a", "b"}


# ---------------------------------------------------------------------------
# Fix 4: MIME type inferred from extension
# ---------------------------------------------------------------------------


class TestMimeTypeInference:
    """comfy_get_output_image returns correct MIME for non-PNG outputs."""

    def test_mime_for_png(self):
        from comfy_mcp.tools.images import _mime_for
        assert _mime_for("output.png") == "image/png"

    def test_mime_for_webp(self):
        from comfy_mcp.tools.images import _mime_for
        assert _mime_for("output.webp") == "image/webp"

    def test_mime_for_jpg(self):
        from comfy_mcp.tools.images import _mime_for
        assert _mime_for("photo.jpg") == "image/jpeg"

    def test_mime_for_jpeg(self):
        from comfy_mcp.tools.images import _mime_for
        assert _mime_for("photo.jpeg") == "image/jpeg"

    def test_mime_for_unknown_defaults_to_png(self):
        from comfy_mcp.tools.images import _mime_for
        assert _mime_for("file.xyz") == "image/png"

    def test_mime_for_no_extension_defaults_to_png(self):
        from comfy_mcp.tools.images import _mime_for
        assert _mime_for("noext") == "image/png"

    @pytest.mark.asyncio
    async def test_get_output_image_uses_correct_mime(self, mock_ctx):
        mock_ctx.request_context.lifespan_context["comfy_client"].get_image = AsyncMock(
            return_value=b"\x00\x01"
        )
        from comfy_mcp.tools.images import comfy_get_output_image
        result = await comfy_get_output_image("anim.webp", ctx=mock_ctx)
        assert result[1].mimeType == "image/webp"

    @pytest.mark.asyncio
    async def test_get_output_image_png_still_works(self, mock_ctx):
        mock_ctx.request_context.lifespan_context["comfy_client"].get_image = AsyncMock(
            return_value=b"\x89PNG"
        )
        from comfy_mcp.tools.images import comfy_get_output_image
        result = await comfy_get_output_image("out.png", ctx=mock_ctx)
        assert result[1].mimeType == "image/png"

"""Tests for history tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from comfy_mcp.tools.history import (
    comfy_clear_history,
    comfy_delete_history,
    comfy_get_history,
    comfy_get_run_result,
    comfy_search_history,
)


MOCK_HISTORY = {
    "prompt_1": {
        "prompt": [1, "prompt_1", {"1": {"class_type": "KSampler", "inputs": {}}}, {}, []],
        "outputs": {"1": {"images": [{"filename": "test.png", "subfolder": "", "type": "output"}]}},
        "status": {"status_str": "success", "completed": True},
    },
    "prompt_2": {
        "prompt": [2, "prompt_2", {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}, {}, []],
        "outputs": {},
        "status": {"status_str": "success", "completed": True},
    },
}


class TestGetHistory:
    @pytest.mark.asyncio
    async def test_get_history(self, mock_ctx, mock_client):
        """Test getting history with pagination."""
        mock_client.get_history = AsyncMock(return_value=MOCK_HISTORY)
        result = await comfy_get_history(limit=20, ctx=mock_ctx)
        data = json.loads(result)
        assert data["total_count"] == 2
        assert len(data["entries"]) == 2
        assert data["entries"][0]["prompt_id"] in ["prompt_1", "prompt_2"]
        mock_client.get_history.assert_awaited_once_with(max_items=20)

    @pytest.mark.asyncio
    async def test_get_history_with_custom_limit(self, mock_ctx, mock_client):
        """Test getting history with custom limit."""
        mock_client.get_history = AsyncMock(return_value={"prompt_1": MOCK_HISTORY["prompt_1"]})
        result = await comfy_get_history(limit=1, ctx=mock_ctx)
        data = json.loads(result)
        assert data["total_count"] == 1
        mock_client.get_history.assert_awaited_once_with(max_items=1)


class TestGetRunResult:
    @pytest.mark.asyncio
    async def test_get_run_result(self, mock_ctx, mock_client):
        """Test getting result of a specific prompt execution."""
        mock_client.get_history = AsyncMock(return_value={"prompt_1": MOCK_HISTORY["prompt_1"]})
        result = await comfy_get_run_result(prompt_id="prompt_1", ctx=mock_ctx)
        assert result.prompt_id == "prompt_1"
        assert result.status["status_str"] == "success"
        assert "images" in result.outputs["1"]
        mock_client.get_history.assert_awaited_once_with(prompt_id="prompt_1")

    @pytest.mark.asyncio
    async def test_get_run_result_not_found(self, mock_ctx, mock_client):
        """Test getting result for non-existent prompt."""
        mock_client.get_history = AsyncMock(return_value={})
        result = await comfy_get_run_result(prompt_id="nonexistent", ctx=mock_ctx)
        assert result.error is not None
        assert result.prompt_id == "nonexistent"

    @pytest.mark.asyncio
    async def test_get_run_result_surfaces_create_time(self, mock_ctx, mock_client):
        """ComfyUI v0.3.69+ exposes create_time on /history entries."""
        mock_client.get_history = AsyncMock(return_value={
            "prompt_1": {
                "create_time": 1747000000.5,
                "prompt": [1, "prompt_1", {}, {}, []],
                "outputs": {},
                "status": {"status_str": "success"},
            },
        })
        result = await comfy_get_run_result(prompt_id="prompt_1", ctx=mock_ctx)
        assert result.create_time == 1747000000.5

    @pytest.mark.asyncio
    async def test_get_run_result_create_time_in_status(self, mock_ctx, mock_client):
        """Some forks pack create_time inside the status dict - handle both."""
        mock_client.get_history = AsyncMock(return_value={
            "prompt_1": {
                "prompt": [1, "prompt_1", {}, {}, []],
                "outputs": {},
                "status": {"status_str": "success", "create_time": 1747000123},
            },
        })
        result = await comfy_get_run_result(prompt_id="prompt_1", ctx=mock_ctx)
        assert result.create_time == 1747000123.0

    @pytest.mark.asyncio
    async def test_get_run_result_create_time_from_current_prompt_tuple_ms(
        self, mock_ctx, mock_client
    ):
        mock_client.get_history = AsyncMock(return_value={
            "prompt_1": {
                "prompt": [
                    7,
                    "prompt_1",
                    {},
                    {"client_id": "client", "create_time": 1_747_000_456_250},
                    [],
                ],
                "outputs": {},
                "status": {"status_str": "success"},
            },
        })
        result = await comfy_get_run_result(prompt_id="prompt_1", ctx=mock_ctx)
        assert result.create_time == 1_747_000_456.25

    @pytest.mark.asyncio
    async def test_get_run_result_reconciles_job_tracker(self, mock_ctx, mock_client):
        history = {"prompt_1": MOCK_HISTORY["prompt_1"]}
        mock_client.get_history = AsyncMock(return_value=history)
        await comfy_get_run_result(prompt_id="prompt_1", ctx=mock_ctx)
        tracker = mock_ctx.request_context.lifespan_context["job_tracker"]
        tracker.reconcile.assert_called_once_with(prompt_id="prompt_1", history=history)

    @pytest.mark.asyncio
    async def test_get_run_result_create_time_absent_on_old_comfy(self, mock_ctx, mock_client):
        """Older ComfyUI builds omit create_time - field stays None."""
        mock_client.get_history = AsyncMock(return_value={
            "prompt_1": {
                "prompt": [1, "prompt_1", {}, {}, []],
                "outputs": {},
                "status": {"status_str": "success"},
            },
        })
        result = await comfy_get_run_result(prompt_id="prompt_1", ctx=mock_ctx)
        assert result.create_time is None


class TestDeleteHistory:
    @pytest.mark.asyncio
    async def test_delete_history(self, mock_ctx, mock_client):
        """Test deleting a specific history entry."""
        mock_client.delete_history = AsyncMock()
        result = await comfy_delete_history(prompt_id="prompt_1", confirm=True, ctx=mock_ctx)
        data = json.loads(result)
        assert data["status"] == "deleted"
        assert data["prompt_id"] == "prompt_1"
        mock_client.delete_history.assert_awaited_once_with(prompt_id="prompt_1")


class TestClearHistory:
    @pytest.mark.asyncio
    async def test_clear_history(self, mock_ctx, mock_client):
        """Test clearing all history."""
        mock_client.clear_history = AsyncMock()
        result = await comfy_clear_history(confirm=True, ctx=mock_ctx)
        data = json.loads(result)
        assert data["status"] == "cleared"
        assert "All execution history" in data["message"]
        mock_client.clear_history.assert_awaited_once()


class TestSearchHistory:
    @pytest.mark.asyncio
    async def test_search_by_node_type(self, mock_ctx, mock_client):
        """Test searching history by node type."""
        mock_client.get_history = AsyncMock(return_value=MOCK_HISTORY)
        result = await comfy_search_history(query="ksampler", ctx=mock_ctx)
        data = json.loads(result)
        assert data["query"] == "ksampler"
        assert len(data["matches"]) == 1
        assert data["matches"][0]["prompt_id"] == "prompt_1"
        assert "ksampler" in data["matches"][0]["matched_node"]
        mock_client.get_history.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, mock_ctx, mock_client):
        """Test that search is case-insensitive."""
        mock_client.get_history = AsyncMock(return_value=MOCK_HISTORY)
        result = await comfy_search_history(query="CHECKPOINTLOADERSIMPLE", ctx=mock_ctx)
        data = json.loads(result)
        assert len(data["matches"]) == 1
        assert data["matches"][0]["prompt_id"] == "prompt_2"

    @pytest.mark.asyncio
    async def test_search_no_matches(self, mock_ctx, mock_client):
        """Test search with no matches."""
        mock_client.get_history = AsyncMock(return_value=MOCK_HISTORY)
        result = await comfy_search_history(query="nonexistent", ctx=mock_ctx)
        data = json.loads(result)
        assert data["match_count"] == 0
        assert len(data["matches"]) == 0

    @pytest.mark.asyncio
    async def test_search_with_limit(self, mock_ctx, mock_client):
        """Test search respects limit."""
        mock_history = {
            "prompt_1": MOCK_HISTORY["prompt_1"],
            "prompt_3": {
                "prompt": [3, "prompt_3", {"1": {"class_type": "KSampler", "inputs": {}}}, {}, []],
                "outputs": {},
                "status": {"status_str": "success", "completed": True},
            },
        }
        mock_client.get_history = AsyncMock(return_value=mock_history)
        result = await comfy_search_history(query="ksampler", limit=1, ctx=mock_ctx)
        data = json.loads(result)
        assert data["match_count"] == 1
        assert len(data["matches"]) == 1

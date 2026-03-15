"""Tests for workflow tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from comfy_mcp.memory.snapshot_manager import SnapshotManager
from comfy_mcp.tools.workflow import (
    comfy_cancel_run,
    comfy_clear_queue,
    comfy_export_workflow,
    comfy_get_queue,
    comfy_import_workflow,
    comfy_interrupt,
    comfy_queue_prompt,
    comfy_validate_workflow,
)


class TestQueuePrompt:
    @pytest.mark.asyncio
    async def test_queue_prompt_basic(self, mock_ctx, mock_client):
        mock_client.queue_prompt = AsyncMock(return_value={
            "prompt_id": "abc123",
            "number": 1,
        })
        result = await comfy_queue_prompt(
            workflow={"1": {"class_type": "KSampler"}},
            ctx=mock_ctx,
        )
        data = json.loads(result)
        assert data["prompt_id"] == "abc123"
        assert data["queue_position"] == 1
        # Verify progress was reported
        mock_ctx.report_progress.assert_any_call(0, 100)
        mock_ctx.report_progress.assert_any_call(100, 100)

    @pytest.mark.asyncio
    async def test_queue_prompt_front(self, mock_ctx, mock_client):
        mock_client.queue_prompt = AsyncMock(return_value={
            "prompt_id": "def456",
            "number": 0,
        })
        result = await comfy_queue_prompt(
            workflow={"1": {"class_type": "KSampler"}},
            front=True,
            ctx=mock_ctx,
        )
        data = json.loads(result)
        assert data["prompt_id"] == "def456"
        assert data["queue_position"] == 0
        mock_client.queue_prompt.assert_awaited_once_with(
            {"1": {"class_type": "KSampler"}},
            front=True,
        )

    @pytest.mark.asyncio
    async def test_queue_prompt_registers_with_job_tracker(self, mock_ctx, mock_client):
        """queue_prompt must call job_tracker.track(prompt_id) after queueing."""
        mock_client.queue_prompt = AsyncMock(return_value={
            "prompt_id": "abc-123",
            "number": 1,
        })
        job_tracker = mock_ctx.request_context.lifespan_context["job_tracker"]

        result = await comfy_queue_prompt(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            ctx=mock_ctx,
        )

        job_tracker.track.assert_awaited_once_with("abc-123")

    @pytest.mark.asyncio
    async def test_queue_prompt_creates_auto_snapshot_when_enabled(self, mock_ctx, mock_client):
        mock_client.queue_prompt = AsyncMock(return_value={
            "prompt_id": "snap-123",
            "number": 2,
        })
        mgr = SnapshotManager()
        mgr.auto_snapshot = True
        mock_ctx.request_context.lifespan_context["snapshot_manager"] = mgr
        workflow = {"1": {"class_type": "KSampler"}}

        result = json.loads(await comfy_queue_prompt(workflow=workflow, ctx=mock_ctx))
        snapshot_id = result["auto_snapshot"]["id"]
        snapshot = mgr.get(snapshot_id)

        assert snapshot is not None
        assert snapshot["workflow"] == workflow


class TestGetQueue:
    @pytest.mark.asyncio
    async def test_get_queue_empty(self, mock_ctx, mock_client):
        mock_client.get_queue = AsyncMock(return_value={
            "queue_running": [],
            "queue_pending": [],
        })
        result = await comfy_get_queue(ctx=mock_ctx)
        data = json.loads(result)
        assert data["running_count"] == 0
        assert data["pending_count"] == 0

    @pytest.mark.asyncio
    async def test_get_queue_with_items(self, mock_ctx, mock_client):
        mock_client.get_queue = AsyncMock(return_value={
            "queue_running": [["prompt1", 0, {}]],
            "queue_pending": [["prompt2", 1, {}], ["prompt3", 2, {}]],
        })
        result = await comfy_get_queue(ctx=mock_ctx)
        data = json.loads(result)
        assert data["running_count"] == 1
        assert data["pending_count"] == 2


class TestCancelRun:
    @pytest.mark.asyncio
    async def test_cancel_run(self, mock_ctx, mock_client):
        mock_client.cancel_prompt = AsyncMock(return_value={})
        result = await comfy_cancel_run(
            prompt_id="abc123",
            ctx=mock_ctx,
        )
        data = json.loads(result)
        assert data["status"] == "cancelled"
        assert data["prompt_id"] == "abc123"
        mock_client.cancel_prompt.assert_awaited_once_with("abc123")


class TestInterrupt:
    @pytest.mark.asyncio
    async def test_interrupt(self, mock_ctx, mock_client):
        mock_client.interrupt = AsyncMock(return_value={})
        result = await comfy_interrupt(ctx=mock_ctx)
        data = json.loads(result)
        assert data["status"] == "interrupted"
        mock_client.interrupt.assert_awaited_once()


class TestClearQueue:
    @pytest.mark.asyncio
    async def test_clear_queue(self, mock_ctx, mock_client):
        mock_client.clear_queue = AsyncMock(return_value={})
        result = await comfy_clear_queue(ctx=mock_ctx)
        data = json.loads(result)
        assert data["status"] == "cleared"
        mock_client.clear_queue.assert_awaited_once()


class TestValidateWorkflow:
    @pytest.mark.asyncio
    async def test_valid_workflow(self, mock_ctx):
        result = await comfy_validate_workflow(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            ctx=mock_ctx,
        )
        data = json.loads(result)
        assert data["valid"] is True
        assert data["node_count"] == 1
        assert data["errors"] == []

    @pytest.mark.asyncio
    async def test_empty_workflow(self, mock_ctx):
        result = await comfy_validate_workflow(workflow={}, ctx=mock_ctx)
        data = json.loads(result)
        assert data["valid"] is False
        assert "cannot be empty" in data["errors"][0].lower()

    @pytest.mark.asyncio
    async def test_workflow_not_dict(self, mock_ctx):
        result = await comfy_validate_workflow(workflow=[], ctx=mock_ctx)
        data = json.loads(result)
        assert data["valid"] is False
        assert "must be a dict" in data["errors"][0].lower()

    @pytest.mark.asyncio
    async def test_workflow_missing_class_type(self, mock_ctx):
        result = await comfy_validate_workflow(
            workflow={"1": {"inputs": {}}},
            ctx=mock_ctx,
        )
        data = json.loads(result)
        assert data["valid"] is False
        assert "missing 'class_type'" in data["errors"][0]

    @pytest.mark.asyncio
    async def test_workflow_multiple_nodes(self, mock_ctx):
        result = await comfy_validate_workflow(
            workflow={
                "1": {"class_type": "KSampler"},
                "2": {"class_type": "VAEDecode"},
                "3": {"class_type": "SaveImage"},
            },
            ctx=mock_ctx,
        )
        data = json.loads(result)
        assert data["valid"] is True
        assert data["node_count"] == 3

    @pytest.mark.asyncio
    async def test_validate_detects_unknown_node_type(self, mock_ctx, mock_client):
        """Validator should flag node types not in object_info."""
        mock_client.get_object_info = AsyncMock(return_value={
            "KSampler": {"input": {}, "output": []},
        })
        result = await comfy_validate_workflow(
            workflow={"1": {"class_type": "FakeNode", "inputs": {}}},
            ctx=mock_ctx,
        )
        result_dict = json.loads(result)
        assert not result_dict["valid"]
        assert any("FakeNode" in e for e in result_dict["errors"])

    @pytest.mark.asyncio
    async def test_validate_passes_valid_workflow(self, mock_ctx, mock_client):
        """Validator should pass when all node types are in object_info."""
        mock_client.get_object_info = AsyncMock(return_value={
            "CheckpointLoaderSimple": {"input": {}, "output": []},
            "KSampler": {"input": {}, "output": []},
        })
        result = await comfy_validate_workflow(
            workflow={
                "1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
                "2": {"class_type": "KSampler", "inputs": {}},
            },
            ctx=mock_ctx,
        )
        result_dict = json.loads(result)
        assert result_dict["valid"]

    @pytest.mark.asyncio
    async def test_validate_checks_broken_links(self, mock_ctx, mock_client):
        """Validator should flag links to non-existent nodes."""
        mock_client.get_object_info = AsyncMock(return_value={
            "KSampler": {"input": {}, "output": []},
        })
        result = await comfy_validate_workflow(
            workflow={"1": {"class_type": "KSampler", "inputs": {"model": ["99", 0]}}},
            ctx=mock_ctx,
        )
        result_dict = json.loads(result)
        assert not result_dict["valid"]
        assert any("99" in e for e in result_dict["errors"])


class TestExportWorkflow:
    @pytest.mark.asyncio
    async def test_export_workflow(self, mock_ctx):
        workflow = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 42}},
            "2": {"class_type": "VAEDecode"},
        }
        result = await comfy_export_workflow(workflow=workflow, ctx=mock_ctx)
        data = json.loads(result)
        assert data == workflow

    @pytest.mark.asyncio
    async def test_export_empty_workflow(self, mock_ctx):
        result = await comfy_export_workflow(workflow={}, ctx=mock_ctx)
        data = json.loads(result)
        assert data == {}


class TestImportWorkflow:
    @pytest.mark.asyncio
    async def test_import_valid_workflow_json(self, mock_ctx):
        workflow_json = '{"1": {"class_type": "KSampler"}, "2": {"class_type": "VAEDecode"}}'
        result = await comfy_import_workflow(workflow_json=workflow_json, ctx=mock_ctx)
        data = json.loads(result)
        assert data["1"]["class_type"] == "KSampler"
        assert data["2"]["class_type"] == "VAEDecode"

    @pytest.mark.asyncio
    async def test_import_invalid_json(self, mock_ctx):
        workflow_json = '{invalid json}'
        result = await comfy_import_workflow(workflow_json=workflow_json, ctx=mock_ctx)
        data = json.loads(result)
        assert "error" in data
        assert "Invalid JSON" in data["error"]

    @pytest.mark.asyncio
    async def test_import_json_not_dict(self, mock_ctx):
        workflow_json = '["item1", "item2"]'
        result = await comfy_import_workflow(workflow_json=workflow_json, ctx=mock_ctx)
        data = json.loads(result)
        assert "error" in data
        assert "not a dict" in data["error"]

    @pytest.mark.asyncio
    async def test_import_empty_dict(self, mock_ctx):
        workflow_json = '{}'
        result = await comfy_import_workflow(workflow_json=workflow_json, ctx=mock_ctx)
        data = json.loads(result)
        assert data == {}

"""Tests for comfy_fetch_logs - traceback retrieval from /history."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.tools.diagnostics import comfy_fetch_logs


def _ctx(history_response):
    client = MagicMock()
    client.get_history = AsyncMock(return_value=history_response)
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"comfy_client": client}
    return ctx


class TestFetchLogs:
    @pytest.mark.asyncio
    async def test_extracts_errors_from_exec_info(self):
        history = {
            "abc-123": {
                "status": {
                    "status_str": "error",
                    "completed": False,
                    "exec_info": {
                        "errors": [{
                            "node_id": "5",
                            "class_type": "KSampler",
                            "message": "CUDA out of memory",
                            "traceback": "Traceback (most recent call last):\n  File '...'\nRuntimeError: ...",
                        }],
                    },
                },
            },
        }
        result = await comfy_fetch_logs(prompt_id="abc-123", ctx=_ctx(history))
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["completed"] is False
        assert parsed["error_count"] == 1
        assert parsed["errors"][0]["message"] == "CUDA out of memory"
        assert parsed["failed_node"] == "5"

    @pytest.mark.asyncio
    async def test_extracts_errors_from_execution_error_message(self):
        """Some ComfyUI forks emit execution_error via status.messages."""
        history = {
            "abc-123": {
                "status": {
                    "status_str": "error",
                    "messages": [
                        ["execution_error", {
                            "node_id": "7",
                            "node_type": "VAEDecode",
                            "exception_message": "RuntimeError: kernel launch failed",
                            "exception_traceback": "Traceback ...",
                        }],
                    ],
                },
            },
        }
        result = await comfy_fetch_logs(prompt_id="abc-123", ctx=_ctx(history))
        parsed = json.loads(result)
        assert parsed["error_count"] == 1
        assert parsed["errors"][0]["class_type"] == "VAEDecode"
        assert "kernel launch failed" in parsed["errors"][0]["message"]

    @pytest.mark.asyncio
    async def test_collects_completed_nodes(self):
        history = {
            "abc-123": {
                "status": {
                    "status_str": "success",
                    "completed": True,
                    "messages": [
                        ["executed", {"node": "1"}],
                        ["executed", {"node": "2"}],
                        ["execution_cached", {"node": "3"}],
                    ],
                },
            },
        }
        result = await comfy_fetch_logs(prompt_id="abc-123", ctx=_ctx(history))
        parsed = json.loads(result)
        assert sorted(parsed["completed_nodes"]) == ["1", "2", "3"]
        assert parsed["error_count"] == 0

    @pytest.mark.asyncio
    async def test_missing_prompt_returns_not_found(self):
        result = await comfy_fetch_logs(prompt_id="nonexistent", ctx=_ctx({}))
        parsed = json.loads(result)
        assert "error" in parsed
        assert parsed["prompt_id"] == "nonexistent"

    @pytest.mark.asyncio
    async def test_empty_prompt_id_errors(self):
        result = await comfy_fetch_logs(prompt_id="", ctx=_ctx({}))
        parsed = json.loads(result)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_http_failure_surfaced(self):
        client = MagicMock()
        client.get_history = AsyncMock(side_effect=Exception("connection refused"))
        ctx = MagicMock()
        ctx.request_context.lifespan_context = {"comfy_client": client}
        result = await comfy_fetch_logs(prompt_id="abc-123", ctx=ctx)
        parsed = json.loads(result)
        assert "error" in parsed
        assert "connection refused" in parsed["error"]

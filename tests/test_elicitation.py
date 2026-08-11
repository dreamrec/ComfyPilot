"""Tests for destructive-tool elicitation gate."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import Context

from comfy_mcp.safety.confirm import confirm_destructive


def _ctx_with_elicit_result(action: str, confirm_value: bool = False):
    """Build a Context-like mock whose .elicit returns the given ElicitationResult shape."""
    ctx = MagicMock(spec=Context)
    result = SimpleNamespace(action=action, data=SimpleNamespace(confirm=confirm_value))
    ctx.elicit = AsyncMock(return_value=result)
    return ctx


def _ctx_without_elicit():
    """A Context that has no .elicit attribute - simulates elicitation-unaware host."""
    class NoElicit:
        pass
    return NoElicit()


class TestConfirmDestructive:
    @pytest.mark.asyncio
    async def test_already_confirmed_skips_elicit(self):
        ctx = _ctx_with_elicit_result("decline")
        allowed = await confirm_destructive(ctx, "really?", already_confirmed=True)
        assert allowed is True
        ctx.elicit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_user_accepts_with_confirm_true(self):
        ctx = _ctx_with_elicit_result("accept", confirm_value=True)
        allowed = await confirm_destructive(ctx, "really?", already_confirmed=False)
        assert allowed is True
        ctx.elicit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_user_accepts_with_confirm_false_blocks(self):
        """User clicked accept but left confirm=False in the form."""
        ctx = _ctx_with_elicit_result("accept", confirm_value=False)
        allowed = await confirm_destructive(ctx, "really?", already_confirmed=False)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_user_declines(self):
        ctx = _ctx_with_elicit_result("decline")
        allowed = await confirm_destructive(ctx, "really?", already_confirmed=False)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_user_cancels(self):
        ctx = _ctx_with_elicit_result("cancel")
        allowed = await confirm_destructive(ctx, "really?", already_confirmed=False)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_no_ctx_fails_closed(self, monkeypatch):
        monkeypatch.delenv("COMFY_STRICT_CONFIRM", raising=False)
        allowed = await confirm_destructive(None, "really?", already_confirmed=False)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_host_without_elicit_fails_closed(self, monkeypatch):
        monkeypatch.delenv("COMFY_STRICT_CONFIRM", raising=False)
        allowed = await confirm_destructive(_ctx_without_elicit(), "really?", already_confirmed=False)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_elicit_raises_fails_closed(self, monkeypatch):
        """A host failure must never be interpreted as destructive consent."""
        monkeypatch.delenv("COMFY_STRICT_CONFIRM", raising=False)
        ctx = MagicMock(spec=Context)
        ctx.elicit = AsyncMock(side_effect=Exception("not supported"))
        allowed = await confirm_destructive(ctx, "really?", already_confirmed=False)
        assert allowed is False


class TestStrictMode:
    """Strict is the default; an explicit false value enables legacy mode."""

    @pytest.mark.asyncio
    async def test_strict_mode_blocks_when_no_ctx(self, monkeypatch):
        monkeypatch.setenv("COMFY_STRICT_CONFIRM", "1")
        allowed = await confirm_destructive(None, "really?", already_confirmed=False)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_strict_mode_blocks_when_host_lacks_elicit(self, monkeypatch):
        monkeypatch.setenv("COMFY_STRICT_CONFIRM", "1")
        class NoElicit:
            pass
        allowed = await confirm_destructive(NoElicit(), "really?", already_confirmed=False)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_strict_mode_blocks_when_elicit_raises(self, monkeypatch):
        monkeypatch.setenv("COMFY_STRICT_CONFIRM", "1")
        ctx = MagicMock(spec=Context)
        ctx.elicit = AsyncMock(side_effect=Exception("not supported"))
        allowed = await confirm_destructive(ctx, "really?", already_confirmed=False)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_strict_mode_still_respects_confirm_true(self, monkeypatch):
        """Explicit confirm=True always wins, regardless of strict mode."""
        monkeypatch.setenv("COMFY_STRICT_CONFIRM", "1")
        allowed = await confirm_destructive(None, "really?", already_confirmed=True)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_strict_mode_still_accepts_explicit_yes(self, monkeypatch):
        monkeypatch.setenv("COMFY_STRICT_CONFIRM", "1")
        ctx = _ctx_with_elicit_result("accept", confirm_value=True)
        allowed = await confirm_destructive(ctx, "really?", already_confirmed=False)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_false_value_disables_strict(self, monkeypatch):
        monkeypatch.setenv("COMFY_STRICT_CONFIRM", "0")
        allowed = await confirm_destructive(None, "really?", already_confirmed=False)
        assert allowed is True


class TestToolIntegration:
    """End-to-end: destructive tools gate on confirm param and ctx.elicit."""

    @pytest.mark.asyncio
    async def test_clear_queue_bypass_with_confirm_true(self):
        from comfy_mcp.tools.workflow import comfy_clear_queue
        client = MagicMock()
        client.clear_queue = AsyncMock(return_value={})
        ctx = MagicMock(spec=Context)
        ctx.request_context.lifespan_context = {"comfy_client": client}

        result = json.loads(await comfy_clear_queue(confirm=True, ctx=ctx))
        assert result["status"] == "cleared"
        client.clear_queue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clear_queue_cancels_when_user_declines(self):
        from comfy_mcp.tools.workflow import comfy_clear_queue
        client = MagicMock()
        client.clear_queue = AsyncMock(return_value={})
        ctx = MagicMock(spec=Context)
        ctx.request_context.lifespan_context = {"comfy_client": client}
        ctx.elicit = AsyncMock(return_value=SimpleNamespace(action="decline", data=None))

        result = json.loads(await comfy_clear_queue(confirm=False, ctx=ctx))
        assert result["status"] == "cancelled"
        assert result["reason"] == "user_declined"
        client.clear_queue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_history_confirms(self):
        from comfy_mcp.tools.history import comfy_delete_history
        client = MagicMock()
        client.delete_history = AsyncMock(return_value={})
        ctx = MagicMock(spec=Context)
        ctx.request_context.lifespan_context = {"comfy_client": client}

        result = json.loads(await comfy_delete_history(prompt_id="abc", confirm=True, ctx=ctx))
        assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_snapshot_cancels_via_elicit(self):
        from comfy_mcp.tools.snapshots import comfy_delete_snapshot
        mgr = MagicMock()
        mgr.delete = MagicMock(return_value=True)
        ctx = MagicMock(spec=Context)
        ctx.request_context.lifespan_context = {"snapshot_manager": mgr}
        ctx.elicit = AsyncMock(return_value=SimpleNamespace(action="decline", data=None))

        result = json.loads(await comfy_delete_snapshot(snapshot_id="s1", confirm=False, ctx=ctx))
        assert result["status"] == "cancelled"
        mgr.delete.assert_not_called()

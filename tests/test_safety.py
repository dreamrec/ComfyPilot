"""Tests for VRAMGuard and safety tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.safety.vram_guard import VRAMGuard
from comfy_mcp.tools.safety import (
    comfy_check_vram,
    comfy_detect_instability,
    comfy_emergency_stop,
    comfy_set_limits,
    comfy_validate_before_queue,
)

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

_RTX_5090_TOTAL = 34_359_738_368  # 32 GB
_RTX_5090_FREE_OK = 30_000_000_000  # ~87% free → ~13% used → ok


@pytest.fixture
def safety_ctx():
    """Context with real VRAMGuard using mock client."""
    client = AsyncMock()
    client.get_system_stats = AsyncMock(return_value={
        "system": {"os": "nt"},
        "devices": [{
            "name": "NVIDIA GeForce RTX 5090",
            "type": "cuda",
            "index": 0,
            "vram_total": _RTX_5090_TOTAL,
            "vram_free": _RTX_5090_FREE_OK,
        }],
    })
    client.get_queue = AsyncMock(return_value={"queue_running": [], "queue_pending": []})
    client.interrupt = AsyncMock(return_value={})
    client.clear_queue = AsyncMock(return_value={})
    client.free_vram = AsyncMock(return_value={})

    guard = VRAMGuard(client)
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"vram_guard": guard}
    return ctx


def _guard(ctx) -> VRAMGuard:
    return ctx.request_context.lifespan_context["vram_guard"]


# ---------------------------------------------------------------------------
# check_vram
# ---------------------------------------------------------------------------

class TestCheckVram:
    @pytest.mark.asyncio
    async def test_ok_status(self, safety_ctx):
        result = json.loads(await comfy_check_vram(ctx=safety_ctx))
        assert result["status"] == "ok"
        assert result["vram_used_pct"] < 80.0
        assert len(result["devices"]) == 1
        assert result["devices"][0]["name"] == "NVIDIA GeForce RTX 5090"

    @pytest.mark.asyncio
    async def test_warn_status(self, safety_ctx):
        # 85% used → warn
        guard = _guard(safety_ctx)
        total = 1000
        guard._client.get_system_stats = AsyncMock(return_value={
            "devices": [{"name": "GPU", "vram_total": total, "vram_free": 150}],
        })
        result = json.loads(await comfy_check_vram(ctx=safety_ctx))
        assert result["status"] == "warn"
        assert result["vram_used_pct"] == 85.0
        assert result["devices"][0]["status"] == "warn"

    @pytest.mark.asyncio
    async def test_critical_status(self, safety_ctx):
        guard = _guard(safety_ctx)
        guard._client.get_system_stats = AsyncMock(return_value={
            "devices": [{"name": "GPU", "vram_total": 1000, "vram_free": 30}],
        })
        result = json.loads(await comfy_check_vram(ctx=safety_ctx))
        assert result["status"] == "critical"
        assert result["vram_used_pct"] == 97.0
        assert result["devices"][0]["status"] == "critical"

    @pytest.mark.asyncio
    async def test_no_devices_returns_unknown(self, safety_ctx):
        guard = _guard(safety_ctx)
        guard._client.get_system_stats = AsyncMock(return_value={"devices": []})
        result = json.loads(await comfy_check_vram(ctx=safety_ctx))
        assert result["status"] == "unknown"
        assert result["devices"] == []
        assert "No GPU devices found" in result["message"]

    @pytest.mark.asyncio
    async def test_device_info_fields(self, safety_ctx):
        result = json.loads(await comfy_check_vram(ctx=safety_ctx))
        dev = result["devices"][0]
        for field in ("name", "vram_total", "vram_free", "vram_used", "vram_used_pct", "status"):
            assert field in dev

    @pytest.mark.asyncio
    async def test_exactly_at_warn_threshold(self, safety_ctx):
        # exactly 80% used
        guard = _guard(safety_ctx)
        guard._client.get_system_stats = AsyncMock(return_value={
            "devices": [{"name": "GPU", "vram_total": 1000, "vram_free": 200}],
        })
        result = json.loads(await comfy_check_vram(ctx=safety_ctx))
        assert result["status"] == "warn"

    @pytest.mark.asyncio
    async def test_exactly_at_block_threshold(self, safety_ctx):
        # exactly 95% used
        guard = _guard(safety_ctx)
        guard._client.get_system_stats = AsyncMock(return_value={
            "devices": [{"name": "GPU", "vram_total": 1000, "vram_free": 50}],
        })
        result = json.loads(await comfy_check_vram(ctx=safety_ctx))
        assert result["status"] == "critical"


# ---------------------------------------------------------------------------
# validate_before_queue
# ---------------------------------------------------------------------------

class TestValidateBeforeQueue:
    @pytest.mark.asyncio
    async def test_safe_to_queue_true_when_ok(self, safety_ctx):
        result = json.loads(await comfy_validate_before_queue(ctx=safety_ctx))
        assert result["safe_to_queue"] is True
        assert result["issues"] == []
        assert result["vram_status"] == "ok"
        assert result["queue_running"] == 0
        assert result["queue_pending"] == 0

    @pytest.mark.asyncio
    async def test_safe_to_queue_false_when_vram_critical(self, safety_ctx):
        guard = _guard(safety_ctx)
        guard._client.get_system_stats = AsyncMock(return_value={
            "devices": [{"name": "GPU", "vram_total": 1000, "vram_free": 30}],
        })
        result = json.loads(await comfy_validate_before_queue(ctx=safety_ctx))
        assert result["safe_to_queue"] is False
        assert any("VRAM" in issue for issue in result["issues"])

    @pytest.mark.asyncio
    async def test_safe_to_queue_false_when_queue_full(self, safety_ctx):
        guard = _guard(safety_ctx)
        # Fill queue to max (10)
        guard._client.get_queue = AsyncMock(return_value={
            "queue_running": ["j1", "j2"],
            "queue_pending": ["j3", "j4", "j5", "j6", "j7", "j8", "j9", "j10"],
        })
        result = json.loads(await comfy_validate_before_queue(ctx=safety_ctx))
        assert result["safe_to_queue"] is False
        assert any("Queue full" in issue for issue in result["issues"])

    @pytest.mark.asyncio
    async def test_multiple_issues_accumulate(self, safety_ctx):
        guard = _guard(safety_ctx)
        guard._client.get_system_stats = AsyncMock(return_value={
            "devices": [{"name": "GPU", "vram_total": 1000, "vram_free": 10}],
        })
        guard._client.get_queue = AsyncMock(return_value={
            "queue_running": ["j"] * 10,
            "queue_pending": ["j"] * 5,
        })
        result = json.loads(await comfy_validate_before_queue(ctx=safety_ctx))
        assert result["safe_to_queue"] is False
        assert len(result["issues"]) == 2


# ---------------------------------------------------------------------------
# set_limits
# ---------------------------------------------------------------------------

class TestSetLimits:
    @pytest.mark.asyncio
    async def test_set_warn_pct(self, safety_ctx):
        result = json.loads(await comfy_set_limits(warn_pct=70.0, ctx=safety_ctx))
        assert result["warn_pct"] == 70.0
        guard = _guard(safety_ctx)
        assert guard.warn_pct == 70.0

    @pytest.mark.asyncio
    async def test_set_block_pct(self, safety_ctx):
        result = json.loads(await comfy_set_limits(block_pct=90.0, ctx=safety_ctx))
        assert result["block_pct"] == 90.0

    @pytest.mark.asyncio
    async def test_set_max_queue(self, safety_ctx):
        result = json.loads(await comfy_set_limits(max_queue=5, ctx=safety_ctx))
        assert result["max_queue"] == 5

    @pytest.mark.asyncio
    async def test_set_timeout(self, safety_ctx):
        result = json.loads(await comfy_set_limits(timeout=600, ctx=safety_ctx))
        assert result["timeout"] == 600

    @pytest.mark.asyncio
    async def test_set_multiple_limits(self, safety_ctx):
        result = json.loads(await comfy_set_limits(warn_pct=75.0, block_pct=92.0, max_queue=8, timeout=120, ctx=safety_ctx))
        assert result["warn_pct"] == 75.0
        assert result["block_pct"] == 92.0
        assert result["max_queue"] == 8
        assert result["timeout"] == 120

    @pytest.mark.asyncio
    async def test_set_limits_no_args_returns_current(self, safety_ctx):
        # Calling with no overrides returns existing defaults
        result = json.loads(await comfy_set_limits(ctx=safety_ctx))
        assert result["warn_pct"] == 80.0
        assert result["block_pct"] == 95.0
        assert result["max_queue"] == 10
        assert result["timeout"] == 300


# ---------------------------------------------------------------------------
# emergency_stop
# ---------------------------------------------------------------------------

class TestEmergencyStop:
    @pytest.mark.asyncio
    async def test_emergency_stop_calls_interrupt(self, safety_ctx):
        await comfy_emergency_stop(ctx=safety_ctx)
        guard = _guard(safety_ctx)
        guard._client.interrupt.assert_called_once()

    @pytest.mark.asyncio
    async def test_emergency_stop_calls_clear_queue(self, safety_ctx):
        await comfy_emergency_stop(ctx=safety_ctx)
        guard = _guard(safety_ctx)
        guard._client.clear_queue.assert_called_once()

    @pytest.mark.asyncio
    async def test_emergency_stop_calls_free_vram(self, safety_ctx):
        await comfy_emergency_stop(ctx=safety_ctx)
        guard = _guard(safety_ctx)
        guard._client.free_vram.assert_called_once_with(unload_models=True, free_memory=True)

    @pytest.mark.asyncio
    async def test_emergency_stop_returns_stopped_status(self, safety_ctx):
        result = json.loads(await comfy_emergency_stop(ctx=safety_ctx))
        assert result["status"] == "stopped"
        assert "interrupted" in result["actions"]
        assert "queue_cleared" in result["actions"]
        assert "vram_freed" in result["actions"]


# ---------------------------------------------------------------------------
# detect_instability
# ---------------------------------------------------------------------------

class TestDetectInstability:
    @pytest.mark.asyncio
    async def test_stable_when_ok(self, safety_ctx):
        result = json.loads(await comfy_detect_instability(ctx=safety_ctx))
        assert result["stable"] is True
        assert result["issues"] == []

    @pytest.mark.asyncio
    async def test_unstable_near_oom(self, safety_ctx):
        guard = _guard(safety_ctx)
        # <5% free → near-OOM
        guard._client.get_system_stats = AsyncMock(return_value={
            "devices": [{"name": "RTX 5090", "vram_total": 1000, "vram_free": 40}],
        })
        result = json.loads(await comfy_detect_instability(ctx=safety_ctx))
        assert result["stable"] is False
        assert len(result["issues"]) == 1
        assert "Near-OOM" in result["issues"][0]
        assert "RTX 5090" in result["issues"][0]

    @pytest.mark.asyncio
    async def test_queue_counts_reported(self, safety_ctx):
        guard = _guard(safety_ctx)
        guard._client.get_queue = AsyncMock(return_value={
            "queue_running": ["j1", "j2"],
            "queue_pending": ["j3"],
        })
        result = json.loads(await comfy_detect_instability(ctx=safety_ctx))
        assert result["queue_running"] == 2
        assert result["queue_pending"] == 1


# ---------------------------------------------------------------------------
# Round-trip: check → set limits → check again with new thresholds
# ---------------------------------------------------------------------------

class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_check_set_limits_check(self, safety_ctx):
        """Lower warn threshold, confirm previously-ok reading now triggers warn."""
        guard = _guard(safety_ctx)
        # Set VRAM to 50% used
        guard._client.get_system_stats = AsyncMock(return_value={
            "devices": [{"name": "GPU", "vram_total": 1000, "vram_free": 500}],
        })

        # First check → ok with default 80% warn threshold
        result1 = json.loads(await comfy_check_vram(ctx=safety_ctx))
        assert result1["status"] == "ok"
        assert result1["vram_used_pct"] == 50.0

        # Lower warn threshold to 40%
        await comfy_set_limits(warn_pct=40.0, ctx=safety_ctx)

        # Second check → now warn because 50% >= 40%
        result2 = json.loads(await comfy_check_vram(ctx=safety_ctx))
        assert result2["status"] == "warn"

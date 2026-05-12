"""Tests for VRAMGuard.recommended_flags() and detect_instability advice."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from comfy_mcp.safety.vram_guard import VRAMGuard


def test_recommended_flags_marks_dynamic_vram_as_default():
    flags = VRAMGuard.recommended_flags()
    assert flags["dynamic_vram_default"] is True


def test_recommended_flags_lists_fp16_intermediates():
    flags = VRAMGuard.recommended_flags()
    assert "--fp16-intermediates" in flags["flags"]


def test_recommended_flags_lists_enable_dynamic_vram():
    flags = VRAMGuard.recommended_flags()
    assert "--enable-dynamic-vram" in flags["flags"]


def test_recommended_flags_lists_modern_precision_formats():
    flags = VRAMGuard.recommended_flags()
    assert "mxfp8" in flags["precision_formats"]
    assert "nvfp4" in flags["precision_formats"]


@pytest.mark.asyncio
async def test_detect_instability_includes_recommendations_when_near_oom():
    client = AsyncMock()
    client.get_system_stats = AsyncMock(return_value={
        "devices": [
            {
                "name": "RTX 5090",
                "vram_total": 1000,
                "vram_free": 10,  # 1% free => near-OOM
            }
        ],
    })
    client.get_queue = AsyncMock(return_value={"queue_running": [], "queue_pending": []})
    vg = VRAMGuard(client)
    result = await vg.detect_instability()
    assert result["stable"] is False
    assert "recommendations" in result
    assert "--fp16-intermediates" in result["recommendations"]["flags"]


@pytest.mark.asyncio
async def test_detect_instability_no_recommendations_when_stable():
    client = AsyncMock()
    client.get_system_stats = AsyncMock(return_value={
        "devices": [
            {"name": "RTX 5090", "vram_total": 1000, "vram_free": 800},  # 80% free
        ],
    })
    client.get_queue = AsyncMock(return_value={"queue_running": [], "queue_pending": []})
    vg = VRAMGuard(client)
    result = await vg.detect_instability()
    assert result["stable"] is True
    assert "recommendations" not in result

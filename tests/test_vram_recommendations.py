"""Tests for VRAMGuard.recommended_flags() and detect_instability advice."""
from __future__ import annotations

from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from comfy_mcp.safety.vram_guard import VRAMGuard


def test_nvidia_smi_fallback_parses_devices_and_wddm_processes(monkeypatch):
    monkeypatch.setattr("comfy_mcp.safety.vram_guard.shutil.which", lambda name: "nvidia-smi")

    def fake_run(argv, **kwargs):
        if argv[1].startswith("--query-gpu="):
            return SimpleNamespace(
                returncode=0,
                stdout="0, GPU-uuid, RTX Test, 1000, 250, 750\n",
                stderr="",
            )
        return SimpleNamespace(
            returncode=0,
            stdout="123, GPU-uuid, [N/A], C:\\python.exe\n",
            stderr="",
        )

    monkeypatch.setattr("comfy_mcp.safety.vram_guard.subprocess.run", fake_run)
    result = VRAMGuard._read_nvidia_smi_snapshot()
    assert result["available"] is True
    assert result["source"] == "nvidia-smi"
    assert result["devices"][0]["vram_free"] == 750 * 1024 * 1024
    assert result["processes"][0] == {
        "pid": 123,
        "device_index": 0,
        "used_gpu_memory": 0,
        "name": "C:\\python.exe",
    }


@pytest.mark.asyncio
async def test_remote_comfy_does_not_report_mcp_hosts_nvml():
    client = AsyncMock()
    client.base_url = "https://remote.example.com"
    client.get_system_stats = AsyncMock(return_value={
        "devices": [{"name": "remote GPU", "vram_total": 1000, "vram_free": 500}],
    })
    guard = VRAMGuard(client)
    guard._get_nvml_snapshot = AsyncMock(return_value={
        "available": True,
        "devices": [{"index": 0, "vram_free": 1}],
        "processes": [{"pid": 999}],
    })
    result = await guard.check_vram()
    assert result["nvml_available"] is False
    assert result["gpu_processes"] == []
    guard._get_nvml_snapshot.assert_not_awaited()


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

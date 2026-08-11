"""Smoke tests for response model shape and roundtrip serialization."""
from __future__ import annotations

import pytest

from comfy_mcp.responses import (
    DynamicsReport,
    JobStatus,
    ModelList,
    QueueAck,
    SnapshotEntry,
    SnapshotList,
    SystemStats,
    TechniqueEntry,
    TechniqueList,
    ValidationReport,
    VRAMStatus,
    WatchProgressFrame,
)


def test_validation_report_roundtrip():
    r = ValidationReport(
        valid=True, node_count=5,
        passes=["schema", "catalog", "graph", "environment", "execution_risk"],
    )
    data = r.model_dump()
    assert data["valid"] is True
    assert len(data["passes"]) == 5


def test_queue_ack_with_error_preserved():
    a = QueueAck(prompt_id=None, error="invalid workflow")
    assert a.error == "invalid workflow"
    assert a.model_dump()["error"] == "invalid workflow"


def test_queue_ack_distinguishes_number_from_position():
    ack = QueueAck(prompt_id="abc", queue_number=-3.5)
    assert ack.queue_number == -3.5
    assert ack.queue_position is None


def test_job_status_state_literal():
    j = JobStatus(prompt_id="abc", status="running")
    assert j.status == "running"
    # Invalid state should fail validation
    with pytest.raises(Exception):
        JobStatus(prompt_id="abc", status="not-a-state")


def test_model_list_pagination_fields():
    m = ModelList(folder="checkpoints", models=["a.safetensors"], total_count=50, has_more=True, next_offset=20)
    assert m.next_offset == 20


def test_vram_status_level_literal():
    v = VRAMStatus(status="critical", vram_used_pct=98.5)
    assert v.status == "critical"
    with pytest.raises(Exception):
        VRAMStatus(status="fine")


def test_vram_status_preserves_nvml_process_details():
    status = VRAMStatus.model_validate({
        "status": "ok",
        "nvml_available": True,
        "devices": [{
            "name": "GPU",
            "index": 0,
            "nvml_vram_used": 123,
            "process_vram_used": 100,
        }],
        "gpu_processes": [{
            "pid": 42,
            "device_index": 0,
            "used_gpu_memory": 100,
            "name": "python.exe",
        }],
    })
    assert status.nvml_available is True
    assert status.devices[0].nvml_vram_used == 123
    assert status.gpu_processes[0].pid == 42


def test_system_stats_accepts_empty_defaults():
    s = SystemStats()
    assert s.system.ram_total == 0
    assert s.devices == []


def test_system_stats_accepts_current_comfy_package_version_list():
    s = SystemStats.model_validate({
        "system": {
            "comfyui_version": "0.31.0",
            "comfy_package_versions": [
                {
                    "name": "comfyui-frontend-package",
                    "installed": "1.48.7",
                    "required": "1.48.7",
                }
            ],
        }
    })
    assert isinstance(s.system.comfy_package_versions, list)
    assert s.system.comfy_package_versions[0].name == "comfyui-frontend-package"
    assert s.system.comfy_package_versions[0].installed == "1.48.7"


def test_technique_list_empty_defaults():
    t = TechniqueList()
    assert t.count == 0
    assert t.techniques == []


def test_dynamics_report_shape():
    d = DynamicsReport(
        queue_running=1, queue_pending=3,
        event_types_seen=["progress", "executing"],
        recent_event_count=5,
        active_job_count=1,
        active_jobs=[{"prompt_id": "x", "status": "running"}],
    )
    assert d.queue_pending == 3
    assert len(d.active_jobs) == 1


def test_snapshot_entry_and_list():
    e = SnapshotEntry(id="abc123", name="before-edit", timestamp=123456.0, node_count=12)
    lst = SnapshotList(snapshots=[e], count=1)
    assert lst.count == 1
    assert lst.snapshots[0].id == "abc123"


def test_watch_progress_frame_shape():
    f = WatchProgressFrame(prompt_id="x", progress=10, max_progress=20, status="ok", elapsed_s=3.5)
    assert f.progress == 10.0
    assert f.status == "ok"


def test_technique_entry_required_fields():
    t = TechniqueEntry(id="abc", name="my-technique")
    assert t.tags == []
    assert t.rating == -1

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


def test_system_stats_accepts_empty_defaults():
    s = SystemStats()
    assert s.system.ram_total == 0
    assert s.devices == []


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

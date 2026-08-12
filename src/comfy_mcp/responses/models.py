"""Pydantic response models for ComfyPilot's high-signal tools.

These replace free-form json.dumps strings so agents receive typed,
introspectable JSON. Each model is a thin schema over what the tool
actually computes - no business logic lives here.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------- System ----------


class GPUInfo(BaseModel):
    name: str = ""
    type: str = ""
    index: int | None = None
    vram_total: int = 0
    vram_free: int = 0
    torch_vram_total: int = 0
    torch_vram_free: int = 0


class ComfyPackageVersion(BaseModel):
    """Installed/required version pair returned by current ComfyUI builds."""

    name: str = ""
    installed: str | None = None
    required: str | None = None


class SystemInfo(BaseModel):
    python_version: str = ""
    pytorch_version: str = ""
    comfyui_version: str = ""
    os: str = ""
    embedded_python: bool = False
    argv: list[str] = Field(default_factory=list)
    ram_total: int = 0
    ram_free: int = 0
    comfyui_frontend_package: str = ""
    required_frontend_version: str = ""
    installed_templates_version: str = ""
    required_templates_version: str = ""
    # Current ComfyUI Desktop returns a list of named package records. Keep
    # accepting the short-lived mapping shape too so older/custom builds do
    # not fail response validation.
    comfy_package_versions: list[ComfyPackageVersion] | dict[str, str] = Field(
        default_factory=list
    )
    deploy_environment: str | None = None


class SystemStats(BaseModel):
    system: SystemInfo = Field(default_factory=SystemInfo)
    devices: list[GPUInfo] = Field(default_factory=list)


# ---------- Workflow / Queue / Jobs ----------


class ValidationReport(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    node_count: int = 0
    passes: list[str] = Field(default_factory=list)


class NodeError(BaseModel):
    errors: list[dict[str, Any]] = Field(default_factory=list)
    dependent_outputs: list[str] = Field(default_factory=list)
    class_type: str = ""


class QueueAck(BaseModel):
    prompt_id: str | None = None
    # ComfyUI calls this `number`: a monotonic/priority queue key, not an
    # ordinal position. Preserve the old field as a deprecated compatibility
    # slot, but new responses intentionally leave it unset.
    queue_number: int | float | None = None
    queue_position: int | None = Field(
        default=None,
        description="Deprecated: ComfyUI does not return an ordinal queue position",
    )
    error: str | None = None
    node_errors: dict[str, NodeError] | None = None
    auto_snapshot: dict[str, Any] | None = None
    # Populated by comfy_run_with_inputs with the per-label upload record
    # (local_path, uploaded_filename, size_bytes, applied_to). Stays None
    # for the regular comfy_queue_prompt path.
    upload_map: dict[str, Any] | None = None


JobState = Literal[
    "queued", "running", "completed", "failed",
    "cancelled", "interrupted", "timeout",
]


class JobStatus(BaseModel):
    prompt_id: str
    status: JobState = "queued"
    submitted_at: float = 0.0
    completed_at: float | None = None
    progress: float = 0.0
    max_progress: float = 0.0
    error: str | None = None
    result: dict[str, Any] | None = None


class RunResult(BaseModel):
    """Result of a completed prompt as returned by ComfyUI's /history/{id} endpoint."""

    prompt_id: str
    status: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    prompt: list[Any] = Field(default_factory=list)
    # ComfyUI v0.3.69+ exposes a `create_time` field on /history entries -
    # epoch seconds when the prompt was queued. Older builds omit it.
    create_time: float | None = None
    error: str | None = None


# ---------- Models / Techniques / Snapshots ----------


class ModelList(BaseModel):
    folder: str
    models: list[str] = Field(default_factory=list)
    total_count: int = 0
    has_more: bool = False
    next_offset: int | None = None


class TechniqueEntry(BaseModel):
    id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    timestamp: float = 0.0
    node_count: int = 0
    favorite: bool = False
    rating: int = -1
    use_count: int = 0


class TechniqueList(BaseModel):
    techniques: list[TechniqueEntry] = Field(default_factory=list)
    count: int = 0


class SnapshotEntry(BaseModel):
    id: str
    name: str
    timestamp: float = 0.0
    node_count: int = 0


class SnapshotList(BaseModel):
    snapshots: list[SnapshotEntry] = Field(default_factory=list)
    count: int = 0


# ---------- Safety ----------


VRAMLevel = Literal["ok", "warn", "critical", "unknown"]


class VRAMDeviceInfo(BaseModel):
    name: str = "unknown"
    index: int | None = None
    vram_total: int = 0
    vram_free: int = 0
    vram_used: int = 0
    vram_used_pct: float = 0.0
    status: VRAMLevel = "ok"
    nvml_vram_total: int | None = None
    nvml_vram_free: int | None = None
    nvml_vram_used: int | None = None
    process_vram_used: int = 0


class VRAMProcessInfo(BaseModel):
    pid: int
    device_index: int = 0
    used_gpu_memory: int = 0
    name: str = "unknown"


class VRAMStatus(BaseModel):
    status: VRAMLevel = "unknown"
    vram_used_pct: float = 0.0
    devices: list[VRAMDeviceInfo] = Field(default_factory=list)
    nvml_available: bool = False
    gpu_processes: list[VRAMProcessInfo] = Field(default_factory=list)
    message: str = ""


# ---------- Monitoring ----------


class DynamicsReport(BaseModel):
    queue_running: int = 0
    queue_pending: int = 0
    event_types_seen: list[str] = Field(default_factory=list)
    recent_event_count: int = 0
    active_job_count: int = 0
    active_jobs: list[dict[str, Any]] = Field(default_factory=list)


class WatchProgressFrame(BaseModel):
    prompt_id: str
    status: Literal["ok", "no_progress"] = "no_progress"
    progress: float = 0.0
    max_progress: float = 0.0
    timestamp: float = 0.0
    elapsed_s: float = 0.0

"""Structured response models for high-signal ComfyPilot tools.

Agents plan better against typed JSON than free-text. Each model here
defines the exact shape a tool's return value will have when serialized.
"""
from comfy_mcp.responses.models import (
    ComfyPackageVersion,
    DynamicsReport,
    JobStatus,
    ModelList,
    QueueAck,
    RunResult,
    SnapshotList,
    SnapshotEntry,
    SystemInfo,
    SystemStats,
    TechniqueEntry,
    TechniqueList,
    ValidationReport,
    VRAMDeviceInfo,
    VRAMProcessInfo,
    VRAMStatus,
    WatchProgressFrame,
)

__all__ = [
    "ComfyPackageVersion",
    "DynamicsReport",
    "JobStatus",
    "ModelList",
    "QueueAck",
    "RunResult",
    "SnapshotEntry",
    "SnapshotList",
    "SystemInfo",
    "SystemStats",
    "TechniqueEntry",
    "TechniqueList",
    "ValidationReport",
    "VRAMDeviceInfo",
    "VRAMProcessInfo",
    "VRAMStatus",
    "WatchProgressFrame",
]

"""Structured response models for high-signal ComfyPilot tools.

Agents plan better against typed JSON than free-text. Each model here
defines the exact shape a tool's return value will have when serialized.
"""
from comfy_mcp.responses.models import (
    DynamicsReport,
    JobStatus,
    ModelList,
    QueueAck,
    SnapshotList,
    SnapshotEntry,
    SystemStats,
    TechniqueEntry,
    TechniqueList,
    ValidationReport,
    VRAMStatus,
    WatchProgressFrame,
)

__all__ = [
    "DynamicsReport",
    "JobStatus",
    "ModelList",
    "QueueAck",
    "SnapshotEntry",
    "SnapshotList",
    "SystemStats",
    "TechniqueEntry",
    "TechniqueList",
    "ValidationReport",
    "VRAMStatus",
    "WatchProgressFrame",
]

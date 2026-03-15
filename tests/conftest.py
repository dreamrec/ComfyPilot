"""Shared pytest fixtures for ComfyPilot tests."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_client():
    """Mock ComfyClient with common method stubs."""
    client = AsyncMock()
    client.base_url = "http://localhost:8188"
    client.get = AsyncMock(return_value={})
    client.post = AsyncMock(return_value={})
    client.get_system_stats = AsyncMock(return_value={
        "system": {
            "os": "nt",
            "comfyui_version": "0.17.0",
            "python_version": "3.12.0",
            "pytorch_version": "2.5.0",
            "embedded_python": False,
        },
        "devices": [
            {
                "name": "NVIDIA GeForce RTX 5090",
                "type": "cuda",
                "index": 0,
                "vram_total": 34359738368,
                "vram_free": 30000000000,
                "torch_vram_total": 34359738368,
                "torch_vram_free": 30000000000,
            }
        ],
    })
    client.get_queue = AsyncMock(return_value={
        "queue_running": [],
        "queue_pending": [],
    })
    return client


@pytest.fixture
def mock_ctx(mock_client):
    """Mock MCP Context with lifespan_context wired to mock_client."""
    # Create event manager mock with a health() method
    event_manager_mock = MagicMock()
    event_manager_mock.health = MagicMock(return_value={
        "running": True,
        "connected": True,
        "reconnect_count": 0,
        "buffer_size": 0,
        "buffer_capacity": 1000,
        "subscription_count": 0,
        "subscribed_types": [],
    })
    event_manager_mock.peek_events = MagicMock(return_value=[])

    snapshot_manager_mock = MagicMock()
    snapshot_manager_mock.auto_snapshot = False

    job_tracker_mock = MagicMock()
    job_tracker_mock.track = AsyncMock()
    job_tracker_mock.mark_cancelled = AsyncMock()
    job_tracker_mock.list_active = MagicMock(return_value=[])

    ctx = MagicMock()
    ctx.request_context.lifespan_context = {
        "comfy_client": mock_client,
        "event_manager": event_manager_mock,
        "snapshot_manager": snapshot_manager_mock,
        "technique_store": MagicMock(),
        "vram_guard": MagicMock(),
        "job_tracker": job_tracker_mock,
    }
    ctx.report_progress = AsyncMock()
    ctx.log_info = AsyncMock()
    ctx.log_warning = AsyncMock()
    ctx.log_error = AsyncMock()
    return ctx

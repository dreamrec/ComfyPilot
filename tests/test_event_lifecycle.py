"""Test that EventManager is started during lifespan."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.base_url = "http://localhost:8188"
    client.connect = AsyncMock()
    client.close = AsyncMock()
    client.get_system_stats = AsyncMock(return_value={"devices": []})
    client.capabilities = {"ws_available": True}
    return client


@pytest.mark.asyncio
async def test_event_manager_started_in_lifespan(mock_client, monkeypatch):
    """EventManager.start() must be called during lifespan setup."""
    monkeypatch.setenv("COMFY_SNAPSHOT_DIR", "0")
    with patch("comfy_mcp.server.ComfyClient", return_value=mock_client):
        with patch("comfy_mcp.events.event_manager.EventManager") as MockEM:
            mock_em_instance = MagicMock()
            mock_em_instance.start = AsyncMock()
            mock_em_instance.shutdown = AsyncMock()
            MockEM.return_value = mock_em_instance

            from comfy_mcp.server import comfy_lifespan, mcp

            async with comfy_lifespan(mcp) as ctx:
                mock_em_instance.start.assert_awaited_once()
                assert ctx["event_manager"] is mock_em_instance

            mock_em_instance.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_event_manager_not_started_without_ws(mock_client, monkeypatch):
    monkeypatch.setenv("COMFY_SNAPSHOT_DIR", "0")
    mock_client.capabilities = {"ws_available": False}
    with patch("comfy_mcp.server.ComfyClient", return_value=mock_client):
        with patch("comfy_mcp.events.event_manager.EventManager") as MockEM:
            mock_em_instance = MagicMock()
            mock_em_instance.start = AsyncMock()
            mock_em_instance.shutdown = AsyncMock()
            MockEM.return_value = mock_em_instance

            from comfy_mcp.server import comfy_lifespan, mcp

            async with comfy_lifespan(mcp):
                mock_em_instance.start.assert_not_called()

            mock_em_instance.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_uses_persistent_snapshot_directory_by_default(
    mock_client, monkeypatch, tmp_path,
):
    monkeypatch.delenv("COMFY_SNAPSHOT_DIR", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    with patch("comfy_mcp.server.ComfyClient", return_value=mock_client), \
         patch("comfy_mcp.events.event_manager.EventManager") as MockEM, \
         patch("comfy_mcp.memory.snapshot_manager.SnapshotManager") as MockSM:
        mock_em_instance = MagicMock()
        mock_em_instance.start = AsyncMock()
        mock_em_instance.shutdown = AsyncMock()
        MockEM.return_value = mock_em_instance
        from comfy_mcp.server import comfy_lifespan, mcp

        async with comfy_lifespan(mcp):
            pass

        assert MockSM.call_args.kwargs["storage_dir"] == str(
            tmp_path / ".comfypilot" / "snapshots"
        )

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
    return client


@pytest.mark.asyncio
async def test_event_manager_started_in_lifespan(mock_client):
    """EventManager.start() must be called during lifespan setup."""
    with patch("comfy_mcp.server.ComfyClient", return_value=mock_client):
        with patch("comfy_mcp.events.event_manager.EventManager") as MockEM:
            mock_em_instance = AsyncMock()
            MockEM.return_value = mock_em_instance

            from comfy_mcp.server import comfy_lifespan, mcp

            async with comfy_lifespan(mcp) as ctx:
                mock_em_instance.start.assert_awaited_once()
                assert ctx["event_manager"] is mock_em_instance

            mock_em_instance.shutdown.assert_awaited_once()

"""Tests for the /workflow_templates integration."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.comfy_client import ComfyClient


@pytest.mark.asyncio
async def test_get_workflow_templates_local_profile():
    """Local profile tries /workflow_templates first."""
    client = ComfyClient("http://127.0.0.1:8188")
    client.capabilities["profile"] = "local"

    http = MagicMock()
    resp = MagicMock(is_success=True, status_code=200)
    resp.json = MagicMock(return_value={"comfyui-frontend": ["txt2img.json", "img2img.json"]})
    http.get = AsyncMock(return_value=resp)
    client._http = http

    result = await client.get_workflow_templates()
    assert "comfyui-frontend" in result
    assert "txt2img.json" in result["comfyui-frontend"]
    http.get.assert_awaited_with("/workflow_templates")


@pytest.mark.asyncio
async def test_get_workflow_templates_cloud_profile():
    """Cloud profile prefers the /api/ prefix."""
    client = ComfyClient("https://cloud.comfy.org")
    client.capabilities["profile"] = "cloud"

    http = MagicMock()
    resp = MagicMock(is_success=True, status_code=200)
    resp.json = MagicMock(return_value={"core": ["sdxl.json"]})
    http.get = AsyncMock(return_value=resp)
    client._http = http

    result = await client.get_workflow_templates()
    assert "core" in result
    http.get.assert_awaited_with("/api/workflow_templates")


@pytest.mark.asyncio
async def test_get_workflow_templates_fallback_on_404():
    """When primary returns 404, the client falls back to the alternate path."""
    client = ComfyClient("http://127.0.0.1:8188")
    client.capabilities["profile"] = "local"

    async def get_side_effect(path):
        resp = MagicMock(status_code=200, is_success=True)
        if path == "/workflow_templates":
            # Simulate 404 -> raise through _check_status
            from comfy_mcp.errors import ComfyAPIError
            raise ComfyAPIError(
                error_code="HTTP_404",
                message="not found",
                suggestion="check version",
                retry_possible=False,
            )
        resp.json = MagicMock(return_value={"fallback": ["x.json"]})
        return resp

    client._http = MagicMock()
    client._http.get = AsyncMock(side_effect=get_side_effect)

    result = await client.get_workflow_templates()
    assert "fallback" in result

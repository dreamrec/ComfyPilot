from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from comfy_mcp.tools.instance import comfy_instance_doctor


@pytest.mark.asyncio
async def test_instance_doctor_correlates_desktop_process_and_paths(mock_ctx, mock_client):
    mock_client.base_url = "http://127.0.0.1:8000"
    mock_client.api_key = ""
    mock_client.get_system_stats = AsyncMock(return_value={
        "system": {
            "comfyui_version": "0.31.0",
            "required_frontend_version": "1.48.7",
            "deploy_environment": "local-desktop2-standalone",
            "argv": [
                "ComfyUI/main.py",
                "--base-directory", "C:/Data/ComfyUI",
                "--user-directory", "C:/Data/ComfyUI/user",
                "--input-directory", "C:/Data/ComfyUI/input",
                "--output-directory", "C:/Data/ComfyUI/output",
                "--port", "8000",
                "--listen", "0.0.0.0",
                "--enable-manager",
            ],
        },
        "devices": [],
    })
    mock_client.get_text = AsyncMock(return_value="V4.2.2")
    installations = [{
        "id": "inst-selected",
        "name": "ComfyUI",
        "sourceId": "standalone",
        "installPath": "C:/Installs/ComfyUI",
        "adoptedBaseDir": "C:/Data/ComfyUI",
        "inputDir": "C:/Data/ComfyUI/input",
        "outputDir": "C:/Data/ComfyUI/output",
        "launchArgs": "--port 8000",
        "version": "0.25.0",
    }]
    process = {"pid": 123, "parent_pid": 456, "name": "python.exe"}
    desktop = {"pid": 789, "name": "Comfy Desktop.exe"}
    with (
        patch("comfy_mcp.tools.instance._read_desktop_installations", return_value=(installations, "registry.json")),
        patch("comfy_mcp.tools.instance._discover_process", return_value=(
            [{"address": "0.0.0.0", "port": 8000, "pid": 123}],
            [process, desktop],
            "test",
        )),
    ):
        result = json.loads(await comfy_instance_doctor(ctx=mock_ctx))

    assert result["status"] == "ok"
    assert result["instance_id"] == "inst-selected"
    assert result["owner_type"] == "comfy_desktop"
    assert result["listener"]["pid"] == 123
    assert result["supervisor"]["name"] == "Comfy Desktop.exe"
    assert result["paths"]["code_root"]["path"].replace("\\", "/").endswith(
        "C:/Installs/ComfyUI/ComfyUI"
    )
    assert result["paths"]["output_root"]["path"].replace("\\", "/") == "C:/Data/ComfyUI/output"
    assert result["manager"]["version"] == "V4.2.2"
    assert result["warnings"]


@pytest.mark.asyncio
async def test_instance_doctor_offline_is_actionable(mock_ctx, mock_client):
    mock_client.base_url = "http://127.0.0.1:8000"
    mock_client.get_system_stats = AsyncMock(side_effect=RuntimeError("connection refused"))
    result = json.loads(await comfy_instance_doctor(ctx=mock_ctx))
    assert result["status"] == "offline"
    assert result["port"] == 8000
    assert "connection refused" in result["error"]

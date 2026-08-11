"""Tests for the 5 lifecycle tools (comfy-cli wrappers)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comfy_mcp.cli.comfy_cli import ComfyCliError, ComfyCliResult
from comfy_mcp.tools.lifecycle import (
    comfy_download_model,
    comfy_install_node,
    comfy_launch_server,
    comfy_list_installed_nodes,
    comfy_stop_server,
)


def _ok_result(stdout: str = "", stderr: str = "") -> ComfyCliResult:
    return ComfyCliResult(returncode=0, stdout=stdout, stderr=stderr, argv=("/bin/comfy",))


def _fail_result(stderr: str = "failed") -> ComfyCliResult:
    return ComfyCliResult(returncode=1, stdout="", stderr=stderr, argv=("/bin/comfy",))


@pytest.fixture
def mock_run():
    """Patch `comfy_mcp.tools.lifecycle.run_comfy_cli`."""
    with patch("comfy_mcp.tools.lifecycle.run_comfy_cli", new_callable=AsyncMock) as m:
        yield m


class TestLaunchServer:
    @pytest.mark.asyncio
    async def test_returns_launched_on_success(self, mock_run):
        mock_run.return_value = _ok_result(stdout="server started\n")
        result = await comfy_launch_server(
            port=8188, host="127.0.0.1", workspace="C:/ComfyUI", confirm=True
        )
        parsed = json.loads(result)
        assert parsed["status"] == "launched"
        assert parsed["port"] == 8188

    @pytest.mark.asyncio
    async def test_forwards_port_and_host_after_dashes(self, mock_run):
        mock_run.return_value = _ok_result()
        await comfy_launch_server(
            port=8190, host="0.0.0.0", workspace="C:/ComfyUI", confirm=True
        )
        called_args = mock_run.call_args[0][0]
        assert "--port" in called_args
        assert "8190" in called_args
        assert "--listen" in called_args
        assert "0.0.0.0" in called_args

    @pytest.mark.asyncio
    async def test_returns_error_when_cli_missing(self, mock_run):
        mock_run.side_effect = ComfyCliError("not on PATH")
        result = await comfy_launch_server(
            port=8188, workspace="C:/ComfyUI", confirm=True
        )
        parsed = json.loads(result)
        assert "error" in parsed
        assert "not on PATH" in parsed["error"]


class TestStopServer:
    @pytest.mark.asyncio
    async def test_stops_successfully(self, mock_run):
        mock_run.return_value = _ok_result(stdout="stopped")
        result = await comfy_stop_server(workspace="C:/ComfyUI", confirm=True)
        parsed = json.loads(result)
        assert parsed["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_cli_missing(self, mock_run):
        mock_run.side_effect = ComfyCliError("not on PATH")
        result = await comfy_stop_server(workspace="C:/ComfyUI", confirm=True)
        parsed = json.loads(result)
        assert "error" in parsed


class TestInstallNode:
    @pytest.mark.asyncio
    async def test_installs_successfully(self, mock_run):
        mock_run.return_value = _ok_result(stdout="installed comfyui-impact-pack")
        result = await comfy_install_node(
            name="comfyui-impact-pack", workspace="C:/ComfyUI", confirm=True
        )
        parsed = json.loads(result)
        assert parsed["status"] == "installed"
        assert parsed["name"] == "comfyui-impact-pack"

    @pytest.mark.asyncio
    async def test_rejects_path_traversal_in_name(self, mock_run):
        result = await comfy_install_node(name="../evil")
        parsed = json.loads(result)
        assert "error" in parsed
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_empty_name(self, mock_run):
        result = await comfy_install_node(name="")
        parsed = json.loads(result)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_failed_install_returns_failed_status(self, mock_run):
        mock_run.return_value = _fail_result(stderr="node not found")
        result = await comfy_install_node(
            name="nonexistent-pkg", workspace="C:/ComfyUI", confirm=True
        )
        parsed = json.loads(result)
        assert parsed["status"] == "failed"


class TestListInstalledNodes:
    @pytest.mark.asyncio
    async def test_parses_raw_lines(self, mock_run):
        mock_run.return_value = _ok_result(stdout="""=== installed nodes ===
comfyui-impact-pack
comfyui-controlnet-aux

------
""")
        result = await comfy_list_installed_nodes(workspace="C:/ComfyUI")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "comfyui-impact-pack" in parsed["raw_lines"]
        assert parsed["line_count"] == 2

    @pytest.mark.asyncio
    async def test_cli_missing(self, mock_run):
        mock_run.side_effect = ComfyCliError("not on PATH")
        result = await comfy_list_installed_nodes(workspace="C:/ComfyUI")
        parsed = json.loads(result)
        assert "error" in parsed


class TestDownloadModel:
    @pytest.mark.asyncio
    async def test_downloads_with_url_and_folder(self, mock_run):
        mock_run.return_value = _ok_result(stdout="downloaded")
        result = await comfy_download_model(
            url="https://huggingface.co/foo/bar.safetensors",
            folder="checkpoints",
            workspace="C:/ComfyUI",
            confirm=True,
        )
        parsed = json.loads(result)
        assert parsed["status"] == "downloaded"
        assert parsed["url"].startswith("https://")
        assert parsed["folder"] == "checkpoints"

    @pytest.mark.asyncio
    async def test_rejects_non_http_url(self, mock_run):
        result = await comfy_download_model(url="file:///etc/passwd", folder="checkpoints")
        parsed = json.loads(result)
        assert "error" in parsed
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_folder_with_separator(self, mock_run):
        result = await comfy_download_model(
            url="https://example.com/x.safetensors",
            folder="../etc",
        )
        parsed = json.loads(result)
        assert "error" in parsed
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_civitai_token_forwarded(self, mock_run):
        mock_run.return_value = _ok_result()
        await comfy_download_model(
            url="https://civitai.com/api/download/models/123",
            folder="loras",
            civitai_api_token="secret-token",
            workspace="C:/ComfyUI",
            confirm=True,
        )
        called_args = mock_run.call_args[0][0]
        assert "--set-civitai-api-token" in called_args
        assert "secret-token" in called_args


class TestLifecycleSafety:
    @pytest.mark.asyncio
    async def test_launch_requires_explicit_workspace_and_port(self, mock_run):
        parsed = json.loads(await comfy_launch_server(confirm=True))
        assert parsed["status"] == "selection_required"
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_install_requires_confirmation(self, mock_run):
        parsed = json.loads(await comfy_install_node(
            name="comfyui-impact-pack", workspace="C:/ComfyUI", confirm=False
        ))
        assert parsed["status"] == "cancelled"
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_manager_v2_inventory_preferred(self, mock_ctx, mock_client, mock_run):
        mock_client.get = AsyncMock(return_value={
            "comfyui-impact-pack": {
                "ver": "8.28.2",
                "cnr_id": "comfyui-impact-pack",
                "enabled": True,
            }
        })
        parsed = json.loads(await comfy_list_installed_nodes(ctx=mock_ctx))
        assert parsed["source"] == "manager_v2"
        assert parsed["packages"][0]["version"] == "8.28.2"
        mock_run.assert_not_called()

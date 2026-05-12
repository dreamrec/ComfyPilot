"""Tests for the comfy-cli subprocess wrapper."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comfy_mcp.cli.comfy_cli import (
    ComfyCliError,
    ComfyCliResult,
    detect_comfy_cli,
    run_comfy_cli,
)


class TestDetectComfyCli:
    def test_returns_path_when_on_path(self):
        with patch("shutil.which", return_value="/usr/local/bin/comfy"):
            assert detect_comfy_cli() == "/usr/local/bin/comfy"

    def test_returns_none_when_missing(self):
        with patch("shutil.which", return_value=None):
            assert detect_comfy_cli() is None

    def test_falls_back_to_alternate_names(self):
        def which(name):
            return "/path/to/comfy-cli" if name == "comfy-cli" else None
        with patch("shutil.which", side_effect=which):
            assert detect_comfy_cli() == "/path/to/comfy-cli"


class TestRunComfyCli:
    @pytest.mark.asyncio
    async def test_missing_binary_raises(self):
        with patch("comfy_mcp.cli.comfy_cli.detect_comfy_cli", return_value=None):
            with pytest.raises(ComfyCliError) as exc_info:
                await run_comfy_cli(["--version"])
            assert "not on PATH" in str(exc_info.value)
            assert "pipx install" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_successful_run_returns_result(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"comfy v1.0.0\n", b""))
        mock_proc.kill = MagicMock()
        with patch("comfy_mcp.cli.comfy_cli.detect_comfy_cli", return_value="/bin/comfy"), \
             patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
            result = await run_comfy_cli(["--version"])
            assert isinstance(result, ComfyCliResult)
            assert result.ok is True
            assert result.returncode == 0
            assert "comfy v1.0.0" in result.stdout

    @pytest.mark.asyncio
    async def test_non_zero_returncode_does_not_raise(self):
        """A non-zero exit is just returned; the caller decides how to react."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"node not found\n"))
        mock_proc.kill = MagicMock()
        with patch("comfy_mcp.cli.comfy_cli.detect_comfy_cli", return_value="/bin/comfy"), \
             patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
            result = await run_comfy_cli(["node", "install", "missing-package"])
            assert result.ok is False
            assert result.returncode == 1
            assert "node not found" in result.stderr

    @pytest.mark.asyncio
    async def test_timeout_kills_process_and_raises(self):
        async def slow_communicate():
            await asyncio.sleep(10)
            return (b"", b"")
        mock_proc = MagicMock()
        mock_proc.communicate = slow_communicate
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()
        with patch("comfy_mcp.cli.comfy_cli.detect_comfy_cli", return_value="/bin/comfy"), \
             patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
            with pytest.raises(ComfyCliError) as exc_info:
                await run_comfy_cli(["launch"], timeout=0.05)
            assert "timed out" in str(exc_info.value)
            mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_prompt_default_on(self):
        captured = {}

        async def fake_exec(*args, **kwargs):
            captured["args"] = args
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            return mock_proc

        with patch("comfy_mcp.cli.comfy_cli.detect_comfy_cli", return_value="/bin/comfy"), \
             patch("asyncio.create_subprocess_exec", fake_exec):
            await run_comfy_cli(["node", "show", "installed"])
            assert "--skip-prompt" in captured["args"]

    @pytest.mark.asyncio
    async def test_workspace_prefix_inserted(self):
        captured = {}

        async def fake_exec(*args, **kwargs):
            captured["args"] = args
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            return mock_proc

        with patch("comfy_mcp.cli.comfy_cli.detect_comfy_cli", return_value="/bin/comfy"), \
             patch("asyncio.create_subprocess_exec", fake_exec):
            await run_comfy_cli(["launch"], workspace="/data/comfy")
            assert "--workspace" in captured["args"]
            assert "/data/comfy" in captured["args"]

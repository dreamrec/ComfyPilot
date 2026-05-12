"""Tests for comfy_install_workflow_deps."""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from comfy_mcp.cli.comfy_cli import ComfyCliError, ComfyCliResult
from comfy_mcp.tools.auto_fix_deps import comfy_install_workflow_deps


def _ok_result(stdout: str = "") -> ComfyCliResult:
    return ComfyCliResult(returncode=0, stdout=stdout, stderr="", argv=("/bin/comfy",))


@pytest.mark.asyncio
async def test_rejects_empty_workflow():
    result = await comfy_install_workflow_deps(workflow={})
    parsed = json.loads(result)
    assert "error" in parsed


@pytest.mark.asyncio
async def test_rejects_editor_format():
    editor = {"nodes": [{"id": 1}], "links": []}
    result = await comfy_install_workflow_deps(workflow=editor)
    parsed = json.loads(result)
    assert "error" in parsed
    assert "editor format" in parsed["error"].lower()


@pytest.mark.asyncio
async def test_calls_install_deps_with_temp_file():
    captured = {}

    async def fake_run(args, **kw):
        captured["args"] = list(args)
        # Verify the workflow file exists at the path passed to comfy-cli
        workflow_arg = next((a for a in args if a.startswith("--workflow=")), None)
        assert workflow_arg is not None
        path = workflow_arg.split("=", 1)[1]
        captured["tmp_path"] = path
        captured["file_exists_during_call"] = os.path.exists(path)
        # Verify it contains valid JSON of our workflow
        with open(path) as f:
            captured["written_content"] = json.load(f)
        return _ok_result(stdout="installed 2 packages")

    workflow = {"1": {"class_type": "CustomNodeX", "inputs": {}}}
    with patch("comfy_mcp.tools.auto_fix_deps.run_comfy_cli", side_effect=fake_run):
        result = await comfy_install_workflow_deps(workflow=workflow)

    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert captured["file_exists_during_call"] is True
    assert captured["written_content"] == workflow
    # Temp file cleaned up afterward
    assert not os.path.exists(captured["tmp_path"])
    # Right CLI argv
    assert "node" in captured["args"]
    assert "install-deps" in captured["args"]


@pytest.mark.asyncio
async def test_cli_missing_returns_error():
    workflow = {"1": {"class_type": "X", "inputs": {}}}
    with patch(
        "comfy_mcp.tools.auto_fix_deps.run_comfy_cli",
        side_effect=ComfyCliError("not on PATH"),
    ):
        result = await comfy_install_workflow_deps(workflow=workflow)
    parsed = json.loads(result)
    assert "error" in parsed
    assert "not on PATH" in parsed["error"]


@pytest.mark.asyncio
async def test_cli_non_zero_returncode_is_failed():
    workflow = {"1": {"class_type": "X", "inputs": {}}}

    async def fake_run(args, **kw):
        return ComfyCliResult(returncode=2, stdout="", stderr="install error", argv=("/bin/comfy",))

    with patch("comfy_mcp.tools.auto_fix_deps.run_comfy_cli", side_effect=fake_run):
        result = await comfy_install_workflow_deps(workflow=workflow)
    parsed = json.loads(result)
    assert parsed["status"] == "failed"
    assert parsed["comfy_cli_returncode"] == 2


@pytest.mark.asyncio
async def test_temp_file_cleaned_up_after_error():
    """Even if comfy-cli throws, the temp workflow file should be removed."""
    workflow = {"1": {"class_type": "X", "inputs": {}}}
    captured = {}

    async def fake_run(args, **kw):
        workflow_arg = next((a for a in args if a.startswith("--workflow=")), None)
        captured["tmp_path"] = workflow_arg.split("=", 1)[1]
        raise ComfyCliError("kaboom")

    with patch("comfy_mcp.tools.auto_fix_deps.run_comfy_cli", side_effect=fake_run):
        await comfy_install_workflow_deps(workflow=workflow)
    assert not os.path.exists(captured["tmp_path"])

"""Regression guard: path-traversal attempts in workflow-supplied filenames.

A malicious workflow with a custom save node can return a filename like
`../../etc/passwd.png` from /history. Our output-routing tools must refuse
to write outside the configured output directory regardless of what the
server (or agent) sends.

Our protection lives in `_validate_filename` + `_prepare_destination_path`.
This file locks the contract.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.tools.output_routing import (
    _prepare_destination_path,
    _validate_filename,
    comfy_send_to_blender,
    comfy_send_to_disk,
    comfy_send_to_td,
)


def _ctx(tmp_path, get_image_returns=b"fake-png-bytes"):
    """Build a Context whose mock client returns fake bytes for get_image."""
    client = MagicMock()
    client.get_image = AsyncMock(return_value=get_image_returns)
    client.get_history = AsyncMock(return_value={})
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"comfy_client": client}
    return ctx


class TestValidateFilename:
    @pytest.mark.parametrize("malicious", [
        "../etc/passwd.png",
        "../../etc/passwd.png",
        "..\\..\\windows\\system32\\evil.png",  # Windows separators
        "/etc/passwd.png",  # POSIX absolute
        "C:\\windows\\system32\\evil.png",  # Windows absolute
        "..",
        ".",
        "",
        "foo/bar.png",  # forward-slash subdir
        "foo\\bar.png",  # backslash subdir
    ])
    def test_blocks_traversal_attempts(self, malicious):
        with pytest.raises(ValueError):
            _validate_filename(malicious)

    @pytest.mark.parametrize("safe", [
        "image.png",
        "ComfyUI_00001_.png",
        "output_with_dots.123.png",
        "name with spaces.webp",
        "image-with-hyphens.jpg",
    ])
    def test_allows_simple_filenames(self, safe):
        assert _validate_filename(safe) == safe


class TestPrepareDestinationPath:
    def test_constructs_path_under_dest_dir(self, tmp_path):
        result = _prepare_destination_path(tmp_path, "image.png")
        assert result == tmp_path / "image.png"
        assert result.is_absolute() == tmp_path.is_absolute()
        assert tmp_path in result.parents

    def test_creates_dest_dir_if_missing(self, tmp_path):
        new_dir = tmp_path / "nested" / "outputs"
        result = _prepare_destination_path(new_dir, "image.png")
        assert new_dir.exists()
        assert result == new_dir / "image.png"

    @pytest.mark.parametrize("malicious", ["../escaped.png", "../../escaped.png", "/abs.png"])
    def test_refuses_traversal(self, tmp_path, malicious):
        with pytest.raises(ValueError):
            _prepare_destination_path(tmp_path, malicious)


class TestRoutingToolsHonorValidation:
    @pytest.mark.asyncio
    async def test_send_to_disk_refuses_traversal_filename(self, tmp_path, monkeypatch):
        """A workflow that returns '../../etc/passwd.png' in /history must be refused."""
        monkeypatch.setenv("COMFY_OUTPUT_DIR", str(tmp_path))
        result = await comfy_send_to_disk(
            filename="../../etc/passwd.png",
            ctx=_ctx(tmp_path),
        )
        parsed = json.loads(result)
        assert "error" in parsed
        assert "filename" in parsed
        # Verify nothing was actually written under tmp_path
        assert not any(p.name == "passwd.png" for p in tmp_path.iterdir())

    @pytest.mark.asyncio
    async def test_send_to_td_refuses_traversal(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COMFY_TD_OUTPUT_DIR", str(tmp_path))
        result = await comfy_send_to_td(
            filename="/etc/passwd.png",
            ctx=_ctx(tmp_path),
        )
        parsed = json.loads(result)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_send_to_blender_refuses_traversal(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COMFY_BLENDER_OUTPUT_DIR", str(tmp_path))
        result = await comfy_send_to_blender(
            filename="..\\..\\evil.png",
            ctx=_ctx(tmp_path),
        )
        parsed = json.loads(result)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_send_to_disk_safe_filename_succeeds(self, tmp_path, monkeypatch):
        """Sanity check: a legit filename does write to the configured dir."""
        monkeypatch.setenv("COMFY_OUTPUT_DIR", str(tmp_path))
        result = await comfy_send_to_disk(
            filename="legit_output.png",
            ctx=_ctx(tmp_path),
        )
        parsed = json.loads(result)
        assert parsed["status"] == "saved"
        # File must be inside tmp_path
        written = tmp_path / "legit_output.png"
        assert written.exists()
        assert written.read_bytes() == b"fake-png-bytes"

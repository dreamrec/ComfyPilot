"""Tests for security hardening done in Phases 1-2."""

from __future__ import annotations

import base64
import json

import pytest


class TestSafeFilenamePathTraversal:
    """Test _safe_filename rejects path traversal and unsafe names."""

    def test_strips_parent_traversal(self):
        """Path traversal components are stripped — only the leaf name survives."""
        from comfy_mcp.tools.output_routing import _safe_filename

        # ../etc/passwd -> Path.name gives "passwd", which is safe
        assert _safe_filename("../etc/passwd") == "passwd"

    def test_strips_double_traversal(self):
        """Multiple ../ segments are stripped — only the leaf name survives."""
        from comfy_mcp.tools.output_routing import _safe_filename

        assert _safe_filename("../../foo.png") == "foo.png"

    def test_rejects_only_traversal_no_leaf(self):
        """If after stripping there is no valid leaf, it must raise."""
        from comfy_mcp.tools.output_routing import _safe_filename

        with pytest.raises(ValueError, match="Unsafe filename"):
            _safe_filename("../")

    def test_rejects_slash_only(self):
        from comfy_mcp.tools.output_routing import _safe_filename

        with pytest.raises(ValueError, match="Unsafe filename"):
            _safe_filename("/")

    def test_rejects_hidden_dotfile(self):
        from comfy_mcp.tools.output_routing import _safe_filename

        with pytest.raises(ValueError, match="Unsafe filename"):
            _safe_filename(".hidden")

    def test_rejects_empty_string(self):
        from comfy_mcp.tools.output_routing import _safe_filename

        with pytest.raises(ValueError, match="Unsafe filename"):
            _safe_filename("")

    def test_rejects_bare_dotdot(self):
        from comfy_mcp.tools.output_routing import _safe_filename

        with pytest.raises(ValueError, match="Unsafe filename"):
            _safe_filename("..")

    def test_accepts_simple_png(self):
        from comfy_mcp.tools.output_routing import _safe_filename

        assert _safe_filename("image.png") == "image.png"

    def test_accepts_comfyui_output_name(self):
        from comfy_mcp.tools.output_routing import _safe_filename

        assert _safe_filename("ComfyUI_00001_.png") == "ComfyUI_00001_.png"


class TestCommandInjectionPrevention:
    """Verify td_command and blender_command use repr() to escape paths."""

    @pytest.mark.asyncio
    async def test_td_command_escapes_quotes_in_path(self, mock_ctx, mock_client, tmp_path, monkeypatch):
        """Paths with quotes must be escaped via repr(), not string concat."""
        fake_png = b"\x89PNG" + b"\x00" * 20
        mock_client.get_image = AsyncMock(return_value=fake_png)

        td_dir = tmp_path / "td_out"
        monkeypatch.setenv("COMFY_TD_OUTPUT_DIR", str(td_dir))

        from comfy_mcp.tools.output_routing import comfy_send_to_td

        result = json.loads(await comfy_send_to_td("normal.png", ctx=mock_ctx))

        # The td_command must use repr() so the path is a proper Python string literal
        td_cmd = result["td_command"]
        expected_path = str(td_dir / "normal.png")
        assert repr(expected_path) in td_cmd, "td_command must embed path via repr()"

    @pytest.mark.asyncio
    async def test_blender_command_escapes_quotes_in_path(self, mock_ctx, mock_client, tmp_path, monkeypatch):
        """Paths with quotes must be escaped via repr(), not string concat."""
        fake_png = b"\x89PNG" + b"\x00" * 20
        mock_client.get_image = AsyncMock(return_value=fake_png)

        blender_dir = tmp_path / "blender_out"
        monkeypatch.setenv("COMFY_BLENDER_OUTPUT_DIR", str(blender_dir))

        from comfy_mcp.tools.output_routing import comfy_send_to_blender

        result = json.loads(await comfy_send_to_blender("normal.png", ctx=mock_ctx))

        blender_cmd = result["blender_command"]
        expected_path = str(blender_dir / "normal.png")
        assert repr(expected_path) in blender_cmd, "blender_command must embed path via repr()"

    @pytest.mark.asyncio
    async def test_td_command_with_special_chars_dir(self, mock_ctx, mock_client, tmp_path, monkeypatch):
        """A directory name with special chars should be safely escaped."""
        fake_png = b"\x89PNG" + b"\x00" * 10
        mock_client.get_image = AsyncMock(return_value=fake_png)

        # Use a path with a single-quote to verify repr-based escaping
        td_dir = tmp_path / "it's a dir"
        monkeypatch.setenv("COMFY_TD_OUTPUT_DIR", str(td_dir))

        from comfy_mcp.tools.output_routing import comfy_send_to_td

        result = json.loads(await comfy_send_to_td("file.png", ctx=mock_ctx))

        td_cmd = result["td_command"]
        # repr() will backslash-escape or use alternate quoting for the quote char
        expected_path = str(td_dir / "file.png")
        assert repr(expected_path) in td_cmd


class TestSetLimitsInputValidation:
    """Test comfy_set_limits rejects out-of-range values."""

    @pytest.mark.asyncio
    async def test_warn_pct_above_100(self, mock_ctx):
        from comfy_mcp.tools.safety import comfy_set_limits

        result = json.loads(await comfy_set_limits(warn_pct=101.0, ctx=mock_ctx))
        assert "error" in result
        assert "warn_pct" in result["error"]

    @pytest.mark.asyncio
    async def test_block_pct_below_zero(self, mock_ctx):
        from comfy_mcp.tools.safety import comfy_set_limits

        result = json.loads(await comfy_set_limits(block_pct=-1.0, ctx=mock_ctx))
        assert "error" in result
        assert "block_pct" in result["error"]

    @pytest.mark.asyncio
    async def test_max_queue_below_one(self, mock_ctx):
        from comfy_mcp.tools.safety import comfy_set_limits

        result = json.loads(await comfy_set_limits(max_queue=0, ctx=mock_ctx))
        assert "error" in result
        assert "max_queue" in result["error"]

    @pytest.mark.asyncio
    async def test_timeout_below_one(self, mock_ctx):
        from comfy_mcp.tools.safety import comfy_set_limits

        result = json.loads(await comfy_set_limits(timeout=0, ctx=mock_ctx))
        assert "error" in result
        assert "timeout" in result["error"]

    @pytest.mark.asyncio
    async def test_valid_values_accepted(self, mock_ctx):
        from comfy_mcp.tools.safety import comfy_set_limits

        # Configure the vram_guard mock to return a serializable dict
        guard = mock_ctx.request_context.lifespan_context["vram_guard"]
        guard.set_limits.return_value = {"warn_pct": 80.0, "block_pct": 95.0}

        result = json.loads(await comfy_set_limits(warn_pct=80.0, ctx=mock_ctx))
        # A valid call should NOT return an error
        assert "error" not in result


class TestConfigKeyWhitelisting:
    """Test that comfy_set_config rejects unknown keys and accepts known ones."""

    @pytest.mark.asyncio
    async def test_unknown_key_rejected(self, mock_ctx):
        from comfy_mcp.tools.knowledge import comfy_set_config

        result = json.loads(await comfy_set_config(
            key="malicious.key", value="evil", ctx=mock_ctx
        ))
        assert "error" in result
        assert "Unknown config key" in result["error"]
        assert "allowed_keys" in result

    @pytest.mark.asyncio
    async def test_known_key_accepted(self, mock_ctx):
        from comfy_mcp.tools.knowledge import comfy_set_config

        result = json.loads(await comfy_set_config(
            key="safety.vram_warn_pct", value=85.0, ctx=mock_ctx
        ))
        assert result["status"] == "ok"
        assert result["key"] == "safety.vram_warn_pct"
        assert result["value"] == 85.0

    @pytest.mark.asyncio
    async def test_each_allowed_key_accepted(self, mock_ctx):
        from comfy_mcp.tools.knowledge import comfy_set_config

        allowed = [
            "safety.vram_warn_pct", "safety.vram_block_pct", "safety.max_queue",
            "cache.ttl", "output.default_dir",
        ]
        for key in allowed:
            result = json.loads(await comfy_set_config(
                key=key, value="test_value", ctx=mock_ctx
            ))
            assert result["status"] == "ok", f"Key {key!r} should be allowed"


class TestUploadSizeLimit:
    """Test that comfy_upload_image rejects oversized base64 payloads."""

    @pytest.mark.asyncio
    async def test_oversized_upload_rejected(self, mock_ctx):
        from comfy_mcp.tools.images import comfy_upload_image

        # 50 MB limit => base64 threshold is 50*1024*1024 * 4 // 3
        # Create data that exceeds the limit
        max_bytes = 50 * 1024 * 1024
        oversized_b64 = "A" * (max_bytes * 4 // 3 + 1)

        result = json.loads(await comfy_upload_image(
            image_data=oversized_b64, filename="huge.png", ctx=mock_ctx
        ))
        assert "error" in result
        assert "too large" in result["error"].lower() or "Maximum" in result["error"]

    @pytest.mark.asyncio
    async def test_small_upload_accepted(self, mock_ctx, mock_client):
        from comfy_mcp.tools.images import comfy_upload_image

        small_data = base64.b64encode(b"\x89PNG" + b"\x00" * 100).decode()
        mock_client.upload_image = AsyncMock(return_value={"name": "small.png"})

        result = json.loads(await comfy_upload_image(
            image_data=small_data, filename="small.png", ctx=mock_ctx
        ))
        assert "error" not in result


# Import AsyncMock at module level for use in test methods
from unittest.mock import AsyncMock

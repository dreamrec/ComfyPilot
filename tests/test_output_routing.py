"""Tests for output routing tools."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


class TestSendToDisk:
    @pytest.mark.asyncio
    async def test_saves_file_to_default_dir(self, mock_ctx, mock_client, tmp_path, monkeypatch):
        """Test that file is saved to default directory when no output_dir given."""
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_client.get_image = AsyncMock(return_value=fake_png)

        from comfy_mcp.tools.output_routing import comfy_send_to_disk

        result = json.loads(
            await comfy_send_to_disk("test.png", output_dir=str(tmp_path), ctx=mock_ctx)
        )

        assert result["status"] == "saved"
        assert result["size_bytes"] == len(fake_png)
        assert (tmp_path / "test.png").exists()
        assert (tmp_path / "test.png").read_bytes() == fake_png

    @pytest.mark.asyncio
    async def test_saves_with_custom_output_dir(self, mock_ctx, mock_client, tmp_path):
        """Test that custom output_dir parameter is respected."""
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\xAA" * 50
        mock_client.get_image = AsyncMock(return_value=fake_png)

        from comfy_mcp.tools.output_routing import comfy_send_to_disk

        custom_dir = tmp_path / "custom_output"
        result = json.loads(
            await comfy_send_to_disk(
                "custom.png", output_dir=str(custom_dir), ctx=mock_ctx
            )
        )

        assert result["status"] == "saved"
        assert custom_dir.exists()
        assert (custom_dir / "custom.png").exists()

    @pytest.mark.asyncio
    async def test_respects_env_var_comfy_output_dir(self, mock_ctx, mock_client, tmp_path, monkeypatch):
        """Test that COMFY_OUTPUT_DIR env var is used when no output_dir parameter."""
        fake_png = b"\x89PNG" + b"\xFF" * 30
        mock_client.get_image = AsyncMock(return_value=fake_png)

        env_dir = tmp_path / "env_output"
        monkeypatch.setenv("COMFY_OUTPUT_DIR", str(env_dir))

        from comfy_mcp.tools.output_routing import comfy_send_to_disk

        result = json.loads(
            await comfy_send_to_disk("envtest.png", ctx=mock_ctx)
        )

        assert result["status"] == "saved"
        assert env_dir.exists()
        assert (env_dir / "envtest.png").exists()

    @pytest.mark.asyncio
    async def test_file_contents_match(self, mock_ctx, mock_client, tmp_path):
        """Test that saved file contents match the downloaded image bytes."""
        expected_bytes = b"PNG_HEADER" + b"\xAB\xCD\xEF" * 100
        mock_client.get_image = AsyncMock(return_value=expected_bytes)

        from comfy_mcp.tools.output_routing import comfy_send_to_disk

        await comfy_send_to_disk("match.png", output_dir=str(tmp_path), ctx=mock_ctx)

        saved_bytes = (tmp_path / "match.png").read_bytes()
        assert saved_bytes == expected_bytes

    @pytest.mark.asyncio
    async def test_with_subfolder(self, mock_ctx, mock_client, tmp_path):
        """Test that subfolder parameter is passed to get_image."""
        fake_png = b"\x89PNG" + b"x" * 50
        mock_client.get_image = AsyncMock(return_value=fake_png)

        from comfy_mcp.tools.output_routing import comfy_send_to_disk

        result = json.loads(
            await comfy_send_to_disk(
                "subfolder_test.png", subfolder="mysubfolder", output_dir=str(tmp_path), ctx=mock_ctx
            )
        )

        assert result["status"] == "saved"
        mock_client.get_image.assert_called_once_with("subfolder_test.png", subfolder="mysubfolder")
        assert (tmp_path / "subfolder_test.png").exists()

    @pytest.mark.asyncio
    async def test_rejects_path_traversal_filename(self, mock_ctx, mock_client, tmp_path):
        mock_client.get_image = AsyncMock(return_value=b"data")

        from comfy_mcp.tools.output_routing import comfy_send_to_disk

        result = json.loads(
            await comfy_send_to_disk("../escape.png", output_dir=str(tmp_path), ctx=mock_ctx)
        )

        assert "error" in result
        mock_client.get_image.assert_not_awaited()


class TestSendToTouchDesigner:
    @pytest.mark.asyncio
    async def test_saves_and_returns_td_command(self, mock_ctx, mock_client, tmp_path, monkeypatch):
        """Test that file is saved and td_command is returned."""
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_client.get_image = AsyncMock(return_value=fake_png)

        td_dir = tmp_path / "td_output"
        monkeypatch.setenv("COMFY_TD_OUTPUT_DIR", str(td_dir))

        from comfy_mcp.tools.output_routing import comfy_send_to_td

        result = json.loads(await comfy_send_to_td("td_test.png", ctx=mock_ctx))

        assert result["status"] == "saved"
        assert result["size_bytes"] == len(fake_png)
        assert "td_command" in result
        assert "moviefilein1" in result["td_command"]
        assert str(td_dir / "td_test.png") in result["td_command"]
        assert td_dir.exists()
        assert (td_dir / "td_test.png").exists()

    @pytest.mark.asyncio
    async def test_default_td_output_dir_when_env_not_set(self, mock_ctx, mock_client, monkeypatch):
        """Test that default TD output dir is used when env var not set."""
        fake_png = b"\x89PNG" + b"x" * 50
        mock_client.get_image = AsyncMock(return_value=fake_png)

        # Ensure env var is not set
        monkeypatch.delenv("COMFY_TD_OUTPUT_DIR", raising=False)

        from comfy_mcp.tools.output_routing import comfy_send_to_td

        result = json.loads(await comfy_send_to_td("default_td.png", ctx=mock_ctx))

        assert result["status"] == "saved"
        assert "comfypilot_output/touchdesigner" in result["path"]

    @pytest.mark.asyncio
    async def test_td_command_includes_path(self, mock_ctx, mock_client, tmp_path, monkeypatch):
        """Test that td_command includes the full path to the saved file."""
        fake_png = b"\x89PNG" + b"y" * 30
        mock_client.get_image = AsyncMock(return_value=fake_png)

        td_dir = tmp_path / "td"
        monkeypatch.setenv("COMFY_TD_OUTPUT_DIR", str(td_dir))

        from comfy_mcp.tools.output_routing import comfy_send_to_td

        result = json.loads(await comfy_send_to_td("image.png", ctx=mock_ctx))

        assert f"{td_dir / 'image.png'}" in result["td_command"]

    @pytest.mark.asyncio
    async def test_suggestion_field_present(self, mock_ctx, mock_client, tmp_path, monkeypatch):
        """Test that suggestion field is present in result."""
        fake_png = b"\x89PNG" + b"z" * 20
        mock_client.get_image = AsyncMock(return_value=fake_png)

        td_dir = tmp_path / "td"
        monkeypatch.setenv("COMFY_TD_OUTPUT_DIR", str(td_dir))

        from comfy_mcp.tools.output_routing import comfy_send_to_td

        result = json.loads(await comfy_send_to_td("test.png", ctx=mock_ctx))

        assert "suggestion" in result
        assert "td_exec_python" in result["suggestion"]

    @pytest.mark.asyncio
    async def test_td_command_escapes_quotes_in_path(self, mock_ctx, mock_client, tmp_path, monkeypatch):
        fake_png = b"\x89PNG" + b"q" * 20
        mock_client.get_image = AsyncMock(return_value=fake_png)

        td_dir = tmp_path / "td"
        monkeypatch.setenv("COMFY_TD_OUTPUT_DIR", str(td_dir))

        from comfy_mcp.tools.output_routing import comfy_send_to_td

        result = json.loads(await comfy_send_to_td("bad'name.png", ctx=mock_ctx))
        expected_path = str(td_dir / "bad'name.png")

        assert result["td_command"] == f"op('moviefilein1').par.file = {expected_path!r}"


class TestSendToBlender:
    @pytest.mark.asyncio
    async def test_saves_and_returns_blender_command(self, mock_ctx, mock_client, tmp_path, monkeypatch):
        """Test that file is saved and blender_command is returned."""
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_client.get_image = AsyncMock(return_value=fake_png)

        blender_dir = tmp_path / "blender_output"
        monkeypatch.setenv("COMFY_BLENDER_OUTPUT_DIR", str(blender_dir))

        from comfy_mcp.tools.output_routing import comfy_send_to_blender

        result = json.loads(await comfy_send_to_blender("blender_test.png", ctx=mock_ctx))

        assert result["status"] == "saved"
        assert result["size_bytes"] == len(fake_png)
        assert "blender_command" in result
        assert "bpy.data.images.load" in result["blender_command"]
        assert str(blender_dir / "blender_test.png") in result["blender_command"]
        assert blender_dir.exists()
        assert (blender_dir / "blender_test.png").exists()

    @pytest.mark.asyncio
    async def test_default_blender_output_dir_when_env_not_set(self, mock_ctx, mock_client, monkeypatch):
        """Test that default Blender output dir is used when env var not set."""
        fake_png = b"\x89PNG" + b"b" * 40
        mock_client.get_image = AsyncMock(return_value=fake_png)

        # Ensure env var is not set
        monkeypatch.delenv("COMFY_BLENDER_OUTPUT_DIR", raising=False)

        from comfy_mcp.tools.output_routing import comfy_send_to_blender

        result = json.loads(await comfy_send_to_blender("default_blender.png", ctx=mock_ctx))

        assert result["status"] == "saved"
        assert "comfypilot_output/blender" in result["path"]

    @pytest.mark.asyncio
    async def test_blender_command_format(self, mock_ctx, mock_client, tmp_path, monkeypatch):
        """Test that blender_command has correct format."""
        fake_png = b"\x89PNG" + b"c" * 25
        mock_client.get_image = AsyncMock(return_value=fake_png)

        blender_dir = tmp_path / "blender"
        monkeypatch.setenv("COMFY_BLENDER_OUTPUT_DIR", str(blender_dir))

        from comfy_mcp.tools.output_routing import comfy_send_to_blender

        result = json.loads(await comfy_send_to_blender("render.png", ctx=mock_ctx))

        assert result["blender_command"].startswith("bpy.data.images.load('")
        assert result["blender_command"].endswith("')")

    @pytest.mark.asyncio
    async def test_with_subfolder(self, mock_ctx, mock_client, tmp_path, monkeypatch):
        """Test that subfolder parameter is passed to get_image."""
        fake_png = b"\x89PNG" + b"d" * 30
        mock_client.get_image = AsyncMock(return_value=fake_png)

        blender_dir = tmp_path / "blender"
        monkeypatch.setenv("COMFY_BLENDER_OUTPUT_DIR", str(blender_dir))

        from comfy_mcp.tools.output_routing import comfy_send_to_blender

        result = json.loads(
            await comfy_send_to_blender(
                "subfolder_blender.png", subfolder="renders", ctx=mock_ctx
            )
        )

        assert result["status"] == "saved"
        mock_client.get_image.assert_called_once_with("subfolder_blender.png", subfolder="renders")

    @pytest.mark.asyncio
    async def test_rejects_absolute_path_filename(self, mock_ctx, mock_client, tmp_path, monkeypatch):
        mock_client.get_image = AsyncMock(return_value=b"data")

        blender_dir = tmp_path / "blender"
        monkeypatch.setenv("COMFY_BLENDER_OUTPUT_DIR", str(blender_dir))

        from comfy_mcp.tools.output_routing import comfy_send_to_blender

        result = json.loads(await comfy_send_to_blender("/tmp/owned.png", ctx=mock_ctx))

        assert "error" in result
        mock_client.get_image.assert_not_awaited()


class TestListDestinations:
    @pytest.mark.asyncio
    async def test_returns_all_destinations(self, mock_ctx):
        """Test that all three destinations are listed."""
        from comfy_mcp.tools.output_routing import comfy_list_destinations

        result = json.loads(await comfy_list_destinations(ctx=mock_ctx))

        assert "destinations" in result
        assert "disk" in result["destinations"]
        assert "touchdesigner" in result["destinations"]
        assert "blender" in result["destinations"]

    @pytest.mark.asyncio
    async def test_each_destination_has_path_and_configured(self, mock_ctx):
        """Test that each destination has 'path' and 'configured' fields."""
        from comfy_mcp.tools.output_routing import comfy_list_destinations

        result = json.loads(await comfy_list_destinations(ctx=mock_ctx))
        destinations = result["destinations"]

        for dest_name, dest_info in destinations.items():
            assert "path" in dest_info, f"{dest_name} missing 'path'"
            assert "configured" in dest_info, f"{dest_name} missing 'configured'"
            assert isinstance(dest_info["path"], str)
            assert isinstance(dest_info["configured"], bool)

    @pytest.mark.asyncio
    async def test_configured_true_when_env_var_set(self, mock_ctx, monkeypatch):
        """Test that 'configured' is True when env var is set."""
        monkeypatch.setenv("COMFY_OUTPUT_DIR", "/custom/output")

        from comfy_mcp.tools.output_routing import comfy_list_destinations

        result = json.loads(await comfy_list_destinations(ctx=mock_ctx))

        assert result["destinations"]["disk"]["configured"] is True
        assert result["destinations"]["disk"]["path"] == "/custom/output"

    @pytest.mark.asyncio
    async def test_configured_false_when_env_var_not_set(self, mock_ctx, monkeypatch):
        """Test that 'configured' is False when env var is not set."""
        monkeypatch.delenv("COMFY_OUTPUT_DIR", raising=False)
        monkeypatch.delenv("COMFY_TD_OUTPUT_DIR", raising=False)
        monkeypatch.delenv("COMFY_BLENDER_OUTPUT_DIR", raising=False)

        from comfy_mcp.tools.output_routing import comfy_list_destinations

        result = json.loads(await comfy_list_destinations(ctx=mock_ctx))

        assert result["destinations"]["disk"]["configured"] is False
        assert result["destinations"]["touchdesigner"]["configured"] is False
        assert result["destinations"]["blender"]["configured"] is False

    @pytest.mark.asyncio
    async def test_default_paths_present(self, mock_ctx, monkeypatch):
        """Test that default paths are included even when env vars not set."""
        monkeypatch.delenv("COMFY_OUTPUT_DIR", raising=False)
        monkeypatch.delenv("COMFY_TD_OUTPUT_DIR", raising=False)
        monkeypatch.delenv("COMFY_BLENDER_OUTPUT_DIR", raising=False)

        from comfy_mcp.tools.output_routing import comfy_list_destinations

        result = json.loads(await comfy_list_destinations(ctx=mock_ctx))

        disk_path = result["destinations"]["disk"]["path"]
        td_path = result["destinations"]["touchdesigner"]["path"]
        blender_path = result["destinations"]["blender"]["path"]

        assert "comfypilot_output" in disk_path
        assert "comfypilot_output" in td_path
        assert "comfypilot_output" in blender_path
        assert "touchdesigner" in td_path
        assert "blender" in blender_path

    @pytest.mark.asyncio
    async def test_multiple_env_vars_configured(self, mock_ctx, monkeypatch):
        """Test correct configured state when multiple env vars are set."""
        monkeypatch.setenv("COMFY_TD_OUTPUT_DIR", "/custom/td")
        monkeypatch.setenv("COMFY_BLENDER_OUTPUT_DIR", "/custom/blender")
        monkeypatch.delenv("COMFY_OUTPUT_DIR", raising=False)

        from comfy_mcp.tools.output_routing import comfy_list_destinations

        result = json.loads(await comfy_list_destinations(ctx=mock_ctx))

        assert result["destinations"]["disk"]["configured"] is False
        assert result["destinations"]["touchdesigner"]["configured"] is True
        assert result["destinations"]["blender"]["configured"] is True

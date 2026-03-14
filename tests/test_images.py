"""Tests for image tools."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock

import pytest
from mcp.types import TextContent, ImageContent


class TestGetOutputImage:
    @pytest.mark.asyncio
    async def test_returns_image_content(self, mock_ctx, mock_client):
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_client.get_image = AsyncMock(return_value=fake_png)
        from comfy_mcp.tools.images import comfy_get_output_image
        result = await comfy_get_output_image(filename="test.png", ctx=mock_ctx)
        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], TextContent)
        assert isinstance(result[1], ImageContent)
        # Verify metadata
        meta = json.loads(result[0].text)
        assert meta["filename"] == "test.png"
        assert meta["size_bytes"] == len(fake_png)
        # Verify image data
        assert result[1].mimeType == "image/png"
        decoded = base64.b64decode(result[1].data)
        assert decoded == fake_png

    @pytest.mark.asyncio
    async def test_with_subfolder(self, mock_ctx, mock_client):
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        mock_client.get_image = AsyncMock(return_value=fake_png)
        from comfy_mcp.tools.images import comfy_get_output_image
        result = await comfy_get_output_image(filename="sub/image.png", subfolder="mysub", ctx=mock_ctx)
        mock_client.get_image.assert_called_once_with("sub/image.png", "mysub")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_size_bytes_correct(self, mock_ctx, mock_client):
        fake_data = b"A" * 2048
        mock_client.get_image = AsyncMock(return_value=fake_data)
        from comfy_mcp.tools.images import comfy_get_output_image
        result = await comfy_get_output_image(filename="big.png", ctx=mock_ctx)
        meta = json.loads(result[0].text)
        assert meta["size_bytes"] == 2048


class TestUploadImage:
    @pytest.mark.asyncio
    async def test_upload_basic(self, mock_ctx, mock_client):
        mock_client.upload_image = AsyncMock(return_value={"name": "uploaded.png", "subfolder": "", "type": "input"})
        fake_data = base64.b64encode(b"fake image data").decode()
        from comfy_mcp.tools.images import comfy_upload_image
        result = json.loads(await comfy_upload_image(image_data=fake_data, filename="test.png", ctx=mock_ctx))
        assert result["name"] == "uploaded.png"
        # Verify the client was called with decoded bytes
        mock_client.upload_image.assert_called_once()
        call_args = mock_client.upload_image.call_args
        assert call_args[0][0] == b"fake image data"  # first positional arg is bytes

    @pytest.mark.asyncio
    async def test_upload_with_subfolder_and_overwrite(self, mock_ctx, mock_client):
        mock_client.upload_image = AsyncMock(return_value={"name": "img.png", "subfolder": "mysub", "type": "input"})
        fake_data = base64.b64encode(b"data").decode()
        from comfy_mcp.tools.images import comfy_upload_image
        result = json.loads(await comfy_upload_image(
            image_data=fake_data,
            filename="img.png",
            subfolder="mysub",
            overwrite=True,
            ctx=mock_ctx,
        ))
        call_args = mock_client.upload_image.call_args
        assert call_args[1].get("overwrite") is True or call_args[0][3] is True

    @pytest.mark.asyncio
    async def test_decodes_base64(self, mock_ctx, mock_client):
        mock_client.upload_image = AsyncMock(return_value={})
        original = b"\x89PNG\r\n\x1a\n" + b"\xff" * 20
        fake_data = base64.b64encode(original).decode()
        from comfy_mcp.tools.images import comfy_upload_image
        await comfy_upload_image(image_data=fake_data, filename="test.png", ctx=mock_ctx)
        call_args = mock_client.upload_image.call_args
        assert call_args[0][0] == original


class TestListOutputImages:
    @pytest.mark.asyncio
    async def test_list_images_from_history(self, mock_ctx, mock_client):
        mock_client.get_history = AsyncMock(return_value={
            "abc123": {
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "ComfyUI_00001_.png", "subfolder": "", "type": "output"},
                            {"filename": "ComfyUI_00002_.png", "subfolder": "", "type": "output"},
                        ]
                    }
                }
            }
        })
        from comfy_mcp.tools.images import comfy_list_output_images
        result = json.loads(await comfy_list_output_images(ctx=mock_ctx))
        assert "images" in result
        filenames = [e["filename"] for e in result["images"]]
        assert "ComfyUI_00001_.png" in filenames
        assert "ComfyUI_00002_.png" in filenames
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_empty_history(self, mock_ctx, mock_client):
        mock_client.get_history = AsyncMock(return_value={})
        from comfy_mcp.tools.images import comfy_list_output_images
        result = json.loads(await comfy_list_output_images(ctx=mock_ctx))
        assert result["images"] == []
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_subfolder_filter(self, mock_ctx, mock_client):
        mock_client.get_history = AsyncMock(return_value={
            "abc": {
                "outputs": {
                    "1": {
                        "images": [
                            {"filename": "img1.png", "subfolder": "wanted", "type": "output"},
                            {"filename": "img2.png", "subfolder": "other", "type": "output"},
                        ]
                    }
                }
            }
        })
        from comfy_mcp.tools.images import comfy_list_output_images
        result = json.loads(await comfy_list_output_images(subfolder="wanted", ctx=mock_ctx))
        filenames = [e["filename"] for e in result["images"]]
        assert "img1.png" in filenames
        assert "img2.png" not in filenames

    @pytest.mark.asyncio
    async def test_limit_respected(self, mock_ctx, mock_client):
        images = [{"filename": f"img{i}.png", "subfolder": "", "type": "output"} for i in range(20)]
        mock_client.get_history = AsyncMock(return_value={
            "abc": {"outputs": {"1": {"images": images}}}
        })
        from comfy_mcp.tools.images import comfy_list_output_images
        result = json.loads(await comfy_list_output_images(limit=5, ctx=mock_ctx))
        assert result["count"] <= 5


class TestDownloadBatch:
    @pytest.mark.asyncio
    async def test_returns_metadata_only(self, mock_ctx, mock_client):
        fake_bytes = b"A" * 512
        mock_client.get_image = AsyncMock(return_value=fake_bytes)
        from comfy_mcp.tools.images import comfy_download_batch
        result = json.loads(await comfy_download_batch(
            filenames=["img1.png", "img2.png"],
            ctx=mock_ctx,
        ))
        assert result["count"] == 2
        assert result["images"][0]["filename"] == "img1.png"
        assert result["images"][0]["size_bytes"] == 512
        assert result["images"][1]["filename"] == "img2.png"
        # No raw image data in response
        for entry in result["images"]:
            assert "data" not in entry

    @pytest.mark.asyncio
    async def test_empty_list(self, mock_ctx, mock_client):
        from comfy_mcp.tools.images import comfy_download_batch
        result = json.loads(await comfy_download_batch(filenames=[], ctx=mock_ctx))
        assert result["count"] == 0
        assert result["images"] == []

    @pytest.mark.asyncio
    async def test_calls_get_image_per_file(self, mock_ctx, mock_client):
        mock_client.get_image = AsyncMock(return_value=b"x" * 10)
        from comfy_mcp.tools.images import comfy_download_batch
        await comfy_download_batch(filenames=["a.png", "b.png", "c.png"], ctx=mock_ctx)
        assert mock_client.get_image.call_count == 3


class TestGetImageUrl:
    @pytest.mark.asyncio
    async def test_constructs_url(self, mock_ctx, mock_client):
        from comfy_mcp.tools.images import comfy_get_image_url
        result = json.loads(await comfy_get_image_url(filename="test.png", ctx=mock_ctx))
        assert "url" in result
        assert "http://localhost:8188/view" in result["url"]
        assert "filename=test.png" in result["url"]
        assert "type=output" in result["url"]

    @pytest.mark.asyncio
    async def test_custom_type(self, mock_ctx, mock_client):
        from comfy_mcp.tools.images import comfy_get_image_url
        result = json.loads(await comfy_get_image_url(filename="tmp.png", image_type="temp", ctx=mock_ctx))
        assert "type=temp" in result["url"]

    @pytest.mark.asyncio
    async def test_subfolder_in_url(self, mock_ctx, mock_client):
        from comfy_mcp.tools.images import comfy_get_image_url
        result = json.loads(await comfy_get_image_url(
            filename="img.png", subfolder="mydir", ctx=mock_ctx
        ))
        assert "subfolder=mydir" in result["url"]

    @pytest.mark.asyncio
    async def test_filename_in_result(self, mock_ctx, mock_client):
        from comfy_mcp.tools.images import comfy_get_image_url
        result = json.loads(await comfy_get_image_url(filename="portrait.png", ctx=mock_ctx))
        assert result["filename"] == "portrait.png"
        assert result["type"] == "output"

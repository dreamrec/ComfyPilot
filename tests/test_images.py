"""Tests for image tools."""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlparse
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

    @pytest.mark.asyncio
    async def test_mime_type_is_inferred_from_filename(self, mock_ctx, mock_client):
        fake_jpeg = b"\xff\xd8\xff" + b"\x00" * 20
        mock_client.get_image = AsyncMock(return_value=fake_jpeg)
        from comfy_mcp.tools.images import comfy_get_output_image
        result = await comfy_get_output_image(filename="photo.jpg", ctx=mock_ctx)
        assert result[1].mimeType == "image/jpeg"


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
        assert "ComfyUI_00001_.png" in result["images"]
        assert "ComfyUI_00002_.png" in result["images"]
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
        assert "img1.png" in result["images"]
        assert "img2.png" not in result["images"]

    @pytest.mark.asyncio
    async def test_limit_respected(self, mock_ctx, mock_client):
        images = [{"filename": f"img{i}.png", "subfolder": "", "type": "output"} for i in range(20)]
        mock_client.get_history = AsyncMock(return_value={
            "abc": {"outputs": {"1": {"images": images}}}
        })
        from comfy_mcp.tools.images import comfy_list_output_images
        result = json.loads(await comfy_list_output_images(limit=5, ctx=mock_ctx))
        assert result["count"] <= 5

    @pytest.mark.asyncio
    async def test_empty_history_falls_back_to_local_output_directory(
        self, tmp_path, mock_ctx, mock_client
    ):
        (tmp_path / "kept.png").write_bytes(b"png")
        (tmp_path / "ignored.glb").write_bytes(b"mesh")
        mock_client.base_url = "http://127.0.0.1:8000"
        mock_client.get_history = AsyncMock(return_value={})
        mock_client.get_system_stats = AsyncMock(return_value={
            "system": {"argv": ["main.py", "--output-directory", str(tmp_path)]}
        })
        from comfy_mcp.tools.images import comfy_list_output_images
        result = json.loads(await comfy_list_output_images(ctx=mock_ctx))
        assert result["images"] == ["kept.png"]
        assert result["source"] == "history+filesystem"


class TestDownloadBatch:
    @pytest.mark.asyncio
    async def test_returns_metadata_only_no_network(self, mock_ctx, mock_client):
        """Default call must not hit get_image at all - it's pure metadata."""
        mock_client.get_image = AsyncMock()
        from comfy_mcp.tools.images import comfy_download_batch
        result = json.loads(await comfy_download_batch(
            filenames=["img1.png", "img2.png"],
            ctx=mock_ctx,
        ))
        assert result["count"] == 2
        mock_client.get_image.assert_not_awaited()
        # Metadata fields present
        for entry in result["images"]:
            assert "filename" in entry
            assert "url" in entry
            assert "/view?" in entry["url"]
            assert "data" not in entry
            assert "size_bytes" not in entry  # skipped without include_size

    @pytest.mark.asyncio
    async def test_include_size_opt_in_populates_size_bytes(self, mock_ctx, mock_client):
        fake_bytes = b"A" * 512
        mock_client.get_image = AsyncMock(return_value=fake_bytes)
        from comfy_mcp.tools.images import comfy_download_batch
        result = json.loads(await comfy_download_batch(
            filenames=["img1.png", "img2.png"],
            include_size=True,
            ctx=mock_ctx,
        ))
        assert result["images"][0]["size_bytes"] == 512
        assert result["images"][1]["size_bytes"] == 512
        assert mock_client.get_image.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_list(self, mock_ctx, mock_client):
        from comfy_mcp.tools.images import comfy_download_batch
        result = json.loads(await comfy_download_batch(filenames=[], ctx=mock_ctx))
        assert result["count"] == 0
        assert result["images"] == []

    @pytest.mark.asyncio
    async def test_include_size_error_does_not_abort_batch(self, mock_ctx, mock_client):
        """One failing image must not break the whole batch."""
        call = [0]
        async def flaky(*args, **kwargs):
            call[0] += 1
            if call[0] == 2:
                raise Exception("boom")
            return b"x" * 10
        mock_client.get_image = AsyncMock(side_effect=flaky)
        from comfy_mcp.tools.images import comfy_download_batch
        result = json.loads(await comfy_download_batch(
            filenames=["a.png", "b.png", "c.png"],
            include_size=True,
            ctx=mock_ctx,
        ))
        assert result["count"] == 3
        assert result["images"][0]["size_bytes"] == 10
        assert "size_error" in result["images"][1]
        assert result["images"][2]["size_bytes"] == 10


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

    @pytest.mark.asyncio
    async def test_query_values_are_url_encoded(self, mock_ctx, mock_client):
        from comfy_mcp.tools.images import comfy_get_image_url

        result = json.loads(
            await comfy_get_image_url(
                filename="img &=.png",
                subfolder="dir=a&b",
                image_type="temp",
                ctx=mock_ctx,
            )
        )
        query = parse_qs(urlparse(result["url"]).query, keep_blank_values=True)

        assert query["filename"] == ["img &=.png"]
        assert query["subfolder"] == ["dir=a&b"]
        assert query["type"] == ["temp"]

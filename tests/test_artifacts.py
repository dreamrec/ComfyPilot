from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock

import pytest

from comfy_mcp.tools.artifacts import comfy_get_artifact, comfy_list_artifacts


def _configure_output(mock_client, root):
    mock_client.base_url = "http://127.0.0.1:8000"
    mock_client.get_system_stats = AsyncMock(return_value={
        "system": {"argv": ["main.py", "--output-directory", str(root)]}
    })


@pytest.mark.asyncio
async def test_lists_all_artifact_kinds_from_filesystem_after_history_reset(
    tmp_path, mock_ctx, mock_client
):
    (tmp_path / "image.png").write_bytes(b"png")
    (tmp_path / "movie.mp4").write_bytes(b"video")
    (tmp_path / "sound.mp3").write_bytes(b"audio")
    (tmp_path / "mesh.glb").write_bytes(b"mesh")
    mock_client.get_history = AsyncMock(return_value={})
    _configure_output(mock_client, tmp_path)

    data = json.loads(await comfy_list_artifacts(ctx=mock_ctx))
    assert data["total_count"] == 4
    assert {item["kind"] for item in data["artifacts"]} == {
        "image", "video", "audio", "mesh"
    }
    assert data["diagnostics"]["filesystem_count"] == 4


@pytest.mark.asyncio
async def test_history_3d_asset_is_normalised(mock_ctx, mock_client):
    mock_client.get_history = AsyncMock(return_value={
        "prompt": {"outputs": {"9": {"3d": [{
            "filename": "model.glb", "subfolder": "objects", "type": "output"
        }]}}}
    })
    # A remote endpoint intentionally disables local filesystem fallback.
    mock_client.base_url = "https://example.invalid"
    data = json.loads(await comfy_list_artifacts(
        kind="mesh", filesystem_fallback=False, ctx=mock_ctx
    ))
    assert data["artifacts"][0]["relative_path"] == "objects/model.glb"
    assert data["artifacts"][0]["prompt_id"] == "prompt"


@pytest.mark.asyncio
async def test_get_artifact_metadata_and_opt_in_bytes(tmp_path, mock_ctx, mock_client):
    payload = b"glTF-test"
    subfolder = tmp_path / "objects"
    subfolder.mkdir()
    (subfolder / "model.glb").write_bytes(payload)
    _configure_output(mock_client, tmp_path)

    data = json.loads(await comfy_get_artifact(
        "objects/model.glb", include_data=True, include_sha256=True, ctx=mock_ctx
    ))
    artifact = data["artifact"]
    assert artifact["kind"] == "mesh"
    assert artifact["size_bytes"] == len(payload)
    assert base64.b64decode(artifact["data_base64"]) == payload
    assert len(artifact["sha256"]) == 64


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["../secret.txt", "/absolute/file.png", "C:/Windows/win.ini", "image.png:stream"],
)
async def test_get_artifact_rejects_traversal(path, tmp_path, mock_ctx, mock_client):
    _configure_output(mock_client, tmp_path)
    data = json.loads(await comfy_get_artifact(path, ctx=mock_ctx))
    assert "error" in data


@pytest.mark.asyncio
async def test_inline_size_limit_does_not_read_large_file(tmp_path, mock_ctx, mock_client):
    (tmp_path / "large.mp4").write_bytes(b"x" * 100)
    _configure_output(mock_client, tmp_path)
    data = json.loads(await comfy_get_artifact(
        "large.mp4", include_data=True, max_inline_bytes=10, ctx=mock_ctx
    ))
    assert "data_base64" not in data["artifact"]
    assert "inline limit" in data["artifact"]["data_error"]

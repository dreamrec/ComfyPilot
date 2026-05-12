"""Tests for comfy://docs/{node_class} resource and ComfyClient.get_node_docs."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from comfy_mcp.comfy_client import ComfyClient


@pytest.mark.asyncio
async def test_get_node_docs_returns_dict_on_success():
    client = ComfyClient("http://localhost:8188")
    fake_docs = {"description": "K-sampler with Karras schedule.", "examples": []}
    with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = fake_docs
        await client.connect()
        docs = await client.get_node_docs("KSampler")
        assert docs == fake_docs
    await client.close()


@pytest.mark.asyncio
async def test_get_node_docs_string_response_wraps_as_description():
    """Some forks return raw markdown - wrap it for callers."""
    client = ComfyClient("http://localhost:8188")
    with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = "Markdown doc body"
        await client.connect()
        docs = await client.get_node_docs("KSampler")
        assert docs == {"description": "Markdown doc body"}
    await client.close()


@pytest.mark.asyncio
async def test_get_node_docs_returns_none_when_all_paths_fail():
    client = ComfyClient("http://localhost:8188")
    with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("404")
        await client.connect()
        docs = await client.get_node_docs("KSampler")
        assert docs is None
    await client.close()


@pytest.mark.asyncio
async def test_get_node_docs_empty_class_type_returns_none():
    client = ComfyClient("http://localhost:8188")
    await client.connect()
    docs = await client.get_node_docs("")
    assert docs is None
    await client.close()

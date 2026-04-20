"""Tests for node tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

# Mock object_info response structure:
MOCK_OBJECT_INFO = {
    "KSampler": {
        "input": {"required": {"model": ["MODEL"], "seed": ["INT", {"default": 0}]}},
        "output": ["LATENT"],
        "category": "sampling",
    },
    "CheckpointLoaderSimple": {
        "input": {"required": {"ckpt_name": ["STRING"]}},
        "output": ["MODEL", "CLIP", "VAE"],
        "category": "loaders",
    },
    "CLIPTextEncode": {
        "input": {"required": {"text": ["STRING"], "clip": ["CLIP"]}},
        "output": ["CONDITIONING"],
        "category": "conditioning",
    },
}


class TestListNodeTypes:
    @pytest.mark.asyncio
    async def test_list_all(self, mock_ctx, mock_client):
        """Test listing all node types."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_list_node_types

        result = json.loads(await comfy_list_node_types(ctx=mock_ctx))
        assert result["total_count"] == 3
        assert len(result["node_types"]) == 3
        # Verify sorted
        assert result["node_types"] == sorted(result["node_types"])

    @pytest.mark.asyncio
    async def test_pagination(self, mock_ctx, mock_client):
        """Test pagination of node types."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_list_node_types

        result = json.loads(
            await comfy_list_node_types(limit=2, offset=0, ctx=mock_ctx)
        )
        assert len(result["node_types"]) == 2
        assert result["has_more"] is True
        assert result["next_offset"] == 2

    @pytest.mark.asyncio
    async def test_pagination_last_page(self, mock_ctx, mock_client):
        """Test last page of pagination."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_list_node_types

        result = json.loads(
            await comfy_list_node_types(limit=2, offset=2, ctx=mock_ctx)
        )
        assert len(result["node_types"]) == 1
        assert result["has_more"] is False
        assert result["next_offset"] is None


MOCK_V3_OBJECT_INFO = {
    "V3ExampleNode": {
        "schema_version": "v3",
        "name": "V3ExampleNode",
        "category": "testing",
        "description": "V3-shape node",
        "output_node": False,
        "inputs": [
            {"name": "image", "type": "IMAGE", "required": True, "is_link_target": True},
            {"name": "iterations", "type": "INT", "required": True, "default": 5, "min": 1, "max": 100},
        ],
        "outputs": [{"name": "image", "type": "IMAGE"}],
    },
}


class TestGetNodeInfo:
    @pytest.mark.asyncio
    async def test_get_v3_node_transparently(self, mock_ctx, mock_client):
        """V3-shape object_info entries are normalized to the same shape as V1."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_V3_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_get_node_info

        result = json.loads(
            await comfy_get_node_info(node_type="V3ExampleNode", ctx=mock_ctx)
        )
        assert result["class_type"] == "V3ExampleNode"
        assert result["schema_version"] == "v3"
        assert result["category"] == "testing"
        names = {i["name"] for i in result["inputs"]}
        assert names == {"image", "iterations"}

    @pytest.mark.asyncio
    async def test_get_existing_node(self, mock_ctx, mock_client):
        """Returns the normalized NodeSchema payload (class_type, category, inputs, outputs)."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_get_node_info

        result = json.loads(
            await comfy_get_node_info(node_type="KSampler", ctx=mock_ctx)
        )
        assert result["class_type"] == "KSampler"
        assert result["category"] == "sampling"
        assert result["schema_version"] == "v1"
        assert isinstance(result["inputs"], list)
        assert isinstance(result["outputs"], list)

    @pytest.mark.asyncio
    async def test_get_nonexistent_node(self, mock_ctx, mock_client):
        """Test getting info for a non-existent node."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_get_node_info

        result = json.loads(
            await comfy_get_node_info(node_type="NonExistent", ctx=mock_ctx)
        )
        assert "error" in result
        assert "not found" in result["error"].lower()


class TestSearchNodes:
    @pytest.mark.asyncio
    async def test_case_insensitive_search(self, mock_ctx, mock_client):
        """Test case-insensitive search."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_search_nodes

        result = json.loads(await comfy_search_nodes(query="ksampler", ctx=mock_ctx))
        assert len(result["matches"]) == 1
        assert "KSampler" in result["matches"]

    @pytest.mark.asyncio
    async def test_substring_match(self, mock_ctx, mock_client):
        """Test substring matching."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_search_nodes

        result = json.loads(await comfy_search_nodes(query="loader", ctx=mock_ctx))
        assert len(result["matches"]) == 1
        assert "CheckpointLoaderSimple" in result["matches"]

    @pytest.mark.asyncio
    async def test_search_multiple_results(self, mock_ctx, mock_client):
        """Test search returning multiple results."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_search_nodes

        result = json.loads(await comfy_search_nodes(query="Clip", ctx=mock_ctx))
        assert len(result["matches"]) >= 1
        assert result["total_matches"] >= 1

    @pytest.mark.asyncio
    async def test_search_limit(self, mock_ctx, mock_client):
        """Test search limit parameter."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_search_nodes

        result = json.loads(await comfy_search_nodes(query="", limit=2, ctx=mock_ctx))
        assert len(result["matches"]) <= 2
        assert result["returned"] <= 2


class TestGetCategories:
    @pytest.mark.asyncio
    async def test_get_categories(self, mock_ctx, mock_client):
        """Test getting all categories."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_get_categories

        result = json.loads(await comfy_get_categories(ctx=mock_ctx))
        assert "categories" in result
        assert result["total_categories"] == 3
        assert len(result["categories"]) == 3
        # Verify sorted
        cat_names = [c["name"] for c in result["categories"]]
        assert cat_names == sorted(cat_names)

    @pytest.mark.asyncio
    async def test_category_counts(self, mock_ctx, mock_client):
        """Test that category counts are correct."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_get_categories

        result = json.loads(await comfy_get_categories(ctx=mock_ctx))
        counts = {c["name"]: c["count"] for c in result["categories"]}
        assert counts["sampling"] == 1
        assert counts["loaders"] == 1
        assert counts["conditioning"] == 1


class TestGetEmbeddings:
    @pytest.mark.asyncio
    async def test_get_embeddings(self, mock_ctx, mock_client):
        """Test getting embeddings list."""
        mock_client.get_embeddings = AsyncMock(
            return_value=["embedding1.pt", "embedding2.pt"]
        )
        from comfy_mcp.tools.nodes import comfy_get_embeddings

        result = json.loads(await comfy_get_embeddings(ctx=mock_ctx))
        assert len(result["embeddings"]) == 2
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_empty_embeddings(self, mock_ctx, mock_client):
        """Test with no embeddings."""
        mock_client.get_embeddings = AsyncMock(return_value=[])
        from comfy_mcp.tools.nodes import comfy_get_embeddings

        result = json.loads(await comfy_get_embeddings(ctx=mock_ctx))
        assert result["count"] == 0
        assert len(result["embeddings"]) == 0


class TestInspectWidget:
    @pytest.mark.asyncio
    async def test_inspect_existing_node(self, mock_ctx, mock_client):
        """Returns normalized inputs list with widget_inputs/link_inputs split."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_inspect_widget

        result = json.loads(
            await comfy_inspect_widget(node_type="KSampler", ctx=mock_ctx)
        )
        assert result["node_type"] == "KSampler"
        assert isinstance(result["inputs"], list)
        assert isinstance(result["widget_inputs"], list)
        assert isinstance(result["link_inputs"], list)
        assert result["schema_version"] in ("v1", "v3")

    @pytest.mark.asyncio
    async def test_inspect_nonexistent_node(self, mock_ctx, mock_client):
        """Test inspecting widgets of a non-existent node."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_inspect_widget

        result = json.loads(
            await comfy_inspect_widget(node_type="NonExistent", ctx=mock_ctx)
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_inspect_widget_details(self, mock_ctx, mock_client):
        """Widget details come back with names, types, and constraints intact."""
        mock_client.get_object_info = AsyncMock(return_value=MOCK_OBJECT_INFO)
        from comfy_mcp.tools.nodes import comfy_inspect_widget

        result = json.loads(
            await comfy_inspect_widget(node_type="CLIPTextEncode", ctx=mock_ctx)
        )
        assert result["node_type"] == "CLIPTextEncode"
        input_names = {i["name"] for i in result["inputs"]}
        assert "text" in input_names
        assert "clip" in input_names

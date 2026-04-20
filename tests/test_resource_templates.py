"""Tests for paginated and category-filtered node-catalog resource templates."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

import comfy_mcp.server as server_module


@pytest.fixture
def mock_catalog(monkeypatch):
    """Install a fake shared_client so the resources can be called directly."""
    fake = AsyncMock()
    # Build 250 fake nodes across 3 categories
    nodes = {}
    for i in range(250):
        category = ("sampling", "loaders", "conditioning")[i % 3]
        nodes[f"FakeNode_{i:03d}"] = {
            "input": {"required": {}},
            "output": ["OUT"],
            "output_name": ["out"],
            "category": category,
            "output_node": False,
        }
    fake.get_object_info = AsyncMock(return_value=nodes)
    monkeypatch.setattr(server_module, "_shared_client", fake)
    return fake


class TestPagination:
    @pytest.mark.asyncio
    async def test_page_zero_returns_first_100(self, mock_catalog):
        # Access the resource function via the fastmcp decorator
        result = json.loads(await server_module.nodes_catalog_page("0"))
        assert result["page"] == 0
        assert result["total_nodes"] == 250
        assert result["total_pages"] == 3
        assert len(result["nodes"]) == 100
        # Sorted alphabetically
        assert result["nodes"] == sorted(result["nodes"])

    @pytest.mark.asyncio
    async def test_page_two_returns_last_50(self, mock_catalog):
        result = json.loads(await server_module.nodes_catalog_page("2"))
        assert result["page"] == 2
        assert len(result["nodes"]) == 50

    @pytest.mark.asyncio
    async def test_page_out_of_range_returns_empty(self, mock_catalog):
        result = json.loads(await server_module.nodes_catalog_page("99"))
        assert result["nodes"] == []

    @pytest.mark.asyncio
    async def test_invalid_page_returns_error(self, mock_catalog):
        result = json.loads(await server_module.nodes_catalog_page("abc"))
        assert "error" in result

    @pytest.mark.asyncio
    async def test_negative_page_rejected(self, mock_catalog):
        result = json.loads(await server_module.nodes_catalog_page("-1"))
        assert "error" in result


class TestByCategory:
    @pytest.mark.asyncio
    async def test_sampling_returns_one_third(self, mock_catalog):
        result = json.loads(await server_module.nodes_by_category("sampling"))
        assert result["category_prefix"] == "sampling"
        # ~84 of 250 have sampling category
        assert 80 <= result["count"] <= 90
        # All entries have category starting with sampling
        for n in result["nodes"]:
            assert n["category"].startswith("sampling")

    @pytest.mark.asyncio
    async def test_unknown_category_returns_empty(self, mock_catalog):
        result = json.loads(await server_module.nodes_by_category("nonexistent"))
        assert result["count"] == 0
        assert result["nodes"] == []


class TestResourceFailureModes:
    @pytest.mark.asyncio
    async def test_uninitialized_client_returns_error(self, monkeypatch):
        monkeypatch.setattr(server_module, "_shared_client", None)
        result = json.loads(await server_module.nodes_catalog_page("0"))
        assert "error" in result
        result2 = json.loads(await server_module.nodes_by_category("sampling"))
        assert "error" in result2

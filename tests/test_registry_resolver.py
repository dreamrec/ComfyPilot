"""Tests for RegistryResolver -- missing node to package resolution."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest


SNAPSHOT = {
    "version": "0.17.0",
    "os": "nt",
    "gpu_devices": [{"name": "NVIDIA RTX 5090", "type": "cuda"}],
}


class TestResolveSingle:
    @pytest.mark.asyncio
    async def test_resolve_from_cache(self):
        from comfy_mcp.registry.resolver import RegistryResolver
        index = MagicMock()
        index.lookup = MagicMock(return_value={
            "class": "ADE_Loader", "package": "comfyui-animatediff", "version": "1.2.3", "cached_at": time.time(),
        })
        client = AsyncMock()
        resolver = RegistryResolver(client, index, SNAPSHOT)
        result = await resolver.resolve_one("ADE_Loader")
        assert result["package"] == "comfyui-animatediff"
        client.reverse_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_from_api(self):
        from comfy_mcp.registry.resolver import RegistryResolver
        index = MagicMock()
        index.lookup = MagicMock(return_value=None)
        index.cache_positive = MagicMock()
        client = AsyncMock()
        client.reverse_lookup = AsyncMock(return_value={
            "comfy_node_name": "ADE_Loader",
            "node": {"id": "comfyui-animatediff", "name": "AnimateDiff",
                     "latest_version": {"version": "1.2.3"}},
        })
        resolver = RegistryResolver(client, index, SNAPSHOT)
        result = await resolver.resolve_one("ADE_Loader")
        assert result["package"] == "comfyui-animatediff"
        index.cache_positive.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_not_in_registry(self):
        from comfy_mcp.registry.resolver import RegistryResolver
        index = MagicMock()
        index.lookup = MagicMock(return_value=None)
        index.cache_negative = MagicMock()
        client = AsyncMock()
        client.reverse_lookup = AsyncMock(return_value=None)
        resolver = RegistryResolver(client, index, SNAPSHOT)
        result = await resolver.resolve_one("MyPrivateNode")
        assert result["package"] is None
        assert "not found" in result["note"].lower() or "private" in result["note"].lower()
        index.cache_negative.assert_called_once()


class TestResolveBatch:
    @pytest.mark.asyncio
    async def test_batch_deduplicates_packages(self):
        from comfy_mcp.registry.resolver import RegistryResolver
        index = MagicMock()
        # Both nodes from same package
        def lookup_side_effect(name):
            return {"class": name, "package": "comfyui-animatediff", "version": "1.2.3", "cached_at": time.time()}
        index.lookup = MagicMock(side_effect=lookup_side_effect)
        client = AsyncMock()
        resolver = RegistryResolver(client, index, SNAPSHOT)
        result = await resolver.resolve_batch(["ADE_Loader", "ADE_Settings"])
        assert result["unique_packages"] == 1
        assert "Install 1 package" in result["resolution"]

    @pytest.mark.asyncio
    async def test_batch_with_mixed_results(self):
        from comfy_mcp.registry.resolver import RegistryResolver
        index = MagicMock()
        def lookup_side_effect(name):
            if name == "KnownNode":
                return {"class": name, "package": "pkg-a", "version": "1.0", "cached_at": time.time()}
            return None
        index.lookup = MagicMock(side_effect=lookup_side_effect)
        index.cache_negative = MagicMock()
        client = AsyncMock()
        client.reverse_lookup = AsyncMock(return_value=None)
        resolver = RegistryResolver(client, index, SNAPSHOT)
        result = await resolver.resolve_batch(["KnownNode", "UnknownNode"])
        assert result["resolved"] == 1
        assert result["unresolved"] == 1

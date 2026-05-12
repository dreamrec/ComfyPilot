"""Tests for comfy_list_partner_apis tool."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.tools.partner_apis import (
    KNOWN_PARTNER_APIS,
    comfy_list_partner_apis,
)


def _ctx(client):
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"comfy_client": client}
    return ctx


@pytest.mark.asyncio
async def test_lists_installed_partners():
    client = MagicMock()
    client.get_extensions = AsyncMock(return_value=[
        "comfyui-veo",
        "comfyui-kling",
        "some-other-custom-node",
    ])
    result = await comfy_list_partner_apis(ctx=_ctx(client))
    parsed = json.loads(result)
    keys = {p["key"] for p in parsed["installed"]}
    assert "veo" in keys
    assert "kling" in keys
    assert parsed["installed_count"] == 2


@pytest.mark.asyncio
async def test_no_installed_partners_returns_empty():
    client = MagicMock()
    client.get_extensions = AsyncMock(return_value=["unrelated-node"])
    result = await comfy_list_partner_apis(ctx=_ctx(client))
    parsed = json.loads(result)
    assert parsed["installed_count"] == 0
    assert parsed["installed"] == []


@pytest.mark.asyncio
async def test_extension_endpoint_error_still_returns_catalog():
    """When /extensions errors, still surface the catalog so the agent knows what's possible."""
    client = MagicMock()
    client.get_extensions = AsyncMock(side_effect=Exception("404"))
    result = await comfy_list_partner_apis(ctx=_ctx(client))
    parsed = json.loads(result)
    assert "error" in parsed
    assert len(parsed["available"]) >= 10


def test_catalog_has_categories():
    """The curated catalog should cover video, image, 3D, audio at minimum."""
    cats = {meta["category"] for meta in KNOWN_PARTNER_APIS.values()}
    assert "video" in cats
    assert "image" in cats
    assert "3d" in cats
    assert "audio" in cats


def test_catalog_entries_have_required_fields():
    for key, meta in KNOWN_PARTNER_APIS.items():
        assert "vendor" in meta, f"{key} missing vendor"
        assert "category" in meta, f"{key} missing category"
        assert "models" in meta, f"{key} missing models"
        assert "homepage" in meta, f"{key} missing homepage"

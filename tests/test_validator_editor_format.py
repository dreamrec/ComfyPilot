"""Tests for editor-format detection pre-pass.

The ComfyUI web UI exports workflows in two shapes - "API format" (each
top-level key is a node ID with class_type) and "editor format" (top-level
nodes/links arrays plus UI metadata). Only API format is queueable. The
validator should catch editor format up-front and tell the caller to
re-export, rather than emitting N generic 'missing class_type' errors.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import Context

from comfy_mcp.tools.workflow import comfy_validate_workflow


def _ctx(client, vram_guard=None):
    ctx = MagicMock(spec=Context)
    ctx.request_context.lifespan_context = {"comfy_client": client, "vram_guard": vram_guard}
    return ctx


def _client_with(catalog: dict | None = None) -> MagicMock:
    client = MagicMock()
    client.get_object_info = AsyncMock(return_value=catalog or {})
    client.get_models = AsyncMock(return_value=[])
    return client


@pytest.mark.asyncio
async def test_editor_format_short_circuits_with_actionable_error():
    """A workflow with top-level `nodes` + `links` arrays gets a re-export message."""
    editor_workflow = {
        "last_node_id": 9,
        "last_link_id": 9,
        "nodes": [
            {"id": 1, "type": "CheckpointLoaderSimple", "pos": [50, 100]},
            {"id": 2, "type": "KSampler", "pos": [400, 100]},
        ],
        "links": [[1, 1, 0, 2, 0, "MODEL"]],
        "groups": [],
        "config": {},
        "extra": {},
    }
    result = await comfy_validate_workflow(
        workflow=editor_workflow,
        ctx=_ctx(_client_with()),
    )
    assert result.valid is False
    assert any("editor format" in e.lower() for e in result.errors)
    assert any("export (api)" in e.lower() or "api format" in e.lower() for e in result.errors)
    assert "editor_format_detected" in result.passes


@pytest.mark.asyncio
async def test_editor_format_reports_node_count():
    """Editor format with 5 UI nodes should report node_count=5."""
    editor_workflow = {
        "nodes": [{"id": i, "type": "X"} for i in range(5)],
        "links": [],
    }
    result = await comfy_validate_workflow(
        workflow=editor_workflow,
        ctx=_ctx(_client_with()),
    )
    assert result.node_count == 5


@pytest.mark.asyncio
async def test_api_format_unaffected():
    """A normal API-format workflow does not trip the editor-format pre-pass."""
    api_workflow = {
        "1": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
    }
    result = await comfy_validate_workflow(
        workflow=api_workflow,
        ctx=_ctx(_client_with({"EmptyLatentImage": {}, "SaveImage": {}})),
    )
    assert "editor_format_detected" not in result.passes
    # Should reach later passes
    assert "schema" in result.passes


@pytest.mark.asyncio
async def test_api_format_with_node_named_nodes_is_not_editor_format():
    """A workflow with a literal node ID 'nodes' (string key) is still API format.

    Edge case: nothing prevents a workflow from having a node whose key is
    'nodes'. The pre-pass keys on `isinstance(workflow.get("nodes"), list)`
    so a dict-shaped value at 'nodes' is correctly treated as a regular node.
    """
    workflow = {
        "nodes": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "links": {"class_type": "SaveImage", "inputs": {"images": ["nodes", 0]}},
    }
    result = await comfy_validate_workflow(
        workflow=workflow,
        ctx=_ctx(_client_with({"EmptyLatentImage": {}, "SaveImage": {}})),
    )
    # Should NOT trigger editor-format short-circuit since values are dicts, not lists
    assert "editor_format_detected" not in result.passes

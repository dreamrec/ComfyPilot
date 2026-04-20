"""Tests for Phase 3 features: Mermaid viz, PNG ingest, parameter sweep."""
from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import Context

from comfy_mcp.ingest.png_metadata import extract_workflow_from_png
from comfy_mcp.tools.ingest import comfy_import_workflow_from_png
from comfy_mcp.tools.sweep import comfy_sweep
from comfy_mcp.tools.viz import comfy_visualize_workflow
from comfy_mcp.viz.mermaid import workflow_to_mermaid


SAMPLE = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "hi", "clip": ["1", 1]}},
    "5": {
        "class_type": "KSampler",
        "inputs": {
            "model": ["1", 0], "positive": ["2", 0],
            "seed": 42, "steps": 20, "cfg": 7.0,
            "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
        },
    },
}


class TestMermaidViz:
    def test_flowchart_header(self):
        source = workflow_to_mermaid(SAMPLE)
        assert source.startswith("flowchart TD\n")

    def test_one_line_per_node(self):
        source = workflow_to_mermaid(SAMPLE)
        assert 'n1["1: CheckpointLoaderSimple"]' in source
        assert 'n2["2: CLIPTextEncode"]' in source
        assert 'n5["5: KSampler"]' in source

    def test_arrows_trace_links(self):
        source = workflow_to_mermaid(SAMPLE)
        assert "n1 -->|clip| n2" in source
        assert "n1 -->|model| n5" in source
        assert "n2 -->|positive| n5" in source

    def test_title_comment(self):
        source = workflow_to_mermaid(SAMPLE, title="My Workflow")
        assert "%% My Workflow" in source

    def test_rejects_non_dict(self):
        with pytest.raises(TypeError):
            workflow_to_mermaid([])  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_tool_returns_mermaid_source(self):
        source = await comfy_visualize_workflow(workflow=SAMPLE)
        assert source.startswith("flowchart TD")


# --- PNG helpers -------------------------------------------------------------


def _png_crc(chunk_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)


def _make_text_chunk(keyword: str, text: str) -> bytes:
    payload = keyword.encode("latin-1") + b"\x00" + text.encode("utf-8")
    return struct.pack(">I", len(payload)) + b"tEXt" + payload + _png_crc(b"tEXt", payload)


def _build_png(text_chunks: list[tuple[str, str]]) -> bytes:
    """Build a minimal-but-valid PNG with IHDR + optional tEXt chunks + IEND."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_payload = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    ihdr = struct.pack(">I", len(ihdr_payload)) + b"IHDR" + ihdr_payload + _png_crc(b"IHDR", ihdr_payload)
    # Minimal IDAT - single zlib-compressed byte
    idat_payload = zlib.compress(b"\x00\x00")
    idat = struct.pack(">I", len(idat_payload)) + b"IDAT" + idat_payload + _png_crc(b"IDAT", idat_payload)
    iend = struct.pack(">I", 0) + b"IEND" + _png_crc(b"IEND", b"")
    text_blocks = b"".join(_make_text_chunk(k, v) for k, v in text_chunks)
    return sig + ihdr + text_blocks + idat + iend


class TestPNGIngest:
    def test_extracts_api_prompt_chunk(self, tmp_path):
        path = tmp_path / "out.png"
        api_workflow = {"1": {"class_type": "X", "inputs": {}}}
        path.write_bytes(_build_png([("prompt", json.dumps(api_workflow))]))

        result = extract_workflow_from_png(path)
        assert result["format"] == "api"
        assert result["workflow"] == api_workflow

    def test_falls_back_to_ui_workflow_chunk(self, tmp_path):
        path = tmp_path / "out.png"
        ui_workflow = {"version": 1, "nodes": []}
        path.write_bytes(_build_png([("workflow", json.dumps(ui_workflow))]))

        result = extract_workflow_from_png(path)
        assert result["format"] == "ui"
        assert result["workflow"] == ui_workflow

    def test_prefers_prompt_when_both_present(self, tmp_path):
        path = tmp_path / "out.png"
        api = {"a": {"class_type": "Y", "inputs": {}}}
        ui = {"version": 1, "nodes": []}
        path.write_bytes(_build_png([
            ("workflow", json.dumps(ui)),
            ("prompt", json.dumps(api)),
        ]))

        result = extract_workflow_from_png(path)
        assert result["format"] == "api"
        assert result["workflow"] == api

    def test_no_chunks_returns_none_format(self, tmp_path):
        path = tmp_path / "plain.png"
        path.write_bytes(_build_png([]))
        result = extract_workflow_from_png(path)
        assert result["format"] == "none"

    def test_invalid_png_raises_valueerror(self, tmp_path):
        path = tmp_path / "notapng.png"
        path.write_bytes(b"not a png")
        with pytest.raises(ValueError):
            extract_workflow_from_png(path)

    @pytest.mark.asyncio
    async def test_tool_roundtrip(self, tmp_path):
        path = tmp_path / "out.png"
        api_workflow = {"1": {"class_type": "X", "inputs": {}}}
        path.write_bytes(_build_png([("prompt", json.dumps(api_workflow))]))

        result = json.loads(await comfy_import_workflow_from_png(png_path=str(path)))
        assert result["format"] == "api"

    @pytest.mark.asyncio
    async def test_tool_missing_file_returns_error(self, tmp_path):
        result = json.loads(await comfy_import_workflow_from_png(png_path=str(tmp_path / "nope.png")))
        assert "error" in result


# --- Parameter sweep ---------------------------------------------------------


def _sweep_ctx(client, tracker):
    ctx = MagicMock(spec=Context)
    ctx.request_context.lifespan_context = {"comfy_client": client, "job_tracker": tracker}
    return ctx


class TestParameterSweep:
    @pytest.mark.asyncio
    async def test_four_seeds_queues_four(self):
        client = MagicMock()
        queued_prompts = []

        async def fake_queue(wf, **kwargs):
            queued_prompts.append(wf)
            return {"prompt_id": f"p{len(queued_prompts)}", "number": len(queued_prompts)}

        client.queue_prompt = AsyncMock(side_effect=fake_queue)
        tracker = MagicMock()
        tracker.track = AsyncMock()

        result = json.loads(await comfy_sweep(
            workflow=SAMPLE, node_id="5", param="seed",
            values=[1, 2, 3, 4], ctx=_sweep_ctx(client, tracker),
        ))
        assert len(result["prompt_ids"]) == 4
        assert result["values_requested"] == 4
        # Each variant had a different seed
        seeds = [wf["5"]["inputs"]["seed"] for wf in queued_prompts]
        assert seeds == [1, 2, 3, 4]
        # Grid is 2x2 for 4 values
        assert result["grid_layout"] == {"cols": 2, "rows": 2}

    @pytest.mark.asyncio
    async def test_each_prompt_registered_with_tracker(self):
        client = MagicMock()
        client.queue_prompt = AsyncMock(return_value={"prompt_id": "abc", "number": 0})
        tracker = MagicMock()
        tracker.track = AsyncMock()

        await comfy_sweep(
            workflow=SAMPLE, node_id="5", param="cfg",
            values=[5.0, 7.0, 9.0], ctx=_sweep_ctx(client, tracker),
        )
        assert tracker.track.await_count == 3

    @pytest.mark.asyncio
    async def test_queue_failure_logged_not_fatal(self):
        client = MagicMock()
        call = [0]

        async def fake_queue(wf, **kwargs):
            call[0] += 1
            if call[0] == 2:
                raise Exception("server offline")
            return {"prompt_id": f"p{call[0]}"}

        client.queue_prompt = AsyncMock(side_effect=fake_queue)
        tracker = MagicMock()
        tracker.track = AsyncMock()

        result = json.loads(await comfy_sweep(
            workflow=SAMPLE, node_id="5", param="steps",
            values=[10, 20, 30], ctx=_sweep_ctx(client, tracker),
        ))
        assert len(result["prompt_ids"]) == 2
        assert len(result["errors"]) == 1

    @pytest.mark.asyncio
    async def test_unknown_node_returns_error(self):
        client = MagicMock()
        client.queue_prompt = AsyncMock()
        tracker = MagicMock()

        result = json.loads(await comfy_sweep(
            workflow=SAMPLE, node_id="nope", param="seed",
            values=[1, 2], ctx=_sweep_ctx(client, tracker),
        ))
        assert "error" in result

    @pytest.mark.asyncio
    async def test_empty_values_returns_error(self):
        client = MagicMock()
        tracker = MagicMock()
        result = json.loads(await comfy_sweep(
            workflow=SAMPLE, node_id="5", param="seed",
            values=[], ctx=_sweep_ctx(client, tracker),
        ))
        assert "error" in result

"""Tests for comfy_run_with_inputs."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from comfy_mcp.tools.run_with_inputs import (
    _apply_label_to_workflow,
    comfy_run_with_inputs,
)


def _ctx_with_queue_success(prompt_id="abc-123"):
    client = MagicMock()
    client.upload_image = AsyncMock(return_value={"name": "photo.png", "subfolder": "", "type": "input"})
    client.queue_prompt = AsyncMock(return_value={"prompt_id": prompt_id, "number": 1})
    tracker = MagicMock()
    tracker.track = AsyncMock()
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"comfy_client": client, "job_tracker": tracker}
    return ctx, client


class TestApplyLabel:
    def test_explicit_node_input_targeting(self):
        wf = {"3": {"class_type": "LoadImage", "inputs": {"image": "old.png"}}}
        applied = _apply_label_to_workflow(wf, "3.image", "new.png")
        assert applied == ["3.image"]
        assert wf["3"]["inputs"]["image"] == "new.png"

    def test_implicit_label_patches_every_matching_field(self):
        wf = {
            "1": {"class_type": "LoadImage", "inputs": {"image": "a.png"}},
            "2": {"class_type": "LoadImage", "inputs": {"image": "b.png"}},
            "3": {"class_type": "KSampler", "inputs": {"seed": 1}},
        }
        applied = _apply_label_to_workflow(wf, "image", "new.png")
        assert "1.image" in applied
        assert "2.image" in applied
        assert "3.seed" not in applied  # different field name
        assert wf["1"]["inputs"]["image"] == "new.png"
        assert wf["2"]["inputs"]["image"] == "new.png"

    def test_does_not_overwrite_link_tuples(self):
        """Don't replace a link [node_id, output_idx] with a string filename."""
        wf = {
            "1": {"class_type": "LoadImage", "inputs": {"image": "input.png"}},
            "2": {"class_type": "ImageScale", "inputs": {"image": ["1", 0]}},  # link, not a widget
        }
        applied = _apply_label_to_workflow(wf, "image", "new.png")
        assert "1.image" in applied
        assert "2.image" not in applied
        assert wf["2"]["inputs"]["image"] == ["1", 0]

    def test_explicit_targeting_unknown_node_is_noop(self):
        wf = {"1": {"class_type": "LoadImage", "inputs": {"image": "x.png"}}}
        applied = _apply_label_to_workflow(wf, "99.image", "new.png")
        assert applied == []


class TestComfyRunWithInputs:
    @pytest.mark.asyncio
    async def test_uploads_injects_and_queues(self, tmp_path):
        photo = tmp_path / "photo.png"
        photo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        workflow = {"3": {"class_type": "LoadImage", "inputs": {"image": "placeholder.png"}}}
        ctx, client = _ctx_with_queue_success()
        result = await comfy_run_with_inputs(
            workflow=workflow,
            inputs={"image": str(photo)},
            ctx=ctx,
        )
        assert result.prompt_id == "abc-123"
        assert result.queue_number == 1
        assert result.queue_position is None
        # Upload happened
        client.upload_image.assert_awaited_once()
        # Queue happened with patched workflow
        queued = client.queue_prompt.await_args.args[0]
        assert queued["3"]["inputs"]["image"] == "photo.png"

    @pytest.mark.asyncio
    async def test_caller_workflow_not_mutated(self, tmp_path):
        """Deep-copy guarantee: caller's dict stays unchanged."""
        photo = tmp_path / "photo.png"
        photo.write_bytes(b"x")
        workflow = {"3": {"class_type": "LoadImage", "inputs": {"image": "placeholder.png"}}}
        ctx, _ = _ctx_with_queue_success()
        await comfy_run_with_inputs(workflow=workflow, inputs={"image": str(photo)}, ctx=ctx)
        assert workflow["3"]["inputs"]["image"] == "placeholder.png"

    @pytest.mark.asyncio
    async def test_missing_local_file_errors_without_uploading(self, tmp_path):
        ctx, client = _ctx_with_queue_success()
        result = await comfy_run_with_inputs(
            workflow={"3": {"class_type": "LoadImage", "inputs": {"image": ""}}},
            inputs={"image": str(tmp_path / "doesnotexist.png")},
            ctx=ctx,
        )
        assert result.prompt_id is None
        assert "not found" in (result.error or "")
        client.upload_image.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_inputs_inpaint_flow(self, tmp_path):
        photo = tmp_path / "photo.png"
        mask = tmp_path / "mask.png"
        photo.write_bytes(b"a")
        mask.write_bytes(b"b")
        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {"image": "p.png"}},
            "2": {"class_type": "LoadImage", "inputs": {"image": "m.png"}},
        }
        ctx, client = _ctx_with_queue_success()
        # Return distinct uploaded names by sequencing upload_image
        client.upload_image = AsyncMock(side_effect=[
            {"name": "photo.png"}, {"name": "mask.png"},
        ])
        result = await comfy_run_with_inputs(
            workflow=workflow,
            inputs={"1.image": str(photo), "2.image": str(mask)},
            ctx=ctx,
        )
        assert result.prompt_id == "abc-123"
        queued = client.queue_prompt.await_args.args[0]
        assert queued["1"]["inputs"]["image"] == "photo.png"
        assert queued["2"]["inputs"]["image"] == "mask.png"
        assert client.upload_image.await_count == 2

    @pytest.mark.asyncio
    async def test_rejects_non_dict_inputs(self, tmp_path):
        ctx, _ = _ctx_with_queue_success()
        result = await comfy_run_with_inputs(
            workflow={"1": {"class_type": "X", "inputs": {}}},
            inputs="not a dict",  # type: ignore[arg-type]
            ctx=ctx,
        )
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_upload_failure_propagated(self, tmp_path):
        photo = tmp_path / "photo.png"
        photo.write_bytes(b"x")
        ctx, client = _ctx_with_queue_success()
        client.upload_image = AsyncMock(side_effect=Exception("upload 500"))
        result = await comfy_run_with_inputs(
            workflow={"1": {"class_type": "LoadImage", "inputs": {"image": ""}}},
            inputs={"image": str(photo)},
            ctx=ctx,
        )
        assert "upload 500" in (result.error or "")

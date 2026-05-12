"""Regression tests for the v1.8.0 audit-driven fixes.

Each test pins one of the 6 bugs the code review uncovered so they can't
silently regress. Numbered to match the audit summary.
"""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comfy_mcp.cli.comfy_cli import ComfyCliResult
from comfy_mcp.comfy_client import ComfyClient
from comfy_mcp.errors import ComfyAPIError
from comfy_mcp.tools.auto_fix_deps import comfy_install_workflow_deps
from comfy_mcp.tools.diagnostics import comfy_extract_schema, comfy_fetch_logs
from comfy_mcp.tools.lifecycle import comfy_launch_server
from comfy_mcp.tools.randomize_seeds import comfy_randomize_seeds


def _ctx():
    client = MagicMock()
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"comfy_client": client}
    return ctx


# -----------------------------------------------------------------
# Fix #1: temp-file fd leak in auto_fix_deps when os.fdopen fails
# -----------------------------------------------------------------

class TestAutoFixDepsFdLeak:
    @pytest.mark.asyncio
    async def test_fdopen_failure_closes_fd_and_unlinks(self, tmp_path):
        """If os.fdopen raises, the raw fd must still be closed and tmp file removed."""
        captured = {}

        original_mkstemp = __import__("tempfile").mkstemp
        original_close = os.close
        original_unlink = os.unlink

        def fake_mkstemp(*args, **kwargs):
            fd, path = original_mkstemp(*args, **kwargs)
            captured["fd"] = fd
            captured["path"] = path
            return fd, path

        def fake_fdopen(fd, *args, **kwargs):
            raise OSError("simulated resource exhaustion")

        close_calls = []

        def fake_close(fd):
            close_calls.append(fd)
            return original_close(fd)

        unlink_calls = []

        def fake_unlink(path):
            unlink_calls.append(path)
            return original_unlink(path)

        workflow = {"1": {"class_type": "X", "inputs": {}}}
        with patch("comfy_mcp.tools.auto_fix_deps.tempfile.mkstemp", side_effect=fake_mkstemp), \
             patch("comfy_mcp.tools.auto_fix_deps.os.fdopen", side_effect=fake_fdopen), \
             patch("comfy_mcp.tools.auto_fix_deps.os.close", side_effect=fake_close), \
             patch("comfy_mcp.tools.auto_fix_deps.os.unlink", side_effect=fake_unlink):
            with pytest.raises(OSError, match="resource exhaustion"):
                await comfy_install_workflow_deps(workflow=workflow)
        # The raw fd we captured must have been closed
        assert captured["fd"] in close_calls
        # And the temp path must have been unlinked in the finally
        assert captured["path"] in unlink_calls


# -----------------------------------------------------------------
# Fix #2: fetch_logs deduplicates errors that appear in both
#         status.exec_info.errors AND status.messages
# -----------------------------------------------------------------

class TestFetchLogsDedup:
    @pytest.mark.asyncio
    async def test_same_error_in_both_sources_reported_once(self):
        client = MagicMock()
        client.get_history = AsyncMock(return_value={
            "abc-123": {
                "status": {
                    "status_str": "error",
                    "exec_info": {
                        "errors": [{
                            "node_id": "5",
                            "class_type": "KSampler",
                            "message": "CUDA OOM",
                            "traceback": "Traceback: ...",
                        }],
                    },
                    "messages": [
                        ["execution_error", {
                            "node_id": "5",
                            "node_type": "KSampler",
                            "exception_message": "CUDA OOM",
                            "exception_traceback": "Traceback: ...",
                        }],
                    ],
                },
            },
        })
        ctx = MagicMock()
        ctx.request_context.lifespan_context = {"comfy_client": client}
        result = await comfy_fetch_logs(prompt_id="abc-123", ctx=ctx)
        parsed = json.loads(result)
        assert parsed["error_count"] == 1, "duplicate error from both sources must be deduped"
        assert parsed["failed_node"] == "5"

    @pytest.mark.asyncio
    async def test_distinct_errors_not_deduplicated(self):
        client = MagicMock()
        client.get_history = AsyncMock(return_value={
            "abc-123": {
                "status": {
                    "exec_info": {
                        "errors": [
                            {"node_id": "5", "message": "OOM"},
                            {"node_id": "7", "message": "Missing model"},
                        ],
                    },
                },
            },
        })
        ctx = MagicMock()
        ctx.request_context.lifespan_context = {"comfy_client": client}
        result = await comfy_fetch_logs(prompt_id="abc-123", ctx=ctx)
        parsed = json.loads(result)
        assert parsed["error_count"] == 2


# -----------------------------------------------------------------
# Fix #3: has_negative_prompt detection now uses link-target, not
#         numeric node-ID substring (which never matched)
# -----------------------------------------------------------------

class TestNegativePromptDetection:
    @pytest.mark.asyncio
    async def test_negative_link_to_ksampler_detected(self):
        """Standard SD workflow: CLIPTextEncode -> KSampler.negative as a link."""
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly, blurry", "clip": ["1", 1]}},
            "4": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "seed": 0,
            }},
        }
        result = await comfy_extract_schema(workflow=wf, summary_only=True, ctx=_ctx())
        parsed = json.loads(result)
        assert parsed["has_negative_prompt"] is True

    @pytest.mark.asyncio
    async def test_explicit_negative_widget_detected(self):
        """Some nodes carry the negative prompt directly as a widget."""
        wf = {
            "1": {"class_type": "SUPIRSample", "inputs": {
                "positive_prompt": "cinematic",
                "negative_prompt": "painting, blurry",
                "seed": 42,
            }},
        }
        result = await comfy_extract_schema(workflow=wf, summary_only=True, ctx=_ctx())
        parsed = json.loads(result)
        assert parsed["has_negative_prompt"] is True

    @pytest.mark.asyncio
    async def test_positive_only_workflow_reports_false(self):
        wf = {
            "1": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        result = await comfy_extract_schema(workflow=wf, summary_only=True, ctx=_ctx())
        parsed = json.loads(result)
        assert parsed["has_negative_prompt"] is False


# -----------------------------------------------------------------
# Fix #4: cloud tier probe distinguishes 403 (free) from other errors
# -----------------------------------------------------------------

class TestCloudTierProbe403:
    def _make_routes(self, object_info_response):
        """Simulate a cloud profile (local /system_stats fails, /api/...
        succeeds) so the tier-probe fallback runs against the chosen
        /api/object_info response."""
        async def handler(path):
            if path == "/system_stats":
                raise Exception("local 404")
            if path == "/api/system_stats":
                return {"system": {"comfyui_version": "0.20.1"}}
            if path.endswith("/features"):
                return {}
            if "user" in path or "account" in path or "/me" in path:
                raise Exception("404")
            if path == "/api/object_info":
                if isinstance(object_info_response, Exception):
                    raise object_info_response
                return object_info_response
            return {}
        return handler

    @pytest.mark.asyncio
    async def test_http_403_classified_as_free(self):
        client = ComfyClient("https://cloud.comfy.org", api_key="ck")
        err = ComfyAPIError(error_code="HTTP_403", message="forbidden", suggestion="")
        with patch.object(client, "get", new=self._make_routes(err)), \
             patch.object(client, "_probe_ws_available", new_callable=AsyncMock) as ws:
            ws.return_value = True
            await client.connect()
            await client.probe_capabilities()
            assert client.capabilities["tier"] == "free"
        await client.close()

    @pytest.mark.asyncio
    async def test_http_404_classified_as_none(self):
        """404 = endpoint doesn't exist on this fork. Tier is unknown, not free."""
        client = ComfyClient("https://cloud.comfy.org", api_key="ck")
        err = ComfyAPIError(error_code="HTTP_404", message="not found", suggestion="")
        with patch.object(client, "get", new=self._make_routes(err)), \
             patch.object(client, "_probe_ws_available", new_callable=AsyncMock) as ws:
            ws.return_value = True
            await client.connect()
            await client.probe_capabilities()
            assert client.capabilities["tier"] is None
        await client.close()

    @pytest.mark.asyncio
    async def test_connection_error_classified_as_none(self):
        """Network blip during probe must not silently mark the user as free tier."""
        client = ComfyClient("https://cloud.comfy.org", api_key="ck")
        with patch.object(client, "get", new=self._make_routes(Exception("connection refused"))), \
             patch.object(client, "_probe_ws_available", new_callable=AsyncMock) as ws:
            ws.return_value = True
            await client.connect()
            await client.probe_capabilities()
            assert client.capabilities["tier"] is None
        await client.close()


# -----------------------------------------------------------------
# Fix #5: comfy_launch_server warns when extra_args overrides
#         --port / --listen
# -----------------------------------------------------------------

class TestLaunchServerOverrideWarning:
    @pytest.mark.asyncio
    async def test_extra_args_with_port_emits_warning(self):
        with patch("comfy_mcp.tools.lifecycle.run_comfy_cli", new_callable=AsyncMock) as mock:
            mock.return_value = ComfyCliResult(returncode=0, stdout="", stderr="", argv=())
            result = await comfy_launch_server(port=8188, extra_args=["--port", "9000"])
        parsed = json.loads(result)
        assert "warning" in parsed
        assert "--port" in parsed["overridden_flags"]

    @pytest.mark.asyncio
    async def test_extra_args_with_listen_emits_warning(self):
        with patch("comfy_mcp.tools.lifecycle.run_comfy_cli", new_callable=AsyncMock) as mock:
            mock.return_value = ComfyCliResult(returncode=0, stdout="", stderr="", argv=())
            result = await comfy_launch_server(host="127.0.0.1", extra_args=["--listen", "0.0.0.0"])
        parsed = json.loads(result)
        assert "warning" in parsed
        assert "--listen" in parsed["overridden_flags"]

    @pytest.mark.asyncio
    async def test_extra_args_without_overrides_no_warning(self):
        with patch("comfy_mcp.tools.lifecycle.run_comfy_cli", new_callable=AsyncMock) as mock:
            mock.return_value = ComfyCliResult(returncode=0, stdout="", stderr="", argv=())
            result = await comfy_launch_server(extra_args=["--cpu"])
        parsed = json.loads(result)
        assert "warning" not in parsed


# -----------------------------------------------------------------
# Fix #6: randomize_seeds never produces 0 (some custom nodes treat
#         0 as a re-randomise sentinel like -1)
# -----------------------------------------------------------------

class TestRandomizeSeedsExcludesZero:
    @pytest.mark.asyncio
    async def test_seed_is_in_range_1_to_2pow32_minus_one(self):
        """Run many randomisations and verify none hit 0."""
        for _ in range(200):
            wf = {"5": {"class_type": "KSampler", "inputs": {"seed": -1}}}
            result = await comfy_randomize_seeds(workflow=wf, ctx=None)
            parsed = json.loads(result)
            seed = parsed["workflow"]["5"]["inputs"]["seed"]
            assert 1 <= seed < 2 ** 32

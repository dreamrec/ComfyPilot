"""Tests for the --transport CLI flag."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from comfy_mcp.server import _parse_cli_args


ROOT = Path(__file__).resolve().parents[1]
_REGISTRY_MARKER = "COMFYPILOT_REGISTRY="
_ENTRYPOINT_PROBE = r"""
import json
import runpy
import sys

from mcp.server.fastmcp import FastMCP

from comfy_mcp import __version__


def capture_run(self, *args, **kwargs):
    print("COMFYPILOT_REGISTRY=" + json.dumps({
        "tools": sorted(self._tool_manager._tools),
        "transport": kwargs.get("transport"),
    }))


FastMCP.run = capture_run


def test_protocol_server_reports_comfypilot_version():
    from comfy_mcp.server import mcp

    assert mcp._mcp_server.version == __version__
mode = sys.argv[1]
if mode == "module":
    sys.argv = ["comfy_mcp.server", "--transport", "stdio"]
    runpy.run_module("comfy_mcp.server", run_name="__main__", alter_sys=True)
else:
    from comfy_mcp.server import main
    sys.argv = ["comfypilot", "--transport", "stdio"]
    main()
"""


def _probe_entrypoint(mode: str) -> dict:
    env = dict(os.environ)
    source_root = str(ROOT / "src")
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (source_root, env.get("PYTHONPATH", "")) if value
    )
    result = subprocess.run(
        [sys.executable, "-c", _ENTRYPOINT_PROBE, mode],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    payload_line = next(
        (line for line in result.stdout.splitlines() if line.startswith(_REGISTRY_MARKER)),
        None,
    )
    assert payload_line is not None, result.stderr or result.stdout
    return json.loads(payload_line.removeprefix(_REGISTRY_MARKER))


@pytest.fixture(scope="module")
def entrypoint_registries() -> tuple[dict, dict]:
    return _probe_entrypoint("module"), _probe_entrypoint("console")


class TestCLIParser:
    def test_default_is_stdio(self):
        args = _parse_cli_args([])
        assert args.transport == "stdio"

    def test_streamable_http_selected(self):
        args = _parse_cli_args(["--transport", "streamable-http"])
        assert args.transport == "streamable-http"
        assert args.host == "127.0.0.1"  # default
        assert args.port == 8765  # default

    def test_custom_host_and_port(self):
        args = _parse_cli_args([
            "--transport", "streamable-http",
            "--host", "0.0.0.0",
            "--port", "9000",
        ])
        assert args.host == "0.0.0.0"
        assert args.port == 9000

    def test_invalid_transport_rejected(self):
        with pytest.raises(SystemExit):
            _parse_cli_args(["--transport", "sse"])

    def test_port_must_be_int(self):
        with pytest.raises(SystemExit):
            _parse_cli_args(["--port", "not-a-number"])


def test_python_module_entrypoint_registers_tools(entrypoint_registries):
    module_registry, _ = entrypoint_registries

    assert module_registry["transport"] == "stdio"
    assert len(module_registry["tools"]) >= 90
    assert "comfy_get_system_stats" in module_registry["tools"]
    assert "comfy_instance_doctor" in module_registry["tools"]


def test_python_module_and_console_entrypoints_share_registry(entrypoint_registries):
    module_registry, console_registry = entrypoint_registries

    assert module_registry == console_registry

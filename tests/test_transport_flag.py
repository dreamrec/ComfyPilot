"""Tests for the --transport CLI flag."""
from __future__ import annotations

import pytest

from comfy_mcp.server import _parse_cli_args


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

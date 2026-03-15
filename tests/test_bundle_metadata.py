"""Tests for bundled MCP launch metadata."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent


def _args_for(rel_path: str) -> list[str]:
    data = json.loads((ROOT / rel_path).read_text())
    if rel_path == "mcp/manifest.json":
        return data["args"]
    return data["mcpServers"]["comfypilot"]["args"]


@pytest.mark.parametrize(
    "rel_path",
    [
        "mcp/manifest.json",
        "mcp/profiles/claude-desktop.json",
        "mcp/profiles/cursor.json",
        "mcp/profiles/generic.json",
    ],
)
def test_bundle_configs_pin_project_directory(rel_path: str):
    args = _args_for(rel_path)
    assert "--directory" in args
    directory_index = args.index("--directory") + 1
    assert directory_index < len(args)
    assert args[directory_index] not in {"", "."}

"""Smoke test: every bundled blueprint loads and round-trips through the store."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from comfy_mcp.blueprints.store import BlueprintStore


BUNDLED_DIR = Path(__file__).resolve().parents[1] / "blueprints"


def _bundled_files() -> list[Path]:
    return sorted(BUNDLED_DIR.glob("*.json"))


def test_bundled_dir_exists():
    assert BUNDLED_DIR.is_dir()
    assert len(_bundled_files()) >= 8, "Should ship at least one blueprint per family"


@pytest.mark.parametrize("path", _bundled_files(), ids=lambda p: p.stem)
def test_bundled_blueprint_is_valid(path):
    data = json.loads(path.read_text())
    assert data.get("name") == path.stem, f"name field must match filename for {path.name}"
    assert "nodes" in data and isinstance(data["nodes"], dict)
    assert data.get("node_count") == len(data["nodes"])
    assert "tags" in data
    assert "description" in data
    # Every node declares a class_type
    for node_id, node in data["nodes"].items():
        assert "class_type" in node, f"{path.name} node {node_id} missing class_type"


def test_store_lists_every_bundled(tmp_path):
    """BlueprintStore.list() must return every bundled blueprint (none shadowed)."""
    store = BlueprintStore(user_dir=tmp_path, bundled_dir=BUNDLED_DIR)
    listed = {b["name"]: b["source"] for b in store.list()}
    for p in _bundled_files():
        assert p.stem in listed, f"Bundled {p.stem} not listed"
        assert listed[p.stem] == "bundled"


def test_store_inserts_every_bundled(tmp_path):
    """Each bundled blueprint must be insertable into a workflow dict."""
    store = BlueprintStore(user_dir=tmp_path, bundled_dir=BUNDLED_DIR)
    for p in _bundled_files():
        result = store.insert(p.stem)
        assert "workflow" in result
        assert len(result["workflow"]) > 0

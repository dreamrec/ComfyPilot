"""Tests for release metadata consistency."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]


ROOT = Path(__file__).parent.parent


def test_release_versions_match():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    expected = pyproject["project"]["version"]

    package_ns: dict[str, str] = {}
    exec((ROOT / "src" / "comfy_mcp" / "__init__.py").read_text(encoding="utf-8"), package_ns)
    assert package_ns["__version__"] == expected

    manifest = json.loads((ROOT / "mcp" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == expected

    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert plugin["version"] == expected

    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert marketplace["plugins"][0]["version"] == expected

    bundle = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert bundle["version"] == expected

    registry = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert registry["version"] == expected
    assert registry["packages"][0]["version"] == expected

    lock_text = (ROOT / "uv.lock").read_text(encoding="utf-8")
    package_block = re.search(
        r'\[\[package\]\]\s+name = "comfypilot"\s+version = "([^"]+)"',
        lock_text,
    )
    assert package_block is not None
    assert package_block.group(1) == expected


def test_public_docs_reference_current_version():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    expected = pyproject["project"]["version"]

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert f"# ComfyPilot v{expected}" in readme
    assert re.search(rf"## \[{re.escape(expected)}\]", changelog)


def test_tracked_public_files_are_ascii_clean():
    # README.md is deliberately excluded: it contains an intentional Unicode
    # ASCII-art banner (box-drawing characters). The ASCII gate still protects
    # every other tracked surface where stray smart quotes / em-dashes from
    # copy-paste would be a real problem.
    tracked_paths = [
        ROOT / "CHANGELOG.md",
        ROOT / "docs" / "MANUAL.md",
        ROOT / "pyproject.toml",
        ROOT / "mcp" / "manifest.json",
        ROOT / ".claude-plugin" / "plugin.json",
        ROOT / ".claude-plugin" / "marketplace.json",
        ROOT / "skills" / "comfypilot-core" / "SKILL.md",
    ]

    tracked_paths.extend(sorted((ROOT / "src").rglob("*.py")))
    tracked_paths.extend(sorted((ROOT / "tests").rglob("*.py")))

    for path in tracked_paths:
        text = path.read_text(encoding="utf-8")
        assert text.isascii(), f"{path.relative_to(ROOT)} contains non-ASCII text"

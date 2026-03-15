"""Tests for release metadata consistency."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_release_versions_match():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    expected = pyproject["project"]["version"]

    package_ns: dict[str, str] = {}
    exec((ROOT / "src" / "comfy_mcp" / "__init__.py").read_text(), package_ns)
    assert package_ns["__version__"] == expected

    manifest = json.loads((ROOT / "mcp" / "manifest.json").read_text())
    assert manifest["version"] == expected

    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["version"] == expected

    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert marketplace["plugins"][0]["version"] == expected


def test_public_docs_reference_current_version():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    expected = pyproject["project"]["version"]

    readme = (ROOT / "README.md").read_text()
    changelog = (ROOT / "CHANGELOG.md").read_text()

    assert f"# ComfyPilot v{expected}" in readme
    assert re.search(rf"## \[{re.escape(expected)}\]", changelog)


def test_tracked_public_files_are_ascii_clean():
    tracked_paths = [
        ROOT / "README.md",
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
        text = path.read_text()
        assert text.isascii(), f"{path.relative_to(ROOT)} contains non-ASCII text"

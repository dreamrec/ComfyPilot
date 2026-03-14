"""DocsStore — disk cache for ComfyUI documentation."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def _content_hash(text: str) -> str:
    """SHA-256 prefix for change detection."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class DocsStore:
    """Manages on-disk documentation cache at ~/.comfypilot/docs/."""

    def __init__(self, storage_dir: str | None = None):
        self._dir = Path(storage_dir or Path.home() / ".comfypilot" / "docs")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._embedded_dir = self._dir / "embedded"
        self._embedded_dir.mkdir(exist_ok=True)
        self._manifest = self._load_manifest()

    def _manifest_path(self) -> Path:
        return self._dir / "manifest.json"

    def _load_manifest(self) -> dict[str, Any]:
        path = self._manifest_path()
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_manifest(self) -> None:
        path = self._manifest_path()
        path.write_text(json.dumps(self._manifest, indent=2))

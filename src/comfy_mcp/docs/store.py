"""DocsStore — disk cache for ComfyUI documentation."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("comfypilot.docs")


def _content_hash(text: str) -> str:
    """SHA-256 prefix for change detection."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _sanitize_filename(class_name: str) -> str:
    """Convert a node class name to a filesystem-safe filename."""
    return re.sub(r'[^\w\-.]', '_', class_name)


class DocsStore:
    """Manages on-disk documentation cache at ~/.comfypilot/docs/."""

    def __init__(self, storage_dir: str | None = None, fetcher: Any | None = None):
        self._fetcher = fetcher
        self._dir = Path(storage_dir or Path.home() / ".comfypilot" / "docs")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._embedded_dir = self._dir / "embedded"
        self._embedded_dir.mkdir(exist_ok=True)
        self._manifest = self._load_manifest()
        self._name_to_file: dict[str, str] = {}
        self._rebuild_name_map()

    def _manifest_path(self) -> Path:
        return self._dir / "manifest.json"

    def _load_manifest(self) -> dict[str, Any]:
        path = self._manifest_path()
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_manifest(self) -> None:
        path = self._manifest_path()
        path.write_text(json.dumps(self._manifest, indent=2), encoding="utf-8")

    def _rebuild_name_map(self) -> None:
        self._name_to_file = {}
        for class_name, info in self._manifest.get("embedded", {}).items():
            self._name_to_file[class_name] = info.get("filename", _sanitize_filename(class_name))

    def save_embedded(self, class_name: str, content: str) -> None:
        safe_name = _sanitize_filename(class_name)
        path = self._embedded_dir / f"{safe_name}.md"
        path.write_text(content, encoding="utf-8")
        if "embedded" not in self._manifest:
            self._manifest["embedded"] = {}
        self._manifest["embedded"][class_name] = {
            "filename": safe_name,
            "hash": _content_hash(content),
            "cached_at": time.time(),
        }
        self._manifest["last_updated"] = time.time()
        self._name_to_file[class_name] = safe_name
        self._save_manifest()

    def get_embedded(self, class_name: str) -> str | None:
        safe_name = self._name_to_file.get(class_name, _sanitize_filename(class_name))
        path = self._embedded_dir / f"{safe_name}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def is_stale(self, max_age: float = 300) -> bool:
        last = self._manifest.get("last_updated")
        if last is None:
            return True
        return (time.time() - last) >= max_age

    def content_hash(self) -> str:
        hashes = sorted(
            info.get("hash", "")
            for info in self._manifest.get("embedded", {}).values()
        )
        combined = "|".join(hashes)
        return _content_hash(combined)

    def clear(self) -> None:
        for path in self._embedded_dir.glob("*.md"):
            path.unlink()
        llms_path = self._dir / "llms-full.txt"
        if llms_path.exists():
            llms_path.unlink()
        sections_path = self._dir / "sections.json"
        if sections_path.exists():
            sections_path.unlink()
        self._manifest = {}
        self._name_to_file = {}
        self._save_manifest()

    async def refresh(self) -> None:
        """Re-fetch documentation from source."""
        if self._fetcher is None:
            logger.warning("DocsStore.refresh() called without fetcher instance, skipping")
            return
        content = await self._fetcher.fetch_llms_full()
        if content:
            self.save_llms(content)

    def list_embedded_classes(self) -> list[str]:
        return list(self._manifest.get("embedded", {}).keys())

    def summary(self) -> dict:
        embedded_count = len(self._manifest.get("embedded", {}))
        has_llms = (self._dir / "llms-full.txt").exists()
        has_sections = (self._dir / "sections.json").exists()
        return {
            "embedded_docs": embedded_count,
            "llms_full_cached": has_llms,
            "sections_indexed": has_sections,
            "stale": self.is_stale(),
            "last_updated": self._manifest.get("last_updated"),
            "content_hash": self.content_hash() if embedded_count > 0 else None,
        }

    def save_llms(self, content: str) -> None:
        llms_path = self._dir / "llms-full.txt"
        llms_path.write_text(content, encoding="utf-8")
        self._manifest["llms_hash"] = _content_hash(content)
        self._manifest["llms_cached_at"] = time.time()
        self._manifest["last_updated"] = time.time()
        self._save_manifest()
        self._build_section_index(content)

    def _build_section_index(self, content: str) -> None:
        lines = content.split("\n")
        sections = []
        current: dict | None = None
        for i, line in enumerate(lines):
            if line.startswith("#"):
                if current is not None:
                    current["end_line"] = i - 1
                    sections.append(current)
                level = len(line) - len(line.lstrip("#"))
                title = line.lstrip("#").strip()
                current = {
                    "title": title,
                    "start_line": i,
                    "end_line": len(lines) - 1,
                    "level": level,
                }
        if current is not None:
            current["end_line"] = len(lines) - 1
            sections.append(current)
        sections_path = self._dir / "sections.json"
        sections_path.write_text(json.dumps(sections, indent=2), encoding="utf-8")

    def get_section(self, topic: str) -> dict | None:
        sections_path = self._dir / "sections.json"
        if not sections_path.exists():
            return None
        llms_path = self._dir / "llms-full.txt"
        if not llms_path.exists():
            return None
        sections = json.loads(sections_path.read_text(encoding="utf-8"))
        topic_lower = topic.lower()
        best = None
        for s in sections:
            if topic_lower == s["title"].lower():
                best = s
                break
            if topic_lower in s["title"].lower() and best is None:
                best = s
        if best is None:
            return None
        lines = llms_path.read_text(encoding="utf-8").split("\n")
        content = "\n".join(lines[best["start_line"]:best["end_line"] + 1])
        return {
            "title": best["title"],
            "level": best["level"],
            "content": content,
        }

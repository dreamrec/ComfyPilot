"""KnowledgeStore — protocol for subsystems that cache data to ~/.comfypilot/.

This is a duck-typed interface, not a base class. Each subsystem implements
these methods independently. The Protocol class is for type checking only.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class KnowledgeStore(Protocol):
    """Interface that cacheable subsystems implement."""

    def is_stale(self, max_age: float = 300) -> bool:
        """Check if cached data is missing or older than max_age seconds."""
        ...

    def content_hash(self) -> str:
        """SHA-256 prefix of cached content for change detection."""
        ...

    def summary(self) -> dict[str, Any]:
        """Return compact status summary."""
        ...

    def clear(self) -> None:
        """Remove all cached data."""
        ...


def atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically (write to temp, then rename).

    Prevents corruption from concurrent writes or crashes mid-write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    closed = False
    try:
        os.write(fd, content.encode())
        os.close(fd)
        closed = True
        # On Windows, need to remove target first
        if path.exists():
            path.unlink()
        os.rename(tmp_path, str(path))
    except Exception:
        if not closed:
            os.close(fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

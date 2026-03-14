"""KnowledgeManager — unified state tracking across all knowledge stores.

Manages state.json for cross-subsystem staleness tracking and provides
orchestration for refresh-all and clear-cache operations.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from comfy_mcp.knowledge.store import atomic_write

logger = logging.getLogger("comfypilot.knowledge")


class KnowledgeManager:
    """Orchestrates multiple KnowledgeStore instances."""

    def __init__(self, stores: dict[str, Any], state_dir: str | None = None):
        self._stores = stores
        self._dir = Path(state_dir or Path.home() / ".comfypilot")
        self._dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self) -> Path:
        return self._dir / "state.json"

    def status(self) -> dict[str, Any]:
        """Aggregate status from all registered stores."""
        stores_status = {}
        any_stale = False

        for name, store in self._stores.items():
            try:
                stale = store.is_stale()
                stores_status[name] = {
                    "stale": stale,
                    "content_hash": store.content_hash(),
                    "summary": store.summary(),
                }
                if stale:
                    any_stale = True
            except Exception as exc:
                stores_status[name] = {"error": str(exc), "stale": True}
                any_stale = True

        return {
            "store_count": len(self._stores),
            "any_stale": any_stale,
            "stores": stores_status,
            "checked_at": time.time(),
        }

    async def refresh_all(self) -> dict[str, Any]:
        """Refresh all registered stores."""
        results = {}
        for name, store in self._stores.items():
            try:
                await store.refresh()
                results[name] = {"status": "ok"}
            except Exception as exc:
                logger.warning("Failed to refresh %s: %s", name, exc)
                results[name] = {"status": "error", "error": str(exc)}

        self.save_state()
        return {"refreshed": results}

    def clear(self, subsystem: str = "all") -> dict[str, Any]:
        """Clear cached data for one or all subsystems."""
        cleared = []
        if subsystem == "all":
            for name, store in self._stores.items():
                store.clear()
                cleared.append(name)
        elif subsystem in self._stores:
            self._stores[subsystem].clear()
            cleared.append(subsystem)
        else:
            return {"error": f"Unknown subsystem: {subsystem}", "available": list(self._stores.keys())}

        self.save_state()
        return {"cleared": cleared}

    def save_state(self) -> None:
        """Persist unified state to state.json."""
        state = {
            "saved_at": time.time(),
            "stores": {},
        }
        for name, store in self._stores.items():
            try:
                state["stores"][name] = {
                    "content_hash": store.content_hash(),
                    "stale": store.is_stale(),
                }
            except Exception as exc:
                state["stores"][name] = {"error": str(exc)}

        atomic_write(self._state_path(), json.dumps(state, indent=2))

    def load_state(self) -> dict[str, Any] | None:
        """Load state from disk. Returns None if missing or corrupted."""
        path = self._state_path()
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("state.json corrupted, treating all stores as stale")
            return None

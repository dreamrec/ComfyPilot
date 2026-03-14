"""Migration helper — manifest.json -> state.json with .bak backup.

Handles idempotent migration: skips if state.json already exists,
creates .bak backup of manifest.json before migrating.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from comfy_mcp.knowledge.store import atomic_write

logger = logging.getLogger("comfypilot.knowledge.migration")


def migrate_manifest_to_state(data_dir: Path) -> bool:
    """Migrate manifest.json to state.json if needed.

    Returns True if migration was performed, False if skipped.
    """
    data_dir = Path(data_dir)
    manifest_path = data_dir / "manifest.json"
    state_path = data_dir / "state.json"
    backup_path = data_dir / "manifest.json.bak"

    # Skip if no manifest to migrate
    if not manifest_path.exists():
        return False

    # Skip if already migrated (state.json exists)
    if state_path.exists():
        logger.info("state.json already exists, skipping migration")
        return False

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot read manifest.json for migration: %s", exc)
        return False

    # Create backup
    shutil.copy2(str(manifest_path), str(backup_path))

    # Build state from manifest
    state = {
        "migrated_from": "manifest.json",
        **manifest_data,
    }

    atomic_write(state_path, json.dumps(state, indent=2))
    logger.info("Migrated manifest.json -> state.json (backup at manifest.json.bak)")
    return True

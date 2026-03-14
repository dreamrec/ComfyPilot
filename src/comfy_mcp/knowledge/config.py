"""ConfigManager — persistent user preferences with env var override.

Reads/writes ~/.comfypilot/config.json. Environment variables always
take precedence over file-based config.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from comfy_mcp.knowledge.store import atomic_write

# Default configuration
DEFAULTS = {
    "safety": {
        "vram_warn_pct": 80,
        "vram_block_pct": 95,
        "max_queue_size": 10,
    },
    "output": {
        "default_dir": "~/comfypilot_output",
    },
    "cache": {
        "max_age_seconds": 300,
        "auto_refresh": True,
    },
}

# Map from dotted config key to environment variable name
ENV_MAP = {
    "safety.vram_warn_pct": "COMFY_VRAM_WARN_PCT",
    "safety.vram_block_pct": "COMFY_VRAM_BLOCK_PCT",
    "safety.max_queue_size": "COMFY_MAX_QUEUE_SIZE",
    "output.default_dir": "COMFY_OUTPUT_DIR",
    "cache.max_age_seconds": "COMFY_CACHE_MAX_AGE",
}


class ConfigManager:
    """Manages persistent configuration with env var override."""

    def __init__(self, config_dir: str | None = None):
        self._dir = Path(config_dir or Path.home() / ".comfypilot")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._config = self._load()

    def _config_path(self) -> Path:
        return self._dir / "config.json"

    def _load(self) -> dict[str, Any]:
        """Load config from disk, falling back to defaults."""
        import copy
        config = copy.deepcopy(DEFAULTS)
        path = self._config_path()
        if path.exists():
            try:
                disk = json.loads(path.read_text())
                # Deep merge disk values into defaults
                for section, values in disk.items():
                    if section in config and isinstance(values, dict):
                        config[section].update(values)
                    else:
                        config[section] = values
            except (json.JSONDecodeError, OSError):
                pass
        return config

    def _save(self) -> None:
        """Persist config to disk atomically."""
        atomic_write(self._config_path(), json.dumps(self._config, indent=2))

    def get(self, key: str) -> Any:
        """Get a config value by dotted key (e.g., 'safety.vram_warn_pct').

        Environment variables override file-based values.
        """
        # Check env override first
        env_name = ENV_MAP.get(key)
        if env_name:
            env_val = os.environ.get(env_name)
            if env_val is not None:
                # Try to cast to the same type as default
                default_val = self._get_from_dict(key)
                if isinstance(default_val, bool):
                    return env_val.lower() in ("true", "1", "yes")
                if isinstance(default_val, int):
                    try:
                        return int(env_val)
                    except ValueError:
                        pass
                if isinstance(default_val, float):
                    try:
                        return float(env_val)
                    except ValueError:
                        pass
                return env_val

        return self._get_from_dict(key)

    def _get_from_dict(self, key: str) -> Any:
        """Get value from in-memory config dict."""
        parts = key.split(".")
        current = self._config
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    def set(self, key: str, value: Any) -> None:
        """Set a config value by dotted key and persist to disk."""
        parts = key.split(".")
        current = self._config
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
        self._save()

    def get_all(self) -> dict[str, Any]:
        """Return the full config dict (file values, not env overrides)."""
        import copy
        return copy.deepcopy(self._config)

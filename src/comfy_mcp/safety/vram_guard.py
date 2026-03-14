"""VRAMGuard — VRAM monitoring and safety enforcement.

Monitors GPU VRAM usage and provides safety checks before operations.
"""
from __future__ import annotations

from typing import Any


class VRAMGuard:
    """Monitors and enforces VRAM safety thresholds."""

    def __init__(self, client: Any, warn_pct: float = 80.0, block_pct: float = 95.0):
        self._client = client
        self.warn_pct = warn_pct
        self.block_pct = block_pct
        self._limits = {"max_queue": 10, "timeout": 300}

    async def check_vram(self) -> dict:
        """Check current VRAM usage and return status (ok/warn/critical)."""
        stats = await self._client.get_system_stats()
        devices = stats.get("devices", [])
        if not devices:
            return {"status": "unknown", "message": "No GPU devices found", "devices": []}

        device_infos = []
        overall_status = "ok"
        for dev in devices:
            total = dev.get("vram_total", 0)
            free = dev.get("vram_free", 0)
            used = total - free
            used_pct = round(used / total * 100, 1) if total > 0 else 0

            status = "ok"
            if used_pct >= self.block_pct:
                status = "critical"
                overall_status = "critical"
            elif used_pct >= self.warn_pct:
                status = "warn"
                if overall_status != "critical":
                    overall_status = "warn"

            device_infos.append({
                "name": dev.get("name", "unknown"),
                "vram_total": total,
                "vram_free": free,
                "vram_used": used,
                "vram_used_pct": used_pct,
                "status": status,
            })

        return {
            "status": overall_status,
            "vram_used_pct": device_infos[0]["vram_used_pct"] if device_infos else 0,
            "devices": device_infos,
        }

    async def validate_before_queue(self) -> dict:
        """Pre-flight check before queueing a prompt. Checks VRAM headroom and queue size."""
        vram = await self.check_vram()
        queue = await self._client.get_queue()
        running = len(queue.get("queue_running", []))
        pending = len(queue.get("queue_pending", []))
        total_queued = running + pending

        issues = []
        if vram["status"] == "critical":
            issues.append(f"VRAM critically high at {vram['vram_used_pct']}%")
        if total_queued >= self._limits["max_queue"]:
            issues.append(f"Queue full: {total_queued} items (max {self._limits['max_queue']})")

        return {
            "safe_to_queue": len(issues) == 0,
            "vram_status": vram["status"],
            "vram_used_pct": vram["vram_used_pct"],
            "queue_running": running,
            "queue_pending": pending,
            "issues": issues,
        }

    def set_limits(self, **kwargs) -> dict:
        """Update safety thresholds."""
        if "warn_pct" in kwargs:
            self.warn_pct = float(kwargs["warn_pct"])
        if "block_pct" in kwargs:
            self.block_pct = float(kwargs["block_pct"])
        if "max_queue" in kwargs:
            self._limits["max_queue"] = int(kwargs["max_queue"])
        if "timeout" in kwargs:
            self._limits["timeout"] = int(kwargs["timeout"])
        return {
            "warn_pct": self.warn_pct,
            "block_pct": self.block_pct,
            "max_queue": self._limits["max_queue"],
            "timeout": self._limits["timeout"],
        }

    async def emergency_stop(self) -> dict:
        """Emergency stop: interrupt current job, clear queue, free VRAM."""
        await self._client.interrupt()
        await self._client.clear_queue()
        await self._client.free_vram(unload_models=True, free_memory=True)
        return {
            "status": "stopped",
            "actions": ["interrupted", "queue_cleared", "vram_freed"],
        }

    async def detect_instability(self) -> dict:
        """Check for stuck jobs, error spikes, OOM patterns."""
        stats = await self._client.get_system_stats()
        queue = await self._client.get_queue()

        issues = []
        devices = stats.get("devices", [])
        for dev in devices:
            total = dev.get("vram_total", 0)
            free = dev.get("vram_free", 0)
            if total > 0 and free / total < 0.05:
                issues.append(f"Near-OOM: {dev.get('name', 'GPU')} has <5% VRAM free")

        running = queue.get("queue_running", [])

        return {
            "stable": len(issues) == 0,
            "issues": issues,
            "queue_running": len(running),
            "queue_pending": len(queue.get("queue_pending", [])),
        }

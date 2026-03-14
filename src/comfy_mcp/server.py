"""FastMCP server for ComfyPilot.

Entry point: `comfypilot` CLI command.
Initializes the MCP server with lifespan management for persistent connections.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from comfy_mcp.comfy_client import ComfyClient


@asynccontextmanager
async def comfy_lifespan(server: FastMCP):
    """Manage ComfyClient and subsystem lifecycles."""
    url = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
    api_key = os.environ.get("COMFY_API_KEY", "")
    timeout = float(os.environ.get("COMFY_TIMEOUT", "300"))
    snapshot_limit = int(os.environ.get("COMFY_SNAPSHOT_LIMIT", "50"))

    client = ComfyClient(url, api_key=api_key, timeout=timeout)
    await client.connect()

    # Subsystem managers — imported lazily to avoid circular deps
    from comfy_mcp.events.event_manager import EventManager
    from comfy_mcp.jobs.job_tracker import JobTracker
    from comfy_mcp.memory.snapshot_manager import SnapshotManager
    from comfy_mcp.memory.technique_store import TechniqueStore
    from comfy_mcp.safety.vram_guard import VRAMGuard

    event_mgr = EventManager(client)
    snapshot_mgr = SnapshotManager(max_snapshots=snapshot_limit)
    technique_store = TechniqueStore()
    vram_guard = VRAMGuard(client)
    job_tracker = JobTracker(client, event_mgr)

    try:
        yield {
            "comfy_client": client,
            "event_manager": event_mgr,
            "snapshot_manager": snapshot_mgr,
            "technique_store": technique_store,
            "vram_guard": vram_guard,
            "job_tracker": job_tracker,
        }
    finally:
        await event_mgr.shutdown()
        await client.close()


mcp = FastMCP("comfypilot", lifespan=comfy_lifespan)


def _register_tools():
    """Import tool modules to trigger @mcp.tool() registration."""
    import comfy_mcp.tool_registry  # noqa: F401


def main():
    """CLI entry point."""
    _register_tools()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

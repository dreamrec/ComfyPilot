"""FastMCP server for ComfyPilot.

Entry point: `comfypilot` CLI command.
Initializes the MCP server with lifespan management for persistent connections.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from comfy_mcp.comfy_client import ComfyClient

# Module-level reference for resources (set during lifespan)
_shared_client: ComfyClient | None = None


@asynccontextmanager
async def comfy_lifespan(server: FastMCP):
    """Manage ComfyClient and subsystem lifecycles."""
    global _shared_client

    url = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
    api_key = os.environ.get("COMFY_API_KEY", "")
    timeout = float(os.environ.get("COMFY_TIMEOUT", "300"))
    snapshot_limit = int(os.environ.get("COMFY_SNAPSHOT_LIMIT", "50"))
    auth_method = os.environ.get("COMFY_AUTH_METHOD", "auto")

    client = ComfyClient(url, api_key=api_key, auth_method=auth_method, timeout=timeout)
    await client.connect()
    await client.probe_capabilities()
    _shared_client = client

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

    await event_mgr.start()

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
        _shared_client = None
        await event_mgr.shutdown()
        await client.close()


mcp = FastMCP("comfypilot", lifespan=comfy_lifespan)


@mcp.resource("comfy://system/info")
async def system_info_resource() -> str:
    """System stats, GPU info, ComfyUI version."""
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    result = await _shared_client.get_system_stats()
    return json.dumps(result, indent=2)


@mcp.resource("comfy://nodes/catalog")
async def nodes_catalog_resource() -> str:
    """Node catalog preview (first 100 names). Use comfy_list_node_types for full paginated access."""
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    result = await _shared_client.get_object_info()
    return json.dumps({
        "node_count": len(result),
        "preview_count": min(100, len(result)),
        "nodes": list(result.keys())[:100],
        "note": "Preview only. Use comfy_list_node_types tool for full paginated catalog.",
    })


@mcp.resource("comfy://models/{folder}")
async def models_resource(folder: str) -> str:
    """List models in a specific folder (checkpoints, loras, etc)."""
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    result = await _shared_client.get_models(folder)
    return json.dumps(result, indent=2)


@mcp.resource("comfy://embeddings")
async def embeddings_resource() -> str:
    """List all available embeddings."""
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    result = await _shared_client.get_embeddings()
    return json.dumps(result, indent=2)


@mcp.resource("comfy://server/capabilities")
async def capabilities_resource() -> str:
    """Detected ComfyUI server capabilities and profile."""
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    return json.dumps(_shared_client.capabilities, indent=2)


def _register_tools():
    """Import tool modules to trigger @mcp.tool() registration."""
    import comfy_mcp.tool_registry  # noqa: F401


def main():
    """CLI entry point."""
    _register_tools()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

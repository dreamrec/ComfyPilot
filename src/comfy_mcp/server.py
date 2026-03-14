"""FastMCP server for ComfyPilot.

Entry point: `comfypilot` CLI command.
Initializes the MCP server with lifespan management for persistent connections.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from comfy_mcp.comfy_client import ComfyClient

logger = logging.getLogger("comfypilot.server")

# Module-level references for resources (set during lifespan)
_shared_client: ComfyClient | None = None
_shared_install_graph = None
_shared_docs_store = None
_shared_template_index = None
_shared_knowledge_manager = None
_shared_registry_index = None
_shared_ecosystem_registry = None
_shared_model_awareness_scanner = None


@asynccontextmanager
async def comfy_lifespan(server: FastMCP):
    """Manage ComfyClient and subsystem lifecycles."""
    global _shared_client, _shared_install_graph, _shared_docs_store, _shared_template_index, _shared_knowledge_manager, _shared_registry_index, _shared_ecosystem_registry, _shared_model_awareness_scanner

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
    from comfy_mcp.install.install_graph import InstallGraph
    from comfy_mcp.jobs.job_tracker import JobTracker
    from comfy_mcp.memory.snapshot_manager import SnapshotManager
    from comfy_mcp.memory.technique_store import TechniqueStore
    from comfy_mcp.safety.vram_guard import VRAMGuard

    event_mgr = EventManager(client)
    snapshot_mgr = SnapshotManager(max_snapshots=snapshot_limit)
    technique_store = TechniqueStore()
    vram_guard = VRAMGuard(client)
    job_tracker = JobTracker(client, event_mgr)
    install_graph = InstallGraph(client)
    _bg_task = None
    # Try loading install graph from disk cache for faster startup
    if install_graph.load_from_disk() and not install_graph.is_stale():
        logger.info("Loaded install graph from disk cache")
    elif install_graph.load_from_disk():
        # Cache exists but is stale — use it immediately, refresh in background
        logger.info("Install graph cache stale, scheduling background refresh")
        async def _bg_refresh():
            try:
                await install_graph.refresh()
                install_graph.save_to_disk()
                logger.info("Background install graph refresh complete")
            except Exception as exc:
                logger.warning("Background refresh failed: %s", exc)
        _bg_task = asyncio.create_task(_bg_refresh())
    else:
        # No cache at all — must block on first refresh
        await install_graph.refresh()
        install_graph.save_to_disk()
    _shared_install_graph = install_graph

    from comfy_mcp.docs.store import DocsStore
    from comfy_mcp.docs.fetcher import DocsFetcher
    docs_fetcher = DocsFetcher()
    docs_store = DocsStore(fetcher=docs_fetcher)
    _shared_docs_store = docs_store

    from comfy_mcp.templates.discovery import TemplateDiscovery
    from comfy_mcp.templates.index import TemplateIndex
    template_discovery = TemplateDiscovery(client)
    template_index = TemplateIndex(discovery=template_discovery)
    _shared_template_index = template_index

    from comfy_mcp.knowledge.config import ConfigManager
    from comfy_mcp.knowledge.manager import KnowledgeManager

    config_manager = ConfigManager()

    # Build stores dict dynamically — only include subsystems that are available
    stores: dict = {"install_graph": install_graph}
    if docs_store is not None:
        stores["docs"] = docs_store
    if template_index is not None:
        stores["templates"] = template_index

    knowledge_manager = KnowledgeManager(stores)
    _shared_knowledge_manager = knowledge_manager

    from comfy_mcp.registry.client import RegistryClient
    from comfy_mcp.registry.index import RegistryIndex

    registry_client = RegistryClient()
    registry_index = RegistryIndex()
    _shared_registry_index = registry_index

    from comfy_mcp.ecosystem import EcosystemRegistry, ModelAwarenessScanner

    ecosystem_registry = EcosystemRegistry()
    model_awareness_scanner = ModelAwarenessScanner(ecosystem_registry)
    _shared_ecosystem_registry = ecosystem_registry
    _shared_model_awareness_scanner = model_awareness_scanner

    if client.capabilities.get("ws_available", False):
        await event_mgr.start()

    try:
        yield {
            "comfy_client": client,
            "event_manager": event_mgr,
            "snapshot_manager": snapshot_mgr,
            "technique_store": technique_store,
            "vram_guard": vram_guard,
            "job_tracker": job_tracker,
            "install_graph": install_graph,
            "docs_store": docs_store,
            "docs_fetcher": docs_fetcher,
            "template_discovery": template_discovery,
            "template_index": template_index,
            "knowledge_manager": knowledge_manager,
            "config_manager": config_manager,
            "registry_client": registry_client,
            "registry_index": registry_index,
            "ecosystem_registry": ecosystem_registry,
            "model_awareness_scanner": model_awareness_scanner,
        }
    finally:
        _shared_client = None
        _shared_install_graph = None
        _shared_docs_store = None
        _shared_template_index = None
        _shared_knowledge_manager = None
        _shared_registry_index = None
        _shared_ecosystem_registry = None
        _shared_model_awareness_scanner = None
        if _bg_task is not None and not _bg_task.done():
            _bg_task.cancel()
        await registry_client.close()
        await event_mgr.shutdown()
        await docs_fetcher.close()
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


@mcp.resource("comfy://install/graph")
async def install_graph_resource() -> str:
    """Install graph summary — node counts, model counts, hashes for change detection."""
    if _shared_install_graph is None:
        return json.dumps({"error": "Not initialized"})
    return json.dumps(_shared_install_graph.summary(), indent=2)


@mcp.resource("comfy://knowledge/full")
async def knowledge_full_resource() -> str:
    """Complete knowledge status across all subsystems."""
    if _shared_knowledge_manager is None:
        return json.dumps({"status": "not_initialized"})
    return json.dumps(_shared_knowledge_manager.status(), indent=2)


@mcp.resource("comfy://server/capabilities")
async def capabilities_resource() -> str:
    """Detected ComfyUI server capabilities and profile."""
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    return json.dumps(_shared_client.capabilities, indent=2)


@mcp.resource("comfy://docs/status")
async def docs_status_resource() -> str:
    """Documentation cache status — freshness, counts, hashes."""
    if _shared_docs_store is None:
        return json.dumps({"status": "not_initialized"})
    return json.dumps(_shared_docs_store.summary(), indent=2)


@mcp.resource("comfy://templates/index")
async def templates_index_resource() -> str:
    """Template index summary -- counts, categories, sources."""
    if _shared_template_index is None:
        return json.dumps({"status": "not_initialized"})
    return json.dumps(_shared_template_index.summary(), indent=2)


@mcp.resource("comfy://registry/status")
async def registry_status_resource() -> str:
    """Registry cache stats and index coverage."""
    if _shared_registry_index is None:
        return json.dumps({"status": "not_initialized"})
    return json.dumps(_shared_registry_index.summary(), indent=2)


@mcp.resource("comfy://ecosystem/registry")
async def ecosystem_registry_resource() -> str:
    """Curated model families, provider coverage, and verification metadata."""
    if _shared_ecosystem_registry is None:
        return json.dumps({"status": "not_initialized"})
    summary = _shared_ecosystem_registry.summary()
    return json.dumps({
        "summary": summary,
        "families": _shared_ecosystem_registry.list_entries(kind="family"),
        "ecosystems": _shared_ecosystem_registry.list_entries(kind="ecosystem"),
        "providers": _shared_ecosystem_registry.list_entries(kind="provider"),
    }, indent=2)


@mcp.resource("comfy://environment/model-awareness")
async def model_awareness_resource() -> str:
    """Detected model families, provider signals, and capability summary for this install."""
    if _shared_model_awareness_scanner is None or _shared_install_graph is None or _shared_client is None:
        return json.dumps({"status": "not_initialized"})
    snapshot = _shared_install_graph.snapshot or {}
    result = _shared_model_awareness_scanner.scan(snapshot, capabilities=_shared_client.capabilities)
    return json.dumps(result, indent=2)


def _register_tools():
    """Import tool modules to trigger @mcp.tool() registration."""
    import comfy_mcp.tool_registry  # noqa: F401


def main():
    """CLI entry point."""
    _register_tools()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

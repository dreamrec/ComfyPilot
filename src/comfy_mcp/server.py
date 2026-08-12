"""FastMCP server for ComfyPilot.

Entry point: `comfypilot` CLI command.
Initializes the MCP server with lifespan management for persistent connections.
"""

from __future__ import annotations

import json
import os
import inspect
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# ``python -m comfy_mcp.server`` initially publishes this module as
# ``__main__``. Tool modules import ``comfy_mcp.server`` to reach ``mcp``;
# without this alias Python executes the file a second time and the decorators
# populate a different FastMCP instance from the one serving stdio. The
# console-script entry point already imports the canonical name, so it is
# intentionally unchanged by this branch.
if __name__ == "__main__":
    sys.modules.setdefault("comfy_mcp.server", sys.modules[__name__])

from mcp.server.fastmcp import FastMCP

from comfy_mcp import __version__
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
    snapshot_setting = os.environ.get("COMFY_SNAPSHOT_DIR")
    if snapshot_setting is None:
        snapshot_dir: str | None = str(Path.home() / ".comfypilot" / "snapshots")
    elif snapshot_setting.strip().lower() in {"", "0", "false", "off", "none"}:
        snapshot_dir = None
    else:
        snapshot_dir = str(Path(snapshot_setting).expanduser())
    auth_method = os.environ.get("COMFY_AUTH_METHOD", "auto")

    client = ComfyClient(url, api_key=api_key, auth_method=auth_method, timeout=timeout)
    await client.connect()
    await client.probe_capabilities()
    _shared_client = client

    # Subsystem managers - imported lazily to avoid circular deps
    from comfy_mcp.events.event_manager import EventManager
    from comfy_mcp.jobs.job_tracker import JobTracker
    from comfy_mcp.memory.snapshot_manager import SnapshotManager
    from comfy_mcp.memory.technique_store import TechniqueStore
    from comfy_mcp.safety.vram_guard import VRAMGuard

    event_mgr = EventManager(client)
    snapshot_mgr = SnapshotManager(
        max_snapshots=snapshot_limit,
        storage_dir=snapshot_dir,
    )
    technique_store = TechniqueStore()
    vram_guard = VRAMGuard(client)
    job_tracker = JobTracker(client, event_mgr)

    if client.capabilities.get("ws_available", True):
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
# MCP SDK 1.26 does not forward an application version through FastMCP's
# constructor, so set it on the underlying protocol server. Otherwise the
# initialize handshake reports the SDK version instead of ComfyPilot's.
mcp._mcp_server.version = __version__
_tool_signature = inspect.signature(FastMCP.tool)
_tool_supports_annotations = "annotations" in _tool_signature.parameters
_original_tool = mcp.tool


def _compat_tool(*args, **kwargs):
    """Ignore tool annotations when running against older MCP releases."""
    if not _tool_supports_annotations and "annotations" in kwargs:
        kwargs = dict(kwargs)
        kwargs.pop("annotations", None)
    return _original_tool(*args, **kwargs)


mcp.tool = _compat_tool  # type: ignore[assignment]


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


@mcp.resource("comfy://templates/catalog")
async def templates_resource() -> str:
    """Workflow templates advertised by ComfyUI core and custom nodes.

    Comes from ComfyUI's /workflow_templates endpoint (v0.17+). Returns
    a mapping of custom-node package -> list of template workflow JSON names.
    """
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    try:
        result = await _shared_client.get_workflow_templates()
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Could not fetch workflow templates: {e}"})


@mcp.resource("comfy://docs/{node_class}")
async def node_docs_resource(node_class: str) -> str:
    """Embedded documentation for a node class.

    Tries official localized Markdown and structured fork routes, then falls
    back to the node's object_info description.
    """
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    if not node_class:
        return json.dumps({"error": "node_class is required"})

    docs = None
    try:
        docs = await _shared_client.get_node_docs(node_class)
    except Exception as e:
        return json.dumps({"error": f"Could not fetch docs for {node_class!r}: {e}"})

    if docs is not None:
        return json.dumps({"node_class": node_class, "source": "docs_endpoint", **docs}, indent=2)

    # Fall back to object_info description.
    try:
        info = await _shared_client.get_object_info(node_class)
    except Exception:
        info = None
    if isinstance(info, dict):
        # /object_info/{node_class} returns either the raw class info or
        # {class_type: info}. Normalize.
        raw = info.get(node_class, info) if node_class in info else info
        if isinstance(raw, dict):
            description = raw.get("description", "")
            category = raw.get("category", "")
            return json.dumps({
                "node_class": node_class,
                "source": "object_info_fallback",
                "description": description,
                "category": category,
            }, indent=2)

    return json.dumps({
        "node_class": node_class,
        "error": "No docs and no object_info entry available",
    })


@mcp.resource("comfy://api/openapi")
async def openapi_resource() -> str:
    """OpenAPI 3.1 spec when the deployment serves one over HTTP.

    The full spec is too large to inline in tool descriptions, but exposing
    it as an MCP resource lets agents fetch it on demand for endpoint
    introspection, schema-backed validation, or auto-generated client code.
    Returns {"error": ...} when the connected deployment exposes no spec.
    """
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    try:
        spec = await _shared_client.get_openapi_spec()
    except Exception as e:
        return json.dumps({"error": f"Could not fetch /openapi.json: {e}"})
    if spec is None:
        return json.dumps({
            "error": "ComfyUI did not return an OpenAPI spec",
            "hint": "This ComfyUI deployment does not expose /openapi.json",
        })
    return json.dumps(spec, indent=2)


@mcp.resource("comfy://nodes/catalog/{page}")
async def nodes_catalog_page(page: str) -> str:
    """Paginated node catalog - 100 names per page.

    URLs: comfy://nodes/catalog/0, comfy://nodes/catalog/1, ...
    Returns {page, total_pages, total_nodes, nodes: [class_type, ...]}.
    """
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    try:
        p = int(page)
    except (TypeError, ValueError):
        return json.dumps({"error": f"Invalid page: {page!r}"})
    if p < 0:
        return json.dumps({"error": f"Page must be >= 0, got {p}"})

    try:
        all_info = await _shared_client.get_object_info()
    except Exception as e:
        return json.dumps({"error": f"Could not fetch object_info: {e}"})

    keys = sorted(all_info.keys())
    total = len(keys)
    per_page = 100
    total_pages = (total + per_page - 1) // per_page if total else 0
    start = p * per_page
    end = start + per_page
    return json.dumps({
        "page": p,
        "total_pages": total_pages,
        "total_nodes": total,
        "per_page": per_page,
        "nodes": keys[start:end],
    }, indent=2)


@mcp.resource("comfy://nodes/by-category/{category}")
async def nodes_by_category(category: str) -> str:
    """All node class_types whose category starts with the given prefix.

    E.g. comfy://nodes/by-category/sampling returns all nodes in sampling
    and its sub-categories.
    """
    if _shared_client is None:
        return json.dumps({"error": "Server not initialized"})
    from comfy_mcp.schemas.node_schema import parse_object_info

    try:
        all_info = await _shared_client.get_object_info()
    except Exception as e:
        return json.dumps({"error": f"Could not fetch object_info: {e}"})

    hits = []
    for class_type, raw in all_info.items():
        try:
            schema = parse_object_info(class_type, raw)
        except Exception:
            continue
        if schema.category and schema.category.startswith(category):
            hits.append({"class_type": class_type, "category": schema.category})

    hits.sort(key=lambda h: h["class_type"])
    return json.dumps({
        "category_prefix": category,
        "count": len(hits),
        "nodes": hits,
    }, indent=2)


def _register_tools():
    """Import tool modules to trigger @mcp.tool() registration."""
    import comfy_mcp.tool_registry  # noqa: F401


def _parse_cli_args(argv: list[str] | None = None):
    """CLI parser factored out for testability."""
    import argparse
    parser = argparse.ArgumentParser(
        prog="comfypilot",
        description="ComfyPilot MCP server - controls ComfyUI via agent tools.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="MCP transport: 'stdio' for local clients (default), 'streamable-http' for remote/hosted use.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind when transport=streamable-http (default 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to bind when transport=streamable-http (default 8765).",
    )
    return parser.parse_args(argv)


def main():
    """CLI entry point."""
    args = _parse_cli_args()
    _register_tools()

    if args.transport == "streamable-http":
        # The MCP streamable-http transport binds via settings on the FastMCP
        # instance. Host/port come from the SDK's HTTP-transport config.
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

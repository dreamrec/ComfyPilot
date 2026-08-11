"""Read-only ComfyUI Env Manager environment and worker observability."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.errors import ComfyError
from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


def _error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ComfyError):
        return exc.to_dict()
    return {"message": str(exc), "error_type": type(exc).__name__}


async def _safe_get(client: Any, path: str) -> tuple[Any | None, dict[str, Any] | None]:
    try:
        return await client.get(path), None
    except Exception as exc:
        return None, _error(exc)


@mcp.tool(
    annotations={
        "title": "Inspect ComfyUI Isolated Environments",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_environment_status(
    configured_only: bool = True,
    limit: int = 500,
    ctx: Context = None,
) -> str:
    """Inspect Env Manager runtime, node environments, and workers.

    Each endpoint is independent: a broken ``/env-manager/runtime`` response
    is reported without hiding working environment/worker data. By default the
    often very large environment list is reduced to configured or materialized
    entries.
    """
    if limit < 1 or limit > 5000:
        return json.dumps({"error": "limit must be between 1 and 5000"})
    client = _client(ctx)
    (runtime, runtime_error), (environment_data, environments_error), (worker_data, workers_error) = (
        await asyncio.gather(
            _safe_get(client, "/env-manager/runtime"),
            _safe_get(client, "/env-manager/environments"),
            _safe_get(client, "/env-manager/workers"),
        )
    )

    environments: list[dict[str, Any]] = []
    if isinstance(environment_data, dict):
        raw_environments = environment_data.get("node_environments", [])
        if isinstance(raw_environments, list):
            environments = [entry for entry in raw_environments if isinstance(entry, dict)]
    total_discovered = len(environments)
    if configured_only:
        environments = [
            entry
            for entry in environments
            if entry.get("has_config") or entry.get("has_env") or entry.get("isolated_dirs")
        ]
    environments = environments[:limit]

    workers: list[dict[str, Any]] = []
    if isinstance(worker_data, dict) and isinstance(worker_data.get("workers"), list):
        workers = [entry for entry in worker_data["workers"] if isinstance(entry, dict)]

    errors = {
        key: value
        for key, value in {
            "runtime": runtime_error,
            "environments": environments_error,
            "workers": workers_error,
        }.items()
        if value is not None
    }
    return json.dumps({
        "status": "ok" if not errors else ("partial" if environments or workers else "unavailable"),
        "runtime": runtime,
        "runtime_available": runtime_error is None,
        "environments": environments,
        "environment_count": len(environments),
        "total_discovered_environment_count": total_discovered,
        "configured_only": configured_only,
        "workers": workers,
        "worker_count": len(workers),
        "alive_worker_count": sum(1 for worker in workers if worker.get("alive")),
        "errors": errors,
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "List ComfyUI Isolated Workers",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_workers(ctx: Context) -> str:
    """List active comfy-env subprocess workers, PIDs, Python, and generation."""
    data, error = await _safe_get(_client(ctx), "/env-manager/workers")
    if error is not None:
        return json.dumps({"status": "unavailable", "workers": [], "error": error}, indent=2)
    workers = data.get("workers", []) if isinstance(data, dict) else []
    if not isinstance(workers, list):
        workers = []
    workers = [entry for entry in workers if isinstance(entry, dict)]
    return json.dumps({
        "status": "ok",
        "workers": workers,
        "count": len(workers),
        "alive_count": sum(1 for worker in workers if worker.get("alive")),
        "endpoint_error": data.get("error") if isinstance(data, dict) else None,
    }, indent=2)

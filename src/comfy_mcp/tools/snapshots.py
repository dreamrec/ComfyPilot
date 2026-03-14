"""Snapshot tools — 6 tools for workflow state snapshots."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _snapshot_mgr(ctx: Context):
    return ctx.request_context.lifespan_context["snapshot_manager"]


@mcp.tool(
    annotations={
        "title": "Snapshot Workflow",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_snapshot_workflow(workflow: dict, name: str = "", ctx: Context = None) -> str:
    """Create a snapshot of the current workflow state.

    Args:
        workflow: The workflow dictionary to snapshot
        name: Optional name for the snapshot

    Returns:
        JSON with snapshot id, name, timestamp, and node_count
    """
    mgr = _snapshot_mgr(ctx)
    result = mgr.add(workflow, name=name)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "List Snapshots",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_snapshots(limit: int = 20, ctx: Context = None) -> str:
    """List workflow snapshots (newest first).

    Args:
        limit: Maximum number of snapshots to return (default 20)

    Returns:
        JSON with snapshots list and total count
    """
    mgr = _snapshot_mgr(ctx)
    snapshots = mgr.list(limit=limit)
    return json.dumps({
        "snapshots": snapshots,
        "total_count": len(snapshots),
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Diff Snapshots",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_diff_snapshots(
    id_a: str, id_b: str | None = None, current_workflow: dict | None = None, ctx: Context = None
) -> str:
    """Diff two snapshots or a snapshot vs current workflow.

    Args:
        id_a: First snapshot ID
        id_b: Optional second snapshot ID
        current_workflow: Optional current workflow to diff against

    Returns:
        JSON with added_nodes, removed_nodes, modified_nodes, total_changes
    """
    mgr = _snapshot_mgr(ctx)
    result = mgr.diff(id_a, id_b=id_b, current=current_workflow)
    return json.dumps(result, indent=2)


@mcp.tool(
    annotations={
        "title": "Restore Snapshot",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_restore_snapshot(snapshot_id: str, ctx: Context = None) -> str:
    """Get a snapshot's workflow data for restoration.

    Args:
        snapshot_id: The snapshot ID to restore

    Returns:
        JSON with full snapshot data including workflow
    """
    mgr = _snapshot_mgr(ctx)
    snapshot = mgr.get(snapshot_id)
    if snapshot is None:
        return json.dumps({
            "error": f"Snapshot {snapshot_id} not found",
            "snapshot_id": snapshot_id,
        }, indent=2)

    return json.dumps(snapshot, indent=2)


@mcp.tool(
    annotations={
        "title": "Delete Snapshot",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_delete_snapshot(snapshot_id: str, ctx: Context = None) -> str:
    """Delete a snapshot.

    Args:
        snapshot_id: The snapshot ID to delete

    Returns:
        JSON confirming deletion or error if not found
    """
    mgr = _snapshot_mgr(ctx)
    deleted = mgr.delete(snapshot_id)
    if not deleted:
        return json.dumps({
            "error": f"Snapshot {snapshot_id} not found",
            "snapshot_id": snapshot_id,
        }, indent=2)

    return json.dumps({
        "status": "deleted",
        "snapshot_id": snapshot_id,
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Auto Snapshot Toggle",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_auto_snapshot(enabled: bool, ctx: Context = None) -> str:
    """Toggle automatic snapshot creation on workflow execution.

    Args:
        enabled: Whether to enable auto-snapshots

    Returns:
        JSON confirming the new auto_snapshot flag state
    """
    mgr = _snapshot_mgr(ctx)
    mgr.auto_snapshot = enabled
    return json.dumps({
        "auto_snapshot": mgr.auto_snapshot,
        "status": "enabled" if enabled else "disabled",
    }, indent=2)

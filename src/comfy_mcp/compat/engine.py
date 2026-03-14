"""Compatibility Engine — orchestrates multi-pass workflow preflight.

Runs structural, schema, and environment passes to produce a unified report.
"""

from __future__ import annotations

from typing import Any

from comfy_mcp.compat.structural import check_structural
from comfy_mcp.compat.schema import check_schema
from comfy_mcp.compat.environment import check_environment


def run_preflight(workflow: Any, snapshot: dict) -> dict[str, Any]:
    """Run all compatibility passes and produce a unified preflight report.

    Args:
        workflow: API-format workflow dict
        snapshot: InstallGraph snapshot

    Returns:
        Unified report with status, errors, warnings, missing_nodes,
        missing_models, and confidence score.
    """
    all_errors: list[str] = []
    all_warnings: list[str] = []
    missing_nodes: list[str] = []
    missing_models: list[dict] = []

    # Pass 1: Structural
    p1 = check_structural(workflow)
    all_errors.extend(p1["errors"])
    all_warnings.extend(p1["warnings"])

    if not p1["pass"]:
        return _build_report("blocked", all_errors, all_warnings, missing_nodes, missing_models)

    # Pass 2: Schema
    object_info = snapshot.get("object_info", {})
    p2 = check_schema(workflow, object_info)
    all_errors.extend(p2["errors"])
    all_warnings.extend(p2["warnings"])

    # Pass 3: Environment
    p3 = check_environment(workflow, snapshot)
    all_errors.extend(p3["errors"])
    all_warnings.extend(p3["warnings"])
    missing_nodes = p3.get("missing_nodes", [])
    missing_models = p3.get("missing_models", [])

    # Determine status
    if missing_nodes or missing_models:
        status = "blocked"
    elif all_errors:
        status = "blocked"
    elif all_warnings:
        status = "likely"
    else:
        status = "verified"

    return _build_report(status, all_errors, all_warnings, missing_nodes, missing_models)


def _build_report(
    status: str,
    errors: list[str],
    warnings: list[str],
    missing_nodes: list[str],
    missing_models: list[dict],
) -> dict[str, Any]:
    """Build the unified preflight report with confidence score."""
    if status == "verified":
        confidence = 0.95
    elif status == "likely":
        confidence = max(0.5, 0.9 - 0.1 * len(warnings))
    else:  # blocked
        confidence = 0.0

    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "missing_nodes": missing_nodes,
        "missing_models": missing_models,
        "confidence": round(confidence, 2),
    }

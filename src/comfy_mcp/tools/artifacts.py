"""Generic output-artifact discovery and safe local metadata access."""

from __future__ import annotations

import base64
import asyncio
import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlencode

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp
from comfy_mcp.tools.instance import _argv_options, _is_local_url


_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff",
    ".avif", ".exr", ".hdr",
}
_VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mpeg", ".mpg",
}
_AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus", ".aiff",
    ".aif",
}
_MESH_EXTENSIONS = {
    ".glb", ".gltf", ".obj", ".ply", ".stl", ".fbx", ".usd", ".usda",
    ".usdc", ".usdz", ".3mf", ".blend", ".dae",
}
_MIME_OVERRIDES = {
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".obj": "model/obj",
    ".stl": "model/stl",
    ".ply": "application/octet-stream",
    ".usdz": "model/vnd.usdz+zip",
    ".mkv": "video/x-matroska",
}
_MAX_INLINE_BYTES = 25 * 1024 * 1024


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


def _artifact_kind(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension in _IMAGE_EXTENSIONS:
        return "image"
    if extension in _VIDEO_EXTENSIONS:
        return "video"
    if extension in _AUDIO_EXTENSIONS:
        return "audio"
    if extension in _MESH_EXTENSIONS:
        return "mesh"
    return "other"


def _mime_type(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    return _MIME_OVERRIDES.get(extension) or mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _normalise_relative_path(value: str) -> str:
    """Validate and normalise a user/history path relative to output root."""
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError("artifact path must be a non-empty relative path")
    value = value.replace("\\", "/")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("artifact path must stay inside the ComfyUI output directory")
    # A Windows drive is not considered absolute by PurePosixPath.
    if pure.parts and (re_drive_prefix(pure.parts[0]) or any(":" in part for part in pure.parts)):
        raise ValueError("artifact path must stay inside the ComfyUI output directory")
    return pure.as_posix()


def re_drive_prefix(value: str) -> bool:
    return len(value) >= 2 and value[1] == ":" and value[0].isalpha()


def _safe_output_path(root: Path, relative_path: str) -> Path:
    normalised = _normalise_relative_path(relative_path)
    resolved_root = root.resolve()
    candidate = (resolved_root / Path(*PurePosixPath(normalised).parts)).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("artifact path escapes the ComfyUI output directory") from exc
    return candidate


async def resolve_output_root(ctx: Context) -> tuple[Path | None, str | None]:
    """Resolve a local output root from the connected server's own argv."""
    client = _client(ctx)
    base_url = str(client.base_url)
    if not _is_local_url(base_url):
        return None, "filesystem fallback is only available for a loopback ComfyUI endpoint"
    try:
        stats = await client.get_system_stats()
    except Exception as exc:
        return None, f"could not read system_stats: {exc}"
    system = stats.get("system", {}) if isinstance(stats, dict) else {}
    argv = system.get("argv", []) if isinstance(system, dict) else []
    if not isinstance(argv, list):
        argv = []
    options, _ = _argv_options(argv)
    output = options.get("--output-directory")
    base = options.get("--base-directory")
    if not output and isinstance(base, str):
        output = str(Path(base) / "output")
    if not isinstance(output, str) or not output.strip():
        return None, "ComfyUI did not report --output-directory or --base-directory"
    root = Path(output).expanduser()
    if not root.is_dir():
        return None, f"reported output directory does not exist: {root}"
    return root.resolve(), None


def _record_from_relative(
    relative_path: str,
    *,
    source: str,
    size_bytes: int | None = None,
    modified_at: float | None = None,
    prompt_id: str | None = None,
    node_id: str | None = None,
    asset_id: str | None = None,
) -> dict[str, Any]:
    normalised = _normalise_relative_path(relative_path)
    pure = PurePosixPath(normalised)
    record: dict[str, Any] = {
        "filename": pure.name,
        "relative_path": normalised,
        "subfolder": "" if str(pure.parent) == "." else pure.parent.as_posix(),
        "kind": _artifact_kind(pure.name),
        "mime_type": _mime_type(pure.name),
        "extension": Path(pure.name).suffix.lower(),
        "source": source,
    }
    if size_bytes is not None:
        record["size_bytes"] = size_bytes
    if modified_at is not None:
        record["modified_at"] = modified_at
    if prompt_id is not None:
        record["prompt_id"] = prompt_id
    if node_id is not None:
        record["node_id"] = node_id
    if asset_id is not None:
        record["asset_id"] = asset_id
    return record


def _history_records(history: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not isinstance(history, dict):
        return records
    for prompt_id, entry in history.items():
        if not isinstance(entry, dict):
            continue
        outputs = entry.get("outputs", {})
        if not isinstance(outputs, dict):
            continue
        for node_id, node_output in outputs.items():
            if not isinstance(node_output, dict):
                continue
            for output_key, items in node_output.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    filename = item.get("filename") or item.get("name")
                    if not isinstance(filename, str) or not filename:
                        # Some custom output nodes expose a path rather than a
                        # ComfyUI asset record. Accept relative paths only.
                        filename = item.get("relative_path") or item.get("path")
                    if not isinstance(filename, str) or not filename:
                        continue
                    subfolder = item.get("subfolder", "")
                    if not isinstance(subfolder, str):
                        subfolder = ""
                    try:
                        relative = f"{subfolder}/{filename}" if subfolder else filename
                        record = _record_from_relative(
                            relative,
                            source="history",
                            prompt_id=str(prompt_id),
                            node_id=str(node_id),
                            asset_id=str(item.get("asset_id") or item.get("id") or "") or None,
                        )
                    except ValueError:
                        continue
                    record["history_output_key"] = str(output_key)
                    records.append(record)
    return records


def _filesystem_records(root: Path, subfolder: str = "") -> tuple[list[dict[str, Any]], str | None]:
    try:
        scan_root = _safe_output_path(root, subfolder) if subfolder else root.resolve()
    except ValueError as exc:
        return [], str(exc)
    if not scan_root.is_dir():
        return [], f"output subfolder does not exist: {subfolder}"

    resolved_root = root.resolve()
    records: list[dict[str, Any]] = []
    try:
        for directory, dirnames, filenames in os.walk(scan_root, followlinks=False):
            # Hidden transient directories do not represent user artifacts.
            dirnames[:] = [name for name in dirnames if not name.startswith(".")]
            for filename in filenames:
                candidate = Path(directory) / filename
                try:
                    resolved = candidate.resolve()
                    relative = resolved.relative_to(resolved_root).as_posix()
                    stat = resolved.stat()
                except (OSError, ValueError):
                    # Includes symlinks escaping the output root.
                    continue
                records.append(
                    _record_from_relative(
                        relative,
                        source="filesystem",
                        size_bytes=stat.st_size,
                        modified_at=stat.st_mtime,
                    )
                )
    except OSError as exc:
        return records, str(exc)
    records.sort(key=lambda item: (-float(item.get("modified_at", 0.0)), item["relative_path"].lower()))
    return records, None


def _filter_records(
    records: Iterable[dict[str, Any]],
    *,
    kind: str,
    query: str,
    subfolder: str,
) -> list[dict[str, Any]]:
    kind = kind.lower().strip()
    allowed = {"all", "image", "video", "audio", "mesh", "other"}
    if kind not in allowed:
        raise ValueError(f"kind must be one of {sorted(allowed)}")
    query_lower = query.lower().strip()
    if subfolder:
        subfolder = _normalise_relative_path(subfolder).rstrip("/")
    result: list[dict[str, Any]] = []
    for record in records:
        relative = str(record.get("relative_path", ""))
        if kind != "all" and record.get("kind") != kind:
            continue
        if query_lower and query_lower not in relative.lower():
            continue
        if subfolder and not (relative == subfolder or relative.startswith(f"{subfolder}/")):
            continue
        result.append(record)
    return result


async def discover_artifacts(
    ctx: Context,
    *,
    kind: str = "all",
    query: str = "",
    subfolder: str = "",
    filesystem_fallback: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collect and de-duplicate history and local-filesystem artifacts."""
    client = _client(ctx)
    diagnostics: dict[str, Any] = {"history_error": None, "filesystem_error": None}
    try:
        history = await client.get_history()
        history_records = _history_records(history)
    except Exception as exc:
        history_records = []
        diagnostics["history_error"] = str(exc)

    filesystem_records: list[dict[str, Any]] = []
    output_root: Path | None = None
    if filesystem_fallback:
        output_root, root_error = await resolve_output_root(ctx)
        diagnostics["filesystem_error"] = root_error
        if output_root is not None:
            filesystem_records, scan_error = await asyncio.to_thread(
                _filesystem_records, output_root, subfolder
            )
            diagnostics["filesystem_error"] = scan_error

    merged: dict[str, dict[str, Any]] = {}
    # Filesystem records are freshest and include authoritative size/mtime.
    for record in filesystem_records:
        merged[record["relative_path"].lower()] = dict(record)
    for record in history_records:
        key = record["relative_path"].lower()
        if key in merged:
            merged[key].update({
                field: value
                for field, value in record.items()
                if field not in {"source", "size_bytes", "modified_at"}
            })
            merged[key]["source"] = "history+filesystem"
        else:
            merged[key] = dict(record)

    filtered = _filter_records(merged.values(), kind=kind, query=query, subfolder=subfolder)
    filtered.sort(
        key=lambda item: (
            -float(item.get("modified_at", 0.0)),
            str(item.get("relative_path", "")).lower(),
        )
    )
    diagnostics["output_root"] = str(output_root) if output_root else None
    diagnostics["history_count"] = len(history_records)
    diagnostics["filesystem_count"] = len(filesystem_records)
    return filtered, diagnostics


@mcp.tool(
    annotations={
        "title": "List ComfyUI Output Artifacts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_list_artifacts(
    kind: str = "all",
    query: str = "",
    subfolder: str = "",
    limit: int = 100,
    offset: int = 0,
    filesystem_fallback: bool = True,
    ctx: Context = None,
) -> str:
    """List image, video, audio, mesh, or other output artifacts.

    History is merged with the local output filesystem for loopback instances,
    so outputs remain discoverable after ComfyUI history is reset. Paths are
    constrained to the output root and filesystem symlinks cannot escape it.
    """
    if limit < 1 or limit > 1000:
        return json.dumps({"error": "limit must be between 1 and 1000"})
    if offset < 0:
        return json.dumps({"error": "offset must be >= 0"})
    try:
        records, diagnostics = await discover_artifacts(
            ctx,
            kind=kind,
            query=query,
            subfolder=subfolder,
            filesystem_fallback=filesystem_fallback,
        )
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    total = len(records)
    page = records[offset : offset + limit]
    return json.dumps({
        "status": "ok",
        "kind": kind,
        "query": query,
        "artifacts": page,
        "count": len(page),
        "total_count": total,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < total else None,
        "diagnostics": diagnostics,
    }, indent=2)


@mcp.tool(
    annotations={
        "title": "Get ComfyUI Output Artifact Metadata",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_get_artifact(
    relative_path: str,
    include_data: bool = False,
    include_sha256: bool = False,
    max_inline_bytes: int = 10 * 1024 * 1024,
    ctx: Context = None,
) -> str:
    """Get safe metadata (and optionally base64 bytes) for one output file.

    ``relative_path`` is always resolved beneath the connected local
    instance's argv-derived output directory. Absolute paths, ``..`` and
    symlink escapes are rejected. Inline bytes are opt-in and capped at 25 MiB.
    """
    try:
        normalised = _normalise_relative_path(relative_path)
    except ValueError as exc:
        return json.dumps({"error": str(exc), "relative_path": relative_path})
    root, root_error = await resolve_output_root(ctx)
    if root is None:
        return json.dumps({
            "error": "local_output_unavailable",
            "message": root_error,
            "relative_path": normalised,
        }, indent=2)
    try:
        path = _safe_output_path(root, normalised)
    except ValueError as exc:
        return json.dumps({"error": str(exc), "relative_path": normalised})
    if not path.is_file():
        return json.dumps({"error": "artifact_not_found", "relative_path": normalised})
    try:
        stat = path.stat()
    except OSError as exc:
        return json.dumps({"error": "artifact_unreadable", "message": str(exc)})

    record = _record_from_relative(
        normalised,
        source="filesystem",
        size_bytes=stat.st_size,
        modified_at=stat.st_mtime,
    )
    query = urlencode({"filename": record["filename"], "subfolder": record["subfolder"], "type": "output"})
    record["url"] = f"{_client(ctx).base_url}/view?{query}"
    record["local_path"] = str(path)

    if include_sha256:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            record["sha256"] = digest.hexdigest()
        except OSError as exc:
            record["sha256_error"] = str(exc)

    if include_data:
        try:
            requested_limit = int(max_inline_bytes)
        except (TypeError, ValueError):
            requested_limit = 10 * 1024 * 1024
        limit = min(max(1, requested_limit), _MAX_INLINE_BYTES)
        if stat.st_size > limit:
            record["data_error"] = (
                f"artifact is {stat.st_size} bytes; inline limit is {limit} bytes"
            )
        else:
            try:
                record["data_base64"] = base64.b64encode(path.read_bytes()).decode("ascii")
            except OSError as exc:
                record["data_error"] = str(exc)

    return json.dumps({"status": "ok", "artifact": record}, indent=2)

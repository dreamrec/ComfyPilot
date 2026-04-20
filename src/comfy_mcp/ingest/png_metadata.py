"""Extract workflow JSON from PNG tEXt chunks written by ComfyUI.

ComfyUI's SaveImage node embeds workflow JSON into the PNG via two tEXt
chunks:
- 'prompt' : API-format {node_id: {class_type, inputs}} (directly queueable)
- 'workflow' : UI-format with node positions, links, widget values, etc.

We parse PNG tEXt chunks directly using the stdlib (no Pillow dependency),
so the ingest works on any PNG-writing install. Returns whichever chunk
is present, preferring the API-format 'prompt'.
"""
from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path
from typing import Any


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _iter_png_chunks(data: bytes):
    """Yield (type, payload) tuples for each PNG chunk. Stops at IEND."""
    if not data.startswith(_PNG_SIGNATURE):
        raise ValueError("Not a PNG file (missing signature)")
    pos = len(_PNG_SIGNATURE)
    size = len(data)
    while pos + 8 <= size:
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        chunk_type = data[pos + 4:pos + 8].decode("ascii", errors="replace")
        payload_start = pos + 8
        payload_end = payload_start + length
        if payload_end + 4 > size:
            break  # truncated
        payload = data[payload_start:payload_end]
        yield chunk_type, payload
        if chunk_type == "IEND":
            return
        pos = payload_end + 4  # skip CRC


def _text_chunk_kv(payload: bytes) -> tuple[str, str] | None:
    """tEXt: keyword\0text. zTXt: keyword\0compression_method + zlib-compressed text."""
    # tEXt
    split = payload.find(b"\x00")
    if split == -1:
        return None
    keyword = payload[:split].decode("latin-1", errors="replace")
    text = payload[split + 1:].decode("utf-8", errors="replace")
    return keyword, text


def _ztxt_chunk_kv(payload: bytes) -> tuple[str, str] | None:
    split = payload.find(b"\x00")
    if split == -1:
        return None
    keyword = payload[:split].decode("latin-1", errors="replace")
    rest = payload[split + 1:]
    if not rest:
        return None
    compression = rest[0]
    compressed = rest[1:]
    if compression != 0:
        return None
    try:
        text = zlib.decompress(compressed).decode("utf-8", errors="replace")
    except zlib.error:
        return None
    return keyword, text


def _itxt_chunk_kv(payload: bytes) -> tuple[str, str] | None:
    """iTXt: keyword\0compression_flag, compression_method, language_tag\0translated_keyword\0text."""
    parts = payload.split(b"\x00", 1)
    if len(parts) < 2:
        return None
    keyword = parts[0].decode("latin-1", errors="replace")
    rest = parts[1]
    if len(rest) < 2:
        return None
    compression_flag = rest[0]
    # compression_method = rest[1]
    after = rest[2:]
    # skip language tag and translated keyword
    try:
        _, after = after.split(b"\x00", 1)
        _, text_bytes = after.split(b"\x00", 1)
    except ValueError:
        return None
    if compression_flag == 1:
        try:
            text = zlib.decompress(text_bytes).decode("utf-8", errors="replace")
        except zlib.error:
            return None
    else:
        text = text_bytes.decode("utf-8", errors="replace")
    return keyword, text


def _text_chunks(data: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk_type, payload in _iter_png_chunks(data):
        kv: tuple[str, str] | None = None
        if chunk_type == "tEXt":
            kv = _text_chunk_kv(payload)
        elif chunk_type == "zTXt":
            kv = _ztxt_chunk_kv(payload)
        elif chunk_type == "iTXt":
            kv = _itxt_chunk_kv(payload)
        if kv is not None:
            keyword, text = kv
            out.setdefault(keyword, text)
    return out


def extract_workflow_from_png(png_path: str | Path) -> dict[str, Any]:
    """Return {format, workflow, ...} extracted from a ComfyUI-saved PNG.

    Preference order: 'prompt' (API format, directly queueable),
    then 'workflow' (UI format). Returns {'format': 'none'} if neither
    chunk is present.
    """
    path = Path(png_path)
    data = path.read_bytes()
    chunks = _text_chunks(data)

    for key, fmt in (("prompt", "api"), ("workflow", "ui")):
        if key in chunks:
            try:
                parsed = json.loads(chunks[key])
            except json.JSONDecodeError:
                continue
            return {
                "format": fmt,
                "workflow": parsed,
                "chunk_key": key,
                "path": str(path),
            }

    return {"format": "none", "path": str(path), "chunks_found": sorted(chunks.keys())}

# Changelog

All notable changes to ComfyPilot will be documented in this file.

## [1.0.0] — 2026-03-14

### Added

**Core Infrastructure**
- FastMCP server with lifespan management for persistent ComfyUI connections
- Async HTTP client (`ComfyClient`) with 17 high-level methods
- WebSocket-based `EventManager` with auto-reconnect and event buffering
- `JobTracker` for async prompt completion with history polling
- Module-level `_shared_client` pattern for MCP Resource handlers

**66 MCP Tools across 12 categories**
- System (6): stats, GPU info, features, extensions, restart, free VRAM
- Models (5): list, info, folders, search, refresh
- Workflow (8): queue, cancel, interrupt, validate, export, import
- Nodes (6): list types, get info, search, categories, embeddings, inspect widget
- Images (5): get output (image content blocks), upload, list, batch, URL
- History (5): get history, run result, delete, clear, search
- Monitoring (6): watch progress, subscribe, unsubscribe, events, dynamics, status
- Snapshots (6): snapshot, list, diff, restore, delete, auto-snapshot
- Memory (5): save technique, search, list, replay, favorite
- Safety (5): check VRAM, set limits, detect instability, validate before queue, emergency stop
- Builder (5): build workflow (5 templates), add node, connect, set widget, apply template
- Output Routing (4): send to disk, send to TD, send to Blender, list destinations

**4 MCP Resources**
- `comfy://system/info` — System stats and GPU info
- `comfy://nodes/catalog` — Node type catalog
- `comfy://models/{folder}` — Model listing by folder
- `comfy://embeddings` — Embeddings list

**Subsystems**
- `SnapshotManager` — In-memory workflow snapshots with LRU eviction and diff
- `TechniqueStore` — Persistent workflow technique library with JSON storage, search, favorites
- `VRAMGuard` — VRAM monitoring with warn/block thresholds, pre-flight validation, emergency stop

**Workflow Builder Templates**
- txt2img, img2img, upscale, inpaint, controlnet

**Cross-App Output Routing**
- Agent-orchestrated delivery to disk, TouchDesigner, and Blender project directories

**Plugin Packaging**
- Claude Code plugin manifest (`.claude-plugin/plugin.json`)
- MCP bundle with client profiles (Claude Desktop, Cursor, generic)
- `comfypilot-core` skill for automatic workflow guidance

**Test Suite**
- 275 tests across 17 test files
- Full mock coverage with shared fixtures

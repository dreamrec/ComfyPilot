# Changelog

All notable changes to ComfyPilot will be documented in this file.

## [0.7.1] — 2026-03-14

### Security
- Path traversal prevention in output routing (`_safe_filename`)
- Command injection fix via `repr()` for TD/Blender generated commands
- Input validation for safety thresholds (`comfy_set_limits`)
- Config key whitelisting (`comfy_set_config`)
- Upload size limit (50 MB) for `comfy_upload_image`

### Fixed
- WebSocket binary frame handling (skip instead of crash)
- Progress cache memory leak (LRU-capped dict, maxsize=500)
- Cloud URL detection expanded (`cloud.comfy.org`)
- Core cloud route branching for system stats, queue, prompt, object info, history, image view, and upload
- Cloud history v2 responses normalized to the local history dict shape
- Template discovery route (`/api/workflow_templates`)
- Template discovery now probes both `/workflow_templates` and `/api/workflow_templates` in profile-aware order
- InstallGraph preserves object-shaped feature payloads
- Compatibility wording: `basic_check_passed` instead of misleading `compatible`
- Atomic writes for TechniqueStore, DocsStore, TemplateIndex
- Schema versioning for TechniqueStore with backfill migration
- Private member access fix in `comfy_replay_technique`
- Invalid base64 uploads now return a structured tool error

### Removed
- `comfy_subscribe` / `comfy_unsubscribe` (placebo tools with no real subscription semantics)

### Added
- Model family detection (SD1.5, SDXL, FLUX) with appropriate defaults
- 6 new built-in templates: sdxl_txt2img, sdxl_img2img, flux_txt2img, upscale_basic, inpaint_basic, controlnet_basic
- Template-first builder logic (threshold lowered from 0.7 to 0.4)
- Family-aware defaults (SDXL gets 1024x1024, FLUX gets cfg=1.0)
- 22 security tests + 16 integration smoke tests + 20 new feature tests
- Contributing section in README

### Changed
- Tool count: 92 → 90 (removed 2 placebo tools)
- Built-in templates: 2 → 8
- Test suite: 541 → 598
- Release metadata aligned to `0.7.1` across package/docs

## [0.7.0] — 2026-03-14

### Added

**90 MCP Tools across 15 categories**
- System (6): stats, GPU info, features, extensions, restart, free VRAM
- Models (5): list, info, folders, search, refresh
- Workflow (8): queue, cancel, interrupt, validate, export, import
- Nodes (6): list types, get info, search, categories, embeddings, inspect widget
- Images (5): get output (image content blocks), upload, list, batch, URL
- History (5): get history, run result, delete, clear, search
- Monitoring (4): watch progress, get events, describe dynamics, get status
- Snapshots (6): snapshot, list, diff, restore, delete, auto-snapshot
- Memory (5): save technique, search, list, replay, favorite
- Safety (5): check VRAM, set limits, detect instability, validate before queue, emergency stop
- Builder (5): build workflow, add node, connect, set widget, apply template
- Output Routing (4): send to disk, send to TD, send to Blender, list destinations
- Templates (6): search, get, list categories, status, discover, instantiate
- Knowledge (5): status, refresh all, clear cache, get config, set config
- Install (5): get snapshot, list models, list nodes, check health, resolve model
- Compatibility (4): check compat, explain incompatibility, suggest alternatives, validate workflow
- Registry (4): search, get package, check compat, resolve missing

**10 MCP Resources**
- `comfy://system/info`, `comfy://server/capabilities`
- `comfy://nodes/catalog`, `comfy://models/{folder}`, `comfy://embeddings`
- `comfy://docs/summary`, `comfy://templates/catalog`
- `comfy://install/snapshot`, `comfy://knowledge/status`
- `comfy://support-matrix`

**Subsystems**
- Install graph, compatibility engine, documentation cache
- Template engine with discovery, scoring, and instantiation
- Knowledge layer with unified staleness tracking
- Registry integration for missing node resolution
- Model family detection (SD1.5/SDXL/FLUX)

**Test Suite**
- 598 tests across 25+ test files

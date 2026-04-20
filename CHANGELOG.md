# Changelog

All notable changes to ComfyPilot will be documented in this file.

## [1.6.0] - 2026-04-20

### Unified model discovery across the full ComfyUI folder taxonomy

This rewires every model-discovery tool to treat `/models` as the source of
truth for which folders exist, not a hardcoded 5-folder guess. Modern
UNETLoader-based families (Flux 2, Qwen-Image, Wan 2.2, LTX-2, HunyuanVideo,
Hunyuan3D) store their primary weights under `diffusion_models/`, not
`checkpoints/`. Pre-1.6 those installs were invisible to `comfy_search_models`
and `comfy_refresh_models`, which defaulted to checkpoint-centric folder sets.

- feat (comfy_client.py): new `ComfyClient.get_model_folders()` hits
  `GET /models` (profile-aware, with `/api/models` fallback). Accepts both
  list and `{folders: [...]}` / `{models: [...]}` dict shapes that different
  ComfyUI wrappers return. Returns [] on error so callers can fall back.

- feat (tools/models.py): `comfy_list_model_folders` now calls the live
  endpoint. Response includes `source: "live"` when the live list succeeded
  or `source: "fallback"` when the 16-folder static list was used. Fallback
  list covers: checkpoints, diffusion_models, unet, loras, vae, vae_approx,
  clip, text_encoders, clip_vision, controlnet, upscale_models, style_models,
  embeddings, hypernetworks, gligen, diffusers.

- feat (tools/models.py): `comfy_search_models` searches EVERY discovered
  folder by default (not just 5). Empty query returns a full inventory.
  Response reports `folders_source` (live | fallback | caller) and
  `folders_scanned` so callers can see exactly where the search ran.

- feat (tools/models.py): `comfy_refresh_models` refreshes per-folder and
  returns `counts_by_folder` plus `total_models`. Individual folder errors
  are captured in a dedicated `errors` list rather than aborting the whole
  refresh.

- chore: tool count unchanged (73). Tests 533 -> 541 (+8 regression tests
  covering live-folder discovery, fallback paths, caller-supplied folders,
  per-folder refresh, and the client-level endpoint contract).

## [1.5.3] - 2026-04-20

### Code-review fixes: builder / VRAM / capability / blueprint / batch + fail-closed option

- **P1 fix** (builder.py): auto-detect now probes both `diffusion_models/` and `checkpoints/` folders. Modern families (Flux 2, Qwen, Wan 2.2, LTX-2, HunyuanVideo, Hunyuan3D) store weights under `diffusion_models/` via UNETLoader; the old code only looked in `checkpoints/` so installs with only `diffusion_models/wan2.2-...` fell back to SD 1.5 and then rejected `txt2video`. Resolution strategy: collect candidates from both folders, pick the first whose family supports the requested intent; fall back to any recognised family, then any available file.

- **P2 fix** (vram_guard.py): `check_vram` used to copy `vram_used_pct` from `devices[0]` while aggregating `status` across all devices. On multi-GPU rigs that produced contradictory snapshots like `status=critical` with `vram_used_pct=10.0`. Now reports the max used_pct across devices so the top-level number matches the worst device (and the overall status).

- **P2 fix** (comfy_client.py): `probe_capabilities` preserves `/features` dict payloads (ComfyUI v0.17+ returns `{"progress_text": "binary", ...}`), not just lists. Also resolves `auth_method` from `"auto"` to the actual choice (`"bearer"` / `"x-api-key"` / `"none"`) so `comfy://server/capabilities` no longer underreports.

- **P2 fix** (blueprints/store.py): blueprint name validation rejects `\` (Windows path separator), null bytes, leading dots, and control characters in addition to `/` and `..`. Matters because the MCPB manifest advertises `win32` support.

- **P3 fix** (images.py): `comfy_download_batch` no longer downloads every full image body just to compute size. Now returns pure metadata (filename, subfolder, type, URL) by default. Pass `include_size=True` to opt into per-file `size_bytes` (still requires fetching). Individual size-fetch failures now surface as `size_error` rather than aborting the whole batch.

- **feat** (safety/confirm.py): new `COMFY_STRICT_CONFIRM=1` env var flips destructive-op confirmation to fail-closed. Default stays fail-open (backward compat with elicitation-unaware hosts). Strict mode blocks when no context, no `ctx.elicit`, or `ctx.elicit` raises - ensuring agents can't silently bypass confirmation on broken hosts.

- chore: tool count unchanged (73). Tests 516 -> 533 (17 new regression tests covering every fix above).

## [1.5.2] - 2026-04-20

### MCPB one-click install for Claude Desktop + GitHub releases for every tag

- feat: ships a ready-to-install `.mcpb` bundle (Anthropic's MCP Bundle format) - download `comfypilot-v1.5.2.mcpb` from the latest release and drag into Claude Desktop. Uses `type: "uv"` (manifest v0.4) so compiled deps like pydantic just work. User config (COMFY_URL, API key, dirs, etc.) renders as a GUI form.
- feat: `manifest.json` at repo root (MCPB spec) + `.mcpbignore` to strip tests/docs/build artefacts from the bundle.
- feat: README adds MCPB + GitHub-release badges; Quick Setup gains an "Option 1: MCPB (one-click)" section ahead of the dev-runtime and plugin paths.
- chore: create retroactive GitHub releases for every tag back to v1.1.0 so the Claude Code plugin update surface actually fires. Previously only v1.0.0 had a release published; v1.1.0 through v1.5.1 existed as tags but never as releases.
- chore: attach the `.mcpb` artefact to the v1.5.2 release as a downloadable asset.

## [1.5.1] - 2026-04-20

### Docs refresh: full audit, drift repair, badge row

- audit: caught stale tool count (72 in 4 metadata files; actual is 73) - all fixed.
- chore: mcp/manifest.json categories list now includes `hub_search` (14 -> 15 categories).
- feat: README badge row beyond CI - Version, License (MIT), Python (3.10/3.11/3.12), MCP tools (73), MCP resources (5+3), Blueprints (9), Tests (516), MCP spec (2026-03-26), ComfyUI (v0.17+), Families (10), Transports (stdio / streamable-http).
- feat: README gains Model Families table (distinctive nodes per family) and Transports section documenting --transport streamable-http launch.
- docs: README Tool Map entry 11 now lists every intent including txt2video / img2video / image2_3d / txt2music.
- docs: README MCP Resources section expanded to 5 fixed + 3 resource templates with URI patterns.
- docs: README "What It Is Good At" mentions video, 3D, music, bundled blueprints, parameter sweeps, PNG round-trip, Mermaid, hub search.
- docs: README Environment Variables is now a table and includes `COMFY_SNAPSHOT_DIR` + `COMFY_BLUEPRINT_DIR`.
- docs: MANUAL.md rewritten. Accurate 73-tool reference (new sections: Blueprints, Viz+Ingest+Sweep, Hub Search, Structured Output, Elicitation, Transports, Model families). File structure diagram updated to current package layout. Architecture diagram reflects 13 subsystems. Snapshot persistence, atomic writes + manifests, Comfy Cloud example all documented.
- docs: skills/comfypilot-core/SKILL.md refreshed - 73 tools, 15 categories, 5+3 resources, structured output note, model families table, elicitation docs.
- chore: mcp/profiles/generic.json includes all 10 env vars.
- chore: server.json gains `COMFY_SNAPSHOT_DIR` env var and broader keywords (sdxl, sd3.5, qwen-image, wan2.2, ltx-2, hunyuan3d, image-to-3d, music-generation, subgraph-blueprints, mcp, mcp-server).

## [1.5.0] - 2026-04-20

### Cloud WS probe, hub search, bundled blueprints for every family

- feat: ComfyClient.probe_capabilities now actively probes the WebSocket endpoint with a 3s timeout instead of hardcoding ws_available=(profile==local). Cloud ComfyUI exposes wss://cloud.comfy.org/ws; that surface was being wrongly disabled. Headers (bearer / X-API-Key) flow through to the probe.
- feat: comfy_search_hub tool - searches HuggingFace (/api/models) or CivitAI (/api/v1/models) for public models. Normalized hit shape: {source, id, name, url, downloads, tags, + source-specific extras}. Tool count: 73.
- feat: bundled blueprint library grows from 1 -> 9 (one per supported family): flux2-txt2img, sd35-txt2img, sdxl-hires-fix, qwen-txt2img, wan22-txt2video, ltx2-txt2video, hunyuan-video-txt2video, hunyuan3d-image2_3d, acestep-txt2music. comfy_list_blueprints returns all of them.

## [1.4.0] - 2026-04-20

### Phase 2 Task 2: Full structured-output migration

Ten high-signal tools now return typed Pydantic models directly (FastMCP
auto-serializes). Agents get schema-introspectable JSON instead of opaque
strings. Each migration preserved the previous wire payload - no field
was lost in the shape change.

- comfy_check_vram -> VRAMStatus (with per-device VRAMDeviceInfo)
- comfy_list_models -> ModelList (pagination-aware)
- comfy_list_techniques -> TechniqueList (with TechniqueEntry items)
- comfy_list_snapshots -> SnapshotList (with SnapshotEntry items)
- comfy_describe_dynamics -> DynamicsReport (flattened queue + events + jobs)
- comfy_get_system_stats -> SystemStats (nested SystemInfo + GPUInfo list)
- comfy_get_run_result -> RunResult (new model for history entries)
- comfy_queue_prompt -> QueueAck (preserves prompt_id / queue_position / error / node_errors / auto_snapshot)
- comfy_validate_workflow -> ValidationReport (5-pass structured results)
- comfy_watch_progress -> WatchProgressFrame (status literal, numeric progress, elapsed_s)

This completes Phase 2 of the 2026 modernization roadmap. The remaining
deferred Phase 2 item (sampling-backed prompt expansion) still requires
Context.sample which is not yet in the installed FastMCP SDK.

## [1.3.1] - 2026-04-20

### Hotfix

- fix(ci): use tomli backport for Python 3.10 compatibility (tomllib is 3.11+ stdlib). pyproject.toml claims support for 3.10+; tests now honor it.

## [1.3.0] - 2026-04-20

### Phase 3: Polish and Differentiation

- feat: persistent snapshots via COMFY_SNAPSHOT_DIR env var. SnapshotManager now optionally persists to JSON on disk and reloads on restart. LRU eviction trims both memory and disk together.
- feat: output routing emits sidecar manifests (filename.json) alongside each saved image with schema_version, prompt_id, seeds, model_refs, dimensions, timestamp, size_bytes. Writes are atomic (temp file + os.replace).
- feat: comfy_send_to_disk, comfy_send_to_td, comfy_send_to_blender accept an optional prompt_id param that pulls seeds / model refs / dimensions from /history/{prompt_id} into the manifest.
- feat: comfy_visualize_workflow renders an API-format workflow as Mermaid flowchart TD source. Arrows trace input links with names.
- feat: comfy_import_workflow_from_png extracts embedded workflow JSON from ComfyUI-saved PNGs. Parses tEXt / zTXt / iTXt chunks using stdlib only (no Pillow dep). Prefers 'prompt' (API format) over 'workflow' (UI format).
- feat: comfy_sweep enqueues N variants of a workflow with a single parameter varying. Returns prompt_ids plus a square-ish grid layout hint. Each prompt auto-registers with the job tracker.
- chore: bump tool count 69 -> 72. Test count 460 -> 492.

## [1.2.0] - 2026-04-20

### Phase 2: MCP 2026 Table Stakes

- feat: pydantic response models for high-signal tools (SystemStats, ValidationReport, QueueAck, JobStatus, ModelList, TechniqueList, SnapshotList, VRAMStatus, DynamicsReport, WatchProgressFrame) - ready for incremental adoption by tool bodies.
- feat: elicitation-backed confirmation on destructive tools (comfy_clear_queue, comfy_clear_history, comfy_delete_history, comfy_delete_snapshot, comfy_emergency_stop) via ctx.elicit. Each accepts confirm=True to bypass. Graceful fallback when host lacks elicitation support.
- feat: paginated node catalog resource template comfy://nodes/catalog/{page} (100 per page) and comfy://nodes/by-category/{category} filter.
- feat: --transport streamable-http CLI flag with --host/--port for remote or hosted deployments. stdio remains the default.
- feat: MCP Registry manifest at server.json under namespace io.github.dreamrec/comfypilot. Declares elicitation capability and both transports.

### Skipped this release

- Tool body migration to pydantic-native return types (models shipped, migration is a follow-up so existing tests stay stable).
- Sampling-backed prompt expansion (Context.sample not yet in the installed FastMCP SDK).

## [1.1.0] - 2026-04-20

### Phase 0: Truth Hygiene

- feat: .mcp.local.json override pattern for per-machine config (gitignored)
- ci: pytest matrix workflow for Python 3.10 / 3.11 / 3.12 with doc-drift and release-metadata gates
- docs: CI badge on README and local-override setup section
- test: exclude README from ASCII-clean gate (intentional Unicode banner)

### Phase 1: 2026 Platform Alignment

- feat: normalized NodeSchema model (Pydantic) that parses V1 dict-of-tuples and V3 class-based object_info shapes transparently
- feat: nodes tools (comfy_get_node_info, comfy_inspect_widget) now return normalized NodeSchema with widget_inputs / link_inputs split
- feat: model-family detection from checkpoint filename (SD 1.5, SDXL, SD 3, SD 3.5, Flux 1, Flux 2, Qwen-Image, Wan 2.2, LTX-2, HunyuanVideo, Hunyuan3D, ACE-Step)
- feat: family-aware builder - comfy_build_workflow routes to the correct graph topology based on the detected checkpoint family; SD 1.5 is the UNKNOWN fallback
- feat: Flux 2 family templates (UNETLoader + DualCLIPLoader + FluxGuidance + SamplerCustomAdvanced)
- feat: SDXL family templates (1024x1024 defaults, karras scheduler)
- feat: SD 3.5 family templates (ModelSamplingSD3 + EmptySD3LatentImage)
- feat: Qwen-Image family templates (UNETLoader + CLIPLoader(type=qwen_image))
- feat: Wan 2.2 family templates - txt2video + img2video (EmptyHunyuanLatentVideo, WanImageToVideo)
- feat: LTX-2 family templates - txt2video (LTXVConditioning + LTXVScheduler)
- feat: HunyuanVideo family templates - txt2video + img2video (DualCLIPLoader(type=hunyuan_video), HunyuanImageToVideo)
- feat: Hunyuan3D family templates - image2_3d (EmptyLatentHunyuan3Dv2 + VAEDecodeHunyuan3D + SaveGLB)
- feat: ACE-Step family templates - txt2music (EmptyAceStepLatentAudio + TextEncodeAceStepAudio + SaveAudio)
- feat: validator environment pass - cross-checks referenced model filenames across CheckpointLoaderSimple / UNETLoader / VAELoader / LoraLoader / ControlNetLoader / CLIPLoader / DualCLIPLoader / TripleCLIPLoader / CLIPVisionLoader / StyleModelLoader / UpscaleModelLoader / GLIGENLoader against installed files
- feat: validator execution-risk pass - latent volume estimation (image WxHxbatch, video WxHxlengthxbatch), with VRAM cross-check when VRAMGuard is available
- feat: subgraph blueprints - 3 new tools (comfy_list_blueprints, comfy_insert_blueprint, comfy_publish_subgraph) backed by a user-writable store at ~/.comfypilot/blueprints with bundled fallback. Ships sdxl-hires-fix example.
- feat: comfy://templates/catalog resource via /workflow_templates (profile-aware, /api/ fallback)
- chore: bump tool count from 66 to 69

See docs/superpowers/plans/2026-04-20-modernization-roadmap.md for the full multi-phase roadmap.

## [1.0.0] - 2026-03-16

### Release

- Promoted the repo to a clean `1.0.0` release with aligned package, plugin, and MCP metadata.
- Trimmed stale planning artifacts from the tracked tree and removed tracked bytecode files.

### Hardening

- Sanitized output-routing filenames and escaped generated TouchDesigner and Blender commands.
- URL-encoded image URLs and inferred image MIME types from filenames.
- Forwarded auth headers to WebSocket monitoring and skipped binary preview frames safely.
- Started the event manager only when the connected profile actually exposes WebSocket progress.
- Reconciled tracked running jobs when `comfy_interrupt` is used.
- Added real auto-snapshot behavior before queue and builder edits.

### Documentation

- Tightened the README and manual so they describe the current public surface without stale version drift.
- Corrected resource counts, release metadata, remote-auth notes, and tool descriptions that were too broad.

### Tests

- Expanded regression coverage for routing safety, monitoring, metadata consistency, MIME handling, auth routing, and release bundle wiring.
- Full mock coverage with shared fixtures

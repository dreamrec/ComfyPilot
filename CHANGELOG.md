# Changelog

All notable changes to ComfyPilot will be documented in this file.

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

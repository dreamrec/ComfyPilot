# Changelog

All notable changes to ComfyPilot will be documented in this file.

## [Unreleased]

### Reliability and ComfyUI Desktop control

- Fixed successful empty-body ComfyUI control responses, safe idempotent retries,
  current queue tuple semantics, terminal job reconciliation, and restart-safe
  WebSocket/progress-state recovery.
- Replaced shallow workflow checks with strict live-schema validation and made
  builders resolve installed model folders/auxiliary weights before returning.
- Added Desktop instance discovery/restart, Manager V2 package inventory,
  generic mixed-media artifacts, comfy-env/worker inspection, and aggregate
  GPU process visibility, bringing the MCP surface to 96 tools.
- Destructive confirmation now fails closed by default, snapshots persist by
  default, and artifact/blueprint paths reject traversal and NTFS ADS forms.

## [1.9.0] - 2026-08-11

### ComfyUI 0.20-0.31.1 compatibility update

- Audited every official stable line from ComfyUI 0.20.0 through 0.31.1
  (634 commits / 575 changed files across the endpoint-to-endpoint diff) and
  documented the result in `docs/COMFYUI_COMPATIBILITY.md`.
- Added `comfy_list_jobs`, `comfy_get_job`, and `comfy_cancel_jobs`, bringing
  the MCP surface from 88 to 91 tools. Single cancellation now uses the
  state-aware 0.26+ jobs API and falls back to legacy interrupt/queue deletion.
- Extended `comfy_queue_prompt` with workflow ID, workflow version ID, partial
  execution targets, and extra prompt metadata.
- Fixed official native-subgraph discovery by reading `/global_subgraphs` and
  normalizing its ID-keyed response. Older fork routes remain supported.
- Fixed embedded node documentation by reading the official localized Markdown
  route (`/docs/<class>/en.md`) before structured fork fallbacks.
- Normalized modern V3-derived widget types and socket flags, including combo,
  color, bounding-box, curve, range, webcam, and dynamic input types.
- Preserved modern node/output metadata: lifecycle flags, aliases, output list
  flags/tooltips/match types, essentials categories, and price badges.
- Expanded capability/system data for nullable device indices, multiple GPUs,
  package versions, deployment environment, jobs support, and tested-version
  status.
- Added `Comfy-Usage-Source: comfypilot/1.9.0` to HTTP requests so ComfyUI
  0.25+ can forward accurate client provenance to partner nodes.
- Clarified that HTTP OpenAPI ingestion is deployment-dependent rather than a
  guaranteed local 0.20+ route.

## [1.8.1] - 2026-05-12

### Repo-checkout MCP connectivity fix

- fix (.mcp.json): drop `--directory ${CLAUDE_PLUGIN_ROOT}` from the
  comfypilot launch args. `uv run` defaults to cwd to find the
  `pyproject.toml`, which works for BOTH contexts where this file is
  loaded:
  - **Plugin context** (Claude Code's plugin loader): cwd is the plugin
    install dir which has `pyproject.toml`. Works.
  - **Project context** (`.mcp.json` picked up automatically when the
    repo is opened as a project): cwd is the repo root which also has
    `pyproject.toml`. Now works - previously failed because
    `${CLAUDE_PLUGIN_ROOT}` only resolves inside the plugin loader.

  Symptom prior to this fix: developers who installed the v1.8.0 plugin
  AND had a local checkout would see `comfypilot: ... ${CLAUDE_PLUGIN_ROOT}
  ... Failed to connect` in `claude mcp list` when running from inside the
  repo dir. End-users installing only via .mcpb / plugin marketplace
  never hit this since they have no project-scope load path.

- chore: version bumped 1.8.0 -> 1.8.1 in all seven release files.

## [1.8.0] - 2026-05-12

### Operational toolkit: lifecycle + diagnostics + convenience

Adds an operational layer on top of v1.7.0's structural surface. Original
anchors stay untouched: family-aware builder, snapshot/restore, technique
memory, blueprint library, 6-pass validator. New additions are strictly
additive.

**Lifecycle (5 new tools - comfy-cli wrappers)**
- feat (cli/comfy_cli.py): async subprocess wrapper for the official
  comfy-cli binary. Detects the binary on PATH (tries `comfy` then
  `comfy-cli`), enforces `--skip-prompt` by default, supports per-call
  workspace overrides, kills subprocesses on timeout.
- feat (tools/lifecycle.py): five MCP tools wrap comfy-cli:
  - `comfy_launch_server` (`comfy launch --background --port N --listen H`)
  - `comfy_stop_server` (`comfy stop`)
  - `comfy_install_node` (`comfy node install <slug>`, path-traversal-safe)
  - `comfy_list_installed_nodes` (`comfy node show installed`)
  - `comfy_download_model` (`comfy model download --url ... --relative-path models/<folder>`,
    with optional `--set-civitai-api-token`)
- All five degrade gracefully when comfy-cli isn't installed, returning
  a structured error with `pipx install` / `uvx` / `pip install --user`
  install hints.

**Diagnostics (5 new tools)**
- feat (tools/diagnostics.py::comfy_extract_schema): walks a workflow
  and surfaces every controllable widget input across all nodes, every
  model dependency (loader nodes), every `embedding:NAME` reference in
  text inputs, and every output node. `summary_only=True` returns just
  the counts/flags (parameter_count, has_negative_prompt, has_seed, etc.)
- feat (tools/diagnostics.py::comfy_fetch_logs): pulls /history/{id}
  and extracts just the log-relevant fields - errors with per-node
  traceback, completed nodes list, raw message count. Handles both
  status.exec_info.errors and status.messages execution_error shapes.
- feat (tools/diagnostics.py::comfy_inspect_workflow): trust check. Walks
  every node and classifies its class_type as stock (matches ComfyUI
  core patterns) or custom (everything else). Returns trust_level
  (`stock` / `mixed` / `fully_custom`) plus warnings - useful before
  auto-queueing workflows from untrusted sources.
- feat (tools/diagnostics.py::comfy_recommend_runtime): hardware verdict
  (`ok` / `marginal` / `cloud`) based on /system_stats. Picks the right
  `comfy-cli` install flag (--nvidia / --amd / --m-series / --cpu) and
  declares supports for each family class (sd15 / sdxl / flux2 / video).
- feat (tools/diagnostics.py::comfy_suggest_timeout): scans the workflow
  for long-running output classes (VHS_VideoCombine, SaveAnimatedWEBP,
  SUPIRSample, TrainLora, etc.) and recommends a per-workflow HTTP
  timeout. Default 300s; up to 3600s for training.

**Auto-fix + run-with-inputs convenience (2 new tools)**
- feat (tools/auto_fix_deps.py::comfy_install_workflow_deps): writes the
  workflow to a temp file and shells out to `comfy node install-deps`,
  closing the validate-then-fix loop the validator's environment pass
  starts. Temp file cleaned up after - even on error.
- feat (tools/run_with_inputs.py::comfy_run_with_inputs): collapses the
  three-step img2img / inpaint flow (upload + patch + queue) into one
  call. Accepts `inputs = {"label": "/local/path.png"}` where labels are
  either `node_id.input_name` (explicit) or just `input_name` (implicit -
  patches every matching LoadImage widget). Returns typed QueueAck with
  the upload map in `auto_snapshot`.

**Seed sentinel handling (1 new tool)**
- feat (tools/randomize_seeds.py::comfy_randomize_seeds): replaces
  `seed=-1` / `noise_seed=-1` sentinels with cryptographic-grade random
  uint32 values via `secrets.randbelow(2**32)`. `force=True` randomises
  every seed widget regardless of current value. Wired links (seed
  driven by another node) are never overwritten.

**Validator pre-pass: editor-format detection**
- feat (tools/workflow.py): a Pass 0 short-circuit detects ComfyUI editor
  format (top-level `nodes` + `links` arrays) and returns a specific
  "Re-export via Workflow -> Export (API)" message instead of N generic
  "missing class_type" errors. Saves an agent's debugging round-trip.

**Cloud tier awareness**
- feat (comfy_client.py::_probe_cloud_tier): when the connected profile
  is `cloud`, capabilities now include a `tier` field. Tries user-info
  endpoints (`/api/user`, `/user`, `/api/account`, `/api/me`); falls back
  to behavioural inference (200 on `/api/object_info` = paid tier, 403 =
  free). Local profiles report `tier: null`.

**Security hardening**
- feat (output_routing.py): regression-locked path-traversal protection.
  `_validate_filename` rejects POSIX absolute paths, Windows absolute
  paths, `..` traversal, `/`-separators, `\\`-separators, and bare `.`
  / `..` filenames. 24 new tests pin the contract against malicious
  workflows whose custom save nodes might return crafted filenames.

- chore: tool count 75 -> **88** (+13 operational tools). Tests
  638 -> 755+ green across 11 new test modules.

- docs: README, MANUAL, SKILL extended with the new tool categories.
  The new patterns are operational, not structural - our family-aware
  builder, 6-pass validator, snapshot/memory layer remain unchanged.

## [1.7.0] - 2026-05-12

### ComfyUI v0.20 alignment - new families, new intents, new validator pass

Brings ComfyPilot's surface up to ComfyUI v0.20.1 (was claiming v0.17+).
Adds the Ernie Image family, four new family-agnostic intents (SUPIR
super-resolution, RIFE/FILM frame interpolation, SAM 3.1 segmentation,
native LoRA training, Stable Audio txt2audio), an anti-cycle validator
pass mirroring v0.20's execution-side enforcement, OpenAPI 3.1 ingestion
with a `comfy://api/openapi` resource, native-subgraph awareness, an
asset-manifest parser for v0.19+ output shapes, a deprecated-model lint,
n-dimensional parameter sweep, and a partner-API directory.

- feat (families/detector.py + families/builders/ernie.py + blueprints/ernie-txt2img.json):
  Ernie Image (v0.19.0+) - new image family. UNETLoader + ErnieTEModel_
  CLIP + SamplerCustomAdvanced. v0.19.2 fixed the TE class name to
  `ErnieTEModel_` with trailing underscore - the public selector
  `type="ernie_image"` stays stable.

- feat (families/registry.py): intent-override map. Family-agnostic
  intents (`super_resolution`, `interpolate_frames`, `segment`,
  `train_lora`, `txt2audio`) dispatch by intent name and bypass the
  checkpoint-family probe. The classic family-routed intents
  (`txt2img`/`img2img`/etc.) keep working unchanged.

- feat (families/builders/supir.py + blueprints/supir-upscale.json):
  SUPIR super-resolution (v0.20.0+) - SUPIRLoader + SUPIREncode +
  SUPIRSample + SUPIRDecode pipeline with EDM sampler controls.

- feat (families/builders/interpolation.py + blueprints/rife-interpolate.json):
  RIFE / FILM frame interpolation (v0.20.0+). Method-selectable
  (`method="rife" | "film"`) with multiplier-aware output FPS.

- feat (families/builders/segment.py + blueprints/sam31-segment.json):
  SAM 3.1 prompt-based segmentation (v0.20.0+). Returns masks ready to
  chain into inpaint / controlnet.

- feat (families/builders/training.py): native LoRA training intent
  using v0.3.41 TrainLoraDataLoader + TrainLora + SaveLora. Picks up
  v0.3.45 multi-image-caption datasets and v0.3.76 multi-resolution
  buckets via dataset metadata.

- feat (families/builders/audio_t2a.py): general text-to-audio intent
  for Stable Audio 2.5 (v0.3.58) and similar native audio diffusion
  models. ConditioningStableAudio + EmptyLatentAudio + VAEDecodeAudio.

- feat (tools/workflow.py): pass 4 of validator is now `anti_cycle`,
  mirroring ComfyUI v0.20's execution-side cycle detection. Iterative
  DFS with 3-coloring returns the offending node IDs so the error
  message names the cycle. Existing acyclic DAGs unchanged. Passes
  list expands from 5 to 6.

- feat (safety/deprecated_models.py): deprecated-model lint pass on the
  environment-pass model names. Emits warnings (not errors) for
  `seedream-3-0-t2i`, `seedance-1-0-lite`, `seededit`, `gpt-image-1`,
  legacy `kling-2-1-master`, and `veo-3-0`.

- feat (schemas/node_schema.py): RANGE input type (v0.20.1) is now a
  primitive widget, not a link target. Two-handle range slider with
  `min`/`max`/`step` constraints.

- feat (comfy_client.py + server.py): `get_openapi_spec()` +
  `comfy://api/openapi` resource (v0.20.0). `capabilities.openapi_version`
  records the spec version when reachable. Falls back gracefully when
  /openapi.json is missing.

- feat (comfy_client.py): `frontend_version` (v0.3.46+) and
  `cache_provider` (v0.18+ CacheProvider API) recorded in capabilities.

- feat (comfy_client.py + tools/blueprints.py): `get_published_subgraphs()`
  hits ComfyUI's v0.3.67+ subgraph endpoint. `comfy_list_blueprints`
  accepts `source="user" | "bundled" | "native" | "all"` (default `all`)
  to merge ComfyPilot blueprints with native published subgraphs.

- feat (comfy_client.py + server.py): `comfy://docs/{node_class}`
  resource template proxies v0.3.68 embedded docs; falls back to
  object_info description when the endpoint is absent.

- feat (tools/sweep.py): `comfy_sweep_grid` enqueues an n-dimensional
  Cartesian product across multiple `node.param` axes. Hard cap at 64
  combinations by default (override via `max_combinations`).

- feat (tools/partner_apis.py): `comfy_list_partner_apis` reports which
  partner/API custom nodes (Veo, Kling, Seedance, GPT-Image, Topaz,
  Tripo3D, Rodin, Recraft, Ideogram, NanoBanana, Sonilo, ElevenLabs,
  etc.) are installed on the connected ComfyUI.

- feat (tools/images.py): `_iter_node_outputs` parses both the legacy
  `images` key and the v0.19+ `assets` manifest shape (plus gifs / webp
  / audio / videos). `comfy_list_output_images` now finds output files
  regardless of which response shape ComfyUI returned.

- feat (responses/models.py + tools/history.py): `RunResult.create_time`
  surfaces the v0.3.69+ `/history` `create_time` field. Reads from
  either the top-level key or `status.create_time` (some forks pack
  it inside).

- feat (safety/vram_guard.py): `recommended_flags()` documents v0.16+
  default-dynamic-VRAM, plus `--fp16-intermediates` (v0.18+),
  `--enable-dynamic-vram`, mxfp8 / nvfp4 precision. Surfaced in
  `detect_instability` output when issues are present.

- chore: tool count 73 -> 75 (+comfy_sweep_grid, +comfy_list_partner_apis).
  Family count 10 -> 11 (+Ernie Image). New family-agnostic intents: 5.
  Bundled blueprints 9 -> 13 (+ernie, +supir, +rife, +sam31). MCP
  resources 5+3 -> 6+4 (+api/openapi, +docs/{node_class}). Tests
  541 -> 700+ green across 21 new and updated test modules.

- chore: bump claim from "ComfyUI v0.17+" to "v0.20+" everywhere.

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

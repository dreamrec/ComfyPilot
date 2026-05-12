```
 ██████╗ ██████╗ ███╗   ███╗███████╗██╗   ██╗██████╗ ██╗██╗      ██████╗ ████████╗
██╔════╝██╔═══██╗████╗ ████║██╔════╝╚██╗ ██╔╝██╔══██╗██║██║     ██╔═══██╗╚══██╔══╝
██║     ██║   ██║██╔████╔██║█████╗   ╚████╔╝ ██████╔╝██║██║     ██║   ██║   ██║
██║     ██║   ██║██║╚██╔╝██║██╔══╝    ╚██╔╝  ██╔═══╝ ██║██║     ██║   ██║   ██║
╚██████╗╚██████╔╝██║ ╚═╝ ██║██║        ██║   ██║     ██║███████╗╚██████╔╝   ██║
 ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝        ╚═╝   ╚═╝     ╚═╝╚══════╝ ╚═════╝    ╚═╝
```

# ComfyPilot v1.8.0

[![CI](https://github.com/dreamrec/ComfyPilot/actions/workflows/ci.yml/badge.svg)](https://github.com/dreamrec/ComfyPilot/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.8.0-blue)](https://github.com/dreamrec/ComfyPilot/releases/tag/v1.8.0)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](pyproject.toml)
[![MCP tools](https://img.shields.io/badge/MCP%20tools-88-brightgreen)](#tool-map-88-tools)
[![MCP resources](https://img.shields.io/badge/MCP%20resources-6%20%2B%204%20templates-brightgreen)](#mcp-resources)
[![Blueprints](https://img.shields.io/badge/bundled%20blueprints-13-teal)](blueprints/)
[![Tests](https://img.shields.io/badge/tests-770%20passing-brightgreen)](tests/)
[![MCP spec](https://img.shields.io/badge/MCP-2026--03--26-blueviolet)](https://modelcontextprotocol.io)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-v0.20%2B-orange)](https://github.com/comfyanonymous/ComfyUI)
[![Families](https://img.shields.io/badge/model%20families-11%20%2B%205%20intent--overrides-teal)](#model-families)
[![Transports](https://img.shields.io/badge/transports-stdio%20%7C%20streamable--http-lightgrey)](#transports)
[![MCPB](https://img.shields.io/badge/install-MCPB-purple)](https://github.com/dreamrec/ComfyPilot/releases/latest)
[![GitHub release](https://img.shields.io/github/v/release/dreamrec/ComfyPilot?include_prereleases&sort=semver)](https://github.com/dreamrec/ComfyPilot/releases)

**ComfyPilot** is an MCP server for ComfyUI.
It gives an AI agent a clean tool surface for workflow building, queueing, progress monitoring, image retrieval, snapshots, and VRAM safety.

## Documentation

- Production manual: `docs/MANUAL.md`
- Release notes: `CHANGELOG.md`

## What This Is

- A practical bridge between AI agents and ComfyUI.
- An **88-tool MCP surface** for workflow building, model management, image upload/download, history, monitoring, snapshots, technique memory, VRAM safety, output routing, blueprints, Mermaid viz, PNG ingest, n-dim parameter sweeps, partner-API discovery, model-hub search, **comfy-cli lifecycle** (install ComfyUI, launch/stop server, install nodes, download models), and **diagnostics** (workflow schema extraction, log fetching, trust checks, hardware verdicts, timeout suggestions, auto-fix workflow deps, upload-and-inject convenience).
- Live model-folder discovery: `diffusion_models/`, `text_encoders/`, `clip_vision/`, `style_models/`, `gligen/` (and every other folder the connected ComfyUI actually exposes) are searched by default - no more checkpoint-centric blind spots.
- A workflow-oriented loop built for iteration, not one-shot guessing.
- A small technique library for saving and replaying working patterns.

## Core Thinking Model (How To Think With This MCP)

Use this loop for every non-trivial task:

1. **Check system first** - Read GPU state before loading models. Start with `comfy_get_system_stats`, `comfy_check_vram`.

2. **Check memory** - Before building from scratch, use `comfy_search_techniques` to check if a similar workflow already exists in the library.

3. **Build in small steps** - Use `comfy_build_workflow` for any intent (txt2img, img2img, upscale, inpaint, controlnet, txt2video, img2video, image2_3d, txt2music, super_resolution, interpolate_frames, segment, train_lora, txt2audio). The family is auto-detected from the installed checkpoint for family-routed intents; family-agnostic intents (super_resolution, interpolate_frames, segment, train_lora, txt2audio) dispatch by intent name regardless of checkpoint. For common recipes, start from `comfy_insert_blueprint(name="flux2-txt2img")` or any of the 13 bundled blueprints. Validate with `comfy_validate_workflow` before queueing (6-pass: schema, catalog, graph, anti-cycle, environment, execution-risk).

4. **Monitor and retrieve** - Queue with `comfy_queue_prompt`, watch with `comfy_watch_progress`, retrieve with `comfy_get_output_image` (returns image content blocks directly in chat).

5. **Snapshot before changes** - Always `comfy_snapshot_workflow` before modifying a working workflow. Use `comfy_diff_snapshots` and `comfy_restore_snapshot` for undo.

6. **Route outputs** - Send generated images to disk, TouchDesigner, or Blender with `comfy_send_to_disk`, `comfy_send_to_td`, `comfy_send_to_blender`.

## Tool Map (88 Tools)

### 1) System + GPU
Use for connection health, GPU diagnostics, and VRAM management.

- `comfy_get_system_stats`, `comfy_get_gpu_info`, `comfy_get_features`
- `comfy_list_extensions`, `comfy_restart`, `comfy_free_vram`

### 2) Models
Use for discovering and managing every model file ComfyUI exposes. Folder taxonomy is discovered live from `/models` so modern families whose weights live under `diffusion_models/`, `text_encoders/`, `clip_vision/`, `style_models/`, or `gligen/` are covered by default.

- `comfy_list_models` - Paginated listing inside a single folder (`folder`, `limit`, `offset`).
- `comfy_get_model_info` - Normalized node schema for a model-loader node class.
- `comfy_list_model_folders` - Live folder list from `GET /models`, with fallback to a 16-folder static default when the endpoint is unreachable. Reports `source: live | fallback`.
- `comfy_search_models` - Searches every discovered folder by default. Pass `folders=["checkpoints", "loras"]` to narrow. Empty query returns a full inventory.
- `comfy_refresh_models` - Re-fetches the cache across every folder; returns per-folder counts + a `total_models` number.

### 3) Workflow Execution
Use for queueing, cancelling, and managing prompt execution.

- `comfy_queue_prompt`, `comfy_get_queue`, `comfy_cancel_run`
- `comfy_interrupt`, `comfy_clear_queue`
- `comfy_validate_workflow`, `comfy_export_workflow`, `comfy_import_workflow`

### 4) Nodes + Schema
Use for exploring ComfyUI's node catalog and understanding widget schemas.

- `comfy_list_node_types`, `comfy_get_node_info`, `comfy_search_nodes`
- `comfy_get_categories`, `comfy_get_embeddings`, `comfy_inspect_widget`

### 5) Images + Visual Output
Use for retrieving generated images (returned as image content blocks in chat).

- `comfy_get_output_image`, `comfy_upload_image`, `comfy_list_output_images`
- `comfy_download_batch`, `comfy_get_image_url`

### 6) History
Use for inspecting past generations and their outputs.

- `comfy_get_history`, `comfy_get_run_result`, `comfy_delete_history`
- `comfy_clear_history`, `comfy_search_history`

### 7) Monitoring + Progress
Use for tracking active jobs and observing workflow dynamics.

- `comfy_watch_progress`, `comfy_subscribe`, `comfy_unsubscribe`
- `comfy_get_events`, `comfy_describe_dynamics`, `comfy_get_status`

### 8) Workflow Snapshots
Use for undo/restore and workflow version tracking.

- `comfy_snapshot_workflow`, `comfy_list_snapshots`, `comfy_diff_snapshots`
- `comfy_restore_snapshot`, `comfy_delete_snapshot`, `comfy_auto_snapshot`

### 9) Technique Memory
Use for learning, saving, and replaying reusable workflow patterns.

- `comfy_save_technique` - Save a workflow as a reusable technique with tags and metadata.
- `comfy_search_techniques` - Search the library by text query and/or tags.
- `comfy_list_techniques` - List all saved techniques with metadata.
- `comfy_replay_technique` - Load a saved technique's workflow for immediate use.
- `comfy_favorite_technique` - Mark techniques as favorites and rate them (0-5).

Technique storage lives at `~/.comfypilot/techniques/` as individual JSON files.

### 10) Safety + VRAM Guard
Use for guardrails, pre-flight checks, and emergency control.

- `comfy_check_vram` - Check GPU VRAM usage with status levels (ok/warn/critical).
- `comfy_set_limits` - Configure safety thresholds (warn %, block %, max queue size).
- `comfy_detect_instability` - Check for near-OOM conditions and stuck jobs.
- `comfy_validate_before_queue` - Pre-flight check: VRAM headroom + queue capacity.
- `comfy_emergency_stop` - Interrupt current job, clear queue, free all VRAM.

### 11) Workflow Builder
Use for family-aware template construction and node editing.

- `comfy_build_workflow` - Family-aware: detects the checkpoint family (SD 1.5, SDXL, SD 3.5, Flux 2, Qwen-Image, Wan 2.2, LTX-2, HunyuanVideo, Hunyuan3D, ACE-Step) and dispatches to the right graph topology. Intents: `txt2img`, `img2img`, `upscale`, `inpaint`, `controlnet`, `txt2video`, `img2video`, `image2_3d`, `txt2music`.
- `comfy_add_node` - Add a node to a workflow-in-progress.
- `comfy_connect_nodes` - Wire node outputs to inputs.
- `comfy_set_widget_value` - Set widget values on nodes.
- `comfy_apply_template` - Alias for `comfy_build_workflow`.

### 12) Output Routing
Use for agent-orchestrated cross-app delivery of generated images.

- `comfy_send_to_disk` - Save output image to local filesystem.
- `comfy_send_to_td` - Route output to TouchDesigner project directory.
- `comfy_send_to_blender` - Route output to Blender project directory.
- `comfy_list_destinations` - List configured output destinations.

### 13) Subgraph Blueprints
Use for assembling workflows from named reusable macros.

- `comfy_list_blueprints` - List all available blueprints (user + bundled).
- `comfy_insert_blueprint` - Materialize a blueprint into a workflow dict with optional per-node input overrides.
- `comfy_publish_subgraph` - Save a set of nodes as a reusable named blueprint.

Blueprint storage: user-published at `~/.comfypilot/blueprints/` (override via `COMFY_BLUEPRINT_DIR`); bundled examples ship in `blueprints/` inside the repo.

### 14) Visualization + Ingest + Sweep
Use for rendering workflows, re-importing PNG outputs, and parameter sweeps.

- `comfy_visualize_workflow` - Render an API-format workflow as a Mermaid `flowchart TD` source.
- `comfy_import_workflow_from_png` - Extract the embedded workflow JSON from a ComfyUI-saved PNG (prefers 'prompt' API-format chunk, falls back to 'workflow' UI chunk).
- `comfy_sweep` - Enqueue N copies of a workflow with a single parameter varying across `values`; returns prompt_ids + grid layout hint.
- `comfy_sweep_grid` - N-dimensional Cartesian-product sweep over multiple `node_id.param` axes. Capped at 64 combinations by default (override with `max_combinations`).

### 15) Model Hub Search
Use for discovering models to download from public hubs.

- `comfy_search_hub` - Search HuggingFace or CivitAI for models matching a query. Returns normalized hits (id, name, url, downloads, tags). Use `source="huggingface"` or `source="civitai"`.

### 16) Partner APIs
Use for surfacing which vendor-hosted partner / API custom nodes are installed.

- `comfy_list_partner_apis` - Intersects ComfyUI's installed-extensions list with a curated catalog (Veo, Kling, ByteDance Seedance/Seedream, GPT-Image, Topaz, Tripo3D, Rodin, Recraft, Ideogram, NanoBanana, Sonilo, ElevenLabs, etc.) and reports which are live on this server with vendor / category / homepage metadata.

### 17) Lifecycle (v1.8.0)
Use for full setup-to-server flow when ComfyUI isn't running yet. All five tools shell out to the official [comfy-cli](https://github.com/Comfy-Org/comfy-cli) — install it via `pipx install comfy-cli` or `uvx --from comfy-cli comfy ...`.

- `comfy_launch_server` - Start ComfyUI (`comfy launch --background --port N --listen H`).
- `comfy_stop_server` - Stop the running server (`comfy stop`).
- `comfy_install_node` - Install a custom-node package by slug via Comfy Manager.
- `comfy_list_installed_nodes` - List currently-installed custom nodes.
- `comfy_download_model` - Download a model by URL into a chosen `models/<folder>` (supports CivitAI token).

### 18) Diagnostics (v1.8.0)
Use for workflow introspection, hardware verdicts, traceback extraction, and trust checks.

- `comfy_extract_schema` - Workflow-level controllable param + dependency summary (parameter list, model deps, embedding refs, output nodes, with `summary_only` mode).
- `comfy_fetch_logs` - Extract just the error traceback + completed-nodes list from `/history/{prompt_id}` — handles both `status.exec_info.errors` and `status.messages` shapes.
- `comfy_inspect_workflow` - Trust check: classify every class_type as stock / custom and surface warnings before queueing untrusted workflows.
- `comfy_recommend_runtime` - Hardware verdict (`ok` / `marginal` / `cloud`) + the right `comfy-cli` install flag for this hardware.
- `comfy_suggest_timeout` - Per-workflow HTTP timeout suggestion based on long-running output classes (default 300s, up to 3600s for training).

### 19) Convenience (v1.8.0)
Use to compress multi-step flows that an agent would otherwise script manually.

- `comfy_install_workflow_deps` - Auto-install every missing custom-node package the workflow references (wraps `comfy node install-deps --workflow`).
- `comfy_run_with_inputs` - Upload local images + inject as workflow inputs + queue — collapses the three-step img2img / inpaint flow into one call.
- `comfy_randomize_seeds` - Replace `seed=-1` sentinels with cryptographic-grade random uint32 values; `force=True` randomises every seed widget.

## MCP Resources

Six fixed resources:

- `comfy://system/info` - System stats, GPU info, ComfyUI version
- `comfy://server/capabilities` - Detected server profile, version, frontend version, auth method, WebSocket availability, OpenAPI version, cache provider
- `comfy://nodes/catalog` - Node catalog preview (first 100 names)
- `comfy://models/{folder}` - Model listing by folder (checkpoints, loras, vae, diffusion_models, text_encoders, etc.)
- `comfy://embeddings` - Available embeddings
- `comfy://api/openapi` - ComfyUI's OpenAPI 3.1 spec (v0.20.0+). Returns `{"error": ...}` on older builds.

Plus four resource templates (parameterized URIs):

- `comfy://nodes/catalog/{page}` - Paginated node catalog, 100 nodes per page (`{page}` = 0, 1, 2, ...)
- `comfy://nodes/by-category/{category}` - Node class_types whose category starts with the given prefix (e.g. `sampling`, `loaders/video`)
- `comfy://templates/catalog` - Workflow templates advertised by ComfyUI core + custom nodes (via `/workflow_templates`)
- `comfy://docs/{node_class}` - Embedded node documentation (v0.3.68+ docs endpoint, with object_info description fallback)

## How To Use It (Practical Workflow)

1. Connect MCP client to ComfyPilot.
2. Check system state and VRAM headroom.
3. Build a workflow (template or custom API JSON).
4. Validate, then queue the prompt.
5. Watch progress until complete.
6. Retrieve the output image (displayed inline in chat).
7. Route to disk/TD/Blender if needed. Snapshot at stable milestones.

## What It Is Good At

- Building and iterating on ComfyUI workflows through conversation.
- Family-aware generation across 11 model families (SD 1.5, SDXL, SD 3.5, Flux 2, Qwen-Image, Wan 2.2, LTX-2, HunyuanVideo, Hunyuan3D, ACE-Step, Ernie Image) covering images, video, 3D meshes, and music. Plus 5 family-agnostic intents (super-resolution via SUPIR, frame interpolation via RIFE/FILM, segmentation via SAM 3.1, native LoRA training, text-to-audio via Stable Audio).
- Starting from bundled blueprints for every family (13 ship in-repo) and customizing from there.
- 6-pass workflow validation (schema + catalog + graph + anti-cycle + environment + execution-risk) catching broken links, cycles, missing models, deprecated models, oversized latents before you hit ComfyUI.
- Monitoring GPU resources and preventing OOM situations via VRAMGuard.
- Returning generated images directly in the chat (image content blocks).
- Cross-app output routing to TouchDesigner and Blender with atomic writes + sidecar manifests (prompt_id, seeds, model refs, dimensions).
- Snapshot/restore for non-destructive workflow experimentation, now optionally persistent across restarts.
- Learning and replaying reusable workflow patterns via the technique library.
- Parameter sweeps (queue N variations of a single widget value).
- Importing a workflow back from a saved PNG's embedded metadata.
- Rendering any workflow as Mermaid for quick visual inspection.
- Searching HuggingFace and CivitAI directly for models.

## What It Is Not Good At

- Replacing artistic direction by itself.
- Streaming real-time video output (snapshots and polls, not live frames).
- "One shot perfect generation" without iterative refinement.
- Running without a working ComfyUI instance somewhere (cloud or local). The lifecycle tools (`comfy_launch_server`, `comfy_install_node`, `comfy_install_workflow_deps`, `comfy_download_model`) can bring a local install from zero to ready, but they need comfy-cli on `PATH` — install via `pipx install comfy-cli` or `uvx --from comfy-cli comfy ...` first.

## Model Families

11 first-class model families plus 5 family-agnostic intent-overrides. Each family has a builder template (or several) that emits a workflow matched to the right graph topology. The family is detected from the checkpoint filename; you can override by passing `checkpoint=` in params. Intent-overrides skip family detection entirely and dispatch by intent name.

| Family | Intents | Distinctive nodes |
|---|---|---|
| SD 1.5 | txt2img, img2img, upscale, inpaint, controlnet | `CheckpointLoaderSimple`, `KSampler`, `EmptyLatentImage` |
| SDXL | txt2img | `CheckpointLoaderSimple`, 1024x1024 defaults, `karras` scheduler |
| SD 3.5 | txt2img | `ModelSamplingSD3`, `EmptySD3LatentImage`, `dpmpp_2m` / `sgm_uniform` |
| Flux 2 / Klein | txt2img | `UNETLoader`, `DualCLIPLoader` (flux), `FluxGuidance`, `SamplerCustomAdvanced` |
| Qwen-Image | txt2img | `UNETLoader`, `CLIPLoader(type=qwen_image)`, `EmptySD3LatentImage` |
| Wan 2.2 | txt2video, img2video | `UNETLoader`, `CLIPLoader(type=wan)`, `EmptyHunyuanLatentVideo`, `WanImageToVideo` |
| LTX-2 | txt2video | `LTXVConditioning`, `LTXVScheduler`, `EmptyLTXVLatentVideo` |
| HunyuanVideo 1.5 | txt2video, img2video | `DualCLIPLoader(type=hunyuan_video)`, `EmptyHunyuanLatentVideo`, `HunyuanImageToVideo` |
| Hunyuan3D 2.1 | image2_3d | `EmptyLatentHunyuan3Dv2`, `VAEDecodeHunyuan3D`, `SaveGLB` |
| ACE-Step 1.5 XL | txt2music | `EmptyAceStepLatentAudio`, `TextEncodeAceStepAudio`, `SaveAudio` |
| Ernie Image | txt2img | `UNETLoader`, `CLIPLoader(type=ernie_image)`, `EmptySD3LatentImage` |

Intent-overrides (family-agnostic; dispatched by intent name regardless of detected checkpoint family):

| Intent | Purpose | Distinctive nodes | Origin |
|---|---|---|---|
| `super_resolution` | Image super-resolution / restoration (SUPIR) | `SUPIRLoader`, `SUPIREncode`, `SUPIRSample`, `SUPIRDecode` | ComfyUI v0.20.0+ |
| `interpolate_frames` | Frame interpolation (`method="rife" | "film"`) | `RIFE_VFI` / `FILM_VFI`, `LoadVideo`, `SaveAnimatedWEBP` | ComfyUI v0.20.0+ |
| `segment` | SAM 3.1 prompt-based segmentation | `SAM3Loader`, `SAM3Segment`, `MaskToImage` | ComfyUI v0.20.0+ |
| `train_lora` | Native LoRA training | `TrainLoraDataLoader`, `TrainLora`, `SaveLora` | ComfyUI v0.3.41+ |
| `txt2audio` | Text-to-audio (Stable Audio 2.5) | `ConditioningStableAudio`, `EmptyLatentAudio`, `VAEDecodeAudio`, `SaveAudio` | ComfyUI v0.3.58+ |

## Transports

- **stdio** (default) - Best for local clients like Claude Code, Claude Desktop, Cursor.
- **streamable-http** - Best for hosted / remote deployments. Enable with:

```bash
uv run comfypilot --transport streamable-http --host 0.0.0.0 --port 8765
```

## Support Matrix

| Feature | Status | Notes |
|---|---|---|
| Local ComfyUI (self-hosted) | Supported | Primary target |
| Comfy Cloud API | Partial | Auth and route probing supported; progress depends on remote WS support |
| stdio transport | Supported | Default |
| Streamable HTTP transport | Supported | `comfypilot --transport streamable-http --host 0.0.0.0 --port 8765` |
| Elicitation on destructive tools | Supported | clear_queue, clear_history, delete_history, delete_snapshot, emergency_stop gate on ctx.elicit when confirm=False |
| Structured output | Supported | Top 10 tools return typed Pydantic models (SystemStats, ValidationReport, QueueAck, RunResult, ModelList, TechniqueList, SnapshotList, VRAMStatus, DynamicsReport, WatchProgressFrame) |
| Paginated node catalog | Supported | `comfy://nodes/catalog/{page}` (100 per page) + `comfy://nodes/by-category/{category}` |
| MCP Registry publishing | Manifest ready | `server.json` declares `io.github.dreamrec/comfypilot` |
| Workflow JSON (v0.20+ spec) | Supported | 6-pass validation: schema + catalog + graph + anti-cycle + environment + execution-risk |
| OpenAPI 3.1 spec | Supported | `comfy://api/openapi` resource and `capabilities.openapi_version` (ComfyUI v0.20.0+) |
| Deprecated-model lint | Supported | Validator warns on retired partner models (seedream-3-0, seedance-1-0-lite, seededit, etc.) |
| Native subgraph awareness | Supported | `comfy_list_blueprints(source="native")` reads ComfyUI's v0.3.67+ published subgraphs |
| V3 custom nodes | Supported | Normalized NodeSchema parses V1 dict-of-tuples and V3 class-based shapes transparently |
| Subgraph Blueprints | Supported | User + bundled store, list/insert/publish tools |
| Model families (builder) | Supported | SD 1.5, SDXL, SD 3.5, Flux 2, Qwen-Image, Wan 2.2 (t2v/i2v), LTX-2, HunyuanVideo (t2v/i2v), Hunyuan3D, ACE-Step |
| WebSocket progress events | Supported where `/ws` is available | Binary preview frames are ignored safely |
| Image content blocks | Supported | Inline image display in chat |
| Cross-app routing | Filesystem only | Saves to disk with suggested commands |
| `/workflow_templates` resource | Supported | Exposed as `comfy://templates/catalog` |
| comfy-cli lifecycle | Optional | 5 tools wrap `comfy launch/stop/node install/model download` — degrades gracefully when comfy-cli is missing |
| Workflow diagnostics | Supported | `comfy_extract_schema`, `comfy_fetch_logs`, `comfy_inspect_workflow`, `comfy_recommend_runtime`, `comfy_suggest_timeout` |
| Cloud tier detection | Supported | `capabilities.tier` = `free` / `standard` / `creator` / `pro` / `paid` / `null` |

## Quick Setup

### Option 1: MCPB (one-click, Claude Desktop)

Easiest for Claude Desktop users:

1. Download `comfypilot-v1.8.0.mcpb` from the [latest release](https://github.com/dreamrec/ComfyPilot/releases/latest).
2. Double-click the file (or drag it into Claude Desktop's Settings > Extensions panel).
3. Claude Desktop renders a form for `COMFY_URL`, `COMFY_API_KEY`, and the other config fields — fill in what you need.
4. Click Install. Restart is handled automatically.

MCPB uses the `type: "uv"` server mode, so Python dependencies (`mcp`, `httpx`, `pydantic`, `websockets`) are resolved by `uv` at first run. You need `uv` installed on the host — [install uv](https://docs.astral.sh/uv/getting-started/installation/).

The bundle ships `manifest.json` + `pyproject.toml` + the full `src/comfy_mcp/` package + the 13 bundled blueprints. Manifest: [manifest.json](manifest.json).

### Option 2: Local development runtime

```bash
git clone https://github.com/dreamrec/ComfyPilot.git
cd ComfyPilot
uv sync
uv run comfypilot
```

### Option 3: Claude Code plugin

```bash
claude plugin add /path/to/ComfyPilot
```

### Local override

If your ComfyUI instance lives somewhere other than `127.0.0.1:8188` (Tailscale, remote LAN, custom port), copy `.mcp.local.json.example` to `.mcp.local.json` and edit it. The `.mcp.local.json` file is gitignored so per-machine URLs and secrets never get committed.

## MCP Bundle (Standardized)

ComfyPilot ships a standard MCP bundle in-repo:

- `mcp/manifest.json`
- `mcp/profiles/claude-desktop.json`, `cursor.json`, `generic.json`

The bundled profile JSON files pin `uv run` with `--directory`; replace `/path/to/ComfyPilot` with your checkout path when copying them into a client config. If you're launching from inside this repo, `.mcp.json` already uses `${CLAUDE_PLUGIN_ROOT}`.

Manual client configuration example (Claude Desktop):

```json
{
  "mcpServers": {
    "comfypilot": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/ComfyPilot", "comfypilot"],
      "env": {
        "COMFY_URL": "http://127.0.0.1:8188",
        "COMFY_API_KEY": ""
      }
    }
  }
}
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `COMFY_URL` | `http://127.0.0.1:8188` | ComfyUI server URL |
| `COMFY_API_KEY` | *(empty)* | Optional API key (Bearer for local, X-API-Key for Comfy Cloud) |
| `COMFY_AUTH_METHOD` | `auto` | Auth header style: `auto`, `bearer`, or `x-api-key` |
| `COMFY_TIMEOUT` | `300` | HTTP request timeout in seconds |
| `COMFY_SNAPSHOT_LIMIT` | `50` | Maximum workflow snapshots retained |
| `COMFY_SNAPSHOT_DIR` | *(empty)* | If set, persists snapshots to this directory. If empty, snapshots are in-memory only (pre-1.3 behavior). |
| `COMFY_BLUEPRINT_DIR` | `~/.comfypilot/blueprints` | User-published subgraph blueprints (bundled examples fall back automatically). |
| `COMFY_STRICT_CONFIRM` | *(unset)* | Set to `1` to fail-closed on destructive tools: if the host lacks elicitation (or `ctx.elicit` errors), the operation is rejected. Default is fail-open for backward compat with elicitation-unaware hosts. |
| `COMFY_OUTPUT_DIR` | `~/comfypilot_output` | Image output directory for disk routing |
| `COMFY_TD_OUTPUT_DIR` | `~/comfypilot_output/touchdesigner` | TouchDesigner output path |
| `COMFY_BLENDER_OUTPUT_DIR` | `~/comfypilot_output/blender` | Blender output path |

## Test Suite

Run the test suite:

```bash
uv run pytest -v
```

Run a specific category:

```bash
uv run pytest tests/test_builder.py -v
```

For a quick smoke run:

```bash
uv run pytest -q
```

## Reliability Habit

Treat this as mandatory for every meaningful task: before generations check VRAM, before workflow changes snapshot, after builds validate, after errors check `comfy_detect_instability`.

## License

MIT

`dreamrec // ComfyPilot // live laugh diffuse`

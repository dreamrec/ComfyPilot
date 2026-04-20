```
 ██████╗ ██████╗ ███╗   ███╗███████╗██╗   ██╗██████╗ ██╗██╗      ██████╗ ████████╗
██╔════╝██╔═══██╗████╗ ████║██╔════╝╚██╗ ██╔╝██╔══██╗██║██║     ██╔═══██╗╚══██╔══╝
██║     ██║   ██║██╔████╔██║█████╗   ╚████╔╝ ██████╔╝██║██║     ██║   ██║   ██║
██║     ██║   ██║██║╚██╔╝██║██╔══╝    ╚██╔╝  ██╔═══╝ ██║██║     ██║   ██║   ██║
╚██████╗╚██████╔╝██║ ╚═╝ ██║██║        ██║   ██║     ██║███████╗╚██████╔╝   ██║
 ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝        ╚═╝   ╚═╝     ╚═╝╚══════╝ ╚═════╝    ╚═╝
```

# ComfyPilot v1.5.1

[![CI](https://github.com/dreamrec/ComfyPilot/actions/workflows/ci.yml/badge.svg)](https://github.com/dreamrec/ComfyPilot/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.5.1-blue)](https://github.com/dreamrec/ComfyPilot/releases/tag/v1.5.1)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](pyproject.toml)
[![MCP tools](https://img.shields.io/badge/MCP%20tools-73-brightgreen)](#tool-map-73-tools)
[![MCP resources](https://img.shields.io/badge/MCP%20resources-5%20%2B%203%20templates-brightgreen)](#mcp-resources)
[![Blueprints](https://img.shields.io/badge/bundled%20blueprints-9-teal)](blueprints/)
[![Tests](https://img.shields.io/badge/tests-516%20passing-brightgreen)](tests/)
[![MCP spec](https://img.shields.io/badge/MCP-2026--03--26-blueviolet)](https://modelcontextprotocol.io)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-v0.17%2B-orange)](https://github.com/comfyanonymous/ComfyUI)
[![Families](https://img.shields.io/badge/model%20families-10-teal)](#model-families)
[![Transports](https://img.shields.io/badge/transports-stdio%20%7C%20streamable--http-lightgrey)](#transports)

**ComfyPilot** is an MCP server for ComfyUI.
It gives an AI agent a clean tool surface for workflow building, queueing, progress monitoring, image retrieval, snapshots, and VRAM safety.

## Documentation

- Production manual: `docs/MANUAL.md`
- Release notes: `CHANGELOG.md`

## What This Is

- A practical bridge between AI agents and ComfyUI.
- A 73-tool MCP surface for workflows, models, images, monitoring, safety, routing, blueprints, visualization, PNG ingest, parameter sweeps, and model-hub search.
- A workflow-oriented loop built for iteration, not one-shot guessing.
- A small technique library for saving and replaying working patterns.

## Core Thinking Model (How To Think With This MCP)

Use this loop for every non-trivial task:

1. **Check system first** - Read GPU state before loading models. Start with `comfy_get_system_stats`, `comfy_check_vram`.

2. **Check memory** - Before building from scratch, use `comfy_search_techniques` to check if a similar workflow already exists in the library.

3. **Build in small steps** - Use `comfy_build_workflow` for any intent (txt2img, img2img, upscale, inpaint, controlnet, txt2video, img2video, image2_3d, txt2music) and the family is auto-detected from the installed checkpoint. For common recipes, start from `comfy_insert_blueprint(name="flux2-txt2img")` or any of the 9 bundled blueprints. Validate with `comfy_validate_workflow` before queueing (5-pass: schema, catalog, graph, environment, execution-risk).

4. **Monitor and retrieve** - Queue with `comfy_queue_prompt`, watch with `comfy_watch_progress`, retrieve with `comfy_get_output_image` (returns image content blocks directly in chat).

5. **Snapshot before changes** - Always `comfy_snapshot_workflow` before modifying a working workflow. Use `comfy_diff_snapshots` and `comfy_restore_snapshot` for undo.

6. **Route outputs** - Send generated images to disk, TouchDesigner, or Blender with `comfy_send_to_disk`, `comfy_send_to_td`, `comfy_send_to_blender`.

## Tool Map (73 Tools)

### 1) System + GPU
Use for connection health, GPU diagnostics, and VRAM management.

- `comfy_get_system_stats`, `comfy_get_gpu_info`, `comfy_get_features`
- `comfy_list_extensions`, `comfy_restart`, `comfy_free_vram`

### 2) Models
Use for discovering and managing checkpoints, LoRAs, VAEs, and other model files.

- `comfy_list_models`, `comfy_get_model_info`, `comfy_list_model_folders`
- `comfy_search_models`, `comfy_refresh_models`

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

### 15) Model Hub Search
Use for discovering models to download from public hubs.

- `comfy_search_hub` - Search HuggingFace or CivitAI for models matching a query. Returns normalized hits (id, name, url, downloads, tags). Use `source="huggingface"` or `source="civitai"`.

## MCP Resources

Five fixed resources:

- `comfy://system/info` - System stats, GPU info, ComfyUI version
- `comfy://server/capabilities` - Detected server profile, version, auth method, WebSocket availability
- `comfy://nodes/catalog` - Node catalog preview (first 100 names)
- `comfy://models/{folder}` - Model listing by folder (checkpoints, loras, vae, diffusion_models, text_encoders, etc.)
- `comfy://embeddings` - Available embeddings

Plus three resource templates (parameterized URIs):

- `comfy://nodes/catalog/{page}` - Paginated node catalog, 100 nodes per page (`{page}` = 0, 1, 2, ...)
- `comfy://nodes/by-category/{category}` - Node class_types whose category starts with the given prefix (e.g. `sampling`, `loaders/video`)
- `comfy://templates/catalog` - Workflow templates advertised by ComfyUI core + custom nodes (via `/workflow_templates`)

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
- Family-aware generation across 10 model families (SD 1.5, SDXL, SD 3.5, Flux 2, Qwen-Image, Wan 2.2, LTX-2, HunyuanVideo, Hunyuan3D, ACE-Step) covering images, video, 3D meshes, and music.
- Starting from bundled blueprints for every family (9 ship in-repo) and customizing from there.
- 5-pass workflow validation catching broken links, missing models, oversized latents before you hit ComfyUI.
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
- Running without a live ComfyUI instance (this is a bridge, not a runtime).
- Streaming real-time video output (snapshots and polls, not live frames).
- Automatic custom node installation or dependency management.
- "One shot perfect generation" without iterative refinement.

## Model Families

10 first-class model families. Each has a builder template (or several) that emits a workflow matched to the right graph topology. The family is detected from the checkpoint filename; you can override by passing `checkpoint=` in params.

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
| Workflow JSON (v0.17+ spec) | Supported | 5-pass validation: schema + catalog + graph + environment + execution-risk |
| V3 custom nodes | Supported | Normalized NodeSchema parses V1 dict-of-tuples and V3 class-based shapes transparently |
| Subgraph Blueprints | Supported | User + bundled store, list/insert/publish tools |
| Model families (builder) | Supported | SD 1.5, SDXL, SD 3.5, Flux 2, Qwen-Image, Wan 2.2 (t2v/i2v), LTX-2, HunyuanVideo (t2v/i2v), Hunyuan3D, ACE-Step |
| WebSocket progress events | Supported where `/ws` is available | Binary preview frames are ignored safely |
| Image content blocks | Supported | Inline image display in chat |
| Cross-app routing | Filesystem only | Saves to disk with suggested commands |
| `/workflow_templates` resource | Supported | Exposed as `comfy://templates/catalog` |

## Quick Setup

Local development runtime:

```bash
git clone https://github.com/dreamrec/ComfyPilot.git
cd ComfyPilot
uv sync
uv run comfypilot
```

Claude Code plugin (one-command install):

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

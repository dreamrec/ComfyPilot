---
name: comfypilot-core
description: Core patching discipline for working with ComfyUI through MCP tools. Use this skill whenever the user mentions ComfyUI, Stable Diffusion workflows, image generation pipelines (SDXL, SD 3.5, Flux 2, Qwen-Image, Ernie Image), video generation (Wan 2.2, LTX-2, HunyuanVideo), music generation (ACE-Step), image-to-3D (Hunyuan3D), super-resolution (SUPIR), frame interpolation (RIFE / FILM), segmentation (SAM 3.1), LoRA training, text-to-audio (Stable Audio), or wants to build, queue, monitor, or modify ComfyUI workflows.
---

# ComfyPilot Core Skill

Use this when working with ComfyUI through ComfyPilot's 96 MCP tools (tested with ComfyUI v0.20.0-v0.31.1). v1.9.0 adds modern jobs, strict live-schema validation, Desktop-aware control, generic artifacts, worker observability, native global subgraphs, and expanded V3 widget/schema support.

## Default Workflow

1. **Check system** - `comfy_get_system_stats` (typed `SystemStats`) to verify GPU, VRAM, ComfyUI version.
2. **Check VRAM** - `comfy_check_vram` (typed `VRAMStatus`) for headroom before loading large models.
3. **Discover or build**
   - Search the library first: `comfy_search_techniques` for saved patterns, or `comfy_list_blueprints` for blueprints (13 bundled; pass `source="native"` to read canonical ComfyUI global subgraphs).
   - Build: `comfy_build_workflow(template=<intent>)` auto-detects the installed checkpoint family and emits the right graph (SD 1.5 / SDXL / SD 3.5 / Flux 2 / Qwen / Wan 2.2 / LTX-2 / HunyuanVideo / Hunyuan3D / ACE-Step / Ernie Image). Family-agnostic intents (`super_resolution`, `interpolate_frames`, `segment`, `train_lora`, `txt2audio`) skip checkpoint detection and dispatch by intent name.
   - Or insert a blueprint: `comfy_insert_blueprint(name="flux2-txt2img")` and override inputs. Bundled: flux2-txt2img, sd35-txt2img, sdxl-hires-fix, qwen-txt2img, wan22-txt2video, ltx2-txt2video, hunyuan-video-txt2video, hunyuan3d-image2_3d, acestep-txt2music, ernie-txt2img, supir-upscale, rife-interpolate, sam31-segment.
4. **Validate** - `comfy_validate_workflow` (typed `ValidationReport`) runs 6 passes: schema / catalog / graph / anti_cycle / environment / execution_risk. Anti-cycle mirrors ComfyUI v0.20's execution-side cycle detection. Environment pass also runs a deprecated-model lint that warns on retired partner models.
5. **Snapshot before changes** - `comfy_snapshot_workflow` saves state. Set `COMFY_SNAPSHOT_DIR` to persist across restarts.
6. **Queue** - `comfy_queue_prompt` (typed `QueueAck`) submits for execution. Preserves `error`/`node_errors` from ComfyUI.
7. **Monitor** - `comfy_watch_progress` (typed `WatchProgressFrame`) polls. `comfy_describe_dynamics` (typed `DynamicsReport`) for full queue + events + active jobs view.
8. **Retrieve** - `comfy_get_output_image` returns image content blocks directly in chat.
9. **Route** - `comfy_send_to_disk` / `comfy_send_to_td` / `comfy_send_to_blender` - atomic writes with `<filename>.json` manifest sidecars (prompt_id, seeds, model refs, dimensions).

## Safety

- Always check VRAM before loading large models.
- Snapshot before modifying a working workflow.
- Destructive ops gate on elicitation when `confirm=False`: `comfy_clear_queue`, `comfy_clear_history`, `comfy_delete_history`, `comfy_delete_snapshot`, `comfy_emergency_stop`. Pass `confirm=True` to skip the prompt when the agent has verified intent.
- `comfy_emergency_stop` is the last-resort: interrupts, clears queue, frees VRAM.

## Tool Categories (96 tools)

- **System (6):** stats, GPU info, features, extensions, restart, free VRAM
- **Models (5):** list, info, folders (live /models discovery), search (all folders by default), refresh (per-folder counts). Covers `diffusion_models`, `text_encoders`, `clip_vision`, `style_models`, `gligen`, etc. - not just `checkpoints`.
- **Workflow (11):** queue, get queue, list/get jobs, single/batch cancel, interrupt, clear, validate, export, import
- **Nodes (6):** list types, get info, search, categories, embeddings, inspect widget
- **Images (5):** get output, upload, list outputs, download batch, get URL
- **History (5):** get history, get result, delete, clear, search
- **Monitoring (6):** watch progress, subscribe, unsubscribe, get events, describe dynamics, get status
- **Snapshots (6):** snapshot, list, diff, restore, delete, auto-snapshot
- **Memory (5):** save technique, search, list, replay, favorite
- **Safety (5):** check VRAM, set limits, detect instability, validate before queue, emergency stop
- **Builder (5):** build workflow (family-aware), add node, connect nodes, set widget, apply template
- **Output Routing (4):** send to disk, send to TD, send to Blender, list destinations
- **Subgraph Blueprints (3):** list (source=user/bundled/native/all), insert, publish
- **Viz + Ingest + Sweep (4):** visualize (Mermaid), import from PNG, parameter sweep, sweep grid (n-dim Cartesian product)
- **Hub Search (1):** search HuggingFace or CivitAI
- **Partner APIs (1):** list installed partner / API custom nodes (Veo, Kling, Seedance, GPT-Image, Topaz, Tripo3D, Rodin, etc.) intersected with a curated catalog
- **Lifecycle (5, v1.8.0):** launch_server, stop_server, install_node, list_installed_nodes, download_model - comfy-cli wrappers for full setup-to-server flow
- **Diagnostics (5, v1.8.0):** extract_schema (workflow controllability summary), fetch_logs (traceback from /history), inspect_workflow (custom-node trust check), recommend_runtime (hardware verdict: ok/marginal/cloud), suggest_timeout (per-workflow HTTP timeout)
- **Convenience (3, v1.8.0):** install_workflow_deps (auto-install missing custom nodes from a workflow), run_with_inputs (upload+inject+queue in one call), randomize_seeds (replace seed=-1 sentinels)
- **Desktop + Artifacts + Workers (5):** instance doctor, generic artifact list/get, comfy-env status, active isolated workers

## Resources (6 fixed + 4 templates)

- `comfy://system/info` - System stats
- `comfy://server/capabilities` - Profile, version, frontend_version, auth method, WS availability, openapi_version, cache_provider
- `comfy://nodes/catalog` - First-100 node preview
- `comfy://models/{folder}` - Model listing by folder
- `comfy://embeddings` - Embeddings
- `comfy://api/openapi` - Optional OpenAPI 3.1 spec when `/openapi.json` is exposed

Templates (parameterized URIs):
- `comfy://nodes/catalog/{page}` - Paginated catalog (100 per page)
- `comfy://nodes/by-category/{category}` - Filter by category prefix
- `comfy://templates/catalog` - ComfyUI `/workflow_templates`
- `comfy://docs/{node_class}` - Embedded Markdown docs with object_info fallback

## Structured Output

10 tools return typed Pydantic models: `SystemStats`, `VRAMStatus`, `ModelList`, `TechniqueList`, `SnapshotList`, `DynamicsReport`, `QueueAck`, `ValidationReport`, `RunResult`, `WatchProgressFrame`. Use attribute access on the return value rather than `json.loads`.

## Transports

- **stdio** (default) - Local Claude Code, Claude Desktop, Cursor.
- **streamable-http** - Hosted or remote: `comfypilot --transport streamable-http --host 0.0.0.0 --port 8765`.

## Model Families (builder dispatch)

| Family | Intents |
|---|---|
| SD 1.5 | txt2img, img2img, upscale, inpaint, controlnet |
| SDXL | txt2img |
| SD 3.5 | txt2img |
| Flux 2 / Klein | txt2img |
| Qwen-Image | txt2img |
| Wan 2.2 | txt2video, img2video |
| LTX-2 | txt2video |
| HunyuanVideo 1.5 | txt2video, img2video |
| Hunyuan3D 2.1 | image2_3d |
| ACE-Step 1.5 XL | txt2music |
| Ernie Image | txt2img |

### Family-agnostic intents (intent-override dispatch)

These bypass family detection and dispatch by intent name regardless of the detected checkpoint family.

| Intent | Purpose |
|---|---|
| `super_resolution` | SUPIR image super-resolution / restoration (ComfyUI v0.20.0+) |
| `interpolate_frames` | RIFE or FILM frame interpolation (`method="rife" | "film"`, multiplier 2/4/8) |
| `segment` | SAM 3.1 prompt-based segmentation |
| `train_lora` | Native LoRA training (TrainLoraDataLoader + TrainLora + SaveLora, multi-resolution buckets) |
| `txt2audio` | Stable Audio 2.5 / general text-to-audio (distinct from ACE-Step `txt2music`) |

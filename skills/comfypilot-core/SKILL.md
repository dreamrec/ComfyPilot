---
name: comfypilot-core
description: Core patching discipline for working with ComfyUI through MCP tools. Use this skill whenever the user mentions ComfyUI, Stable Diffusion workflows, image generation pipelines, video generation (Wan, LTX, HunyuanVideo), music generation (ACE-Step), image-to-3D (Hunyuan3D), or wants to build, queue, monitor, or modify ComfyUI workflows.
---

# ComfyPilot Core Skill

Use this when working with ComfyUI through ComfyPilot's 73 MCP tools.

## Default Workflow

1. **Check system** - `comfy_get_system_stats` (typed `SystemStats`) to verify GPU, VRAM, ComfyUI version.
2. **Check VRAM** - `comfy_check_vram` (typed `VRAMStatus`) for headroom before loading large models.
3. **Discover or build**
   - Search the library first: `comfy_search_techniques` for saved patterns, or `comfy_list_blueprints` for bundled blueprints (one per family).
   - Build: `comfy_build_workflow(template=<intent>)` auto-detects the installed checkpoint family and emits the right graph (SD 1.5 / SDXL / SD 3.5 / Flux 2 / Qwen / Wan 2.2 / LTX-2 / HunyuanVideo / Hunyuan3D / ACE-Step).
   - Or insert a blueprint: `comfy_insert_blueprint(name="flux2-txt2img")` and override inputs.
4. **Validate** - `comfy_validate_workflow` (typed `ValidationReport`) runs 5 passes: schema / catalog / graph / environment / execution_risk.
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

## Tool Categories (73 tools)

- **System (6):** stats, GPU info, features, extensions, restart, free VRAM
- **Models (5):** list, info, folders, search, refresh
- **Workflow (8):** queue, get queue, cancel, interrupt, clear, validate, export, import
- **Nodes (6):** list types, get info, search, categories, embeddings, inspect widget
- **Images (5):** get output, upload, list outputs, download batch, get URL
- **History (5):** get history, get result, delete, clear, search
- **Monitoring (6):** watch progress, subscribe, unsubscribe, get events, describe dynamics, get status
- **Snapshots (6):** snapshot, list, diff, restore, delete, auto-snapshot
- **Memory (5):** save technique, search, list, replay, favorite
- **Safety (5):** check VRAM, set limits, detect instability, validate before queue, emergency stop
- **Builder (5):** build workflow (family-aware), add node, connect nodes, set widget, apply template
- **Output Routing (4):** send to disk, send to TD, send to Blender, list destinations
- **Subgraph Blueprints (3):** list, insert, publish
- **Viz + Ingest + Sweep (3):** visualize (Mermaid), import from PNG, parameter sweep
- **Hub Search (1):** search HuggingFace or CivitAI

## Resources (5 fixed + 3 templates)

- `comfy://system/info` - System stats
- `comfy://server/capabilities` - Profile, version, auth method, WS availability
- `comfy://nodes/catalog` - First-100 node preview
- `comfy://models/{folder}` - Model listing by folder
- `comfy://embeddings` - Embeddings

Templates (parameterized URIs):
- `comfy://nodes/catalog/{page}` - Paginated catalog (100 per page)
- `comfy://nodes/by-category/{category}` - Filter by category prefix
- `comfy://templates/catalog` - ComfyUI `/workflow_templates`

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

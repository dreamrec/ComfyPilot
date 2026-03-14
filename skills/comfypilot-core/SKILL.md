---
name: comfypilot-core
description: Core patching discipline for working with ComfyUI through MCP tools. Use this skill whenever the user mentions ComfyUI, Stable Diffusion workflows, image generation pipelines, or wants to build/queue/monitor ComfyUI workflows.
---

# ComfyPilot Core Skill

Use this when working with ComfyUI through MCP tools.

## Workflow
1. Check system: `comfy_get_system_stats` — verify GPU, VRAM, version
2. Check VRAM: `comfy_check_vram` — ensure headroom before loading models
3. Build workflow: `comfy_build_workflow` or `comfy_instantiate_template` — family-aware defaults (SD1.5/SDXL/FLUX)
4. Validate: `comfy_validate_workflow` — catch errors before queueing
5. Queue: `comfy_queue_prompt` — submit for execution
6. Monitor: `comfy_watch_progress` — poll until complete
7. Retrieve: `comfy_get_output_image` — see the generated image
8. Route: `comfy_send_to_disk` / `comfy_send_to_td` / `comfy_send_to_blender`

## Safety
- Always `comfy_check_vram` before loading large models
- Use `comfy_snapshot_workflow` before modifications
- `comfy_emergency_stop` if anything goes wrong

## Tool Categories (90 tools)
- **System (6):** stats, GPU info, features, extensions, restart, free VRAM
- **Models (5):** list, info, folders, search, refresh
- **Workflow (8):** queue, get queue, cancel, interrupt, clear, validate, export, import
- **Nodes (6):** list types, get info, search, categories, embeddings, inspect widget
- **Images (5):** get output, upload, list outputs, download batch, get URL
- **History (5):** get history, get result, delete, clear, search
- **Monitoring (4):** watch progress, get events, describe dynamics, get status
- **Snapshots (6):** snapshot, list, diff, restore, delete, auto-snapshot
- **Memory (5):** save technique, search, list, replay, favorite
- **Safety (5):** check VRAM, set limits, detect instability, emergency stop, validate before queue
- **Builder (5):** build workflow, add node, connect nodes, set widget, apply template
- **Output Routing (4):** send to disk, send to TD, send to Blender, list destinations
- **Templates (6):** search, get, list categories, status, discover, instantiate
- **Knowledge (5):** status, refresh all, clear cache, get config, set config
- **Install + Compat (9):** snapshot, list models/nodes, health, resolve model, check compat, explain, suggest, validate
- **Registry (4):** search, get package, check compat, resolve missing

## Resources (10)
- `comfy://system/info` — System stats
- `comfy://server/capabilities` — Server capabilities
- `comfy://nodes/catalog` — Node catalog
- `comfy://models/{folder}` — Model listing
- `comfy://embeddings` — Embeddings list
- `comfy://docs/summary` — Documentation summary
- `comfy://templates/catalog` — Template catalog
- `comfy://install/snapshot` — Install graph snapshot
- `comfy://knowledge/status` — Knowledge layer status
- `comfy://support-matrix` — Feature support matrix

```
 ██████╗ ██████╗ ███╗   ███╗███████╗██╗   ██╗██████╗ ██╗██╗      ██████╗ ████████╗
██╔════╝██╔═══██╗████╗ ████║██╔════╝╚██╗ ██╔╝██╔══██╗██║██║     ██╔═══██╗╚══██╔══╝
██║     ██║   ██║██╔████╔██║█████╗   ╚████╔╝ ██████╔╝██║██║     ██║   ██║   ██║
██║     ██║   ██║██║╚██╔╝██║██╔══╝    ╚██╔╝  ██╔═══╝ ██║██║     ██║   ██║   ██║
╚██████╗╚██████╔╝██║ ╚═╝ ██║██║        ██║   ██║     ██║███████╗╚██████╔╝   ██║
 ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝        ╚═╝   ╚═╝     ╚═╝╚══════╝ ╚═════╝    ╚═╝
```

# ComfyPilot v1.0.0

**ComfyPilot** is an MCP server for ComfyUI.
It gives an AI agent a clean tool surface for workflow building, queueing, progress monitoring, image retrieval, snapshots, and VRAM safety.

## Documentation

- Production manual: `docs/MANUAL.md`
- Release notes: `CHANGELOG.md`

## What This Is

- A practical bridge between AI agents and ComfyUI.
- A 66-tool MCP surface for workflows, models, images, monitoring, safety, and routing.
- A workflow-oriented loop built for iteration, not one-shot guessing.
- A small technique library for saving and replaying working patterns.

## Core Thinking Model (How To Think With This MCP)

Use this loop for every non-trivial task:

1. **Check system first** - Read GPU state before loading models. Start with `comfy_get_system_stats`, `comfy_check_vram`.

2. **Check memory** - Before building from scratch, use `comfy_search_techniques` to check if a similar workflow already exists in the library.

3. **Build in small steps** - Use `comfy_build_workflow` for common patterns (txt2img, img2img, upscale, inpaint, controlnet), or construct API-format JSON. Validate with `comfy_validate_workflow` before queueing.

4. **Monitor and retrieve** - Queue with `comfy_queue_prompt`, watch with `comfy_watch_progress`, retrieve with `comfy_get_output_image` (returns image content blocks directly in chat).

5. **Snapshot before changes** - Always `comfy_snapshot_workflow` before modifying a working workflow. Use `comfy_diff_snapshots` and `comfy_restore_snapshot` for undo.

6. **Route outputs** - Send generated images to disk, TouchDesigner, or Blender with `comfy_send_to_disk`, `comfy_send_to_td`, `comfy_send_to_blender`.

## Tool Map (66 Tools)

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
Use for template-based workflow construction and editing.

- `comfy_build_workflow` - Build from templates: txt2img, img2img, upscale, inpaint, controlnet.
- `comfy_add_node` - Add a node to a workflow-in-progress.
- `comfy_connect_nodes` - Wire node outputs to inputs.
- `comfy_set_widget_value` - Set widget values on nodes.
- `comfy_apply_template` - Apply a named template to an existing workflow.

### 12) Output Routing
Use for agent-orchestrated cross-app delivery of generated images.

- `comfy_send_to_disk` - Save output image to local filesystem.
- `comfy_send_to_td` - Route output to TouchDesigner project directory.
- `comfy_send_to_blender` - Route output to Blender project directory.
- `comfy_list_destinations` - List configured output destinations.

## MCP Resources (5)

- `comfy://system/info` - System stats, GPU info, ComfyUI version
- `comfy://server/capabilities` - Detected server profile, version, auth method
- `comfy://nodes/catalog` - Node catalog preview (first 100 names)
- `comfy://models/{folder}` - Model listing by folder (checkpoints, loras, etc.)
- `comfy://embeddings` - Available embeddings

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
- Template-based generation (txt2img, img2img, upscale, inpaint, controlnet) with sensible defaults.
- Monitoring GPU resources and preventing OOM situations.
- Returning generated images directly in the chat (image content blocks).
- Cross-app output routing to TouchDesigner and Blender projects.
- Snapshot/restore for non-destructive workflow experimentation.
- Learning and replaying reusable workflow patterns.

## What It Is Not Good At

- Replacing artistic direction by itself.
- Running without a live ComfyUI instance (this is a bridge, not a runtime).
- Streaming real-time video output (snapshots and polls, not live frames).
- Automatic custom node installation or dependency management.
- "One shot perfect generation" without iterative refinement.

## Support Matrix

| Feature | Status | Notes |
|---|---|---|
| Local ComfyUI (self-hosted) | Supported | Primary target |
| Comfy Cloud API | Partial | Auth and route probing supported; progress depends on remote WS support |
| stdio transport | Supported | Default |
| Streamable HTTP transport | Not yet | Planned |
| Workflow JSON (v0.17+ spec) | Supported | Multi-pass validation (schema + catalog + graph) |
| V3 custom nodes | Not tested | V3 migration is ongoing in ComfyUI |
| WebSocket progress events | Supported where `/ws` is available | Binary preview frames are ignored safely |
| Image content blocks | Supported | Inline image display in chat |
| Cross-app routing | Filesystem only | Saves to disk with suggested commands |

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

- `COMFY_URL` (default `http://127.0.0.1:8188`) - ComfyUI server URL
- `COMFY_API_KEY` (default empty) - Optional API key for authenticated access
- `COMFY_TIMEOUT` (default `300`) - HTTP request timeout in seconds
- `COMFY_SNAPSHOT_LIMIT` (default `50`) - Maximum workflow snapshots retained in memory
- `COMFY_OUTPUT_DIR` (default `~/comfypilot_output`) - Image output directory for disk routing
- `COMFY_TD_OUTPUT_DIR` (default `~/comfypilot_output/touchdesigner`) - TouchDesigner output path
- `COMFY_BLENDER_OUTPUT_DIR` (default `~/comfypilot_output/blender`) - Blender output path
- `COMFY_AUTH_METHOD` (default `auto`) - Auth method: `auto`, `bearer`, or `x-api-key`

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

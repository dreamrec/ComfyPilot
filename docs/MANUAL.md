# ComfyPilot Production Manual

Complete reference for operating ComfyPilot — the MCP server for live AI control of ComfyUI.

## Architecture

```
┌──────────────┐     stdio      ┌──────────────┐    HTTP/WS     ┌──────────────┐
│  MCP Client  │◄──────────────►│  ComfyPilot  │◄─────────────►│   ComfyUI    │
│ (Claude, etc)│                │  (FastMCP)   │               │  (GPU host)  │
└──────────────┘                └──────────────┘               └──────────────┘
                                       │
                                       ├── ComfyClient (HTTP + WebSocket)
                                       ├── EventManager (WS auto-reconnect)
                                       ├── JobTracker (prompt completion)
                                       ├── SnapshotManager (in-memory LRU)
                                       ├── TechniqueStore (persistent JSON)
                                       └── VRAMGuard (safety thresholds)
```

ComfyPilot runs as an MCP server over stdio transport. It maintains a persistent HTTP connection to ComfyUI's REST API and a WebSocket connection for real-time progress events. All subsystems are initialized during the lifespan phase and shared across tool invocations.

## Connection Model

**ComfyClient** handles all HTTP communication with ComfyUI:
- REST endpoints for querying system state, models, nodes, history
- Image upload/download via multipart form data
- Prompt queueing via POST to `/prompt`
- Configurable timeout (default 300s for long generations)

**EventManager** maintains a WebSocket connection to ComfyUI's `/ws` endpoint:
- Auto-reconnect on disconnect
- Event buffering with deque (maxlen=1000)
- Supports `progress`, `executing`, `execution_cached`, `execution_error` events

**JobTracker** monitors prompt execution:
- Tracks queued prompt IDs
- Polls history endpoint for completion
- Returns full output metadata including image filenames

## Tool Reference

### System Tools (6)

| Tool | Description | Annotations |
|------|-------------|-------------|
| `comfy_get_system_stats` | GPU info, VRAM, ComfyUI version, Python/PyTorch versions | readOnly |
| `comfy_get_gpu_info` | Detailed GPU device information | readOnly |
| `comfy_get_features` | Enabled ComfyUI features | readOnly |
| `comfy_get_extensions` | Installed custom node extensions | readOnly |
| `comfy_restart_server` | Restart the ComfyUI server process | destructive |
| `comfy_free_vram` | Unload models and free GPU memory | destructive |

### Model Tools (5)

| Tool | Description |
|------|-------------|
| `comfy_list_models` | List models in a folder (checkpoints, loras, vae, etc.) with pagination |
| `comfy_get_model_info` | Detailed info for a specific model file |
| `comfy_list_model_folders` | List available model folder categories |
| `comfy_search_models` | Search across all model folders by name pattern |
| `comfy_refresh_models` | Force ComfyUI to rescan model directories |

### Workflow Execution Tools (8)

| Tool | Description |
|------|-------------|
| `comfy_queue_prompt` | Submit a workflow (API-format JSON) for execution |
| `comfy_get_queue` | Get current queue state (running + pending) |
| `comfy_cancel_job` | Cancel a specific queued job by prompt ID |
| `comfy_interrupt` | Interrupt the currently running generation |
| `comfy_clear_queue` | Clear all pending jobs from the queue |
| `comfy_validate_workflow` | Validate a workflow against the node catalog |
| `comfy_export_workflow` | Export a workflow as shareable JSON |
| `comfy_import_workflow` | Import a workflow from JSON |

### Node Tools (6)

| Tool | Description |
|------|-------------|
| `comfy_list_node_types` | List available node types with pagination |
| `comfy_get_node_info` | Detailed schema for a specific node type (inputs, outputs, widgets) |
| `comfy_search_nodes` | Search nodes by name, category, or description |
| `comfy_list_categories` | List all node categories |
| `comfy_get_embeddings` | List available text embeddings |
| `comfy_inspect_widget` | Inspect a specific widget's schema and valid values |

### Image Tools (5)

| Tool | Description |
|------|-------------|
| `comfy_get_output_image` | Retrieve a generated image — returns as image content block in chat |
| `comfy_upload_image` | Upload an image to ComfyUI's input directory |
| `comfy_list_outputs` | List generated output images |
| `comfy_download_batch` | Download multiple output images |
| `comfy_get_image_url` | Get the direct URL for an output image |

**Image content blocks**: `comfy_get_output_image` returns images as base64-encoded content blocks that display directly in the chat. This is the primary way to view generated results.

### History Tools (5)

| Tool | Description |
|------|-------------|
| `comfy_get_history` | Get execution history with pagination |
| `comfy_get_run_result` | Get full result for a specific prompt ID |
| `comfy_delete_history` | Delete a specific history entry |
| `comfy_clear_history` | Clear all history |
| `comfy_search_history` | Search history by prompt ID or output metadata |

### Monitoring Tools (6)

| Tool | Description |
|------|-------------|
| `comfy_watch_progress` | Poll-based progress monitoring for an active job |
| `comfy_subscribe_events` | Subscribe to WebSocket event types |
| `comfy_unsubscribe_events` | Unsubscribe from event types |
| `comfy_get_events` | Get buffered events with optional type filter |
| `comfy_describe_dynamics` | Observe system dynamics over a time window |
| `comfy_get_status` | Get current execution status |

### Snapshot Tools (6)

| Tool | Description |
|------|-------------|
| `comfy_snapshot_workflow` | Save current workflow state as a named snapshot |
| `comfy_list_snapshots` | List all snapshots (newest first) |
| `comfy_diff_snapshots` | Compare two snapshots or snapshot vs current |
| `comfy_restore_snapshot` | Restore workflow from a snapshot |
| `comfy_delete_snapshot` | Delete a snapshot |
| `comfy_auto_snapshot` | Toggle automatic snapshotting before modifications |

**Snapshot storage**: In-memory with LRU eviction. Default limit: 50 snapshots (configurable via `COMFY_SNAPSHOT_LIMIT`). Snapshots are lost on server restart.

### Memory Tools (5)

| Tool | Description |
|------|-------------|
| `comfy_save_technique` | Save a workflow as a reusable technique with name, description, tags |
| `comfy_search_techniques` | Search techniques by text query and/or tags |
| `comfy_list_techniques` | List all saved techniques with metadata |
| `comfy_replay_technique` | Load a saved technique's workflow |
| `comfy_favorite_technique` | Favorite and rate (0-5) a technique |

**Technique storage**: Persistent JSON files at `~/.comfypilot/techniques/`. Each technique is a separate `.json` file containing the full workflow plus metadata.

### Safety Tools (5)

| Tool | Description |
|------|-------------|
| `comfy_check_vram` | Check VRAM usage — returns ok/warn/critical status |
| `comfy_set_limits` | Configure thresholds: warn % (default 80), block % (default 95), max queue (10) |
| `comfy_detect_instability` | Check for near-OOM, stuck jobs, error patterns |
| `comfy_validate_before_queue` | Pre-flight check: VRAM headroom + queue capacity |
| `comfy_emergency_stop` | Interrupt + clear queue + free all VRAM |

**VRAM status levels**:
- `ok` — Below warn threshold, safe to proceed
- `warn` — Above warn threshold (default 80%), proceed with caution
- `critical` — Above block threshold (default 95%), do not queue new prompts

### Builder Tools (5)

| Tool | Description |
|------|-------------|
| `comfy_build_workflow` | Build from template: txt2img, img2img, upscale, inpaint, controlnet |
| `comfy_add_node` | Add a node to a workflow-in-progress |
| `comfy_connect_nodes` | Wire node outputs to inputs |
| `comfy_set_widget_value` | Set widget values on existing nodes |
| `comfy_apply_template` | Apply a template modification to an existing workflow |

**Templates** provide sensible defaults (checkpoint, dimensions, steps, CFG, sampler) that can be overridden. They generate ComfyUI API-format JSON ready for `comfy_queue_prompt`.

### Output Routing Tools (4)

| Tool | Description |
|------|-------------|
| `comfy_send_to_disk` | Save output image to filesystem with configurable path |
| `comfy_send_to_td` | Copy output to TouchDesigner project directory |
| `comfy_send_to_blender` | Copy output to Blender project directory |
| `comfy_list_destinations` | List configured output destinations and their paths |

Output routing is agent-orchestrated — the AI decides where to send results based on the user's creative pipeline context.

## MCP Resources

Resources provide static/semi-static data without tool call overhead:

| URI | Description |
|-----|-------------|
| `comfy://system/info` | System stats, GPU info, ComfyUI version |
| `comfy://nodes/catalog` | First 100 node types from the catalog |
| `comfy://models/{folder}` | Models in a specific folder |
| `comfy://embeddings` | Available embeddings |

## Safety Protocol

### Before Every Generation
1. `comfy_check_vram` — Verify GPU has headroom
2. `comfy_validate_before_queue` — Check VRAM + queue capacity
3. `comfy_validate_workflow` — Catch node/wiring errors

### Before Workflow Modifications
1. `comfy_snapshot_workflow` — Save current state
2. Make changes
3. `comfy_validate_workflow` — Verify changes are valid
4. If broken: `comfy_restore_snapshot` to roll back

### Emergency Recovery
1. `comfy_emergency_stop` — Interrupts, clears queue, frees VRAM
2. `comfy_detect_instability` — Diagnose what went wrong
3. `comfy_check_vram` — Verify recovery

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMFY_URL` | `http://127.0.0.1:8188` | ComfyUI REST API URL |
| `COMFY_API_KEY` | *(empty)* | API key for authenticated ComfyUI instances |
| `COMFY_TIMEOUT` | `300` | HTTP timeout in seconds |
| `COMFY_SNAPSHOT_LIMIT` | `50` | Max in-memory snapshots |
| `COMFY_OUTPUT_DIR` | `~/comfypilot_output` | Default image output directory |
| `COMFY_TD_OUTPUT_DIR` | `~/comfypilot_output/touchdesigner` | TouchDesigner routing path |
| `COMFY_BLENDER_OUTPUT_DIR` | `~/comfypilot_output/blender` | Blender routing path |

### Remote ComfyUI

ComfyPilot supports remote ComfyUI instances. Set `COMFY_URL` to the remote address:

```bash
COMFY_URL=https://your-remote-host:8188 uv run comfypilot
```

For Tailscale-connected machines:
```bash
COMFY_URL=https://machine-name.tail12345.ts.net uv run comfypilot
```

If the remote instance requires authentication, set `COMFY_API_KEY`.

## File Structure

```
ComfyPilot/
├── .claude-plugin/
│   └── plugin.json          # Claude Code plugin manifest
├── .mcp.json                # MCP server config (plugin-portable)
├── docs/
│   └── MANUAL.md            # This file
├── mcp/
│   ├── manifest.json        # Standardized MCP manifest
│   └── profiles/            # Client config examples
│       ├── claude-desktop.json
│       ├── cursor.json
│       └── generic.json
├── skills/
│   └── comfypilot-core/
│       └── SKILL.md          # Core workflow skill
├── src/
│   └── comfy_mcp/
│       ├── server.py         # FastMCP server + lifespan + resources
│       ├── comfy_client.py   # Async HTTP client for ComfyUI
│       ├── tool_registry.py  # Central tool import aggregator
│       ├── events/
│       │   └── event_manager.py  # WebSocket event system
│       ├── jobs/
│       │   └── job_tracker.py    # Prompt completion tracking
│       ├── memory/
│       │   ├── snapshot_manager.py  # In-memory LRU snapshots
│       │   └── technique_store.py   # Persistent technique library
│       ├── safety/
│       │   └── vram_guard.py        # VRAM monitoring + safety
│       └── tools/
│           ├── system.py       # System tools
│           ├── models.py       # Model tools
│           ├── workflow.py     # Workflow execution tools
│           ├── nodes.py        # Node schema tools
│           ├── images.py       # Image tools
│           ├── history.py      # History tools
│           ├── monitoring.py   # Monitoring tools
│           ├── snapshots.py    # Snapshot tools
│           ├── memory.py       # Technique memory tools
│           ├── safety.py       # Safety tools
│           ├── builder.py      # Workflow builder tools
│           └── output_routing.py  # Cross-app routing tools
├── tests/                    # 275 tests across 17 files
├── pyproject.toml
├── CHANGELOG.md
├── LICENSE
└── README.md
```

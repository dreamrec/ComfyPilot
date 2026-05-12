# ComfyPilot Production Manual

Complete reference for operating ComfyPilot - the MCP server for live control of ComfyUI.
88 tools, 6 resources + 4 resource templates, 11 model families + 5 intent-overrides, 13 bundled blueprints. ComfyUI v0.20+. v1.8.0 adds comfy-cli lifecycle + diagnostics + convenience layers.

## Architecture

```
[MCP Client] <-> [ComfyPilot] <-> [ComfyUI]
                   |
                   +-- ComfyClient (HTTP + WebSocket + capability probe)
                   +-- EventManager (WS auto-reconnect, event buffer, progress cache)
                   +-- JobTracker (7-state prompt lifecycle)
                   +-- SnapshotManager (optional disk-persistent, LRU-evicted)
                   +-- TechniqueStore (persistent JSON at ~/.comfypilot/techniques)
                   +-- BlueprintStore (user dir + bundled fallback)
                   +-- VRAMGuard (safety thresholds, emergency stop)
                   +-- Schemas (NodeSchema V1+V3 normalizer)
                   +-- Families (10-family detector + registry + builders)
                   +-- Responses (pydantic models for top-10 tools)
                   +-- Hub (HuggingFace + CivitAI search)
                   +-- Viz (Mermaid renderer)
                   +-- Ingest (PNG workflow metadata extractor)
```

ComfyPilot runs as an MCP server over stdio (default) or streamable-http (remote/hosted). It maintains a persistent HTTP connection to ComfyUI's REST API and starts a WebSocket listener when the connected profile actually exposes `/ws` (probed with a 3-second handshake attempt during startup). All subsystems are initialized during the FastMCP lifespan phase and shared across tool invocations.

## Connection Model

**ComfyClient** handles all HTTP communication with ComfyUI:
- REST endpoints for system state, models, nodes, history, queue
- Image upload/download via multipart form data
- Prompt queueing via POST to `/prompt`
- Configurable timeout (default 300s)
- Profile-aware routing: local ComfyUI (`/features`) vs Comfy Cloud (`/api/features`) with automatic 404 fallback
- Auth: `Authorization: Bearer` (local) or `X-API-Key` (cloud), auto-detected or forced via `COMFY_AUTH_METHOD`
- Active WebSocket reachability probe: `wss://.../ws` with 3s timeout (not just a profile check)

**EventManager** maintains a WebSocket connection to ComfyUI's `/ws` endpoint when reachable:
- Auto-reconnect with exponential backoff (capped at 16s, max 5 attempts)
- Event buffering with deque (maxlen=1000)
- Supports `progress`, `executing`, `execution_cached`, `execution_error`, `status` events
- Forwards auth headers to the WebSocket for authenticated instances
- Ignores binary preview frames safely
- Health reporting via `comfy_get_status` (running, connected, reconnect_count, buffer_size, subscriptions)

**JobTracker** monitors prompt execution with a 7-state lifecycle:
- `queued` -> `running` -> `completed` / `failed` / `cancelled` / `interrupted` / `timeout`
- Integrates with EventManager progress cache
- Records submitted_at / completed_at timestamps per transition
- Exposed via `comfy_describe_dynamics` and `comfy_get_run_result`

## Transports

| Transport | When to use | Launch |
|---|---|---|
| **stdio** (default) | Local desktop clients (Claude Code, Claude Desktop, Cursor) | `uv run comfypilot` |
| **streamable-http** | Hosted / remote / load-balanced deployments | `uv run comfypilot --transport streamable-http --host 0.0.0.0 --port 8765` |

## Tool Reference

**88 tools across 19 categories.**

### System Tools (6)

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_get_system_stats` | `SystemStats` | Typed: system info + GPU devices |
| `comfy_get_gpu_info` | json str | Detailed GPU device information |
| `comfy_get_features` | json str | Enabled ComfyUI features |
| `comfy_list_extensions` | json str | Installed custom node extensions |
| `comfy_restart` | json str | Report that restart is not supported by the standard API |
| `comfy_free_vram` | json str | Unload models and free GPU memory |

### Model Tools (5)

Every tool in this group uses live folder discovery. `comfy_list_model_folders` hits `GET /models` (falling back to a 16-folder static list when the endpoint is unreachable) and reports `source: live | fallback`. `comfy_search_models` searches every discovered folder by default, and `comfy_refresh_models` fetches counts per folder. This replaces the pre-1.6 hardcoded 5-folder default that missed every UNETLoader-based family (Flux 2, Qwen-Image, Wan 2.2, LTX-2, HunyuanVideo, Hunyuan3D) whose primary weights live under `diffusion_models/`.

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_list_models(folder, limit, offset)` | `ModelList` | Typed: paginated listing inside one folder. |
| `comfy_get_model_info(node_type)` | json str | Normalized `NodeSchema` for a model-loader node class. |
| `comfy_list_model_folders()` | json str | `{folders, count, source}`. Live folder list from ComfyUI, or the 16-folder fallback. |
| `comfy_search_models(query, folders=None)` | json str | Searches every discovered folder by default. Empty query = full inventory. Reports `folders_source` and `folders_scanned`. |
| `comfy_refresh_models()` | json str | Re-fetches across every folder. Returns `counts_by_folder`, `total_models`, and a per-folder `errors` list when individual folders fail. |

**Fallback folder list** (when `/models` is unreachable): `checkpoints`, `diffusion_models`, `unet`, `loras`, `vae`, `vae_approx`, `clip`, `text_encoders`, `clip_vision`, `controlnet`, `upscale_models`, `style_models`, `embeddings`, `hypernetworks`, `gligen`, `diffusers`.

### Workflow Execution Tools (8)

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_queue_prompt` | `QueueAck` | Typed: prompt_id, queue_position, error, node_errors, auto_snapshot |
| `comfy_get_queue` | json str | Current queue state (running + pending) |
| `comfy_cancel_run` | json str | Cancel a specific queued prompt by ID |
| `comfy_interrupt` | json str | Interrupt the currently running generation |
| `comfy_clear_queue` | json str | Clear all pending prompts (gated by elicitation when `confirm=False`) |
| `comfy_validate_workflow` | `ValidationReport` | Typed: 6-pass validation (schema + catalog + graph + anti_cycle + environment + execution_risk) |
| `comfy_export_workflow` | json str | Export a workflow as shareable JSON |
| `comfy_import_workflow` | json str | Parse a JSON string into a workflow dict |

### Node Tools (6)

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_list_node_types` | json str | List available node types with pagination |
| `comfy_get_node_info` | json str | Normalized `NodeSchema` for a node (V1 and V3 transparent) |
| `comfy_search_nodes` | json str | Search nodes by name |
| `comfy_get_categories` | json str | List all node categories |
| `comfy_get_embeddings` | json str | List available text embeddings |
| `comfy_inspect_widget` | json str | Widget-input vs link-input split, constraints preserved |

### Image Tools (5)

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_get_output_image` | image content | Retrieve a generated image (rendered directly in chat) |
| `comfy_upload_image` | json str | Upload an image to ComfyUI's input directory |
| `comfy_list_output_images` | json str | List generated output images |
| `comfy_download_batch` | json str | Return output image metadata for multiple files |
| `comfy_get_image_url` | json str | Get the direct URL for an output image |

### History Tools (5)

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_get_history` | json str | Execution history with pagination |
| `comfy_get_run_result` | `RunResult` | Typed: prompt_id, status, outputs, prompt (ComfyUI history entry) |
| `comfy_delete_history` | json str | Delete a specific history entry (gated by elicitation) |
| `comfy_clear_history` | json str | Clear all history (gated by elicitation) |
| `comfy_search_history` | json str | Search history by workflow node class name |

### Monitoring Tools (6)

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_watch_progress` | `WatchProgressFrame` | Typed: status, progress, max_progress, timestamp, elapsed_s |
| `comfy_subscribe` | json str | Subscribe to WebSocket event types |
| `comfy_unsubscribe` | json str | Unsubscribe from event types |
| `comfy_get_events` | json str | Drain buffered events with optional type filter |
| `comfy_describe_dynamics` | `DynamicsReport` | Typed: queue counts, event types seen, active job summary |
| `comfy_get_status` | json str | Overall status (queue + system + event-manager health) |

### Snapshot Tools (6)

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_snapshot_workflow` | json str | Save current workflow state as a named snapshot |
| `comfy_list_snapshots` | `SnapshotList` | Typed: snapshots array with id, name, timestamp, node_count |
| `comfy_diff_snapshots` | json str | Compare two snapshots or snapshot vs current |
| `comfy_restore_snapshot` | json str | Restore workflow from a snapshot |
| `comfy_delete_snapshot` | json str | Delete a snapshot (gated by elicitation) |
| `comfy_auto_snapshot` | json str | Toggle automatic snapshots before queue and builder edits |

**Snapshot storage**: in-memory by default. Set `COMFY_SNAPSHOT_DIR` to persist snapshots to disk (JSON per snapshot) and survive restarts. LRU eviction respects `COMFY_SNAPSHOT_LIMIT` across both memory and disk.

### Memory Tools (5)

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_save_technique` | json str | Save a workflow as a reusable technique with tags + metadata (node classes, model references) |
| `comfy_search_techniques` | json str | Search techniques by text query and/or tags |
| `comfy_list_techniques` | `TechniqueList` | Typed: techniques array with id, name, description, tags, favorite, rating, use_count |
| `comfy_replay_technique` | json str | Load a saved technique's workflow |
| `comfy_favorite_technique` | json str | Favorite and rate (0-5) a technique |

**Technique storage**: persistent JSON at `~/.comfypilot/techniques/` (one file per technique).

### Safety Tools (5)

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_check_vram` | `VRAMStatus` | Typed: status (ok/warn/critical/unknown), vram_used_pct, per-device VRAMDeviceInfo |
| `comfy_set_limits` | json str | Configure thresholds: warn % (80), block % (95), max queue (10) |
| `comfy_detect_instability` | json str | Check for near-OOM, stuck jobs, error patterns |
| `comfy_validate_before_queue` | json str | Pre-flight: VRAM headroom + queue capacity |
| `comfy_emergency_stop` | json str | Interrupt + clear queue + free all VRAM (gated by elicitation) |

### Builder Tools (5)

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_build_workflow` | json str | Family-aware: detects the checkpoint family and dispatches to the correct graph topology. Returns `{intent, family, checkpoint, node_count, workflow}`. |
| `comfy_add_node` | json str | Add a node to a workflow-in-progress |
| `comfy_connect_nodes` | json str | Wire node outputs to inputs |
| `comfy_set_widget_value` | json str | Set widget values on existing nodes |
| `comfy_apply_template` | json str | Alias for `comfy_build_workflow` |

**Family detection** handles SD 1.5, SDXL, SD 3.5, Flux 1, Flux 2, Qwen-Image, Wan 2.2, LTX-2, HunyuanVideo, Hunyuan3D, ACE-Step by filename pattern. See the README "Model Families" table for the distinctive nodes each family produces.

### Output Routing Tools (4)

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_send_to_disk` | json str | Atomically save an output image to a local path; writes `<filename>.json` sidecar manifest |
| `comfy_send_to_td` | json str | Atomic save to the TouchDesigner output path + manifest + `op().par.file` hint |
| `comfy_send_to_blender` | json str | Atomic save to the Blender output path + manifest + `bpy.data.images.load()` hint |
| `comfy_list_destinations` | json str | List configured output destinations and their paths |

**Manifest schema** (`<filename>.json` sidecar): `{schema_version, filename, subfolder, destination_path, size_bytes, timestamp, prompt_id, seeds, model_refs, dimensions}` when `prompt_id` is supplied and history is reachable. Writes are atomic via temp file + `os.replace`.

### Subgraph Blueprint Tools (3)

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_list_blueprints` | json str | List all blueprints (user-published + bundled; user shadows bundled on name collision) |
| `comfy_insert_blueprint` | json str | Materialize a blueprint into a workflow dict with optional per-node input overrides |
| `comfy_publish_subgraph` | json str | Save a set of nodes as a reusable named blueprint |

**Bundled library** ships 13 blueprints in `blueprints/`: `flux2-txt2img`, `sd35-txt2img`, `sdxl-hires-fix`, `qwen-txt2img`, `wan22-txt2video`, `ltx2-txt2video`, `hunyuan-video-txt2video`, `hunyuan3d-image2_3d`, `acestep-txt2music`, `ernie-txt2img`, `supir-upscale`, `rife-interpolate`, `sam31-segment`. User-published blueprints live at `COMFY_BLUEPRINT_DIR` (default `~/.comfypilot/blueprints`). Native ComfyUI subgraphs (v0.3.67+) surface via `comfy_list_blueprints(source="native")`.

### Viz + Ingest + Sweep (3)

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_visualize_workflow` | plain text | Render any API-format workflow as Mermaid `flowchart TD` source |
| `comfy_import_workflow_from_png` | json str | Extract embedded workflow JSON from a ComfyUI-saved PNG (stdlib-only; prefers `prompt` API chunk, falls back to `workflow` UI chunk) |
| `comfy_sweep` | json str | Queue N copies of a workflow varying one widget; returns prompt_ids + grid layout hint |

### Hub Search (1)

| Tool | Return | Description |
|------|--------|-------------|
| `comfy_search_hub` | json str | Search HuggingFace (`source="huggingface"`) or CivitAI (`source="civitai"`) for models. Returns normalized hits `{source, id, name, url, downloads, tags, ...source-specific extras}`. Limit clamped to 1-50. |

## MCP Resources (6 + 4 resource templates)

Resources provide static/semi-static data without tool-call overhead.

### Fixed resources (5)

| URI | Description |
|-----|-------------|
| `comfy://system/info` | System stats, GPU info, ComfyUI version |
| `comfy://server/capabilities` | Detected server profile, version, auth method, WebSocket availability |
| `comfy://nodes/catalog` | First 100 node class_types (preview) |
| `comfy://models/{folder}` | Models in a specific folder |
| `comfy://embeddings` | Available embeddings |

### Resource templates (3)

| URI pattern | Description |
|-----|-------------|
| `comfy://nodes/catalog/{page}` | Paginated node catalog (100 per page, `{page}` = 0, 1, 2, ...) |
| `comfy://nodes/by-category/{category}` | All nodes whose category starts with the given prefix (e.g. `sampling`, `loaders/video`) |
| `comfy://templates/catalog` | Workflow templates advertised by ComfyUI core + custom nodes (via `/workflow_templates`) |

## Structured Output Models

10 high-signal tools return typed Pydantic models so agents get schema-introspectable JSON:

| Tool | Model |
|------|-------|
| `comfy_get_system_stats` | `SystemStats` (nested `SystemInfo` + `GPUInfo` list) |
| `comfy_check_vram` | `VRAMStatus` (with per-device `VRAMDeviceInfo`) |
| `comfy_list_models` | `ModelList` (pagination-aware) |
| `comfy_list_techniques` | `TechniqueList` |
| `comfy_list_snapshots` | `SnapshotList` |
| `comfy_describe_dynamics` | `DynamicsReport` |
| `comfy_queue_prompt` | `QueueAck` |
| `comfy_validate_workflow` | `ValidationReport` |
| `comfy_get_run_result` | `RunResult` |
| `comfy_watch_progress` | `WatchProgressFrame` |

Model definitions live in `comfy_mcp/responses/models.py`.

## Elicitation (Destructive Operations)

Five tools gate destructive operations on `ctx.elicit()` when `confirm=False`:

- `comfy_clear_queue`
- `comfy_clear_history`
- `comfy_delete_history`
- `comfy_delete_snapshot`
- `comfy_emergency_stop`

Call with `confirm=True` to skip the elicitation (useful for agents with already-verified intent). If the MCP host doesn't implement elicitation, the tools allow (graceful fallback so elicitation-unaware clients aren't silently blocked).

## Safety Protocol

### Before Every Generation
1. `comfy_check_vram` - Verify GPU has headroom
2. `comfy_validate_before_queue` - Check VRAM + queue capacity
3. `comfy_validate_workflow` - 6-pass catch (schema + catalog + graph + anti_cycle + environment + execution_risk)

### Before Workflow Modifications
1. `comfy_snapshot_workflow` - Save current state
2. Make changes
3. `comfy_validate_workflow` - Verify changes are valid
4. If broken: `comfy_restore_snapshot` to roll back

### Emergency Recovery
1. `comfy_emergency_stop` - Interrupts, clears queue, frees VRAM
2. `comfy_detect_instability` - Diagnose what went wrong
3. `comfy_check_vram` - Verify recovery

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMFY_URL` | `http://127.0.0.1:8188` | ComfyUI REST API URL |
| `COMFY_API_KEY` | *(empty)* | API key for authenticated instances (Bearer for local, X-API-Key for cloud) |
| `COMFY_AUTH_METHOD` | `auto` | Auth style: `auto`, `bearer`, `x-api-key` |
| `COMFY_TIMEOUT` | `300` | HTTP timeout in seconds |
| `COMFY_SNAPSHOT_LIMIT` | `50` | Max snapshots retained |
| `COMFY_SNAPSHOT_DIR` | *(empty)* | If set, persists snapshots to disk and restores on startup |
| `COMFY_BLUEPRINT_DIR` | `~/.comfypilot/blueprints` | User-published subgraph blueprints |
| `COMFY_OUTPUT_DIR` | `~/comfypilot_output` | Default image output directory |
| `COMFY_TD_OUTPUT_DIR` | `~/comfypilot_output/touchdesigner` | TouchDesigner routing path |
| `COMFY_BLENDER_OUTPUT_DIR` | `~/comfypilot_output/blender` | Blender routing path |

### Remote ComfyUI

ComfyPilot supports remote ComfyUI instances. Set `COMFY_URL` to the remote address:

```bash
COMFY_URL=https://your-remote-host:8188 uv run comfypilot
```

For Comfy Cloud:
```bash
COMFY_URL=https://cloud.comfy.org COMFY_API_KEY=sk-xxx COMFY_AUTH_METHOD=x-api-key uv run comfypilot
```

If the remote instance requires authentication, set `COMFY_API_KEY`. ComfyPilot forwards the same auth headers to the WebSocket connection when `/ws` is reachable. The probe actively handshakes with `wss://.../ws` during startup to decide whether to enable WS; this is more accurate than the pre-1.5 profile-based heuristic.

### Local Per-Machine Override

If your Comfy instance lives on Tailscale or a custom port, copy `.mcp.local.json.example` to `.mcp.local.json` (gitignored) and edit. MCP clients that support file merging will pick it up without polluting the shared `.mcp.json`.

## File Structure

```
ComfyPilot/
+-- .claude-plugin/
|   +-- plugin.json                  # Claude Code plugin manifest
|   +-- marketplace.json             # Claude Code marketplace entry
+-- .github/workflows/
|   +-- ci.yml                       # pytest matrix (3.10/3.11/3.12) + doc-drift + release-metadata gates
+-- .mcp.json                        # MCP server config (plugin-portable)
+-- .mcp.local.json.example          # Per-machine override template (gitignored real file)
+-- blueprints/                      # Bundled subgraph blueprints (9 shipped)
|   +-- flux2-txt2img.json
|   +-- sd35-txt2img.json
|   +-- sdxl-hires-fix.json
|   +-- qwen-txt2img.json
|   +-- wan22-txt2video.json
|   +-- ltx2-txt2video.json
|   +-- hunyuan-video-txt2video.json
|   +-- hunyuan3d-image2_3d.json
|   +-- acestep-txt2music.json
+-- docs/
|   +-- MANUAL.md                    # This file
+-- mcp/
|   +-- manifest.json                # Standardized MCP manifest
|   +-- profiles/                    # Client config examples
|       +-- claude-desktop.json
|       +-- cursor.json
|       +-- generic.json
+-- server.json                      # MCP Registry manifest (io.github.dreamrec/comfypilot)
+-- skills/
|   +-- comfypilot-core/
|       +-- SKILL.md                 # Core workflow skill
+-- src/
|   +-- comfy_mcp/
|       +-- __init__.py              # __version__
|       +-- server.py                # FastMCP server + lifespan + resources + CLI transport flag
|       +-- comfy_client.py          # Async HTTP + WS client + capability probe + auth
|       +-- tool_registry.py         # Central tool import aggregator
|       +-- errors.py                # Typed ComfyAPIError / ComfyConnectionError / ComfyTimeoutError
|       +-- events/event_manager.py
|       +-- jobs/job_tracker.py
|       +-- memory/
|       |   +-- snapshot_manager.py
|       |   +-- technique_store.py
|       +-- safety/
|       |   +-- vram_guard.py
|       |   +-- confirm.py           # Elicitation gate helper
|       +-- schemas/node_schema.py   # V1 + V3 NodeSchema normalizer
|       +-- families/
|       |   +-- detector.py
|       |   +-- registry.py
|       |   +-- builders/
|       |       +-- sd15.py          # SD 1.5 (txt2img, img2img, upscale, inpaint, controlnet)
|       |       +-- sdxl.py
|       |       +-- sd35.py
|       |       +-- flux2.py
|       |       +-- qwen.py
|       |       +-- wan22.py         # txt2video + img2video
|       |       +-- ltx2.py
|       |       +-- hunyuan_video.py # txt2video + img2video
|       |       +-- hunyuan_3d.py    # image2_3d
|       |       +-- ace_step.py      # txt2music
|       +-- blueprints/store.py
|       +-- responses/models.py      # Pydantic models for 10 tools
|       +-- viz/mermaid.py
|       +-- ingest/png_metadata.py
|       +-- hub/
|       |   +-- huggingface.py
|       |   +-- civitai.py
|       +-- tools/                   # 88 tools across 19 modules
|       +-- cli/                     # comfy-cli subprocess wrappers (v1.8.0)
|           +-- system.py             # 6
|           +-- models.py             # 5
|           +-- workflow.py           # 8
|           +-- nodes.py              # 6
|           +-- images.py             # 5
|           +-- history.py            # 5
|           +-- monitoring.py         # 6
|           +-- snapshots.py          # 6
|           +-- memory.py             # 5
|           +-- safety.py             # 5
|           +-- builder.py            # 5 (family-aware dispatch)
|           +-- output_routing.py     # 4
|           +-- blueprints.py         # 3
|           +-- viz.py                # 1
|           +-- ingest.py             # 1
|           +-- sweep.py              # 1
|           +-- hub.py                # 1
+-- tests/                            # pytest suite (516 tests)
+-- scripts/gen_tool_docs.py          # Tool-registry introspection for doc generation
+-- pyproject.toml
+-- CHANGELOG.md
+-- LICENSE
+-- README.md
```

## Testing

```bash
uv sync --extra dev
uv run pytest -q                          # full suite (~516 tests, <5s)
uv run pytest tests/test_<area>.py -v      # one category
uv run pytest tests/test_doc_drift.py tests/test_release_metadata.py -v   # gates
```

CI runs the full suite on Python 3.10, 3.11, and 3.12 on every push and PR.

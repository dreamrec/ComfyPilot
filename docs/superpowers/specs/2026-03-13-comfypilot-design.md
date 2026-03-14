# ComfyPilot Design Spec

**Date:** 2026-03-13
**Status:** Draft
**Author:** Claude + Silviu

---

## 1. Overview

ComfyPilot is a production-grade MCP server for live AI control of ComfyUI. It provides 71 tools across 12 categories, connecting to any ComfyUI instance via REST API and WebSocket.

**Target:** ComfyUI v0.17.0+ (remote instance at `https://desktop-3lurf0p.tail88651a.ts.net/`, RTX 5090, 34GB VRAM)

**Key differentiators vs existing ComfyUI MCP servers:**
- Typed output schemas on every tool (not raw strings)
- Image content blocks returned in tool results (LLM sees what was generated)
- Workflow snapshots with diff/restore (undo system)
- Live WebSocket progress reporting via `ctx.report_progress()`
- VRAM monitoring and safety guards
- Structured error responses with actionable suggestions
- Cross-app output routing (send results to TouchDesigner/Blender)
- Plugin bundle packaging (`.plugin` ZIP with client profiles)
- MCP Resources for static data (node catalog, model lists)
- Elicitation for ambiguous operations (`ctx.elicit()`)

**Architecture lineage:** Based on TDPilot v1.1's proven patterns, upgraded with Anthropic MCP SDK features that postdate TDPilot's design.

---

## 2. Project Structure

```
~/Desktop/ComfyPilot/
├── pyproject.toml
├── .mcp.json
├── README.md
├── src/
│   └── comfy_mcp/
│       ├── __init__.py
│       ├── server.py              # FastMCP init + lifespan + CLI
│       ├── comfy_client.py        # Async HTTP + WebSocket client
│       ├── tool_registry.py       # Import aggregator: imports all tools/ modules so @mcp.tool decorators execute at startup. Also wires auto-snapshot hooks.
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── system.py          # 6 tools: stats, GPU, features, extensions, restart, free VRAM
│       │   ├── models.py          # 5 tools: list, info, folder listing, search, refresh
│       │   ├── workflow.py        # 8 tools: queue, get queue, cancel, interrupt, clear, validate, export, import
│       │   ├── nodes.py           # 6 tools: list types, get info, search, get categories, get embeddings, inspect widget
│       │   ├── images.py          # 5 tools: upload, get output, list outputs, get temp, download batch
│       │   ├── history.py         # 5 tools: get history, get run result, delete entry, clear, search
│       │   ├── snapshots.py       # 6 tools: snapshot workflow, list, diff, restore, delete, auto-snapshot
│       │   ├── memory.py          # 5 tools: save technique, recall, list, replay, favorite
│       │   ├── monitoring.py      # 6 tools: watch progress, subscribe, unsubscribe, get events, describe dynamics, stream status
│       │   ├── safety.py          # 5 tools: check VRAM, set limits, detect instability, emergency stop, validate before queue
│       │   ├── builder.py         # 5 tools: build workflow, add node, connect, set widget, apply template
│       │   └── output_routing.py  # 4 tools: send to TD, send to Blender, send to disk, list destinations
│       ├── events/
│       │   ├── __init__.py
│       │   └── event_manager.py   # WebSocket subscription + dispatch + auto-reconnect
│       ├── memory/
│       │   ├── __init__.py
│       │   ├── snapshot_manager.py # LRU-bounded workflow snapshots
│       │   └── technique_store.py  # Reusable workflow recipes
│       ├── safety/
│       │   ├── __init__.py
│       │   └── vram_guard.py      # VRAM monitoring + queue limits
│       └── jobs/
│           ├── __init__.py
│           └── job_tracker.py     # Async execution tracking with progress
├── mcp/
│   ├── manifest.json
│   └── profiles/
│       ├── claude-desktop.json
│       ├── cursor.json
│       └── generic.json
├── skills/
│   └── comfypilot-core/
│       ├── SKILL.md
│       └── references/
├── tests/
│   └── ...
└── comfypilot.plugin             # Built artifact (ZIP)
```

---

## 3. Dependencies

```toml
[project]
name = "comfypilot"
version = "1.0.0"
requires-python = ">=3.10"

dependencies = [
    "mcp>=1.0",
    "httpx>=0.27",
    "pydantic>=2.0",
    "websockets>=12.0",
]

[project.scripts]
comfypilot = "comfy_mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/comfy_mcp"]
```

---

## 4. ComfyClient Layer

### 4.1 Class Design

```python
class ComfyClient:
    """Async HTTP + WebSocket client for ComfyUI API."""

    def __init__(self, base_url: str, api_key: str = "", ws_reconnect_max: int = 5):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.ws_reconnect_max = ws_reconnect_max
        self._http: httpx.AsyncClient | None = None
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._client_id: str = str(uuid.uuid4())
```

### 4.2 Key Methods

- `connect()` / `close()` — lifecycle management
- `get(path)` / `post(path, data)` — HTTP with auth headers, retries, error mapping
- `queue_prompt(workflow, front=False)` — POST /prompt
- `get_queue()` — GET /queue
- `get_history(prompt_id)` — GET /history/{prompt_id}
- `get_system_stats()` — GET /system_stats
- `get_object_info(node_type=None)` — GET /object_info or /object_info/{type}
- `get_models(folder)` — GET /models/{folder}
- `get_features()` — GET /api/features (v0.17+)
- `get_extensions()` — GET /api/extensions
- `upload_image(file, subfolder, overwrite)` — POST /upload/image
- `get_image(filename, subfolder, type)` — GET /view?filename=...
- `cancel_prompt(prompt_id)` — POST /queue with `{"delete": [prompt_id]}`
- `interrupt()` — POST /interrupt
- `free_vram(unload_models, free_memory)` — POST /free
- `watch_execution(prompt_id)` — async generator over WebSocket events
- `ws_connect()` — WebSocket with exponential backoff auto-reconnect

### 4.3 Error Hierarchy

```python
class ComfyError(Exception):
    """Base error with structured fields for actionable error reporting."""

    def __init__(
        self,
        error_code: str,
        message: str,
        suggestion: str = "",
        retry_possible: bool = False,
        details: dict | None = None,
    ):
        self.error_code = error_code
        self.message = message
        self.suggestion = suggestion
        self.retry_possible = retry_possible
        self.details = details
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "suggestion": self.suggestion,
            "retry_possible": self.retry_possible,
            "details": self.details,
        }

class ComfyConnectionError(ComfyError): ...   # Cannot reach ComfyUI
class ComfyAPIError(ComfyError): ...           # HTTP 4xx/5xx
class ComfyTimeoutError(ComfyError): ...       # Execution timeout
class ComfyVRAMError(ComfyError): ...          # Out of VRAM
```

### 4.4 Environment Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `COMFY_URL` | `http://127.0.0.1:8188` | ComfyUI base URL |
| `COMFY_API_KEY` | `""` | API key (if auth enabled) |
| `COMFY_WS_RECONNECT_MAX` | `5` | Max WebSocket reconnect attempts |
| `COMFY_SNAPSHOT_LIMIT` | `50` | Max snapshots before LRU eviction |
| `COMFY_TIMEOUT` | `300` | Default execution timeout (seconds) |
| `COMFY_OUTPUT_DIR` | `""` | Default disk output directory for saved images |
| `COMFY_TD_OUTPUT_DIR` | `""` | TouchDesigner output directory (enables TD routing) |
| `COMFY_BLENDER_OUTPUT_DIR` | `""` | Blender output directory (enables Blender routing) |

---

## 5. Tool Registry (71 Tools)

### 5.1 System (6 tools)

| Tool | Annotation | Description |
|------|-----------|-------------|
| `comfy_get_system_stats` | readOnly | System stats: OS, GPU, VRAM, ComfyUI version |
| `comfy_get_gpu_info` | readOnly | Detailed GPU info: VRAM total/free/used, torch version |
| `comfy_get_features` | readOnly | List enabled ComfyUI features |
| `comfy_list_extensions` | readOnly | List installed custom nodes/extensions |
| `comfy_restart` | destructive | Restart ComfyUI server |
| `comfy_free_vram` | not readOnly | Unload models and/or free memory |

### 5.2 Models (5 tools)

| Tool | Annotation | Description |
|------|-----------|-------------|
| `comfy_list_models` | readOnly | List models in a folder (checkpoints, loras, etc.) with pagination |
| `comfy_get_model_info` | readOnly | Detailed info about a specific model file |
| `comfy_list_model_folders` | readOnly | List all 70+ model folder types |
| `comfy_search_models` | readOnly | Fuzzy search across all model folders |
| `comfy_refresh_models` | not readOnly | Trigger model list refresh |

### 5.3 Workflow Execution (8 tools)

| Tool | Annotation | Description |
|------|-----------|-------------|
| `comfy_queue_prompt` | not readOnly | Queue a workflow for execution (with progress tracking) |
| `comfy_get_queue` | readOnly | Get current queue state (running + pending) |
| `comfy_cancel_run` | destructive | Cancel a specific queued/running prompt |
| `comfy_interrupt` | destructive | Interrupt current execution |
| `comfy_clear_queue` | destructive | Clear all pending prompts |
| `comfy_validate_workflow` | readOnly | Validate workflow JSON without executing |
| `comfy_export_workflow` | readOnly | Export workflow as API-format JSON |
| `comfy_import_workflow` | not readOnly | Import workflow from JSON/PNG metadata |

### 5.4 Nodes (6 tools)

| Tool | Annotation | Description |
|------|-----------|-------------|
| `comfy_list_node_types` | readOnly | List all available node types with pagination |
| `comfy_get_node_info` | readOnly | Detailed info for a node type (inputs, outputs, widgets) |
| `comfy_search_nodes` | readOnly | Search nodes by name, category, or description |
| `comfy_get_categories` | readOnly | List all node categories |
| `comfy_get_embeddings` | readOnly | List available embeddings |
| `comfy_inspect_widget` | readOnly | Get widget options/constraints for a node input |

### 5.5 Images & Assets (5 tools)

| Tool | Annotation | Description |
|------|-----------|-------------|
| `comfy_upload_image` | not readOnly | Upload image to ComfyUI input folder |
| `comfy_get_output_image` | readOnly | Get generated image (returns image content block) |
| `comfy_list_outputs` | readOnly | List output images with pagination |
| `comfy_get_temp_image` | readOnly | Get temporary/preview image |
| `comfy_download_batch` | readOnly | Get metadata for multiple output images. Returns list of `{filename, size_bytes, url}` objects (max 20 per call). Does NOT return image bytes — use `comfy_get_output_image` for individual images. Avoids multi-MB base64 payloads. |

### 5.6 History (5 tools)

| Tool | Annotation | Description |
|------|-----------|-------------|
| `comfy_get_history` | readOnly | Get execution history with pagination |
| `comfy_get_run_result` | readOnly | Get full result of a specific run (outputs, timing, errors) |
| `comfy_delete_history` | destructive | Delete a specific history entry |
| `comfy_clear_history` | destructive | Clear all history |
| `comfy_search_history` | readOnly | Search history by node types, status, date range |

### 5.7 Snapshots (6 tools)

| Tool | Annotation | Description |
|------|-----------|-------------|
| `comfy_snapshot_workflow` | not readOnly | Save current workflow state as named snapshot |
| `comfy_list_snapshots` | readOnly | List all snapshots with metadata |
| `comfy_diff_snapshots` | readOnly | Diff two snapshots or snapshot vs current |
| `comfy_restore_snapshot` | not readOnly | Restore workflow from a snapshot |
| `comfy_delete_snapshot` | destructive | Delete a snapshot |
| `comfy_auto_snapshot` | not readOnly | Enable/disable auto-snapshot before modifications |

### 5.8 Memory (5 tools)

| Tool | Annotation | Description |
|------|-----------|-------------|
| `comfy_save_technique` | not readOnly | Save workflow as reusable technique recipe |
| `comfy_recall_technique` | readOnly | Search technique library by query/tags |
| `comfy_list_techniques` | readOnly | List all saved techniques |
| `comfy_replay_technique` | not readOnly | Rebuild a saved technique as a new workflow |
| `comfy_favorite_technique` | not readOnly | Mark/rate a technique |

### 5.9 Monitoring (6 tools)

| Tool | Annotation | Description |
|------|-----------|-------------|
| `comfy_watch_progress` | readOnly | Poll execution progress for a prompt_id. Returns current step/total, node being executed, and completion status. Not streaming — call repeatedly to poll. |
| `comfy_subscribe` | not readOnly | Register interest in event types. Events are buffered internally and retrieved via `comfy_get_events`. |
| `comfy_unsubscribe` | not readOnly | Remove event subscription |
| `comfy_get_events` | readOnly | Get buffered events since last call (drains the buffer). Returns list of recent events with timestamps. |
| `comfy_describe_dynamics` | readOnly | Collect execution metrics over a time window (default 3s), then return a summary snapshot. Blocks for the observation window, then returns. |
| `comfy_get_status` | readOnly | One-shot snapshot of queue state + current execution status. Renamed from `comfy_stream_status` — this is a poll, not a stream. |

### 5.10 Safety (5 tools)

| Tool | Annotation | Description |
|------|-----------|-------------|
| `comfy_check_vram` | readOnly | Check VRAM usage and availability |
| `comfy_set_limits` | not readOnly | Set queue/VRAM/timeout safety limits |
| `comfy_detect_instability` | readOnly | Check for error loops or resource exhaustion |
| `comfy_emergency_stop` | destructive | Interrupt + clear queue + free VRAM |
| `comfy_validate_before_queue` | readOnly | Pre-flight check: VRAM, models loaded, workflow valid |

### 5.11 Workflow Builder (5 tools)

| Tool | Annotation | Description |
|------|-----------|-------------|
| `comfy_build_workflow` | not readOnly | Create workflow from a structured template spec (not NLP). Input: `BuildWorkflowInput(template: str, params: dict)` where `template` is one of the predefined types ("txt2img", "img2img", "upscale", "inpaint", "controlnet") and `params` overrides specific widget values. Output: API-format workflow dict ready for `comfy_queue_prompt`. |
| `comfy_add_node` | not readOnly | Add a node to an in-progress workflow |
| `comfy_connect_nodes` | not readOnly | Connect two nodes in a workflow |
| `comfy_set_widget_value` | not readOnly | Set a widget/input value on a node |
| `comfy_apply_template` | not readOnly | Apply a workflow template (txt2img, img2img, etc.) |

### 5.12 Output Routing (4 tools)

| Tool | Annotation | Description |
|------|-----------|-------------|
| `comfy_send_to_td` | not readOnly | Send output image/data to TouchDesigner via TDPilot |
| `comfy_send_to_blender` | not readOnly | Send output to Blender via Blender MCP |
| `comfy_send_to_disk` | not readOnly | Save output to specific local path |
| `comfy_list_destinations` | readOnly | List available output routing destinations |

---

## 6. MCP Resources

Static/infrequently-changing data exposed as MCP Resources (not tools):

| Resource URI | Description |
|-------------|-------------|
| `comfy://system/info` | System stats, GPU info, ComfyUI version |
| `comfy://nodes/catalog` | Full node type catalog (cached, refreshed on start) |
| `comfy://models/{folder}` | Model list for a folder (resource template) |
| `comfy://embeddings` | Available embeddings list |

---

## 7. Subsystem Architecture

### 7.1 EventManager (`events/event_manager.py`)

- Manages WebSocket connection to ComfyUI `/ws`
- Auto-reconnect with exponential backoff (1s, 2s, 4s, 8s, 16s)
- Dispatches events to subscribers by type
- Event types: `status`, `execution_start`, `execution_cached`, `executing`, `progress`, `executed`
- Rate limiting per subscriber (configurable, default 60ms)

### 7.2 SnapshotManager (`memory/snapshot_manager.py`)

- Stores workflow snapshots as named, timestamped entries
- LRU eviction when exceeding `COMFY_SNAPSHOT_LIMIT` (default 50)
- Diff engine: compares two snapshots or snapshot vs live workflow
- Restore: replaces current workflow with snapshot state
- Auto-snapshot: in-memory flag (default: off, not persisted across restarts). When enabled, automatically creates a snapshot before any tool in the builder category (`comfy_build_workflow`, `comfy_add_node`, `comfy_connect_nodes`, `comfy_set_widget_value`, `comfy_apply_template`) and before `comfy_queue_prompt`. Triggered by the tool_registry wrapper, not by individual tools.

### 7.3 TechniqueStore (`memory/technique_store.py`)

- Saves workflows as reusable recipes with tags and metadata
- Search by text query or tags
- Replay: instantiate a technique as a new workflow
- Storage: JSON files in `~/.comfypilot/techniques/`
- Scopes: global only (stored in `~/.comfypilot/techniques/`). Unlike TDPilot which has per-project techniques tied to TouchDesigner project files, ComfyUI workflows are standalone — a single global library is simpler and sufficient for v1.0. Project-scoping can be added later if users request it.

### 7.4 VRAMGuard (`safety/vram_guard.py`)

- Polls `system_stats` for VRAM usage
- Configurable thresholds (warn at 80%, block at 95%)
- Pre-flight validation before queueing: checks current VRAM headroom against thresholds. Does NOT estimate per-workflow VRAM cost (ComfyUI has no such API). Simply verifies enough free VRAM exists above the configured floor before allowing queue submission.
- Emergency stop: interrupt + free + notify

### 7.5 JobTracker (`jobs/job_tracker.py`)

- Tracks prompt submissions → execution → completion
- Async wait with timeout for execution results
- Progress aggregation from WebSocket events
- Stores recent job history for quick lookup

---

## 8. Key Implementation Patterns

### 8.1 Lifespan Management

```python
@asynccontextmanager
async def comfy_lifespan(server: FastMCP):
    url = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
    api_key = os.environ.get("COMFY_API_KEY", "")

    client = ComfyClient(url, api_key=api_key)
    await client.connect()

    event_mgr = EventManager(client)
    snapshot_mgr = SnapshotManager(limit=int(os.environ.get("COMFY_SNAPSHOT_LIMIT", "50")))
    technique_store = TechniqueStore()
    vram_guard = VRAMGuard(client)
    job_tracker = JobTracker(client, event_mgr)

    try:
        yield {
            "comfy_client": client,
            "event_manager": event_mgr,
            "snapshot_manager": snapshot_mgr,
            "technique_store": technique_store,
            "vram_guard": vram_guard,
            "job_tracker": job_tracker,
        }
    finally:
        await event_mgr.shutdown()
        await client.close()

mcp = FastMCP("comfypilot", lifespan=comfy_lifespan)
```

### 8.2 Tool Pattern (every tool follows this)

```python
class QueuePromptInput(BaseModel):
    model_config = ConfigDict(strict=True)
    workflow: dict = Field(..., description="ComfyUI workflow in API format")
    front: bool = Field(False, description="Queue at front (priority)")

class QueuePromptOutput(BaseModel):
    prompt_id: str
    queue_position: int
    estimated_seconds: float | None = None

@mcp.tool(
    annotations={
        "title": "Queue Prompt",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def comfy_queue_prompt(params: QueuePromptInput, ctx: Context) -> QueuePromptOutput:
    client = ctx.request_context.lifespan_context["comfy_client"]
    await ctx.report_progress(0, 100, "Submitting workflow...")
    # ... implementation
```

### 8.3 Image Return Pattern

```python
async def comfy_get_output_image(params: GetOutputInput, ctx: Context) -> list:
    client = ctx.request_context.lifespan_context["comfy_client"]
    image_bytes = await client.get_image(params.filename, params.subfolder)
    return [
        TextContent(text=json.dumps({
            "filename": params.filename,
            "size_bytes": len(image_bytes),
            "format": "png"
        })),
        ImageContent(
            data=base64.b64encode(image_bytes).decode(),
            mimeType="image/png"
        )
    ]
```

### 8.4 Structured Error Pattern

```python
class ComfyErrorResponse(BaseModel):
    error_code: str
    message: str
    suggestion: str
    retry_possible: bool
    details: dict | None = None
```

All tools catch exceptions and return structured errors instead of raw tracebacks.

### 8.5 Elicitation Pattern

```python
if len(matches) > 1:
    result = await ctx.elicit(
        message=f"Found {len(matches)} matches for '{query}'",
        schema={"type": "object", "properties": {
            "choice": {"type": "string", "enum": [m.name for m in matches]}
        }}
    )
    chosen = result.data["choice"]
```

---

## 9. Plugin Packaging

### 9.1 Manifest (`mcp/manifest.json`)

```json
{
  "schema_version": "1.0.0",
  "name": "comfypilot",
  "display_name": "ComfyPilot",
  "version": "1.0.0",
  "entrypoints": {
    "npm": { "command": "npx", "args": ["comfypilot"] },
    "python": { "command": "uv", "args": ["run", "comfypilot"] }
  },
  "defaults": {
    "env": {
      "COMFY_URL": "http://127.0.0.1:8188",
      "COMFY_API_KEY": ""
    },
    "transport": "stdio"
  },
  "surface": {
    "tool_count": 71,
    "resource_template_count": 1
  },
  "artifacts": ["skills/comfypilot-core"]
}
```

### 9.2 Client Profiles

Each profile in `mcp/profiles/` adapts the MCP config for a specific client:

- **claude-desktop.json**: stdio transport, env vars for URL/key
- **cursor.json**: stdio transport, adapted args
- **generic.json**: minimal config for any MCP client

### 9.3 Plugin Bundle

`comfypilot.plugin` is a ZIP archive containing:
- `plugin.json` (metadata)
- `.mcp.json` (default config)
- `mcp/manifest.json` + `mcp/profiles/`
- `skills/comfypilot-core/`
- `README.md`

---

## 10. Improvements Over TDPilot v1.1

| Pattern | TDPilot v1.1 | ComfyPilot v1.0 |
|---------|-------------|-----------------|
| Tool return types | Raw `str` (untyped) | Pydantic output models with `outputSchema` |
| Image handling | Base64 via dedicated screenshot tool | Image content blocks in tool results |
| Ambiguity resolution | Fail or guess | `ctx.elicit()` for multi-match scenarios |
| Error format | Plain text strings | Structured: `error_code` + `suggestion` + `retry_possible` |
| WebSocket resilience | Single connect, manual reconnect | Exponential backoff auto-reconnect |
| Logging | Mix of print() and basic logging | Consistent `ctx.log_info/warning/error()` |
| Snapshot storage | Unbounded in-memory | LRU eviction (default 50) |
| Static data access | Tools for everything | MCP Resources for node catalog, model lists |

These patterns should backport to TDPilot v1.2.

---

## 11. Cross-App Output Routing

Output routing connects ComfyPilot to other creative tools.

**Mechanism:** Output routing does NOT call other MCP servers directly (MCP servers cannot invoke each other). Instead, routing tools:

1. **Disk routing** (`comfy_send_to_disk`): Downloads the image from ComfyUI and saves it to a configured local path. This is the foundation — other apps watch these paths or the agent orchestrates the next step.
2. **TD routing** (`comfy_send_to_td`): Saves image to disk, then returns a response indicating the file path and a suggested `td_exec_python` command the agent should execute next via TDPilot. The *agent* (Claude) orchestrates the cross-app call, not ComfyPilot.
3. **Blender routing** (`comfy_send_to_blender`): Same pattern — saves to disk, returns suggested `execute_blender_code` command for the agent to run via Blender MCP.
4. **Destination discovery** (`comfy_list_destinations`): Checks env vars (`COMFY_TD_OUTPUT_DIR`, `COMFY_BLENDER_OUTPUT_DIR`, `COMFY_OUTPUT_DIR`) and reports which destinations are configured.

This is agent-orchestrated routing, not server-to-server RPC. The LLM agent coordinates the pipeline across MCP servers.

---

## 12. Testing Strategy

- **Framework:** pytest + pytest-asyncio
- **Unit tests** for ComfyClient: mock `httpx.AsyncClient` responses using `httpx.MockTransport`. Mock WebSocket via `unittest.mock.AsyncMock`.
- **Unit tests** for each tool module: fixture provides a mock `ComfyClient` injected via lifespan context dict. Each tool module gets its own test file (`tests/test_system.py`, etc.).
- **Integration tests** against live ComfyUI: gated by `COMFY_TEST_URL` env var. Skipped when not set. Only runs read-only tools by default.
- **Snapshot/memory tests**: use `tmp_path` pytest fixture for isolated file storage.
- **WebSocket reconnection tests**: simulate disconnects via mock, verify exponential backoff timing and max retry behavior.
- **CI**: GitHub Actions with unit tests only (no live ComfyUI). Integration tests run manually.

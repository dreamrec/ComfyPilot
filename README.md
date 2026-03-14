# ComfyPilot

AI-native MCP server for live ComfyUI control. 66 tools across 12 categories with workflow snapshots, live WebSocket progress, visual output (image content blocks), VRAM safety, and cross-app output routing.

## Quickstart

```bash
# Install
uv pip install -e .

# Run (stdio transport)
uv run comfypilot

# Or configure in Claude Desktop (claude_desktop_config.json)
```

See `mcp/profiles/` for client configuration examples.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMFY_URL` | `http://127.0.0.1:8188` | ComfyUI server URL |
| `COMFY_API_KEY` | *(empty)* | Optional API key |
| `COMFY_TIMEOUT` | `300` | HTTP timeout (seconds) |
| `COMFY_SNAPSHOT_LIMIT` | `50` | Max workflow snapshots |
| `COMFY_OUTPUT_DIR` | `~/comfypilot_output` | Image output directory |
| `COMFY_TD_OUTPUT_DIR` | `~/comfypilot_output/touchdesigner` | TouchDesigner output |
| `COMFY_BLENDER_OUTPUT_DIR` | `~/comfypilot_output/blender` | Blender output |

## Tool Categories

| Category | Tools | Description |
|----------|-------|-------------|
| System | 6 | Stats, GPU info, features, extensions, restart, free VRAM |
| Models | 5 | List, info, folders, search, refresh |
| Workflow | 8 | Queue, cancel, interrupt, validate, export, import |
| Nodes | 6 | List types, get info, search, categories, embeddings, inspect widget |
| Images | 5 | Get output image, upload, list, batch download, URL |
| History | 5 | Get history, run result, delete, clear, search |
| Monitoring | 6 | Watch progress, subscribe, unsubscribe, events, dynamics, status |
| Snapshots | 6 | Snapshot, list, diff, restore, delete, auto-snapshot |
| Memory | 5 | Save technique, search, list, replay, favorite |
| Safety | 5 | Check VRAM, set limits, detect instability, validate before queue, emergency stop |
| Builder | 5 | Build workflow, add node, connect, set widget, template |
| Output Routing | 4 | Send to disk, TouchDesigner, Blender, list destinations |

**Total: 66 tools**

## MCP Resources

- `comfy://system/info` — System stats and GPU info
- `comfy://nodes/catalog` — Node type catalog
- `comfy://models/{folder}` — Model listing by folder
- `comfy://embeddings` — Available embeddings

## Development

```bash
# Run tests
uv run pytest -v

# Run specific test file
uv run pytest tests/test_workflow.py -v
```

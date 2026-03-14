# Model Awareness Rollout Plan

Date: 2026-03-14

## Objective

Ship a smarter ComfyPilot that understands the current ComfyUI ecosystem without destabilizing the server.

This rollout is intentionally phased.

The goal is to improve:

- model awareness
- workflow recommendation quality
- speed
- docs truthfulness
- provider awareness

without turning one release into a giant rewrite.

## Phase 0: Foundation Audit Lock-In

Goal:

- freeze the target architecture before coding

Deliverables:

- `docs/extra/2026-03-14-model-awareness-spec.md`
- this rollout plan

Exit criteria:

- agreed list of Tier 1 model families
- agreed provider scope
- agreed file layout for registry data

## Phase 1: Expand Model Surface Awareness

Goal:

- make ComfyPilot aware of the real model folders and modern asset layouts

Files:

- `src/comfy_mcp/tools/models.py`
- `src/comfy_mcp/comfy_client.py`
- `src/comfy_mcp/server.py`

Changes:

- expand supported model folders
- add better folder listing and folder metadata
- add a normalized internal representation for model inventory
- expose a new environment summary resource

Must include:

- `diffusion_models`
- `text_encoders`
- `model_patches`
- `latent_upscale_models`
- `clip_vision`

Expected user win:

- model tools stop hiding the real install surface

## Phase 2: Introduce Ecosystem Registry

Goal:

- create a structured data layer that knows what major model families need and can do

Files:

- `src/comfy_mcp/ecosystem/*`
- `src/comfy_mcp/data/ecosystem/*`

Changes:

- add registry loader
- add aliases
- add provider catalog
- add freshness metadata
- add a first-pass static dataset for Tier 1 families

Tier 1 target list:

- `sd15`
- `sdxl`
- `flux1`
- `flux2`
- `qwen-image`
- `z-image`
- `hidream`
- `ltx23`
- `wan22`
- `hunyuanvideo15`
- provider families: `google`, `openai`, `black-forest-labs`, `runway`, `kling`, `minimax`, `luma`

Expected user win:

- ComfyPilot gains durable knowledge instead of ad-hoc string matching

## Phase 3: Add Environment Scanner

Goal:

- infer what this specific ComfyUI install can actually do

Files:

- `src/comfy_mcp/ecosystem/scanner.py`
- `src/comfy_mcp/server.py`
- `src/comfy_mcp/templates/*`

Changes:

- detect installed families from model files
- detect partner providers from available nodes and auth
- detect missing required assets
- detect whether native templates exist for a family
- detect community ecosystems from filenames and aliases

Expected user win:

- better answers to "what works here right now?"

## Phase 4: Add Planner and Recommendations

Goal:

- recommend workflows instead of only listing files and nodes

Files:

- `src/comfy_mcp/planner/*`
- `src/comfy_mcp/tools/builder.py`
- `src/comfy_mcp/server.py`

Changes:

- add a ranking engine
- add workflow recommendation tools
- add "why this recommendation" explanations
- move builder from static legacy templates to strategy-driven templates

First supported user intents:

- text-to-image
- image editing
- inpainting
- control-guided image generation
- text-to-video
- image-to-video
- upscale

Expected user win:

- better first suggestion quality
- less wasted time on wrong-family workflows

## Phase 5: Modernize Builder

Goal:

- make workflow generation family-aware

Files:

- `src/comfy_mcp/tools/builder.py`
- `tests/test_builder.py`

Changes:

- keep legacy templates for backwards compatibility
- add native family templates for modern families
- add provider strategy templates
- select defaults based on environment and task

Minimum modern templates:

- `native-sdxl-t2i`
- `native-flux2-t2i`
- `native-qwen-image-t2i`
- `native-qwen-image-edit`
- `native-z-image-control`
- `native-hidream-t2i`
- `native-ltx23-i2v`
- `native-ltx23-t2v`
- `native-wan22-t2v`
- `native-wan22-i2v`
- `native-hunyuanvideo15-t2v`

Expected user win:

- generated workflows feel current instead of archival

## Phase 6: Freshness and Maintenance

Goal:

- keep the registry from rotting

Files:

- `src/comfy_mcp/ecosystem/freshness.py`
- `scripts/refresh_ecosystem_index.py`
- `docs/MANUAL.md`

Changes:

- add explicit refresh command
- store `last_verified_at`
- validate source URLs
- optionally add CI to flag stale data

Expected user win:

- the MCP can stay relevant across fast-moving ComfyUI releases

## Performance Rules

These should remain true throughout all phases:

- no web fetches during normal tool execution
- startup should load cached registry data from disk
- environment scans should be cached and invalidated on demand
- large provider catalogs should be summarized by default
- planner outputs should be ranked and concise

## Testing Plan

Add or expand tests for:

- model folder detection
- asset requirement matching
- alias normalization
- ecosystem tagging
- provider detection
- planner ranking
- builder strategy selection
- cache invalidation

Golden fixtures should model:

- legacy SD install
- modern FLUX/Qwen image install
- video-heavy LTX/Wan/Hunyuan install
- mixed local plus partner-node install

## Recommended Release Slicing

If you want the safest path, ship it in three releases:

### Release A

- Phase 1
- Phase 2
- Phase 3

User-facing message:

- "ComfyPilot now understands more model families and detects your environment better."

### Release B

- Phase 4
- limited Phase 5

User-facing message:

- "ComfyPilot now recommends workflows based on installed models and task intent."

### Release C

- remaining Phase 5
- Phase 6

User-facing message:

- "ComfyPilot now stays fresh and generates modern family-aware starter workflows."

## Honest Priorities

If time is limited, do these first:

1. Expand model folder awareness
2. Add a real ecosystem registry
3. Build environment detection
4. Add recommendations

If time is extremely limited, do not start with:

- popularity scoring
- social trend scraping
- benchmark leaderboards

Those are useful later, but the core win comes from better capability modeling.

## Success Metrics

The rollout is working if:

- workflow recommendations mention current families like Qwen, Z-Image, HiDream, LTX, Wan, and Hunyuan when appropriate
- builder defaults stop picking legacy SD1.5-style templates on modern installs
- the MCP can explain missing assets for a family in plain language
- local-first recommendations beat provider recommendations when the local install is sufficient
- docs and resources expose the new knowledge cleanly

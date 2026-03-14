# Model Awareness Spec

Date: 2026-03-14

## Why This Needs to Change

ComfyPilot currently thinks about model support too narrowly.

Today the workflow builder is still centered on small legacy templates built around `CheckpointLoaderSimple`, classic `CLIPTextEncode`, and SD1.5-style defaults in `src/comfy_mcp/tools/builder.py`. The model tools in `src/comfy_mcp/tools/models.py` also expose only a partial view of the modern ComfyUI model surface.

That is no longer enough for the actual ComfyUI ecosystem in March 2026.

Official ComfyUI docs now treat many more model families and provider-backed workflows as first-class:

- native workflow templates for modern image and video families
- native model storage across `diffusion_models`, `text_encoders`, `vae`, `model_patches`, and `latent_upscale_models`
- partner/API nodes for many commercial providers
- frequent changelog updates that add new models, patches, variants, and pricing/provider changes

The current problem is not just missing a few names like `LTX-2.3`.

The real issue is that ComfyPilot lacks a structured ecosystem knowledge layer.

## Product Goal

Make ComfyPilot able to answer questions like:

- "What is the best available workflow on this machine for cinematic image generation?"
- "Do I have the right files installed for Qwen-Image or HiDream?"
- "Should I use local FLUX, local Qwen, or a provider node for this task?"
- "What are the fastest current options for text-to-video on this setup?"
- "Which workflow template fits this intent and this installed environment?"

The system should become:

- smarter: understands modern model families, providers, and workflow types
- faster: uses cached structured knowledge instead of repeated ad-hoc probing
- more accurate: chooses workflows by capability, not filename guesswork alone
- more up to date: can ingest ecosystem changes without rewriting core logic

## Design Principles

### 1. Separate architecture from popularity

`Pony`, `Illustrious`, `Juggernaut`, and `RealVis` matter in practice, but they should be modeled as ecosystems or fine-tune lineages, not as core runtime architectures.

Core architecture examples:

- `sd15`
- `sdxl`
- `sd35`
- `flux1`
- `flux2`
- `qwen-image`
- `z-image`
- `hidream`
- `wan22`
- `hunyuanvideo15`
- `ltx23`

Community ecosystem examples:

- `pony`
- `illustrious`
- `juggernaut-xl`
- `realvis-xl`

### 2. Prefer capabilities over names

The important question is not only "what model is this?"

The better question is:

- what can it do
- what assets does it require
- which loaders/nodes does it need
- how expensive is it
- is it local, partner-node, or cloud-backed
- what workflow archetypes fit it best

### 3. Use layered truth

ComfyPilot should merge four kinds of truth:

1. Runtime truth: what nodes, models, folders, templates, and credentials exist right now
2. Curated truth: a versioned capability registry shipped with the repo
3. Official ecosystem truth: ComfyUI docs/changelog/provider pages
4. Community truth: common lineages and aliases used by real users

### 4. Stay local-first but not local-only

The planner should prefer local native workflows when they satisfy the task, but it should also understand partner/API nodes when they are the best available option.

## Proposed Architecture

### A. Ecosystem Registry

Add a new package:

```text
src/comfy_mcp/ecosystem/
  __init__.py
  registry.py
  aliases.py
  scoring.py
  freshness.py
  provider_catalog.py
  loader_strategies.py
  builtins.py
```

Add versioned data files:

```text
src/comfy_mcp/data/ecosystem/
  registry.json
  providers.json
  aliases.json
  community_ecosystems.json
```

This registry becomes the shared source of truth for:

- builder defaults
- workflow recommendations
- model classification
- provider recommendations
- install diagnostics
- MCP resources

### B. Runtime Environment Scanner

Add a scanner that combines:

- `client.get_models(folder)` across expanded folders
- `object_info` node availability
- workflow template index
- partner-node presence
- environment variables and auth configuration
- optional local metadata extraction from template `properties.models`

Output:

```json
{
  "detected_architectures": ["flux2", "qwen-image", "wan22"],
  "detected_ecosystems": ["pony"],
  "available_capabilities": ["t2i", "i2v", "t2v", "controlnet", "upscale"],
  "available_runtimes": ["local-native", "partner-nodes"],
  "available_providers": ["google", "runway", "kling"],
  "missing_assets": [
    {
      "family": "qwen-image",
      "missing": ["text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"]
    }
  ]
}
```

### C. Capability-Based Planner

Add a planner layer that accepts:

- user goal
- available environment
- latency preference
- quality preference
- local-only or provider-allowed mode
- VRAM constraints
- installed templates/nodes/models

It should return ranked choices such as:

```json
{
  "recommendations": [
    {
      "strategy_id": "local-qwen-image-edit",
      "score": 0.92,
      "family": "qwen-image",
      "runtime": "local-native",
      "workflow_type": "image-edit",
      "why": [
        "Native workflow template available",
        "Required diffusion model, VAE, and text encoder detected",
        "Best local edit-capable option on this install"
      ],
      "template_hint": "qwen-image-edit",
      "estimated_cost_class": "local",
      "estimated_speed_class": "medium"
    }
  ]
}
```

### D. Freshness Pipeline

Add a manual refresh command and a lightweight update process for official ecosystem data.

Not every update needs scraping.

The best pattern is:

- ship curated registry data in repo
- refresh it on demand or in CI from approved official sources
- annotate each entry with `last_verified_at` and `source_urls`
- keep community aliases separate from official model definitions

## Proposed Registry Schema

Each model family or provider-backed offering should look roughly like this:

```json
{
  "id": "qwen-image",
  "kind": "family",
  "display_name": "Qwen-Image",
  "status": "active",
  "modality": ["image"],
  "tasks": ["t2i", "i2i", "edit", "control"],
  "runtime_modes": ["local-native"],
  "community_tags": [],
  "aliases": ["qwen image", "qwen-image", "qwen_image"],
  "required_folders": [
    "diffusion_models",
    "text_encoders",
    "vae"
  ],
  "optional_folders": [
    "loras",
    "model_patches",
    "controlnet"
  ],
  "required_nodes": [
    "UNETLoader",
    "Load VAE",
    "CLIPTextEncode"
  ],
  "asset_patterns": [
    {
      "folder": "diffusion_models",
      "patterns": ["qwen_image*.safetensors"]
    },
    {
      "folder": "text_encoders",
      "patterns": ["qwen_2.5_vl*.safetensors"]
    },
    {
      "folder": "vae",
      "patterns": ["qwen_image_vae*.safetensors"]
    }
  ],
  "recommended_workflows": [
    "qwen-image-t2i",
    "qwen-image-edit",
    "qwen-image-depth-control"
  ],
  "selection_hints": {
    "best_for": [
      "instruction-following image generation",
      "image editing",
      "depth-guided composition"
    ],
    "avoid_when": [
      "only checkpoint-based legacy SD loader stack is installed"
    ]
  },
  "performance": {
    "latency_class": "medium",
    "memory_class": "high",
    "quality_class": "high"
  },
  "source_urls": [
    "https://docs.comfy.org/tutorials/image/qwen/qwen-image"
  ],
  "last_verified_at": "2026-03-14"
}
```

Provider-backed entries should add:

- `provider`
- `auth_requirements`
- `pricing_reference_url`
- `rate_limit_notes`
- `availability_mode`

## Initial Scope

### Tier 1: Must Understand Immediately

These should ship in the first real registry release.

Local native image:

- `sd15`
- `sdxl`
- `flux1`
- `flux2`
- `qwen-image`
- `z-image`
- `hidream`

Local native video:

- `ltx23`
- `wan22`
- `hunyuanvideo15`

Community ecosystems:

- `pony`
- `illustrious`
- `juggernaut-xl`
- `realvis-xl`

Partner/API families:

- `google`
- `openai`
- `black-forest-labs`
- `runway`
- `kling`
- `minimax`
- `luma`
- `recraft`
- `stability`

### Tier 2: Add Next

- `sd35`
- `kandinsky5`
- `cosmos-predict2`
- `ovis-image`
- `omnigen2`
- `qwen-edit`
- 3D providers and video enhancement providers

### Tier 3: Nice to Have

- deeper LoRA ecosystem tagging
- style or domain clusters
- community popularity weighting
- explicit benchmark metadata

## Expanded Model Folder Awareness

ComfyPilot should stop pretending that the main world is only `checkpoints`, `loras`, and `vae`.

Add awareness for at least:

- `checkpoints`
- `diffusion_models`
- `text_encoders`
- `vae`
- `loras`
- `controlnet`
- `model_patches`
- `latent_upscale_models`
- `clip`
- `clip_vision`
- `upscale_models`
- `embeddings`
- `diffusers`

This matters because current official workflows explicitly use:

- `diffusion_models`, `text_encoders`, and `vae` for Qwen-Image
- `model_patches` for Z-Image ControlNet patching
- `latent_upscale_models` for LTX-2.3
- multi-file text-encoder layouts for HiDream

## New MCP Resources

Add resources such as:

- `comfy://ecosystem/registry`
- `comfy://ecosystem/providers`
- `comfy://ecosystem/community`
- `comfy://environment/model-awareness`
- `comfy://planner/recommendations`
- `comfy://templates/by-capability/{task}`

These should be lightweight cached summaries, not giant raw dumps by default.

## New MCP Tools

Add tools such as:

- `comfy_detect_model_capabilities`
- `comfy_recommend_workflow`
- `comfy_explain_model_choice`
- `comfy_list_provider_models`
- `comfy_diagnose_missing_assets`
- `comfy_refresh_ecosystem_index`
- `comfy_list_model_families`
- `comfy_search_workflow_strategies`

### Example Tool Behavior

`comfy_recommend_workflow` should accept inputs like:

```json
{
  "goal": "generate a vertical social-media talking-head video from a prompt",
  "prefer_local": true,
  "allow_providers": true,
  "speed_priority": "high",
  "quality_priority": "high",
  "max_vram_gb": 24
}
```

And respond with ranked strategies, not just one guess.

## Builder Upgrade Strategy

The current builder should stop being a hardcoded SD1.5-era template box.

Replace the single `_TEMPLATES` mental model with a layered structure:

1. Legacy starter templates
2. Native family-aware templates
3. Provider strategy templates
4. Template-library pass-through recommendations

Example internal strategy IDs:

- `legacy-sd15-txt2img`
- `native-sdxl-txt2img`
- `native-flux2-t2i`
- `native-qwen-image-edit`
- `native-z-image-control`
- `native-ltx23-i2v`
- `native-wan22-t2v`
- `provider-google-nano-banana-2-edit`
- `provider-kling-3-video`
- `provider-runway-video-generation`

## Performance Strategy

This should not make the MCP slower.

Use:

- disk-cached registry data
- startup cache warmup
- background freshness updates
- alias normalization before search
- one-pass environment scans
- lazy provider detail expansion

The planner should never fetch external web pages during a normal tool call.

External refresh should be explicit or scheduled.

## Source Policy

Primary sources only for automatic refresh:

- ComfyUI official docs
- ComfyUI changelog
- ComfyUI template repository metadata
- official provider docs surfaced through ComfyUI docs
- official GitHub repositories when needed for node or model naming

Secondary sources for human review only:

- Reddit
- Civitai
- Hugging Face discussions
- X

Community sources should influence aliases and ecosystem tags, not core capability truth by themselves.

## Repo Integration Points

### Files likely to change first

- `src/comfy_mcp/tools/models.py`
- `src/comfy_mcp/tools/builder.py`
- `src/comfy_mcp/server.py`
- `src/comfy_mcp/templates/index.py`
- `src/comfy_mcp/templates/discovery.py`
- `src/comfy_mcp/knowledge/*`
- `src/comfy_mcp/comfy_client.py`

### New code areas

- `src/comfy_mcp/ecosystem/*`
- `src/comfy_mcp/planner/*`
- `src/comfy_mcp/data/ecosystem/*`

## Testing Strategy

Add tests for:

- filename and alias classification
- family detection from model folders
- provider detection from nodes and auth config
- missing-asset diagnostics
- planner ranking behavior
- cache freshness behavior
- fallback behavior when docs or provider metadata are absent

Golden tests should cover:

- `qwen-image`
- `z-image`
- `hidream`
- `flux2`
- `ltx23`
- `wan22`
- `hunyuanvideo15`
- `pony` as ecosystem tagging on top of `sdxl`

## What Success Looks Like

When this is done, ComfyPilot should be able to:

- understand modern ComfyUI-native models beyond old checkpoint families
- understand partner-node ecosystems without pretending they are local checkpoints
- recommend workflows based on capability and installed reality
- explain its reasoning in a way that actually helps users
- stay current through curated, refreshable ecosystem data

## Sources

- [ComfyUI Workflow Templates](https://docs.comfy.org/interface/features/template)
- [ComfyUI Partner Nodes Overview](https://docs.comfy.org/tutorials/partner-nodes/overview)
- [ComfyUI Partner Nodes Pricing](https://docs.comfy.org/tutorials/partner-nodes/pricing)
- [LTX-2.3 ComfyUI Workflow Examples](https://docs.comfy.org/tutorials/video/ltx/ltx-2-3)
- [Wan2.2 Video Generation](https://docs.comfy.org/tutorials/video/wan/wan2_2)
- [HunyuanVideo 1.5](https://docs.comfy.org/tutorials/video/hunyuan/hunyuan-video-1-5)
- [Qwen-Image](https://docs.comfy.org/tutorials/image/qwen/qwen-image)
- [Z-Image-Turbo](https://docs.comfy.org/tutorials/image/z-image/z-image-turbo)
- [HiDream-E1 / E1.1](https://docs.comfy.org/tutorials/image/hidream/hidream-e1)
- [Flux.2 Klein](https://docs.comfy.org/tutorials/flux/flux-2-klein)
- [Nano Banana 2](https://docs.comfy.org/tutorials/partner-nodes/google/nano-banana-2)
- [Kling 3.0](https://docs.comfy.org/tutorials/partner-nodes/kling/kling-3-0)
- [Runway Video Generation](https://docs.comfy.org/tutorials/partner-nodes/runway/video-generation)
- [ComfyUI Changelog](https://docs.comfy.org/changelog)
- Community signal, secondary only: [Pony Diffusion discussion](https://www.reddit.com/r/comfyui/comments/1rhiicm/clip_vision_problems/), [Illustrious discussion](https://www.reddit.com/r/StableDiffusion/comments/1qsya6n/is_illustrious_still_the_best_for_anime/)

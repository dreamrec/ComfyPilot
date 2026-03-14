# Roadmap To The Best Version Of ComfyPilot

This roadmap is optimized for leverage, not vanity. The goal is not "more tools." The goal is "a ComfyUI pilot an agent can trust."

## Guiding Principles

1. Truth before breadth
2. Runtime correctness before new demos
3. Platform alignment before hand-rolled abstractions
4. Agent trust before marketing language

## Phase 1 - Reliability Hardening

Time horizon: immediate

Ship these before adding any major new surface:

1. Fix local/cloud route branching and auth detection.
2. Harden the WS loop against binary preview frames.
3. Make monitoring non-destructive by default.
4. Reconcile interrupt/cancel/job state truth.
5. Sanitize output-routing paths and command suggestions.
6. Remove tracked cache artifacts and tighten repo hygiene.
7. Add a real integration smoke suite against live ComfyUI.

Expected outcome:

- Fewer "looks fine in tests, breaks live" failures
- Better confidence in progress and job state
- Safer filesystem behavior

## Phase 2 - Truthful Product Surface

Time horizon: next release after hardening

1. Generate tool docs from the runtime registry.
2. Add a brutally honest support matrix:
   - local
   - cloud
   - workflow JSON
   - API prompt format
   - V3 custom nodes
   - remote transport
3. Rename or redesign placebo tools.
4. Move from "JSON string everywhere" toward more structured output contracts where MCP clients benefit.

Expected outcome:

- The README becomes trustworthy
- Agents and humans stop learning the wrong mental model

## Phase 3 - Real ComfyUI Platform Alignment

Time horizon: major feature wave

1. Replace the static builder mindset with template discovery and template instantiation.
2. Ingest official workflow templates when available.
3. Add workflow-format awareness:
   - API prompt format
   - UI/export workflow format
   - explicit conversion or translation pipeline
4. Add install graph awareness:
   - installed nodes
   - installed models
   - embeddings
   - extensions
5. Add registry-aware missing-node resolution.
6. Add model-family-aware planning:
   - SD1.5
   - SDXL
   - FLUX
   - inpainting
   - ControlNet
   - video

Expected outcome:

- ComfyPilot becomes current with how ComfyUI is actually evolving
- The agent stops guessing blind about environment compatibility

## Phase 4 - Agent-Native Differentiation

Time horizon: after the core is solid

1. Upgrade technique memory from simple storage to compatibility-aware memory.
2. Rank reusable techniques by:
   - model availability
   - node availability
   - past success
   - user preference
3. Add better execution summaries and recovery guidance.
4. Add progressive preview strategy:
   - lightweight preview metadata
   - optional thumbnail content blocks
   - links/URLs for large outputs
5. Add richer multi-step workflow orchestration primitives.

Expected outcome:

- ComfyPilot becomes not just a wrapper, but a strong operator for a real creative workstation

## Phase 5 - Distribution and Remote Maturity

Time horizon: later, but important

1. Add Streamable HTTP transport support.
2. Support safer multi-client semantics.
3. Improve auth, origin validation, and remote publishing posture.
4. Prepare for MCP registry-quality metadata if the project is meant to be shared broadly.

Why this phase matters:

The MCP ecosystem is moving toward stronger remote server patterns. If ComfyPilot ever wants to be more than a local plugin helper, it should align with that future.

## What I Would Explicitly Not Prioritize Yet

Do not prioritize these before Phases 1-3 are solid:

- another 20 convenience tools
- more marketing language
- new packaging variants
- clever agent behavior on top of shaky execution truth

## Fastest Path To A Much Better Product

If I were prioritizing the next serious cycle, I would do this in order:

1. Merge or port the strongest upstream `main` fixes back into the working branch you actually use.
2. Close the remaining core runtime issues called out in the audit.
3. Build around official templates, registry, and install-graph truth.
4. Only then expand agent intelligence and distribution.

## Final Recommendation

The best version of ComfyPilot is not "the repo with the most ComfyUI tools."

It is:

the most reliable, compatibility-aware, visually grounded, agent-operable control plane for real ComfyUI environments.

That goal is realistic. The repo already has enough good instincts to get there if it keeps choosing depth over noise.

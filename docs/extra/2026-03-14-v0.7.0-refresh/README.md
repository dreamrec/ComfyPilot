# ComfyPilot Refresh Audit

Audit target: `origin/main` at `a3e8b70`  
Version claimed by upstream repo: `v0.7.0`  
Audit date: 2026-03-14

## Scope

This is the refreshed audit after the repo updates. It is separate from the older top-level audit, which covered the local `v0.2.0` checkout.

I audited:

- upstream code in `src/comfy_mcp/**`
- the current README and support matrix
- the expanded test suite
- the direction of current ComfyUI and MCP docs
- a small amount of community signal from GitHub discussions/issues where it helped confirm real-world pain points

## Method

- Created a dedicated worktree for `origin/main`
- Read the architecture and key tools end to end
- Compared `master..origin/main` to understand what changed
- Verified the refreshed suite in a clean checkout:
  - initial `uv run pytest -q` failed because dev extras were not installed
  - after `uv sync --extra dev`, `uv run pytest -q` passed with `541 passed in 5.80s`

## Headline Judgment

The repo has improved a lot. This is no longer just a nice idea with some useful tools around it. `v0.7.0` has a real architectural spine now:

- install graph
- compatibility engine
- documentation cache
- template engine
- knowledge layer
- registry integration

That said, I still would not call it the final "ultimate ComfyUI Pilot" yet.

The remaining issues are not mostly cosmetic. They are about truth:

- cloud support is still partial and a bit brittle
- the event layer still does not safely account for binary preview frames
- one documented template route still appears mismatched
- compatibility language is stronger than compatibility checking
- the fallback builder still thinks too much like 2024-era ComfyUI

## What Improved Since The Last Audit

- many `v0.2.0` correctness problems were fixed
- the test suite grew from `298` to `541` passing tests
- event draining and interrupt state handling were repaired
- the old "just add more tools" shape has been replaced with more coherent subsystems
- the repo now tracks the real ComfyUI ecosystem better through docs, templates, install knowledge, and registry lookups

## What Still Matters Most

If I had to reduce the whole audit to one sentence:

ComfyPilot is now a serious local-first ComfyUI MCP layer, but the next leap is not more tool count, it is better contract truth, modern workflow intelligence, and sharper product focus.

## Files In This Folder

- [01-code-findings-fixes-and-improvements.md](./01-code-findings-fixes-and-improvements.md)
  - concrete code-level findings, risks, and fix directions
- [02-honest-opinion-and-sense-check.md](./02-honest-opinion-and-sense-check.md)
  - candid product judgment on what really makes sense now
- [03-ecosystem-benchmark-and-latest-context.md](./03-ecosystem-benchmark-and-latest-context.md)
  - where current ComfyUI and MCP have moved, and how ComfyPilot compares
- [04-roadmap-to-the-best-comfypilot.md](./04-roadmap-to-the-best-comfypilot.md)
  - practical roadmap for turning this into the strongest version of itself

## Primary Sources Used

- [ComfyUI server routes](https://docs.comfy.org/development/comfyui-server/comms_routes)
- [Comfy Cloud overview](https://docs.comfy.org/cloud)
- [Comfy Cloud workflows](https://docs.comfy.org/cloud/workflows)
- [ComfyUI workflow templates](https://docs.comfy.org/tutorials/workflow_templates)
- [ComfyUI workflow JSON v3 spec](https://docs.comfy.org/specs/workflow_json_v3)
- [ComfyUI subgraphs](https://docs.comfy.org/tutorials/using-subgraphs)
- [ComfyUI V3 migration](https://docs.comfy.org/custom-nodes/v3_migration)
- [ComfyUI registry publishing](https://docs.comfy.org/registry/publishing)
- [Official workflow template repo](https://github.com/Comfy-Org/workflow_templates)
- [ComfyUI issue: workflow API format confusion](https://github.com/comfyanonymous/ComfyUI/issues/1112)
- [ComfyUI discussion: API format / workflow conversion pain](https://github.com/comfyanonymous/ComfyUI/discussions/3717)
- [MCP transports](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [MCP remote servers](https://modelcontextprotocol.io/registry/remote-servers)

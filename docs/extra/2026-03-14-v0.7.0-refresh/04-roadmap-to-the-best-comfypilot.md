# Roadmap To The Best ComfyPilot

## Core Principle

Do not chase "ultimate" by adding more commands.

Chase it by making the existing system more truthful, more modern, and more useful under real ComfyUI conditions.

## Phase 1 - Truth Hardening

Goal: remove the remaining protocol and trust gaps.

Priority work:

1. Cloud route/auth cleanup
   - detect `cloud.comfy.org` correctly in `auto` mode
   - centralize local/cloud route mapping
   - add contract tests for execution endpoints, not just feature discovery

2. WebSocket resilience
   - handle binary preview frames safely
   - add tests for `bytes` frames and non-JSON payloads

3. Template route fix
   - verify and correct `workflow_templates` pathing
   - add explicit route contract tests

4. Feature payload preservation
   - stop collapsing object-shaped features inside the install graph

5. Compatibility wording cleanup
   - stop reporting `compatible: true` when the system only knows "no obvious version/OS conflict"

Success criteria:

- cloud behavior is explicit and predictable
- event monitoring survives preview traffic
- template discovery cannot silently lie by omission
- compatibility output matches reality

## Phase 2 - Modern ComfyUI Alignment

Goal: make the product feel native to the current ecosystem.

Priority work:

1. Make builder logic template-first
   - use hardcoded graphs only as the last fallback

2. Add modern starter families
   - SDXL
   - FLUX
   - current video-oriented templates where official templates support them

3. Add workflow import help
   - bridge UI workflow JSON and API prompt format
   - even a partial translator plus a clear warning layer would be valuable

4. Add subgraph-aware composition
   - allow assembling workflows from reusable graph chunks instead of only monolithic templates

Success criteria:

- ComfyPilot no longer feels capped at a small legacy workflow set
- more real-world workflows can be adapted instead of rebuilt

## Phase 3 - Product Coherence

Goal: tighten semantics so the tool surface feels cleaner and more honest.

Priority work:

1. Rework event subscriptions
   - either make them real with handles/cursors
   - or remove them and present polling honestly

2. Improve cache durability
   - move docs/template writes to `atomic_write`

3. Improve contributor workflow
   - document `uv sync --extra dev`
   - add a single obvious test command

4. Add live integration checks
   - one local ComfyUI integration path
   - one cloud contract smoke test path if credentials are available in CI

Success criteria:

- fewer tools that feel half-semantic
- easier first-run contributor experience
- better confidence than mock-only testing

## Phase 4 - The Version That Could Become Special

Goal: turn ComfyPilot from a capable MCP wrapper into a truly strong workflow copilot.

This is where the repo can become exceptional:

1. Intent-to-workflow adaptation
   - use install graph + templates + docs + registry + memory together
   - choose the best available approach for the user's actual machine

2. Repair-first reasoning
   - when a workflow is incompatible, suggest:
     - nearest installed alternative
     - missing package from registry
     - subgraph/template replacement
     - downgraded fallback path

3. Family-aware planning
   - detect whether the environment is better suited to SDXL, FLUX, classic SD1.5 flows, or video pipelines

4. Remote-ready MCP story
   - add streamable HTTP transport when the product is ready
   - keep stdio as the excellent local default

## The Highest-Leverage Sequence

If I were prioritizing purely for impact, I would do it in this order:

1. fix cloud/auth/route truth
2. fix binary websocket handling
3. fix template route correctness
4. tighten compatibility semantics
5. modernize the builder around templates and workflow import

## Final Roadmap Judgment

The repo does not need a reinvention.

It needs a disciplined second pass where every major promise becomes fully true, and where the builder/template/workflow story catches up to what modern ComfyUI has already become.

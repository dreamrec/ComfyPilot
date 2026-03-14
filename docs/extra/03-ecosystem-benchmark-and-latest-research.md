# Ecosystem Benchmark and Latest Research

This file connects the local repo to the current ComfyUI and MCP landscape.

## 1. Official ComfyUI Signals In 2026

### Local server routes are broader and more specific than the local checkout assumes

Official route docs show the current local server surface includes:

- `/prompt`
- `/queue`
- `/history`
- `/system_stats`
- `/features`
- `/extensions`
- `/upload/image`
- `/ws`

Source:

- [ComfyUI server routes](https://docs.comfy.org/development/comfyui-server/comms_routes)

Why it matters for ComfyPilot:

- The client cannot treat all route families as one generic API shape.
- Capability detection has to branch correctly by environment.

### Cloud API is its own product, not just "local ComfyUI with a key"

Official cloud docs use:

- base URL: `https://cloud.comfy.org`
- WebSocket URL pattern with token query param
- binary preview frames over WS

Sources:

- [Cloud overview](https://docs.comfy.org/development/cloud/overview)
- [Cloud API reference](https://docs.comfy.org/development/cloud/api-reference)

Why it matters:

- A future-proof ComfyPilot should model local and cloud as explicit profiles.
- "Partial cloud support" should be implemented deliberately, not incidentally.

### ComfyUI now has official workflow templates

Official docs describe:

- server-side workflow templates
- a Template Browser UI
- custom-node packaged templates

Sources:

- [Workflow templates](https://docs.comfy.org/custom-nodes/workflow_templates)
- [Template browser](https://docs.comfy.org/interface/features/template)

Why it matters:

- Hardcoding five starter graphs is no longer enough as a long-term strategy.
- The best agent layer should ingest and adapt official templates instead of competing with them manually.

### ComfyUI has moved further into registry and package-aware workflows

Official docs now emphasize:

- registry concepts
- package standards
- V3 custom-node migration

Sources:

- [Registry overview](https://docs.comfy.org/registry/overview)
- [Registry standards](https://docs.comfy.org/registry/standards)
- [V3 migration](https://docs.comfy.org/custom-nodes/v3_migration)

Why it matters:

- Install graph and compatibility reasoning are now first-class product needs.
- A serious pilot should know what is installed, what is missing, and what package provides it.

### Model families are broader than the local builder surface

Official docs and tutorials now cover much more than a basic SD1.5 graph:

- [SDXL](https://docs.comfy.org/tutorials/basic/text-to-image)
- [FLUX 1 Dev](https://docs.comfy.org/tutorials/flux/flux-1-dev)
- [WAN 2.2 video](https://docs.comfy.org/tutorials/video/wan/wan2_2)

Why it matters:

- "Ultimate ComfyUI pilot" means model-family awareness, not just prompt + checkpoint + KSampler.

## 2. Official MCP Signals In 2026

### Remote MCP is increasingly about Streamable HTTP

The MCP spec and SDK docs now position Streamable HTTP as the modern remote transport and describe HTTP transport security requirements.

Sources:

- [MCP transport spec](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [MCP changelog](https://modelcontextprotocol.io/specification/2025-03-26/changelog)
- [Publishing remote servers](https://modelcontextprotocol.io/registry/remote-servers)

Why it matters:

- `stdio` is still fine for local editor/plugin integration.
- But if ComfyPilot wants to become a more shareable or hosted control plane, Streamable HTTP should be on the roadmap.

## 3. Local `v0.2.0` vs Upstream `main`

This was one of the biggest audit discoveries.

### What the workspace contains

- Local branch: `master`
- Local commit: `3aad603`
- Version in local README / `pyproject.toml`: `0.2.0`

### What GitHub currently contains

- Upstream branch fetched on 2026-03-14: `origin/main`
- Upstream commit: `a3e8b70`
- Upstream README version: `0.7.0`

### Diff size

Between local `v0.2.0` and upstream `main`:

- `96` files changed
- `14,523` insertions
- `52` deletions

### What upstream already adds

Upstream `main` introduces or expands:

- install graph
- compatibility engine
- docs engine
- template engine
- persistent knowledge/config
- registry integration

It also fixes some issues that are still present locally, including:

- route branching for `features` / `extensions`
- more careful interrupt/job reconciliation
- URL-encoded image URLs
- non-PNG MIME inference
- better image listing dedupe
- conditional WebSocket startup

### What this means for the audit

The right framing is:

- the local checkout is behind the public repo
- the repo direction is actually improving in sensible ways
- some recommendations in this audit are already validated by upstream evolution

## 4. Adjacent Repos and Comparative Positioning

I checked adjacent public repos in the same problem space:

- [alecc08/comfyui-mcp](https://github.com/alecc08/comfyui-mcp)
- [AIDC-AI/Pixelle-MCP](https://github.com/AIDC-AI/Pixelle-MCP)

### Where ComfyPilot looks strong

- Better emphasis on inline visual return
- More explicit safety/VRAM thinking
- Workflow snapshots and technique memory are real differentiators
- Cleaner "agent control layer" framing than some generic wrappers

### Where ComfyPilot looks weaker

- Less current with official ComfyUI platform advances in the local checkout
- More doc/runtime mismatch than it can afford
- Static builder surface feels older than the 2026 ecosystem

## 5. Research Takeaways That Matter Most

### Best current direction

ComfyPilot should align itself with the official ComfyUI platform, not compete with it at the wrong layer.

That means:

- ingest official templates
- reason about installed packages and models
- bridge workflow formats cleanly
- understand registry metadata
- support modern model families and video/image branches

### Biggest opportunity

The repo already has the right product DNA for an agentic control plane.

The opportunity is to combine:

- current ComfyUI knowledge
- strong environment introspection
- reliable execution
- honest contracts

That combination is more valuable than another wave of thin convenience tools.

## 6. Practical Benchmark Verdict

Compared with the current ecosystem, local `v0.2.0` ComfyPilot feels like:

- a promising local control bridge
- with a better UX concept than many wrappers
- but still behind the official ComfyUI platform on templates, registry awareness, and model-family breadth

Compared with its own upstream `main`, it looks like an earlier generation of the same idea rather than the repo's current state of the art.

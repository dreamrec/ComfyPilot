# ComfyPilot Audit Package

Audit date: 2026-03-14

## What Is In Here

This folder now holds two audit snapshots:

- Legacy baseline audit:
  - Local checkout in this workspace: `master` at `3aad603` (`v0.2.0`)
  - Files live directly in `docs/extra/`
- Refresh audit after the repo updates:
  - Upstream target: `origin/main` at `a3e8b70` (`v0.7.0`)
  - Files live in [`docs/extra/2026-03-14-v0.7.0-refresh`](./2026-03-14-v0.7.0-refresh/)

## Refresh Audit Method

- Created an isolated audit worktree from `origin/main`
- Read the runtime surface in `src/comfy_mcp/**`, the README, tests, and planning docs
- Diffed local `v0.2.0` against current upstream `v0.7.0`
- Validated the refreshed upstream test suite in a clean worktree:
  - `uv run pytest -q` failed before dev extras were installed
  - `uv sync --extra dev`
  - `uv run pytest -q` -> `541 passed in 5.80s`
- Cross-checked repo behavior against current public sources:
  - [ComfyUI server routes](https://docs.comfy.org/development/comfyui-server/comms_routes)
  - [Comfy Cloud overview](https://docs.comfy.org/cloud)
  - [Comfy Cloud workflows](https://docs.comfy.org/cloud/workflows)
  - [ComfyUI workflow templates](https://docs.comfy.org/tutorials/workflow_templates)
  - [ComfyUI workflow JSON v3 spec](https://docs.comfy.org/specs/workflow_json_v3)
  - [ComfyUI subgraphs](https://docs.comfy.org/tutorials/using-subgraphs)
  - [ComfyUI V3 migration](https://docs.comfy.org/custom-nodes/v3_migration)
  - [ComfyUI registry publishing](https://docs.comfy.org/registry/publishing)
  - [Official workflow template repo](https://github.com/Comfy-Org/workflow_templates)
  - [MCP transports](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
  - [MCP remote servers](https://modelcontextprotocol.io/registry/remote-servers)

## Quick Read

- The old top-level audit still matters if you want the `v0.2.0` baseline.
- The new refresh audit is the one that reflects the repo after the recent wave of changes.
- Short verdict on the current upstream repo: this is now a real product-shaped codebase, not just a promising prototype, but it still has a few truth and modernization gaps before it deserves the "ultimate ComfyUI Pilot" label.

## Legacy Audit Files

- [01-code-errors-fixes-and-improvements.md](./01-code-errors-fixes-and-improvements.md)
- [02-honest-opinion-what-makes-sense-and-what-not.md](./02-honest-opinion-what-makes-sense-and-what-not.md)
- [03-ecosystem-benchmark-and-latest-research.md](./03-ecosystem-benchmark-and-latest-research.md)
- [04-roadmap-to-the-best-version-of-comfypilot.md](./04-roadmap-to-the-best-version-of-comfypilot.md)

## Refresh Audit Files

- [2026-03-14-v0.7.0-refresh/README.md](./2026-03-14-v0.7.0-refresh/README.md)
- [2026-03-14-v0.7.0-refresh/01-code-findings-fixes-and-improvements.md](./2026-03-14-v0.7.0-refresh/01-code-findings-fixes-and-improvements.md)
- [2026-03-14-v0.7.0-refresh/02-honest-opinion-and-sense-check.md](./2026-03-14-v0.7.0-refresh/02-honest-opinion-and-sense-check.md)
- [2026-03-14-v0.7.0-refresh/03-ecosystem-benchmark-and-latest-context.md](./2026-03-14-v0.7.0-refresh/03-ecosystem-benchmark-and-latest-context.md)
- [2026-03-14-v0.7.0-refresh/04-roadmap-to-the-best-comfypilot.md](./2026-03-14-v0.7.0-refresh/04-roadmap-to-the-best-comfypilot.md)

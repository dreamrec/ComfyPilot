# Final Audit Fixes

Date: 2026-03-14

Commit: `d04a543` (`Fix final audit issues`)

## Scope

This document summarizes the code changes made to address the remaining findings from the final repo audit of the latest `origin/main`.

The fixes targeted four areas:

1. Cloud route completeness and response normalization
2. Workflow template route ambiguity
3. Invalid base64 upload handling
4. Release and documentation truthfulness

## What Changed

### 1. Cloud-aware client routing

Updated `src/comfy_mcp/comfy_client.py` to branch correctly between local and cloud-style endpoints.

Key changes:

- Added a `_route()` helper to map local and cloud endpoints cleanly
- Added `build_view_url()` so image URLs can be generated correctly for both profiles
- Normalized cloud history responses to the local shape expected by the rest of the code
- Added cloud-aware handling for:
  - system stats
  - queue
  - prompt submission
  - object info
  - history
  - image view
  - image upload
  - interrupt
  - VRAM free
  - queue cancel / clear
  - model discovery

Practical result:

- Local ComfyUI behavior stays intact
- Cloud-compatible paths now work more consistently
- Downstream code no longer has to care as much about response shape differences

### 2. Workflow template discovery fallback

Updated `src/comfy_mcp/templates/discovery.py` to handle the current route ambiguity around workflow templates.

Behavior now:

- Local profile tries `/workflow_templates` first, then falls back to `/api/workflow_templates`
- Cloud profile tries `/api/workflow_templates` first, then falls back to `/workflow_templates`

Practical result:

- Discovery is more resilient across ComfyUI variants and documentation drift
- The implementation matches real-world ambiguity instead of assuming a single universal route

### 3. Safer base64 image uploads

Updated `src/comfy_mcp/tools/images.py` to validate base64 input and return a structured tool error instead of crashing on malformed data.

Behavior now:

- Valid payloads are decoded and uploaded normally
- Invalid payloads return `{"error": "Invalid base64 image_data"}`

Practical result:

- Better tool robustness
- Cleaner failure mode for LLM-driven or user-generated malformed input

### 4. Version and docs alignment

Updated release metadata and docs so the repo no longer reports mixed version identities.

Files aligned:

- `README.md`
- `docs/MANUAL.md`
- `pyproject.toml`
- `src/comfy_mcp/__init__.py`
- `src/comfy_mcp/registry/client.py`
- `CHANGELOG.md`
- `uv.lock`

Corrections include:

- Version updated to `0.7.1`
- Tool count text corrected to `90 Tools`
- Test-count text updated to match the then-current suite
- Manual resource list updated to match actual exposed MCP resources
- Support matrix wording updated to reflect partial but real cloud support

## Tests Added and Updated

Expanded targeted coverage in:

- `tests/test_route_contracts.py`
- `tests/test_template_discovery.py`
- `tests/test_images.py`

New/updated assertions cover:

- cloud endpoint routing
- cloud history normalization
- cloud image URL building
- template route preference and fallback behavior
- invalid base64 upload handling

## Verification

Full test suite result:

```text
614 passed in 4.89s
```

Command used:

```bash
uv run pytest -q
```

## Outcome

This branch closes the concrete issues called out in the final audit without widening the scope into unrelated refactors.

The main improvements are:

- better cloud compatibility
- safer template discovery
- more robust image tooling
- more truthful release metadata and documentation

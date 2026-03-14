# Code Errors, Fix Ideas, and Improvements

This file focuses on the local checkout at `3aad603` (`v0.2.0`).

Severity guide:

- `Critical`: likely to break real usage or invalidate a major product claim
- `High`: important runtime, safety, or trust issue
- `Medium`: quality, compatibility, or product-coherence issue
- `Low`: hygiene or maintainability issue

## Priority Summary

Hotfix first:

1. Fix route/profile detection and local-vs-cloud API branching.
2. Fix WebSocket handling for binary preview frames.
3. Sanitize output-routing filenames and command suggestions.
4. Stop mutating monitoring state just by observing it.
5. Add one real integration test path against a live ComfyUI instance.

## Findings

### 1. `Critical` - Local route detection and cloud heuristics are wrong

Local refs:

- `src/comfy_mcp/comfy_client.py:50-52`
- `src/comfy_mcp/comfy_client.py:69-90`
- `src/comfy_mcp/comfy_client.py:201-208`

What is wrong:

- Auto auth detection keys off `"api.comfy"` in the URL, but official cloud docs use `https://cloud.comfy.org`, not `https://api.comfy.org`.
- Local ComfyUI route docs show `GET /features` and `GET /extensions`, but the local client hardcodes `/api/features` and `/api/extensions`.
- In practice that means capability probing is partly blind on local servers and cloud detection is brittle.

Why it matters:

- It weakens the trustworthiness of the support matrix.
- It makes local feature discovery silently fail.
- It makes cloud support more aspirational than real.

External evidence:

- [ComfyUI local routes](https://docs.comfy.org/development/comfyui-server/comms_routes)
- [ComfyUI cloud overview](https://docs.comfy.org/development/cloud/overview)

Fix idea:

- Add an explicit `_is_cloud()` branch.
- Use `/features` and `/extensions` for local; keep `/api/*` only for cloud endpoints that actually require it.
- Detect `cloud.comfy.org` explicitly.
- Consider a forced `COMFY_PROFILE=local|cloud` override for unusual deployments.

Upstream `main` status:

- Partly fixed. `origin/main` already switches `get_features()` and `get_extensions()` by profile.

### 2. `Critical` - The WebSocket loop is brittle against binary preview frames

Local refs:

- `src/comfy_mcp/events/event_manager.py:70-77`

What is wrong:

- The loop assumes every WebSocket frame is JSON text.
- Official ComfyUI cloud docs state that preview images are sent as binary WebSocket frames during execution.
- The local code only catches `json.JSONDecodeError`, not `UnicodeDecodeError`, so JPEG/PNG preview frames can tear down the loop.

Why it matters:

- This can make progress monitoring flaky exactly when image generation is active.
- A monitoring system that disconnects on previews is not reliable enough for "live control".

External evidence:

- [ComfyUI cloud API reference: binary preview frames](https://docs.comfy.org/development/cloud/api-reference)

Fix idea:

- Branch on `isinstance(raw_msg, bytes)`.
- Decode or skip binary frames intentionally.
- If preview support is desired, parse the binary frame type and expose lightweight preview metadata or thumbnails.
- Catch `UnicodeDecodeError` separately even if preview parsing is deferred.

Upstream `main` status:

- I did not find evidence that this edge case is fixed yet.

### 3. `High` - The server starts the WS manager even when WS should be considered unavailable

Local refs:

- `src/comfy_mcp/server.py:45-52`
- `src/comfy_mcp/comfy_client.py:90`

What is wrong:

- `probe_capabilities()` sets `ws_available` based on profile.
- `server.py` still starts `EventManager` unconditionally.

Why it matters:

- On cloud or unsupported profiles, startup still spins up reconnect logic to `/ws`.
- That creates noisy logs and false confidence.

Fix idea:

- Only start the event manager when `client.capabilities["ws_available"]` is true.
- Surface that decision in a status resource or startup log.

Upstream `main` status:

- Fixed. `origin/main` guards `event_mgr.start()` behind `ws_available`.

### 4. `High` - `comfy_interrupt` does not reconcile tracked jobs

Local refs:

- `src/comfy_mcp/tools/workflow.py:120-126`
- `src/comfy_mcp/jobs/job_tracker.py:34-45`
- `src/comfy_mcp/jobs/job_tracker.py:79-85`

What is wrong:

- The interrupt tool forwards `/interrupt` to ComfyUI but does not update tracked job state.
- A running prompt can remain "running" or "queued" in tracker memory after interruption.

Why it matters:

- It breaks monitoring truth.
- It makes multi-job orchestration unsafe.
- It confuses agents deciding whether they can queue the next step.

Fix idea:

- Snapshot the queue before interrupt.
- Map currently running prompt IDs.
- Mark only truly running items as `interrupted`.
- Leave pending jobs untouched or report them explicitly.

Upstream `main` status:

- Fixed. `origin/main` already snapshots queue truth before interrupt and reconciles tracked job states.

### 5. `High` - `comfy_describe_dynamics` mutates state just by observing it

Local refs:

- `src/comfy_mcp/tools/monitoring.py:157-159`
- `src/comfy_mcp/events/event_manager.py:134-150`

What is wrong:

- `comfy_describe_dynamics()` uses `drain_events(limit=10)`.
- That means a status/inspection call consumes events that `comfy_get_events()` might need later.

Why it matters:

- Monitoring tools should not erase each other's evidence.
- This makes debugging harder and creates "Heisenbug" observability.

Fix idea:

- Add `peek_events()` for non-destructive reads.
- Reserve `drain_events()` for explicit queue consumption semantics.

Upstream `main` status:

- Partly fixed. `origin/main` adds `peek_events()`.

### 6. `High` - `subscribe` / `unsubscribe` are basically placebo tools for MCP agents

Local refs:

- `src/comfy_mcp/tools/monitoring.py:59-99`
- `src/comfy_mcp/events/event_manager.py:118-132`

What is wrong:

- The MCP tools do not accept callbacks.
- The event manager captures events regardless of subscription state.
- Calling `comfy_subscribe("progress")` only creates an empty list entry; it does not materially change server behavior for the agent.

Why it matters:

- It sounds like a live subscription API, but functionally it is almost a no-op.
- This is a classic example of "tool surface > actual semantics."

Fix idea:

- Either remove these tools, or redesign them around:
  - cursors
  - durable event channels
  - named subscription handles
  - resource subscriptions or Streamable HTTP notification semantics

Upstream `main` status:

- No clear fix found. This is still a design issue.

### 7. `High` - Output routing trusts filenames from the remote server and writes unsanitized paths

Local refs:

- `src/comfy_mcp/tools/output_routing.py:43-51`
- `src/comfy_mcp/tools/output_routing.py:86-95`
- `src/comfy_mcp/tools/output_routing.py:133-141`

What is wrong:

- `dest_path = dest_dir / filename` blindly trusts `filename`.
- A hostile or compromised ComfyUI instance could attempt path traversal with names like `../../something`.
- Generated TD/Blender command snippets also interpolate raw paths without escaping quotes.

Why it matters:

- This is one of the few places where external input crosses directly into the local filesystem.
- It is a genuine security and safety issue.

Fix idea:

- Normalize to `Path(filename).name`.
- Reject path separators and suspicious names.
- Add collision handling.
- Escape any file paths embedded into Python command suggestions.

Upstream `main` status:

- I did not find evidence that this is fixed yet.

### 8. `Medium` - Image helpers have three compatibility/UX bugs in `v0.2.0`

Local refs:

- `src/comfy_mcp/tools/images.py:35-39`
- `src/comfy_mcp/tools/images.py:87-106`
- `src/comfy_mcp/tools/images.py:154-155`

What is wrong:

- `comfy_get_output_image()` always labels output as `image/png`, even if the file is JPEG or WebP.
- `comfy_list_output_images()` deduplicates only by filename, ignoring subfolder and type.
- `comfy_get_image_url()` does not URL-encode query params.

Why it matters:

- Wrong MIME types can break clients.
- Filename-only dedupe can hide valid outputs.
- Unescaped URLs break on spaces, unicode, or special characters.

Fix idea:

- Infer MIME by extension.
- Deduplicate on `(filename, subfolder, type)`.
- Use URL encoding for query params.

Upstream `main` status:

- Fixed. `origin/main` already does all three.

### 9. `Medium` - The builder templates are outdated relative to current ComfyUI practice

Local refs:

- `src/comfy_mcp/tools/builder.py:18-78`
- `src/comfy_mcp/tools/builder.py:237-315`
- `src/comfy_mcp/tools/builder.py:318-400`

What is wrong:

- The builder is centered on a small SD1.5-era mental model.
- Inpaint uses `LoadImage` + `SetLatentNoiseMask`, while current official docs highlight dedicated inpainting nodes like `VAE Encode (for Inpainting)` and `Load Image Mask`.
- ComfyUI now has official workflow template support and a template browser, but the local product still hand-maintains five static templates.
- ControlNet support is narrow and not clearly aligned with current official tutorials.

Why it matters:

- A workflow builder is one of the most important user-facing surfaces in an agent bridge.
- If it is outdated, the whole server feels older than the ecosystem around it.

External evidence:

- [Workflow templates](https://docs.comfy.org/custom-nodes/workflow_templates)
- [Template browser](https://docs.comfy.org/interface/features/template)
- [VAE Encode (for Inpainting)](https://docs.comfy.org/built-in-nodes/latent/vaeencodeforinpaint)
- [Load Image Mask](https://docs.comfy.org/built-in-nodes/mask/loadimagemask)
- [FLUX tutorials](https://docs.comfy.org/tutorials/flux/flux-1-dev)
- [WAN 2.2 video tutorial](https://docs.comfy.org/tutorials/video/wan/wan2_2)

Fix idea:

- Stop treating the builder as a hardcoded workflow library.
- Ingest official templates when available.
- Add model-family-aware template selection for SD1.5, SDXL, FLUX, inpainting, ControlNet, and video.

Upstream `main` status:

- Partly addressed. `origin/main` adds a template engine, which is the right direction.

### 10. `Medium` - The manual overstates what several tools actually do

Local refs:

- `docs/MANUAL.md:51-52`
- `docs/MANUAL.md:59-62`
- `docs/MANUAL.md:83-86`
- `docs/MANUAL.md:95`
- `docs/MANUAL.md:108`
- `docs/MANUAL.md:118-119`
- `docs/MANUAL.md:169`

Reality in code:

- `comfy_restart` does not restart anything; it returns `not_supported`.
- `comfy_get_model_info` returns node schema, not model-file metadata.
- `comfy_refresh_models` does not force a server rescan.
- `comfy_search_nodes` only does a name substring search.
- `comfy_download_batch` returns metadata, not downloaded files.
- `comfy_search_history` searches workflow node class names, not prompt IDs or output metadata.
- `comfy_apply_template` is just an alias for `comfy_build_workflow`, not a true "apply to existing workflow" operation.

Why it matters:

- This is the main trust problem in the repo: names and descriptions sound more complete than behavior.

Fix idea:

- Generate docs from the runtime.
- Keep a brutally honest support matrix.
- Rename or narrow semantics when the implementation is intentionally thinner.

Upstream `main` status:

- Improved in places, but the general lesson still applies.

### 11. `Medium` - The test suite is fast and useful, but not enough to prove live behavior

Evidence:

- `uv run pytest -q` -> `298 passed in 1.15s`
- `tests/` relies heavily on `AsyncMock`, `MagicMock`, and mocked context wiring.

Representative refs:

- `tests/conftest.py`
- `tests/test_builder.py`
- `tests/test_monitoring.py`
- `tests/test_workflow.py`

What is missing:

- Live local ComfyUI smoke tests
- Real WebSocket integration tests
- Format compatibility tests against actual `object_info`
- Cloud-path contract tests

Fix idea:

- Add a thin integration suite behind an opt-in marker or Docker/local fixture.
- At minimum, test:
  - `/features` vs `/api/features`
  - `/ws` preview frames
  - `/prompt` validation failures
  - image retrieval and URL generation

### 12. `Low` - The repo still tracks `__pycache__` artifacts

Local refs:

- `src/comfy_mcp/__pycache__/__init__.cpython-312.pyc`
- `src/comfy_mcp/__pycache__/errors.cpython-312.pyc`
- `tests/__pycache__/conftest.cpython-312-pytest-9.0.2.pyc`
- `tests/__pycache__/conftest.cpython-312.pyc`

Why it matters:

- It is not a runtime bug, but it makes the repo look less disciplined than the code deserves.

Fix idea:

- Remove tracked cache artifacts and keep `.gitignore` enforcing the policy.

Upstream `main` status:

- Improved. Those tracked bytecode files disappear in the upstream diff.

### 13. `Low` - Technique persistence is simple, but durability is weak

Local refs:

- `src/comfy_mcp/memory/technique_store.py:30-38`
- `src/comfy_mcp/memory/technique_store.py:41-78`

What is wrong:

- Writes are not atomic.
- There is no schema versioning.
- Partial writes or future migrations could become messy.

Why it matters:

- This is exactly the kind of subsystem that starts simple and becomes painful later if not versioned early.

Fix idea:

- Add atomic writes, encoding discipline, and a lightweight stored-schema version.

## Recommended First Patch Set

If the goal is the fastest credibility gain, I would ship the next patch set in this order:

1. Route/profile correctness
2. WS binary-frame hardening
3. Output path sanitization
4. Non-destructive monitoring reads
5. Interrupt/job-state truth
6. Generated docs + support matrix
7. One real integration smoke suite

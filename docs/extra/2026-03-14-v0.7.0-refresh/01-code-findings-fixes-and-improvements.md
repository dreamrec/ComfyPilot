# Code Findings, Fix Ideas, and Improvements

This file focuses on the refreshed upstream repo at `origin/main` commit `a3e8b70`.

## Severity Guide

- `High`: likely to break trust, real functionality, or an important product claim
- `Medium`: meaningful correctness, compatibility, or product-coherence issue
- `Low`: mostly resilience, ergonomics, or maintenance

## Overall Read

Compared with the old `v0.2.0` audit, the repo is materially better. A lot of the previous core issues are already fixed. The remaining findings are concentrated in five areas:

1. cloud contract truth
2. event protocol handling
3. template discovery correctness
4. compatibility claim accuracy
5. builder modernization

## Findings

### 1. `High` - `auto` cloud auth detection still keys off `api.comfy`, not the documented cloud host

Repo refs:

- `src/comfy_mcp/comfy_client.py:48-55`
- `src/comfy_mcp/comfy_client.py:69-91`
- `src/comfy_mcp/comfy_client.py:178-237`
- `tests/test_auth_profiles.py:15-28`
- `README.md:229-236`

What is wrong:

- `auth_method="auto"` chooses `X-API-Key` only when the URL contains `api.comfy`.
- Current Comfy Cloud docs center the service on `https://cloud.comfy.org`.
- That means valid cloud URLs can still fall through to bearer auth unless the user overrides the method manually.
- The broader cloud normalization is still incomplete too: `get_queue()`, `get_history()`, `get_object_info()`, `queue_prompt()`, `cancel_prompt()`, `clear_queue()`, and `delete_history()` still use local-style routes only.

Why it matters:

- `auto` mode is exactly where users expect the tool to be safe.
- The support matrix is honest that cloud execution is partial, but the code still makes the partial support easy to misconfigure.
- The current tests only cover cloud route branching for `features`, `extensions`, and `system_stats`, not the execution paths that matter most.

Fix direction:

- detect cloud explicitly from documented hosts and add a `COMFY_PROFILE=local|cloud` override
- centralize endpoint routing in one local/cloud route table
- add cloud tests for `prompt`, `queue`, `object_info`, `history`, and image retrieval

External evidence:

- [Comfy Cloud overview](https://docs.comfy.org/cloud)
- [Comfy Cloud workflows](https://docs.comfy.org/cloud/workflows)
- [ComfyUI server routes](https://docs.comfy.org/development/comfyui-server/comms_routes)

### 2. `High` - Template discovery still appears to call the wrong documented route for workflow templates

Repo refs:

- `src/comfy_mcp/templates/discovery.py:47-65`
- `tests/test_template_discovery.py:48-64`
- `src/comfy_mcp/tools/templates.py:123-132`

What is wrong:

- `discover_custom_node()` fetches `"/workflow_templates"`.
- Current Comfy docs document workflow template discovery on `/api/workflow_templates`.
- The tests only validate the returned shape; they do not assert the actual request path.

Why it matters:

- this can silently zero out the most important modern template source
- if the route is wrong, the template engine falls back to a much smaller built-in library and the product quietly looks older than the ecosystem really is

Fix direction:

- move the template route into the same contract table as the other local/cloud paths
- add a regression test that records the path used
- expose discovery source counts in logs so empty official/custom pulls are visible

External evidence:

- [ComfyUI workflow templates](https://docs.comfy.org/tutorials/workflow_templates)
- [Comfy Cloud workflows](https://docs.comfy.org/cloud/workflows)

### 3. `High` - The WebSocket loop still assumes every incoming frame is JSON text

Repo refs:

- `src/comfy_mcp/events/event_manager.py:70-77`
- `src/comfy_mcp/server.py:115-148`
- `tests/test_event_manager.py:1-137`

What is wrong:

- `_ws_loop()` runs `json.loads(raw_msg)` on every frame and only catches `json.JSONDecodeError`.
- Current Comfy docs describe preview images being delivered as binary WebSocket frames during execution.
- There is no handling for `bytes`, no intentional preview skipping path, and no test for binary frames.

Why it matters:

- this is a protocol-level issue, not a cosmetic one
- a monitor that dies when previews arrive is least reliable exactly when a generation is active
- even if preview support is intentionally deferred, the event loop should survive those frames

Fix direction:

- branch on `isinstance(raw_msg, bytes)`
- either skip binary preview frames safely or parse them into lightweight preview metadata
- catch `UnicodeDecodeError` explicitly
- add a unit test that feeds a binary frame into the loop or dispatch boundary

External evidence:

- [Comfy Cloud workflows](https://docs.comfy.org/cloud/workflows)

### 4. `Medium` - `InstallGraph` still discards non-list feature payloads that `ComfyClient` now preserves

Repo refs:

- `src/comfy_mcp/comfy_client.py:84-88`
- `src/comfy_mcp/install/install_graph.py:72-110`
- `tests/test_route_contracts.py:101-141`

What is wrong:

- `ComfyClient.probe_capabilities()` now keeps object-shaped `features` payloads intact.
- `InstallGraph.refresh()` immediately collapses non-list feature payloads back to `[]`.

Why it matters:

- the install graph is supposed to be the canonical machine snapshot
- once features are discarded there, every downstream subsystem loses that fidelity
- this creates an internal inconsistency: the client knows more than the graph that the rest of the system trusts

Fix direction:

- preserve raw feature payloads in the install graph
- if callers need a list, derive a normalized helper field instead of deleting information
- add an install-graph regression test for object-shaped features

### 5. `Medium` - `subscribe` / `unsubscribe` are still mostly symbolic for MCP clients

Repo refs:

- `src/comfy_mcp/tools/monitoring.py:58-98`
- `src/comfy_mcp/events/event_manager.py:118-132`
- `src/comfy_mcp/events/event_manager.py:163-173`

What is wrong:

- `comfy_subscribe()` calls `event_mgr.subscribe(event_type)` without a callback or handle
- `EventManager.subscribe()` only changes behavior if a callback is supplied
- the agent still reads the same event buffer regardless of whether it "subscribed"

Why it matters:

- the tool names imply durable event semantics that do not really exist
- this is a trust issue more than a crash issue
- it also blocks a clean future path to real stream subscriptions

Fix direction:

- either remove the tools and keep polling-based semantics only
- or redesign them around subscription IDs, event cursors, and durable streams

### 6. `Medium` - Registry compatibility is still over-optimistic

Repo refs:

- `src/comfy_mcp/registry/resolver.py:65-72`
- `src/comfy_mcp/tools/registry.py:149-173`
- `tests/test_tools_registry.py:60-67`

What is wrong:

- `RegistryResolver` hardcodes `"compatible": True`
- `comfy_check_compatibility()` only checks ComfyUI version and OS
- it does not check Python requirements, package conflicts, missing transitive dependencies, or node overlap against the install graph

Why it matters:

- the word "compatible" reads much stronger than the implementation
- agents may confidently recommend installs that are only loosely screened

Fix direction:

- rename the current tool result to something like `basic_compatibility`
- or implement a real compat pass using registry metadata plus install graph data
- add warnings when compatibility is unknown rather than marking it as true

External evidence:

- [ComfyUI registry publishing](https://docs.comfy.org/registry/publishing)

### 7. `Low` - Docs and template caches still use non-atomic writes

Repo refs:

- `src/comfy_mcp/docs/store.py:51-54`
- `src/comfy_mcp/docs/store.py:60-74`
- `src/comfy_mcp/docs/store.py:134-165`
- `src/comfy_mcp/templates/index.py:53-69`
- `src/comfy_mcp/install/install_graph.py:187-198`

What is wrong:

- `DocsStore` and `TemplateIndex` write manifests and indexes with plain `write_text()`
- meanwhile `InstallGraph.save_to_disk()` already uses `atomic_write()`

Why it matters:

- cache corruption on interruption is still possible
- it is inconsistent with the more careful write path already present elsewhere in the repo

Fix direction:

- reuse `comfy_mcp.knowledge.store.atomic_write()` for docs/template manifests and indexes

### 8. `Medium` - The fallback builder is still anchored to older ComfyUI defaults

Repo refs:

- `src/comfy_mcp/tools/builder.py:18-401`
- `src/comfy_mcp/tools/builder.py:438-479`
- `README.md:117-124`
- `README.md:233-236`

What is wrong:

- the repo now has template fallthrough, which is a good move
- but the built-in fallback workflows still center on:
  - SD1.5-style defaults
  - `512x512`
  - legacy ControlNet assumptions
  - a narrow set of five workflow families
- the README also still says UI workflow JSON import is "Not yet"

Why it matters:

- current ComfyUI has moved toward richer official templates, workflow JSON v3, subgraphs, V3 migration, and broader model families
- a local-first MCP that still falls back to old hardcoded graphs will feel outdated even when the rest of the repo is modernizing

Fix direction:

- make the builder template-first, with the hardcoded graphs as true last-resort fallback
- add family-aware starter profiles for SDXL, FLUX, and current video-capable template families
- add a UI-export-to-API import assistant or translator
- teach the builder to compose from subgraphs rather than only monolithic templates

External evidence:

- [ComfyUI workflow templates](https://docs.comfy.org/tutorials/workflow_templates)
- [ComfyUI workflow JSON v3 spec](https://docs.comfy.org/specs/workflow_json_v3)
- [ComfyUI subgraphs](https://docs.comfy.org/tutorials/using-subgraphs)
- [ComfyUI V3 migration](https://docs.comfy.org/custom-nodes/v3_migration)
- [Official workflow template repo](https://github.com/Comfy-Org/workflow_templates)
- [ComfyUI issue: workflow API format confusion](https://github.com/comfyanonymous/ComfyUI/issues/1112)
- [ComfyUI discussion: API format / workflow conversion pain](https://github.com/comfyanonymous/ComfyUI/discussions/3717)

### 9. `Low` - Fresh-checkout test ergonomics are weaker than the repo now deserves

Repo refs:

- `README.md:244-249`
- `pyproject.toml:18-22`

What is wrong:

- the runtime setup is clear
- contributor test setup is less clear, because the test suite needs the `dev` extra but the obvious fresh-checkout path does not call that out

Why it matters:

- the bigger and better the suite gets, the more important it is that contributors can run it cleanly on first try

Fix direction:

- add a short contributing section:
  - `uv sync --extra dev`
  - `uv run pytest -q`
- or add a single `make test` / `just test` entry point

## Coverage Blind Spots Worth Fixing Next

- no binary-frame WebSocket regression test
- no cloud route tests for `prompt`, `queue`, `history`, or `object_info`
- no template route contract test for `workflow_templates`
- no install-graph regression test for object-shaped `features`

## Good News

The repo is much better than it was in the previous audit.

Already-fixed improvements that deserve credit:

- queue-truth interrupt handling
- non-destructive dynamics inspection
- better route branching for `features` and `extensions`
- template fallthrough instead of hardcoded-only builder logic
- a much larger and more useful regression suite

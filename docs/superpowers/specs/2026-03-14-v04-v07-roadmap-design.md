# ComfyPilot v0.4–v0.7 Roadmap Design Spec

## Overview

Four versions building ComfyPilot's knowledge layers from official documentation through registry integration. Each version is independently shippable and builds on the previous.

**Architecture principle:** Five Truth Layers
1. Live Runtime (v0.1–v0.3) — `/object_info`, system stats, queue state
2. Installed Environment (v0.3) — install graph, model resolver
3. Official Platform (v0.4) — ComfyUI documentation, guides
4. Registry/Package (v0.7) — custom node package metadata
5. Learned Local (v0.2+) — technique memory, user preferences

**Dependency chain:**
```
v0.4 (Docs) → standalone
v0.5 (Templates) → uses v0.4 docs for scoring context
v0.6 (Persist) → unifies v0.4 + v0.5 caches, adds install graph disk cache
v0.7 (Registry) → uses v0.6 persistence, enhances v0.3 compat engine
```

**Tool count progression (deltas):** +5 → +6 → +5 → +5 = +21 total

---

## v0.3 Baseline (Starting Point)

This spec assumes the following v0.3 state as its foundation:

- **71 tools** across 14 modules (system, models, workflow, nodes, images, history, monitoring, snapshots, memory, safety, builder, output_routing, install, compat)
- **7 MCP resources** (system/info, server/capabilities, nodes/catalog, models/{folder}, embeddings, install/graph, knowledge/status)
- **387 tests** across 33 test files

**Install Graph** (`src/comfy_mcp/install/install_graph.py`):
- `InstallGraph` class with `refresh()`, `summary()`, `has_node()`, `is_stale()`, `hashes` property
- Snapshot contains: `node_classes` (set), `models` (dict by folder), `embeddings` (list), `object_info` (dict), `system` (dict), `hashes` (dict of SHA-256 prefixes)
- Pure in-memory, refreshed from ComfyUI HTTP endpoints

**Model Resolver** (`src/comfy_mcp/install/model_resolver.py`):
- `ModelResolver` class with `resolve(name, folder)`, `resolve_embedding(name)`, `resolve_all(refs)`
- Exact match first, then substring match across folders

**Compatibility Engine** (`src/comfy_mcp/compat/engine.py`):
- 3-pass: structural → schema → environment
- `run_preflight(workflow, snapshot)` returns `{"status": "verified"|"likely"|"blocked", "confidence": float, "errors": [], "warnings": [], "missing_nodes": [], "missing_models": []}`
- `missing_nodes` is currently a flat list of class name strings

**Technique Store** (`src/comfy_mcp/tools/memory.py`):
- Hybrid disk+RAM at `~/.comfypilot/techniques/`
- Individual JSON files per technique

---

## v0.4 — Docs Engine (Layer 3: Official Platform Knowledge)

### Goal
Give the agent the ability to answer "how does node X work?" using official ComfyUI documentation instead of hallucination.

### Data Sources

| Source | Content | Fetch Method |
|--------|---------|-------------|
| `/object_info` (live) | Node input/output schemas, enum values | Already consumed by install graph |
| `embedded-docs` repo | Per-node markdown (descriptions, usage notes, tips) | HTTP fetch from Comfy-Org/embedded-docs |
| `llms-full.txt` | ~80K word complete doc dump (concepts, guides, best practices) | HTTP fetch |

**Note:** The embedded-docs repo structure must be verified during implementation. The fetcher's URL construction assumes one markdown file per node class, but the actual repo may use different naming conventions or directory layouts. Build the fetcher with a configurable URL pattern.

### Storage

```
~/.comfypilot/docs/
├── embedded/          # Per-node markdown files (sanitized filenames)
├── llms-full.txt      # Cached full doc dump
├── sections.json      # Pre-built section index for llms-full.txt (parsed at cache time)
└── manifest.json      # Content hashes + fetch timestamps
```

**Filename sanitization:** Node class names may contain `+`, parentheses, or other filesystem-unsafe characters. The store must sanitize class names to safe filenames (e.g., URL-encode or replace unsafe chars with `_`) and maintain a lookup map from class name to filename.

### Fetching Strategy
- Lazy on first access, then cached
- `comfy_refresh_docs` forces re-fetch
- Hash-based staleness (same pattern as install graph)

### Failure Modes
- **Embedded-docs source unavailable:** Fall back to object_info-only docs (schema without descriptions). Return partial result with a warning that rich docs are unavailable.
- **llms-full.txt unavailable:** Guide search returns empty results with a warning. Node docs still work via embedded-docs + object_info.
- **No network on first run:** All doc tools return "docs not cached yet, run comfy_refresh_docs when network is available." Tools do not crash.
- **Node class has no embedded doc:** Return object_info schema only (inputs, outputs, enums) with a note that no extended documentation exists.
- **URL structure changes:** Fetcher logs the HTTP error and marks the source as unavailable. Does not retry indefinitely.

### Section Indexing for llms-full.txt
The `store.py` module parses `llms-full.txt` into sections at cache time (splitting on markdown headings) and writes `sections.json` — a list of `{title, start_line, end_line, heading_level}` entries. `comfy_get_guide` searches this index by topic, then reads the relevant line range. This avoids loading ~80K words into memory on every query.

### New Package: `src/comfy_mcp/docs/`

| Module | Responsibility |
|--------|---------------|
| `fetcher.py` | HTTP fetch from embedded-docs repo and llms-full.txt source, with graceful degradation on failure |
| `index.py` | Search and lookup by node class name, full-text search across cached docs, section-based guide lookup |
| `store.py` | Disk cache management, hash computation, staleness checks, filename sanitization, section indexing |

### Tools (+5)

| Tool | Signature | Purpose |
|------|-----------|---------|
| `comfy_get_node_docs` | `(class_name: str)` | Get docs for a specific node (embedded-docs + object_info merged) |
| `comfy_search_docs` | `(query: str, limit: int = 10)` | Full-text search across all cached documentation |
| `comfy_get_guide` | `(topic: str)` | Retrieve a concept/guide section from llms-full.txt via section index |
| `comfy_refresh_docs` | `()` | Re-fetch all doc sources and rebuild cache |
| `comfy_docs_status` | `()` | Cache freshness, source availability, content hashes |

### Resources (+1)

| URI | Purpose |
|-----|---------|
| `comfy://docs/status` | Cache freshness + content hashes |

### Data Flow

```
comfy_get_node_docs("KSampler")
  → Check ~/.comfypilot/docs/embedded/<sanitized_name>.md (cache hit?)
  → If miss: fetch from embedded-docs source, cache locally
  → If fetch fails: fall back to object_info-only
  → Merge with /object_info schema (input types, output types, enums)
  → Return unified doc: description + schema + usage notes
```

### Integration Points
- Install graph's `object_info` provides the schema layer
- Docs engine adds the human-readable layer on top
- Technique memory can reference doc sections

### Test Coverage Target
- ~15–20 new tests
- Fetcher: mock HTTP responses, test cache hit/miss, test hash computation, test graceful degradation on HTTP errors
- Index: test lookup by class name, full-text search ranking, test section-based guide lookup
- Store: test staleness detection, cache clear, manifest integrity, test filename sanitization for unsafe characters
- Tools: test end-to-end via mock context

---

## v0.5 — Template Engine (Smart Workflow Construction)

### Goal
Replace hardcoded workflow templates with discovery + scoring + instantiation using official templates, custom node examples, and installed models.

**Deliberate scoping note:** The v0.3 blueprint proposed "learned templates" (patterns extracted from successful runs) as a fourth source. This is intentionally deferred — technique memory already captures workflow patterns, and auto-extraction from run history adds complexity without clear value until the other three sources are proven.

### Data Sources

| Source | Content | Fetch Method |
|--------|---------|-------------|
| Official templates | ~96 templates with category metadata | `GET /templates/index.json` from ComfyUI server |
| Custom node examples | Example workflows from installed custom nodes | `GET /workflow_templates` endpoint |
| Built-in templates | Existing txt2img/img2img/upscale/inpaint/controlnet | Migrated from hardcoded to files |

### Storage

```
~/.comfypilot/templates/
├── official/          # Cached official templates (JSON workflow files)
├── custom_node/       # Cached custom node example workflows
├── builtin/           # Existing templates migrated from hardcoded
├── index.json         # Unified index with metadata, tags, categories, model requirements
└── manifest.json      # Content hashes + fetch timestamps
```

### Three-Phase Pipeline

```
DISCOVER → SCORE → INSTANTIATE
```

1. **Discover** — Scan all three sources, build unified index with metadata (name, description, tags, category, required models, required nodes)
2. **Score** — Rank templates by relevance to a natural language query using tag matching + category matching + model/node compatibility
3. **Instantiate** — Substitute model references with installed models (via ModelResolver), validate with compat engine, return ready-to-queue workflow

### Scoring Algorithm

```
score = (0.3 * tag_overlap_ratio)
      + (0.2 * category_match)
      + (0.3 * models_available_ratio)
      + (0.2 * nodes_available_ratio)
```

Initial weights are hardcoded defaults (0.3/0.2/0.3/0.2). These may be tuned based on usage — the weights are defined as constants in `scorer.py`, not buried in logic.

- Templates with all required models AND nodes installed get a compatibility boost
- Templates requiring missing nodes get penalized but still shown (with warnings)
- **Source precedence as tiebreaker:** When two templates have equal scores, prefer official > custom_node > builtin. This prevents custom node examples from shadowing official templates at the same relevance level.

### Model Substitution Logic

1. Check exact match against installed models
2. If miss, check if template specifies a model category (e.g., "any SD1.5 checkpoint")
3. If category match, pick first alphabetically among installed models in that category (deterministic default; user can override via `overrides` parameter)
4. If no match, flag as warning — let user choose

### Template Override Semantics

`comfy_instantiate_template(template_id, overrides)` accepts an optional `overrides` dict where:
- **Keys** are template parameter slot names (e.g., `"checkpoint"`, `"lora"`, `"width"`, `"height"`, `"positive_prompt"`)
- **Values** are the substitution values (model filenames, dimensions, prompt strings)
- Overrides take precedence over automatic model substitution
- Unknown keys are ignored with a warning in the response
- Override values are validated against the compat engine (e.g., a model override must be an installed model)

### New Package: `src/comfy_mcp/templates/`

| Module | Responsibility |
|--------|---------------|
| `discovery.py` | Fetch + scan all three template sources |
| `index.py` | Unified index builder with metadata extraction |
| `scorer.py` | Relevance ranking given a query + installed environment |
| `instantiator.py` | Model substitution + compat validation + ready workflow output |

### Tools (+6)

| Tool | Signature | Purpose |
|------|-----------|---------|
| `comfy_discover_templates` | `()` | Scan all sources, rebuild unified template index |
| `comfy_search_templates` | `(query: str, tags: list[str] = None, category: str = None, limit: int = 10)` | Search templates — returns scored results |
| `comfy_get_template` | `(template_id: str)` | Full template details + metadata + model requirements |
| `comfy_instantiate_template` | `(template_id: str, overrides: dict = None)` | Instantiate with model substitution, return ready workflow |
| `comfy_list_template_categories` | `()` | List all available template categories |
| `comfy_template_status` | `()` | Cache freshness, source counts, index stats |

### Resources (+1)

| URI | Purpose |
|-----|---------|
| `comfy://templates/index` | Template index summary (counts per source, categories) |

### Migration Path for Existing Builder
- `comfy_build_workflow` stays as-is (no breaking changes)
- Internally gains a template fallthrough: if a matching official/custom template exists with better coverage, use that; otherwise fall back to current hardcoded builder logic

### Modifications to Existing Code
- `src/comfy_mcp/tools/builder.py` — add template fallthrough path (non-breaking)

### Integration Points
- Install graph → ModelResolver for model substitution
- Compat engine → validates instantiated workflows
- Docs engine (v0.4) → future enhancement: tag expansion could use doc index for synonym resolution (not in v0.5 scope — v0.5 uses literal tag matching only)

### Test Coverage Target
- ~20–25 new tests
- Discovery: mock HTTP responses for official/custom sources
- Scorer: test ranking with various query/tag combinations, test compatibility boost, test source precedence tiebreaker
- Instantiator: test model substitution (exact, category, missing), test override semantics, test compat validation pass-through
- Tools: end-to-end via mock context

---

## v0.6 — Persistent Knowledge (Unified Storage Layer)

### Goal
Unify all disk caches into a coherent persistence layer so docs, templates, install graph, and user preferences all survive restarts and follow the same patterns.

### The Problem
By v0.5, we have three independent disk caches (techniques, docs, templates) each with their own manifest/hash/staleness logic. Install graph is still pure in-memory. User preferences are env-vars only.

### Directory Structure After v0.6

```
~/.comfypilot/
├── config.json              # NEW: user preferences
├── state.json               # NEW: unified staleness manifest
├── techniques/              # EXISTS: technique memory (unchanged)
├── docs/                    # EXISTS from v0.4
│   ├── embedded/
│   ├── llms-full.txt
│   └── sections.json
├── templates/               # EXISTS from v0.5
│   ├── official/
│   ├── custom_node/
│   └── builtin/
└── cache/                   # NEW: install graph disk cache
    └── install_graph.json
```

### Core Pattern: `KnowledgeStore`

Not a framework or base class. A duck-typed interface that each subsystem implements:

```python
class KnowledgeStore:
    """Pattern for any subsystem that caches data to ~/.comfypilot/"""

    def __init__(self, subdir: str):
        self.root = Path.home() / ".comfypilot" / subdir

    async def refresh(self) -> dict        # re-fetch from source
    def is_stale(self, max_age: float) -> bool   # staleness check
    def content_hash(self) -> str          # SHA-256 prefix for change detection
    def summary(self) -> dict              # compact status
    def clear(self) -> None                # wipe cached data
```

### Migration Table

| Subsystem | Before v0.6 | After v0.6 |
|-----------|-------------|------------|
| Techniques | `~/.comfypilot/techniques/` | Gains KnowledgeStore interface, no behavior change |
| Docs cache | Own `manifest.json` | Manifest migrated to unified `state.json` |
| Template cache | Own `manifest.json` | Manifest migrated to unified `state.json` |
| Install graph | Pure in-memory | Cached to `~/.comfypilot/cache/install_graph.json`, loaded on startup |
| Safety thresholds | Env vars only | Persisted in `config.json`, env vars override |
| Workflow snapshots | In-memory LRU | **Stays in-memory** (intentionally session-scoped) |

### Migration Safety

When migrating per-subsystem `manifest.json` files to unified `state.json`:
- Original manifest files are kept as backups (renamed to `manifest.json.bak`) during migration
- If `state.json` is corrupted or unparseable, all subsystems treat their caches as stale and trigger a clean rebuild — no crash, just a slower startup
- Migration is idempotent: running it twice produces the same result

### Config Schema

```json
{
  "safety": {
    "vram_warn_pct": 80,
    "vram_block_pct": 95,
    "max_queue_size": 10
  },
  "output": {
    "default_dir": "~/comfypilot_output"
  },
  "cache": {
    "max_age_seconds": 300,
    "auto_refresh": true
  }
}
```

Env vars always override config.json (backwards compatible). Integration-specific output paths (TouchDesigner, Blender) remain as env vars only — they belong to their respective output routing modules, not the core config.

**Atomic writes:** Both `config.json` and `state.json` use write-to-temp-then-rename to prevent corruption from concurrent writes or crashes mid-write.

### Startup Behavior Change

**Before (v0.3–v0.5):**
```
lifespan → connect client → refresh install graph (HTTP) → start event manager
```

**After (v0.6):**
```
lifespan → connect client → load install graph from disk cache
  → if stale: schedule background refresh task
  → if fresh: use cached, skip HTTP
  → load docs/template indexes from disk
  → start event manager
```

**Background refresh concurrency:** The background refresh builds a complete new snapshot, then atomically swaps the reference (`self._snapshot = new_snapshot`). Tools reading the install graph during refresh see the old (stale but valid) snapshot until the swap completes. No locks needed — Python's GIL makes reference assignment atomic.

Faster startup when caches are warm.

### New Package: `src/comfy_mcp/knowledge/`

| Module | Responsibility |
|--------|---------------|
| `store.py` | KnowledgeStore base pattern |
| `config.py` | Config read/write with env var override, atomic file writes |
| `manager.py` | Unified staleness tracking, refresh orchestration, state.json management |

### Tools (+5)

| Tool | Signature | Purpose |
|------|-----------|---------|
| `comfy_knowledge_status` | `()` | Unified view of all subsystem staleness, hashes, cache sizes |
| `comfy_refresh_all` | `()` | Refresh all knowledge stores |
| `comfy_clear_cache` | `(subsystem: str = "all")` | Clear specific or all cached data |
| `comfy_get_config` | `(key: str = None)` | Read persisted user preferences |
| `comfy_set_config` | `(key: str, value: Any)` | Write persisted user preferences |

### Resources (+1)

| URI | Purpose |
|-----|---------|
| `comfy://knowledge/full` | Complete knowledge status across all subsystems (replaces v0.3's `comfy://knowledge/status`) |

### Modifications to Existing Code
- `src/comfy_mcp/install/install_graph.py` — add disk cache load/save, atomic snapshot swap for background refresh
- `src/comfy_mcp/docs/store.py` — migrate manifest to unified state.json
- `src/comfy_mcp/templates/index.py` — migrate manifest to unified state.json
- `src/comfy_mcp/server.py` — startup uses disk cache, background refresh

### Integration Points
- Every subsystem gets KnowledgeStore interface (non-breaking retrofit)
- `comfy_knowledge_status` becomes the single health check for the entire knowledge pipeline

### Test Coverage Target
- ~20–25 new tests
- KnowledgeStore: test interface compliance for each subsystem
- Config: test read/write, env var override, default values, atomic write safety
- Manager: test unified refresh, staleness aggregation, state.json integrity, test corruption recovery
- Install graph cache: test disk save/load, staleness detection, background refresh with atomic swap
- Migration: test manifest.json → state.json migration, test idempotency, test backup creation
- Tools: end-to-end via mock context

---

## v0.7 — Registry Integration (Layer 4: Package Metadata)

### Goal
When a workflow uses a missing node, resolve it to the exact package, version, and install command. Transform compat engine errors into actionable resolution.

### Data Source

ComfyUI Registry API at `https://api.comfy.org` (public, no auth for reads).

**API versioning note:** The registry API does not currently use URL path versioning (`/v1/`, `/v2/`). The client should include a `User-Agent: ComfyPilot/0.7` header and handle HTTP 410 Gone responses gracefully (treat as "endpoint deprecated, clear cache for that endpoint").

### Key API Endpoints Used

| Endpoint | Purpose in ComfyPilot |
|----------|----------------------|
| `GET /comfy-nodes/{className}/node` | **Reverse lookup** — node class → package (critical!) |
| `GET /nodes` | Search/browse packages |
| `GET /nodes/{nodeId}` | Full package metadata |
| `GET /nodes/{nodeId}/versions` | Version history |
| `GET /nodes/{nodeId}/versions/{v}/comfy-nodes` | All node classes in a package version |
| `POST /bulk/nodes/versions` | Batch resolve |

### Storage

```
~/.comfypilot/cache/registry/
├── node_class_index.json    # Reverse lookup cache (class name → package, includes negative entries)
└── packages/                # Cached package metadata (one JSON per package ID)
```

Unified staleness via `state.json` (v0.6 pattern).

### Three Capabilities

```
RESOLVE → SUGGEST → BROWSE
```

1. **Resolve** — Given missing node class names (from compat engine), batch-lookup which packages provide them
2. **Suggest** — Generate actionable install commands with compatibility checks (OS, GPU, ComfyUI version)
3. **Browse** — Search/explore the registry for discovery

### Registry Client: `src/comfy_mcp/registry/client.py`

```python
class RegistryClient:
    BASE = "https://api.comfy.org"

    async def search_nodes(self, query, page, limit, **filters) -> dict
    async def get_node(self, node_id: str) -> dict
    async def get_versions(self, node_id: str) -> list
    async def get_comfy_nodes(self, node_id: str, version: str) -> list
    async def reverse_lookup(self, class_name: str) -> dict | None
    async def bulk_resolve(self, pairs: list[dict]) -> dict
    async def get_install_url(self, node_id: str, version: str = None) -> str
```

Uses httpx with connection pooling (same `User-Agent` header as ComfyClient). All responses cached locally.

### Rate Limiting Strategy

- Honor `Retry-After` headers from the API
- Implement exponential backoff on 429/5xx responses (initial 1s, max 30s, 3 retries)
- Prefer `POST /bulk/nodes/versions` over individual lookups when resolving 3+ missing nodes simultaneously
- Local request throttle: max 10 requests/second to the registry API

### Reverse Lookup Index Strategy

Lazy incremental population (no bulk pre-fetch):

```
Missing node encountered → check local index
  → hit (positive): instant resolution with cached package info
  → hit (negative): instant "not in registry" response (no HTTP request)
  → miss: GET /comfy-nodes/{className}/node → cache result → return
```

**Negative caching:** When the registry returns no result for a node class (404), cache it as `{"class": "ClassName", "package": null, "cached_at": timestamp}`. Negative entries expire after 24 hours (the package may be published later). This prevents repeated HTTP requests for node classes from unpublished/private custom nodes.

### Compatibility Filtering

When suggesting a package, check against user's environment (from install graph):
- **OS:** `supported_os` vs detected platform
- **GPU:** `supported_accelerators` vs detected GPU
- **ComfyUI version:** `supported_comfyui_version` vs installed version
- **Node conflicts:** `preempted_comfy_node_names` — packages that override core nodes

Incompatible packages still shown with clear warnings.

### Compat Engine Enhancement

**Before (v0.3):**
```json
{
  "status": "blocked",
  "missing_nodes": ["ADE_AnimateDiffLoaderWithContext", "ADE_NoiseLayerAdd"],
  "errors": ["Node ADE_AnimateDiffLoaderWithContext not installed"]
}
```

**After (v0.7):**
```json
{
  "status": "blocked",
  "missing_nodes": [
    {
      "class": "ADE_AnimateDiffLoaderWithContext",
      "package": "comfyui-animatediff-evolved",
      "latest_version": "1.2.3",
      "compatible": true,
      "install_cmd": "comfy node install comfyui-animatediff-evolved"
    },
    {
      "class": "ADE_NoiseLayerAdd",
      "package": "comfyui-animatediff-evolved",
      "latest_version": "1.2.3",
      "compatible": true,
      "install_cmd": "comfy node install comfyui-animatediff-evolved",
      "note": "Same package as ADE_AnimateDiffLoaderWithContext"
    }
  ],
  "resolution": "Install 1 package to resolve all 2 missing nodes"
}
```

When registry lookup returns no result for a node class, the entry shows `"package": null, "note": "Not found in registry — may be a local/private custom node"`.

Deduplicates — multiple missing nodes from the same package produce one install suggestion.

### New Package: `src/comfy_mcp/registry/`

| Module | Responsibility |
|--------|---------------|
| `client.py` | Async HTTP client for api.comfy.org with rate limiting and retry logic |
| `index.py` | Reverse lookup cache with positive and negative entries |
| `resolver.py` | Missing node → package resolution + compatibility checking + deduplication |

### Tools (+5)

| Tool | Signature | Purpose |
|------|-----------|---------|
| `comfy_search_registry` | `(query: str, tags: list[str] = None, limit: int = 10)` | Search registry packages |
| `comfy_get_package` | `(package_id: str)` | Full package metadata (versions, deps, compatibility) |
| `comfy_resolve_missing` | `(workflow: dict = None, node_classes: list[str] = None)` | Resolve missing nodes to packages |
| `comfy_check_compatibility` | `(package_id: str)` | Check package compatibility with user's environment |
| `comfy_registry_status` | `()` | Cache stats, index size, last sync |

### Resources (+1)

| URI | Purpose |
|-----|---------|
| `comfy://registry/status` | Registry cache stats + index coverage |

### Design Constraints
- **No auto-installation.** ComfyPilot tells the user what to install, not does it for them.
- **No auth.** All registry reads are public.
- **No full mirror.** Lazy incremental caching only.

### Modifications to Existing Code
- `src/comfy_mcp/compat/engine.py` — enhance missing node errors with package resolution
- `src/comfy_mcp/compat/environment.py` — pass-through registry data in results

### Integration Points
- Compat engine (v0.3) → enhanced with package resolution
- Install graph (v0.3) → OS, GPU, version for compatibility filtering
- Knowledge store (v0.6) → registry cache follows KnowledgeStore pattern
- Docs engine (v0.4) → package descriptions supplement node docs
- Template engine (v0.5) → template model requirements checked against registry

### Test Coverage Target
- ~20–25 new tests
- Client: mock HTTP responses for all endpoints, test rate limiting, test retry logic, test User-Agent header
- Index: test lazy population, cache hit/miss, incremental build, test negative caching and expiry
- Resolver: test single/batch resolution, deduplication, compatibility filtering, test "not in registry" handling
- Compat enhancement: test enriched error output format, test null-package entries
- Tools: end-to-end via mock context

---

## Summary

| Version | Feature | New Tools | New Resources | Tests (est.) |
|---------|---------|-----------|---------------|-------------|
| v0.3 (baseline) | Install Graph + Compat Engine | 71 total | 7 total | 387 |
| v0.4 | Docs Engine | +5 | +1 | +15–20 |
| v0.5 | Template Engine | +6 | +1 | +20–25 |
| v0.6 | Persistent Knowledge | +5 | +1 | +20–25 |
| v0.7 | Registry Integration | +5 | +1 | +20–25 |
| **v0.7 final** | | **92 total** | **11 total** | **~460–480** |

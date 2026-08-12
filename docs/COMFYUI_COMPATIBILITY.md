# ComfyUI Compatibility Audit

ComfyPilot 1.9.0 is tested against the public API contracts of ComfyUI 0.20.0
through 0.31.1. The minimum remains 0.20.0; connections outside the audited
range are identified in `comfy://server/capabilities` as `legacy`, `tested`, or
`newer_than_tested`.

## Audit scope and method

The audit compared the official `v0.20.0` and `v0.31.1` tags, every stable tag
between them, official release notes, current `server.py`, `openapi.yaml`, the
V3-to-V1 node serializer, embedded documentation packaging, and job cancellation
tests. That range contains 634 commits and changes 575 files (145,359 insertions
and 13,186 deletions in the tag-to-tag diff).

Primary references:

- [All official ComfyUI releases](https://github.com/Comfy-Org/ComfyUI/releases)
- [ComfyUI v0.31.1](https://github.com/Comfy-Org/ComfyUI/releases/tag/v0.31.1)
- [Official ComfyUI repository](https://github.com/Comfy-Org/ComfyUI)

## Stable release stream reviewed

| Stable line | Release window | API/schema changes relevant to MCP clients | ComfyPilot 1.9.0 action |
|---|---|---|---|
| 0.20.0-0.20.3 | 2026-04-27 to 2026-05-08 | OpenAPI 3.1 source contract, blueprint work, `RANGE` widget, and execution-side cycle enforcement | Retains the 0.20 minimum, RANGE widget parsing, anti-cycle validation, and optional OpenAPI probing |
| 0.21.0-0.21.1 | 2026-05-10 to 2026-05-13 | Prompt metadata gained `workflow_id` and `workflow_version_id`; feature flags became generic; MultiCombo `multi_select` became an object; DynamicCombo and Autogrow schemas expanded; embedded docs advanced | Queue tool now accepts workflow metadata and partial targets; schema normalization recognizes combo/dynamic widget types; docs use the official localized Markdown layout |
| 0.22.0-0.22.3 | 2026-05-20 to 2026-05-27 | Asset response fields changed, old upload/mask paths were deprecated, and a workflow-ID WebSocket change was added then reverted | Avoids dependence on the reverted WS shape and keeps tolerant asset/output handling |
| 0.23.0 | 2026-06-01 | OAuth 2.1 and dynamic client registration specifications, more asset changes, MultiGPU work units, V3 conversion work, and queue-management response cleanup | Auth probing remains profile-based; node conversion is handled at `/object_info`; system capability data is multi-device aware |
| 0.24.0-0.24.1 | 2026-06-03 to 2026-06-04 | Model/node and frontend-package updates continued without removing the legacy queue, history, prompt, object-info, model, or image routes used by ComfyPilot | No route migration required; regression coverage retains the stable legacy surface |
| 0.25.0-0.25.1 | 2026-06-15 to 2026-06-18 | Asset dimensions and cursor pagination, asset IDs in executed WebSocket messages, `Comfy-Usage-Source` forwarding, and `deploy_environment` system data | Sends `Comfy-Usage-Source: comfypilot/<version>` and exposes deployment/package capability metadata |
| 0.26.0-0.26.2 | 2026-06-23 to 2026-06-25 | Added state-aware `POST /api/jobs/{job_id}/cancel` and batch `POST /api/jobs/cancel` | Single and batch cancellation prefer the jobs API; 0.20-0.25 servers fall back to queue delete or interrupt |
| 0.27.0-0.27.1 | 2026-06-30 to 2026-07-08 | Bounding-box canvas/schema additions and opt-in asset hashing | `BOUNDING_BOX` and `BOUNDING_BOXES` are normalized as widgets unless `forceInput` requests a socket |
| 0.28.0-0.28.3 | 2026-07-15 to 2026-07-22 | Security fixes, extension filtering for model experiments, and job fixes for cached outputs | No unsafe preview assumptions; jobs are consumed as server records rather than reconstructed client-side |
| 0.29.0-0.29.2 | 2026-07-28 to 2026-07-31 | ComfyUI job IDs began flowing into partner-request headers | Stable prompt/job IDs are preserved throughout job inspection and cancellation |
| 0.30.0-0.30.2 | 2026-08-02 to 2026-08-05 | Job previews prefer media assets; SVG/XSS preview hardening and dataset-folder security fixes | Image retrieval keeps using server-provided metadata and does not evaluate SVG or HTML payloads |
| 0.31.0-0.31.1 | 2026-08-07 to 2026-08-08 | Combo/schema hardening plus model additions and retirements | Combo/widget normalization is explicit and deprecated/experimental/dev/API node metadata is retained |

Patch releases in each line were also diffed. They mostly contain corrective
model, node, frontend-package, execution, or security changes; no patch release
removed the core routes listed below.

## Endpoint contract after the audit

| Purpose | Preferred route | Compatibility behavior |
|---|---|---|
| Queue prompt | `POST /prompt` | Adds optional workflow/version metadata, partial execution targets, and extra data without changing the historical default body |
| Queue snapshot | `GET /queue` | Retained for all audited versions |
| Job list/detail | `GET /api/jobs`, `GET /api/jobs/{id}` | Canonical from 0.20; detail falls back to `/history/{id}` |
| Cancel one/many | `POST /api/jobs/{id}/cancel`, `POST /api/jobs/cancel` | Preferred from 0.26; older servers use `/interrupt` for a running ID or `/queue` delete for a pending ID |
| Node catalog | `GET /object_info` | Handles legacy nodes and the V3 serializer's V1 tuple output |
| Native subgraphs | `GET /global_subgraphs` | Normalizes the official ID-keyed object; older list-shaped fork routes remain fallbacks |
| Embedded node docs | `GET /docs/{class}/en.md` | Reads official localized Markdown; structured JSON fork routes and object-info descriptions remain fallbacks |
| System data | `GET /system_stats`, `GET /features` | Handles nullable device indices, multiple devices, package versions, deployment environment, and generic feature maps |
| OpenAPI | deployment-dependent `/openapi.json` | Probed and ingested when served; the local 0.31.1 backend contains `openapi.yaml` but does not guarantee this HTTP route |

Local and cloud jobs APIs currently use different sort spellings. ComfyPilot
normalizes `create_time`/`execution_time` to local
`created_at`/`execution_duration`, and performs the reverse mapping for the
official cloud host. Cursor `after` is sent only to cloud; local servers remain
offset-paginated through 0.31.1.

## Node schema coverage

ComfyUI's current V3 node classes are converted into a V1-compatible
`/object_info` representation. Treating every non-primitive type as a socket is
therefore incorrect. ComfyPilot 1.9.0 recognizes these widget/dynamic types:

`COMBO`, `WEBCAM`, `IMAGECOMPARE`, `COLOR`, `COLORS`, `BOUNDING_BOX`,
`BOUNDING_BOXES`, `CURVE`, `RANGE`, `COMFY_AUTOGROW_V3`,
`COMFY_DYNAMICCOMBO_V3`, and `COMFY_DYNAMICSLOT_V3`.

`forceInput: true` overrides widget inference and creates a link target;
`socketless: true` forces widget treatment. The normalized schema also retains:

- output list flags, tooltips, and match types;
- display name and Python module;
- deprecated, experimental, dev-only, API-node, and intermediate-output flags;
- search aliases, essentials category, and price-badge metadata.

## Compatibility policy

- Minimum supported: ComfyUI 0.20.0.
- Fully audited/tested maximum: ComfyUI 0.31.1.
- Newer versions are allowed but visibly reported as `newer_than_tested`.
- Missing modern endpoints degrade to audited legacy routes rather than failing
  the entire MCP connection.
- Optional or deployment-specific features, especially HTTP OpenAPI serving,
  are capability-probed and never assumed from version alone.

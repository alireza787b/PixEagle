# PixEagle Agent Context

This directory contains machine-readable context for reviewer workflows and
future MCP/AI-agent integration.

## Current Boundary

PixEagle does not expose a callable MCP tool registry in this slice. Generated
files under `generated/` are non-callable review artifacts only:

- they are candidate inventory only, not MCP execution;
- they are not `tools/list`;
- they are not a runtime automation surface;
- they are not permission for an AI agent or client to execute a route;
- they do not prove PX4, SITL, HIL, field, tracker, follower, or real-aircraft
  success.

The current candidate inventory is:

- `generated/pixeagle-openapi-tool-candidates.yaml`

It is generated from the static route surface in
`src/classes/fastapi_handler.py` plus the typed `/api/v1` route registry in
`src/classes/fastapi_api_v1_routes.py`. The inventory also records source
hashes for `src/classes/api_v1_contracts.py`, which owns the typed `/api/v1`
Pydantic contracts and error-response metadata, and
`src/classes/api_v1_paths.py`, which owns the typed route path constants parsed
by the registry. It also records the source hash for
`src/classes/api_v1_actions.py`, which owns process-local action resources,
idempotency replay, guarded action route execution, action resource lookup, and
legacy action audit behavior for guarded action candidates. It also records
`src/classes/api_legacy_control_routes.py`, which owns the internal Offboard
start/stop and operator-cancel compatibility executors used by guarded typed
action candidates after the former `/commands/*` HTTP aliases were retired.
It also records
`src/classes/api_v1_read_routes.py`, which owns typed read-route error
boundaries for reviewed process-local status/telemetry/media-health candidates.
It also records `src/classes/api_legacy_config_sync.py`,
`src/classes/api_legacy_config_routes.py`,
`src/classes/api_legacy_follower_routes.py`,
`src/classes/api_legacy_gstreamer_routes.py`,
`src/classes/api_legacy_media_routes.py`,
`src/classes/api_legacy_model_routes.py`,
`src/classes/api_legacy_osd_routes.py`,
`src/classes/api_legacy_recording_routes.py`, and
`src/classes/api_legacy_safety_routes.py` because those helpers own extracted
legacy compatibility route bodies while typed `/api/v1` replacements and
tracked alias retirement remain in progress. It also records
`src/classes/api_legacy_tracker_routes.py`, which owns legacy tracker selector
available-types, deprecated set-type, and current-config compatibility route
bodies plus tracker schema/output/capabilities/current-status diagnostics until
typed replacements and alias retirement are handled. It also records
`src/classes/api_v1_snapshots.py`, which owns process-local runtime,
following, and tracking snapshot semantics for reviewed read-only candidates,
and `src/classes/api_v1_telemetry.py`, which owns typed MAVLink
telemetry-health manager delegation and fail-closed unavailable fallback
semantics for the telemetry health candidate. It also records
`src/classes/api_v1_streams.py`, which owns typed media transport and
frame-publisher health snapshots for the streams media-health candidate. It
also records
`src/classes/api_v1_sitl.py`, which owns validation-only SITL injection gates,
payload construction, dry-run summaries, and AppController validation-hook
dispatch for blocked validation-stimulus candidates. It also records
`src/classes/api_exposure_policy.py`, `src/classes/api_auth_runtime.py`,
`src/classes/api_security_audit.py`, `src/classes/api_security_types.py`, and
`src/classes/api_security_policy.py`, which own exposure-boundary decisions,
runtime auth decisions, durable security audit events, principal/scope
semantics, and the default-deny route classification that future API/MCP
promotion must pass. These files do not create a runtime MCP surface or callable
tool exposure.

The current review-stage registry and policy are:

- `agent_tools.yaml`
- `agent_policy.yaml`

These files are docs-stage governance artifacts. They classify the seven reviewed
process-local status/telemetry/media-health GET candidates, but they are not loaded by a
runtime executor and they do not create MCP exposure. All entries remain
`callable: false`, `mcp_exposure: none`, and `promotion_status: unpromoted`.
The registry and generated inventory also record `review_disposition` for every
candidate. Valid disposition states are:

- `approved_for_review_only`: reviewed as a docs-stage candidate only; still
  excluded from runtime MCP `tools/list` and `tools/call`.
- `blocked`: not eligible for agent/MCP promotion without a separate design,
  tests, and independent review.
- `deferred`: intentionally postponed to a later validation or safety slice;
  still non-callable and excluded.

Disposition completion is review coverage, not runtime promotion. The policy
denies action tools, SITL injection tools, direct drone/PX4 exposure, OpenAPI
auto-promotion, missing dispositions, and unknown tools by default.

Regenerate or check it with:

```bash
python3 tools/generate_api_tool_candidates.py
python3 tools/generate_api_tool_candidates.py --check
```

## Promotion Path

A route may become an MCP tool only after this full path is complete:

1. FastAPI route
2. generated non-callable candidate
3. curated registry entry
4. policy classification
5. typed input/output contract
6. operator docs and safety notes
7. tests and evals
8. independent reviewer approval
9. MCP `tools/list` and `tools/call` exposure

Auto-generated discovery must never bypass registry, policy, docs, tests, and
review. Control actions, SITL fault injections, config mutation, model upload,
service control, and any future flight-adjacent action need explicit guard
design before they can be considered callable.

Review completeness does not require promotion. Every generated candidate must
have an explicit `approved_for_review_only`, `blocked`, or `deferred`
disposition with owner, rationale, evidence, and next gate; a sensitive GET
route may remain blocked indefinitely. Agent-specific bypass access to
non-PixEagle drone-local HTTP, PX4, MAVSDK, MAVLink2REST, or companion-sidecar
APIs is prohibited; future agents must use the same typed PixEagle API/state
contracts as other consumers. Callable MCP runtime, public web search,
assistant streaming UX, drone-log tools, and action-enabled agents remain
deferred until the typed API migration, authentication boundary, and separate
safety review are complete.

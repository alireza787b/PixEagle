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
`src/classes/api_legacy_control_routes.py`, which owns the legacy Offboard
start/operator-cancel compatibility route bodies that guarded typed action
candidates still delegate through. It also records
`src/classes/api_v1_read_routes.py`, which owns typed read-route error
boundaries for reviewed process-local status/telemetry candidates. It also
records `src/classes/api_v1_snapshots.py`, which owns process-local runtime,
following, and tracking snapshot semantics for reviewed read-only candidates,
and `src/classes/api_v1_telemetry.py`, which owns typed MAVLink
telemetry-health manager delegation and fail-closed unavailable fallback
semantics for the telemetry health candidate. It also records
`src/classes/api_v1_sitl.py`, which owns validation-only SITL injection gates,
payload construction, dry-run summaries, and AppController validation-hook
dispatch for blocked validation-stimulus candidates.

The current review-stage registry and policy are:

- `agent_tools.yaml`
- `agent_policy.yaml`

These files are docs-stage governance artifacts. They classify the six reviewed
process-local status/telemetry GET candidates, but they are not loaded by a
runtime executor and they do not create MCP exposure. All entries remain
`callable: false`, `mcp_exposure: none`, and `promotion_status: unpromoted`.
The policy denies action tools, SITL injection tools, direct drone/PX4 exposure,
OpenAPI auto-promotion, and unknown tools by default.

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

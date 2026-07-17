# Phase 4 API v1 Read Route Boundary Checkpoint

Date: 2026-06-09
Slice: PXE-0060
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: extract typed read-only `/api/v1` route error boundaries from
`FastAPIHandler`.

## Outcome

PXE-0060 is implemented at code, docs, and focused-guardrail level. The typed
read-route error boundaries for runtime status, following status, following
telemetry, MAVLink telemetry health, tracker runtime status, and tracker
telemetry now live in `src/classes/api_v1_read_routes.py`.

`FastAPIHandler` keeps thin route-method wrappers only. This preserves current
route registration, method names, compatibility call sites, and test fixtures
while removing another typed API route body block from the handler monolith.

No public route, route order, handler method name, response model name, request
model name, read-only candidate classification, action confirmation/idempotency/
dry-run policy, legacy action-audit behavior, SITL enablement default, dashboard
route, runtime MCP endpoint, `tools/list`, `tools/call`, callable tool,
PX4/SITL/HIL behavior, service installation, deployment, or field behavior
changed in this slice.

## Files Changed

- `src/classes/api_v1_read_routes.py`
- `src/classes/fastapi_handler.py`
- `tools/generate_api_tool_candidates.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `docs/agent-context/README.md`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## What Changed

- Added `src/classes/api_v1_read_routes.py` for:
  - `get_runtime_status()`;
  - `get_following_status()`;
  - `get_following_telemetry()`;
  - `get_telemetry_health()`;
  - `get_tracking_runtime_status()`;
  - `get_tracking_telemetry()`.
- Updated `FastAPIHandler` so those six route methods are one-call migration
  wrappers that delegate to `api_v1_read_routes.py`.
- Kept snapshot ownership unchanged:
  - runtime/following/tracking snapshots still live in
    `src/classes/api_v1_snapshots.py`;
  - MAVLink telemetry-health manager delegation/fallback payload construction
    still lives in `src/classes/api_v1_telemetry.py`.
- Regenerated
  `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`.
  - `total_declared_http_routes`: 129.
  - `api_v1_routes`: 14.
  - `candidate_count`: 14.
  - `eligible_read_only_candidates`: 6.
  - `blocked_or_guarded_candidates`: 8.
  - `callable_tools`: 0.
  - `mcp_exposed_tools`: 0.
  - Source provenance now includes `src/classes/api_v1_read_routes.py`.
- Extended static tests so:
  - read-route helpers are present in `api_v1_read_routes.py`;
  - handler read-route methods stay one-call wrappers;
  - typed read-route error strings stay out of `fastapi_handler.py`;
  - generated candidate provenance includes the read-route-helper source file.

## Validation

- `.venv/bin/python -m py_compile src/classes/api_v1_read_routes.py src/classes/fastapi_handler.py tools/generate_api_tool_candidates.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py`:
  passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py -q`:
  31 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_app_controller_offboard_safety.py -k "runtime_status or following_status or following_telemetry or telemetry_health or tracking_runtime_status or tracking_telemetry" -q`:
  27 passed, 45 deselected.
- `.venv/bin/python -m py_compile src/classes/api_v1_read_routes.py src/classes/fastapi_handler.py tools/generate_api_tool_candidates.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/unit/core_app/test_app_controller_offboard_safety.py`:
  passed.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`:
  passed.
- `git diff --check`:
  passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_app_controller_offboard_safety.py -k "api_v1 or runtime_status or following_status or following_telemetry or telemetry_health or tracking_runtime_status or tracking_telemetry" -q`:
  38 passed, 34 deselected.
- `PYTHON=.venv/bin/python make phase0-check`:
  schema up to date, candidate inventory current, 56 passed.

## Review

Review focus for this slice:

- route inventory remains unchanged;
- generated agent candidates remain non-callable and unexposed;
- read-only candidate classification remains limited to the six reviewed
  process-local status/telemetry GET routes;
- action/SITL routes remain blocked or guarded;
- moved error boundaries preserve typed `/api/v1` error envelopes;
- no runtime MCP endpoint, executor, `tools/list`, or `tools/call` exists;
- no PX4/SITL/HIL/field success is claimed.

Independent reviewer checks were attempted before commit closure, but both
reviewer agents returned account usage-limit errors before producing findings.
No independent approval is claimed for PXE-0060.

Local recovery review found no blockers:

- `FastAPIHandler` read-route methods are one-call wrappers.
- typed read-route error strings and path constants live in
  `api_v1_read_routes.py`, not `fastapi_handler.py`.
- `get_telemetry_health()` still delegates to the telemetry helper instead of
  rebuilding fallback payloads in the route layer.
- generated candidate inventory still reports 129 declared HTTP routes, 14
  `/api/v1` candidates, six eligible read-only candidates, eight
  blocked/guarded candidates, zero callable tools, and zero MCP-exposed tools.
- no runtime MCP endpoint, executor, `tools/list`, or `tools/call` exists.
- no PX4/SITL/HIL/field success is claimed.

Residuals accepted for later slices:

- `FastAPIHandler` still keeps migration wrappers until route/router extraction
  can remove them safely.
- This is contract/unit evidence only; runtime PX4/SITL/HIL/field validation
  remains operator-gated and artifact-driven.

## Risks And Boundaries

- This is a structural extraction only. It does not add runtime MCP execution,
  durable storage, route removals, dashboard migrations, PX4/SITL execution,
  HIL, field validation, deployment, or service installation.
- The read-only routes remain process-local snapshots. They are not PX4,
  SITL, HIL, field, or vehicle-response proof.
- `FastAPIHandler` still keeps migration wrappers until route/router extraction
  can remove them safely.

## Next Slice

Continue Phase 4 API modernization under PXE-0008. Good next candidates are
extracting remaining route families behind narrower services/routers, designing
durable action/command resources as a safety-reviewed slice, or resuming
companion-runtime reconciliation under PXE-0022. PXE-0021 dashboard toolchain
migration, PXE-0040 Gazebo runtime proof, and PXE-0041 final no-legacy cleanup
remain open.

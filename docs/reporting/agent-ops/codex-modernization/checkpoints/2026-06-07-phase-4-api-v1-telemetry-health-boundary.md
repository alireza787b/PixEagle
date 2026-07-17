# Phase 4 API v1 Telemetry Health Boundary Checkpoint

Date: 2026-06-07
Slice: PXE-0057
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: extract typed `/api/v1/telemetry/health` helper behavior from
`FastAPIHandler`.

## Outcome

PXE-0057 is implemented at code, docs, and focused-guardrail level. The typed
MAVLink telemetry-health manager delegation and fail-closed unavailable fallback
payload now live in `src/classes/api_v1_telemetry.py`.

No public route, route order, handler method name, response model name, request
model name, action confirmation/idempotency/dry-run behavior, SITL injection
gate, dashboard route, runtime MCP endpoint, `tools/list`, `tools/call`,
callable tool, PX4/SITL/HIL behavior, service installation, deployment, or field
behavior changed in this slice.

## Files Changed

- `src/classes/api_v1_telemetry.py`
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

- Added `src/classes/api_v1_telemetry.py` for:
  - `MavlinkDataManager.get_telemetry_health()` delegation;
  - fail-closed unavailable telemetry-health fallback payload construction;
  - MAVLink telemetry-health claim-boundary usage.
- Updated `FastAPIHandler.get_telemetry_health()` so it remains the route error
  boundary while delegating helper behavior to `api_v1_telemetry.py`.
- Extended `tools/generate_api_tool_candidates.py` and regenerated
  `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`.
  - `total_declared_http_routes`: 129.
  - `api_v1_routes`: 14.
  - `candidate_count`: 14.
  - `eligible_read_only_candidates`: 6.
  - `blocked_or_guarded_candidates`: 8.
  - `callable_tools`: 0.
  - `mcp_exposed_tools`: 0.
  - Source provenance now includes `src/classes/api_v1_telemetry.py`.
- Added static tests that prevent:
  - telemetry-health fallback strings and claim-boundary imports drifting back
    into `fastapi_handler.py`;
  - generated candidate provenance omitting the telemetry-helper source file.

## Validation

- `.venv/bin/python -m py_compile src/classes/api_v1_telemetry.py src/classes/fastapi_handler.py tools/generate_api_tool_candidates.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py`:
  passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py -q`:
  29 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_app_controller_offboard_safety.py -k "telemetry_health or api_v1" -q`:
  20 passed, 51 deselected.
- `git diff --check`: passed.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`: passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_app_controller_offboard_safety.py tests/unit/core_app/test_sitl_injection_api.py -k "telemetry_health or api_v1 or sitl" -q`:
  52 passed, 47 deselected.
- `PYTHON=.venv/bin/python make phase0-check`: schema up to date, candidate
  inventory current, 54 passed.

## Review

Review focus for this slice:

- telemetry-health behavior remains unchanged;
- absent MAVLink data manager still returns the same fail-closed unavailable
  fallback payload;
- manager exceptions still return the typed `/api/v1` error envelope through the
  route error boundary;
- generated agent candidates remain non-callable and unexposed;
- no runtime MCP endpoint, executor, `tools/list`, or `tools/call` exists;
- no PX4/SITL/HIL/field success is claimed.

Review completed locally before commit closure because subagent review capacity
was unavailable in the immediately preceding slice:

- API/MCP provenance review: no blockers. Confirmed generated candidate
  provenance includes `src/classes/api_v1_telemetry.py`, `callable_tools` remains
  `0`, `mcp_exposed_tools` remains `0`, and no generated candidate is
  `callable: true`.
- Runtime/API behavior review: no blockers. Confirmed the telemetry claim
  boundary and fail-closed fallback string live only in `api_v1_telemetry.py`,
  `FastAPIHandler.get_telemetry_health()` delegates once to
  `get_telemetry_health_snapshot()`, and manager exceptions still flow through
  the route method's typed `/api/v1` error envelope.

Residuals accepted for later slices:

- The route method remains in `fastapi_handler.py` until route handler
  extraction is safe.
- Rerun independent reviewer checks when subagent quota is available again.

## Risks And Boundaries

- This is a structural extraction only. It does not introduce durable telemetry
  storage, runtime MCP execution, route removals, dashboard migrations, or
  PX4/SITL execution.
- The route method remains in `fastapi_handler.py` until route handler
  extraction is safe.
- Telemetry health remains a process-local MAVLink2REST client/cache view. It
  does not prove PX4 Offboard state, SITL scenario success, follower response,
  HIL, field behavior, or real-aircraft safety.

## Next Slice

Continue Phase 4 API modernization under PXE-0008. Good next candidates are
extracting `/api/v1` route handler methods into a router/service adapter now
that routes, contracts, paths/errors, actions, read-state snapshots, and
telemetry helpers are separate; designing durable action/command resources as a
safety-reviewed slice; or resuming companion-runtime reconciliation under
PXE-0022. PXE-0021 dashboard toolchain migration, PXE-0040 Gazebo runtime proof,
and PXE-0041 final no-legacy cleanup remain open.

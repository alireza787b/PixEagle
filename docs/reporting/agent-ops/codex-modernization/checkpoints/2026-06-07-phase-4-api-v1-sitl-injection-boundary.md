# Phase 4 API v1 SITL Injection Boundary Checkpoint

Date: 2026-06-07
Slice: PXE-0058
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: extract typed `/api/v1/sitl/injections/*` validation-stimulus helper
behavior from `FastAPIHandler`.

## Outcome

PXE-0058 is implemented at code, docs, and focused-guardrail level. The
validation-only SITL injection gate, `TrackerOutput` and frame-status payload
builders, dry-run summaries, synthetic fault dispatch, and AppController
validation-hook calls now live in `src/classes/api_v1_sitl.py`.

No public route, route order, handler method name, response model name, request
model name, action confirmation/idempotency/dry-run behavior, SITL enablement
default, dashboard route, runtime MCP endpoint, `tools/list`, `tools/call`,
callable tool, PX4/SITL/HIL behavior, service installation, deployment, or field
behavior changed in this slice.

## Files Changed

- `src/classes/api_v1_sitl.py`
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

- Added `src/classes/api_v1_sitl.py` for:
  - `PIXEAGLE_ENABLE_SITL_INJECTIONS` gate evaluation;
  - typed SITL error-envelope construction;
  - `SITLTrackerOutputInjection -> TrackerOutput` conversion;
  - `SITLVideoStallInjection -> frame_status` conversion;
  - dry-run summaries for all five validation routes;
  - AppController validation-hook dispatch for tracker-output, video-stall,
    commander-publish-failure, local MAVSDK-disconnect, and local
    MAVLink2REST-timeout injections.
- Updated `FastAPIHandler` so `_sitl_*` helpers and `inject_sitl_*` route
  methods are one-call migration wrappers.
- Extended `tools/generate_api_tool_candidates.py` and regenerated
  `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`.
  - `total_declared_http_routes`: 129.
  - `api_v1_routes`: 14.
  - `candidate_count`: 14.
  - `eligible_read_only_candidates`: 6.
  - `blocked_or_guarded_candidates`: 8.
  - `callable_tools`: 0.
  - `mcp_exposed_tools`: 0.
  - Source provenance now includes `src/classes/api_v1_sitl.py`.
- Added static tests that prevent:
  - SITL gate strings, response codes, validation-hook names, local
    transport-scope metadata, and `TrackerOutput` construction drifting back
    into `fastapi_handler.py`;
  - handler SITL wrappers growing beyond one delegated call;
  - generated candidate provenance omitting the SITL-helper source file.

## Validation

- `.venv/bin/python -m py_compile src/classes/api_v1_sitl.py src/classes/fastapi_handler.py tools/generate_api_tool_candidates.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py`:
  passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_sitl_injection_api.py -q`:
  28 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py -q`:
  30 passed.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`:
  passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_sitl_injection_api.py tests/unit/core_app/test_app_controller_offboard_safety.py -k "api_v1 or sitl" -q`:
  49 passed, 50 deselected.
- `git diff --check`:
  passed.
- `PYTHON=.venv/bin/python make phase0-check`:
  schema up to date, candidate inventory current, 55 passed.

## Review

Review focus for this slice:

- SITL injection behavior remains unchanged and disabled by default.
- Validation-only POST routes remain blocked from read-only MCP promotion.
- Generated agent candidates remain non-callable and unexposed.
- The helper extraction does not start PX4, Docker, MAVLink routing, video,
  MAVSDK, MAVLink2REST, or Offboard mode.
- No runtime MCP endpoint, executor, `tools/list`, or `tools/call` exists.
- No PX4/SITL/HIL/field success is claimed.

Local review found no blockers:

- `FastAPIHandler` wrappers delegate to `api_v1_sitl.py`.
- The SITL enablement string, disabled/unavailable/rejected response codes,
  AppController validation-hook names, local transport-scope metadata, and
  `TrackerOutput` construction are absent from the handler.
- Candidate inventory still reports `callable_tools: 0`,
  `mcp_exposed_tools: 0`, and the same 14 `/api/v1` routes.

Independent reviewer checks also found no blockers:

- API/MCP contract reviewer confirmed route metadata, structured SITL errors,
  non-callable candidate inventory, SITL `validation_stimulus` blocking, source
  provenance, and route/candidate guardrail tests. Reviewer reran the inventory
  check and route/candidate suite: 30 passed.
- Safety/SITL validation-boundary reviewer confirmed disabled-by-default
  gating, dry-run paths returning before AppController dispatch for all five
  injections, PixEagle-local MAVSDK/MAVLink2REST fault scope, no service/Docker/
  PX4/routing mutation claims, blocked MCP/tool exposure, and report wording
  that avoids unsupported PX4/SITL/HIL/field success claims. Reviewer reran
  diff hygiene, syntax checks, focused safety/SITL tests: 49 passed, and
  route/candidate tests: 30 passed.

Residuals accepted for later slices:

- The route methods remain in `fastapi_handler.py` until route handler/router
  extraction is safe.
- This is still contract/mock evidence only. Runtime L2/L3/L4 validation stays
  operator-gated and artifact-driven.

## Risks And Boundaries

- This is a structural extraction only. It does not add runtime SITL execution,
  durable validation evidence storage, route removals, dashboard migrations,
  or MCP execution.
- The SITL injection routes remain validation-stimulus APIs. They must stay
  disabled by default and excluded from callable AI-agent/MCP exposure.
- A passing unit/contract suite here does not prove PX4 Offboard state, SITL
  scenario success, follower response, HIL, field behavior, or real-aircraft
  safety.

## Next Slice

Continue Phase 4 API modernization under PXE-0008. Good next candidates are
extracting remaining `/api/v1` route handler methods behind router/service
adapters now that route metadata, contracts, paths/errors, actions, snapshots,
telemetry health, and SITL validation helpers are separate; designing durable
action/command resources as a safety-reviewed slice; or resuming
companion-runtime reconciliation under PXE-0022. PXE-0021 dashboard toolchain
migration, PXE-0040 Gazebo runtime proof, and PXE-0041 final no-legacy cleanup
remain open.

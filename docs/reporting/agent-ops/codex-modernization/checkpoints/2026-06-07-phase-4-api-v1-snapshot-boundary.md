# Phase 4 API v1 Snapshot Boundary Checkpoint

Date: 2026-06-07
Slice: PXE-0056
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: extract typed `/api/v1` read-state snapshot builders from
`FastAPIHandler`.

## Outcome

PXE-0056 is implemented at code, docs, and focused-guardrail level. The
process-local runtime, following, and tracking read-state snapshot builders now
live in `src/classes/api_v1_snapshots.py`.

No public route, route order, handler method name, response model name, request
model name, action confirmation/idempotency/dry-run behavior, SITL injection
gate, dashboard route, runtime MCP endpoint, `tools/list`, `tools/call`,
callable tool, PX4/SITL/HIL behavior, service installation, deployment, or field
behavior changed in this slice.

## Files Changed

- `src/classes/api_v1_snapshots.py`
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

- Added `src/classes/api_v1_snapshots.py` for:
  - legacy `/status` snapshot construction;
  - process-local runtime status classification;
  - following commander degradation classification;
  - following profile and command-publication snapshots;
  - following telemetry/setpoint snapshot fallback behavior;
  - circuit-breaker snapshot fallback for typed following telemetry;
  - tracker runtime status snapshot lookup;
  - tracker geometry/field normalization for typed telemetry;
  - tracker-following readiness snapshot assembly.
- Updated `FastAPIHandler` so its existing private snapshot helper names remain
  as migration wrappers while delegating the implementation to
  `api_v1_snapshots.py`.
- Extended `tools/generate_api_tool_candidates.py` and regenerated
  `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`.
  - `total_declared_http_routes`: 129.
  - `api_v1_routes`: 14.
  - `candidate_count`: 14.
  - `eligible_read_only_candidates`: 6.
  - `blocked_or_guarded_candidates`: 8.
  - `callable_tools`: 0.
  - `mcp_exposed_tools`: 0.
  - Source provenance now includes `src/classes/api_v1_snapshots.py`.
- Added static tests that prevent:
  - process-local read-state snapshot semantics being reimplemented inside
    `fastapi_handler.py`;
  - snapshot claim-boundary constants being re-imported into the handler;
  - generated candidate provenance omitting the snapshot source file.

## Validation

- `.venv/bin/python -m py_compile src/classes/api_v1_snapshots.py src/classes/fastapi_handler.py`:
  passed.
- `.venv/bin/python -m py_compile src/classes/api_v1_snapshots.py src/classes/fastapi_handler.py tools/generate_api_tool_candidates.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py`:
  passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py -q`:
  28 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_app_controller_offboard_safety.py -k "api_v1 or legacy_cancel or tracking_telemetry or runtime_status or following" -q`:
  40 passed, 31 deselected.
- `git diff --check`: passed.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`: passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_sitl_injection_api.py tests/unit/core_app/test_app_controller_offboard_safety.py -k "api_v1 or sitl" -q`:
  49 passed, 50 deselected.
- `PYTHON=.venv/bin/python make phase0-check`: schema up to date, candidate
  inventory current, 53 passed.

## Independent Review

Review focus for this slice:

- runtime/following/tracking snapshot semantics remain unchanged;
- tracker readiness remains fail-closed and does not broaden active-tracking
  claims;
- following command-publication status remains process-local and does not claim
  PX4-observed Offboard or vehicle response;
- generated agent candidates remain non-callable and unexposed;
- no runtime MCP endpoint, executor, `tools/list`, or `tools/call` exists;
- no PX4/SITL/HIL/field success is claimed.

Independent API/MCP and safety/runtime subagent reviews were attempted, but both
reviewers returned usage-limit errors before producing findings. No independent
approval is claimed for PXE-0056.

Recovery review completed locally before commit closure:

- API/MCP provenance review: no blockers. Confirmed `FastAPIHandler` keeps
  wrapper methods only for the moved snapshot helpers, generated candidate
  provenance includes `src/classes/api_v1_snapshots.py`, `callable_tools` remains
  `0`, `mcp_exposed_tools` remains `0`, and no generated candidate is
  `callable: true`.
- Runtime/safety semantics review: no blockers. Confirmed tracker runtime
  readiness still comes from `evaluate_tracker_runtime_status()`,
  `usable_for_following` is still the stricter fail-closed signal, following
  command-publication status remains local-only, and the checkpoint/docs do not
  claim PX4/SITL/HIL/field success.

Residuals accepted for later slices:

- `FastAPIHandler` still keeps migration wrappers until route handlers and
  downstream call sites are narrower.
- Snapshot provenance is source-hash based; semantic behavior remains guarded by
  focused backend tests and the static wrapper-boundary test.
- Rerun independent reviewer checks when subagent quota is available again.

## Risks And Boundaries

- This is a structural extraction only. It does not introduce durable command
  resources, runtime MCP execution, route removals, dashboard migrations, or
  PX4/SITL execution.
- `fastapi_handler.py` still keeps migration wrappers for snapshot helpers; a
  later cleanup can remove those wrappers only after internal and external uses
  are migrated.
- The snapshots are process-local memory/telemetry views. They are suitable for
  current operator/API feedback and validation plans, but they do not prove PX4
  Offboard state, SITL scenario success, tracker scene behavior, follower
  response, HIL, field behavior, or real-aircraft safety.

## Next Slice

Continue Phase 4 API modernization under PXE-0008. Good next candidates are
extracting `/api/v1` route handler methods into a router/service adapter now
that routes, contracts, paths/errors, actions, and read-state snapshots are
separate; designing durable action/command resources as a safety-reviewed
slice; or resuming companion-runtime reconciliation under PXE-0022. PXE-0021
dashboard toolchain migration, PXE-0040 Gazebo runtime proof, and PXE-0041
final no-legacy cleanup remain open.

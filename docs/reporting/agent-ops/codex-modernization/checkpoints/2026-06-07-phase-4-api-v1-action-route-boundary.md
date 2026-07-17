# Phase 4 API v1 Action Route Boundary Checkpoint

Date: 2026-06-07
Slice: PXE-0059
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: extract guarded typed `/api/v1/actions/*` route execution and action
resource lookup from `FastAPIHandler`.

## Outcome

PXE-0059 is implemented at code, docs, and focused-guardrail level. Guarded
Offboard-start and operator-abort action execution, idempotent replay handling,
dry-run response construction, execution result classification, and
`GET /api/v1/actions/{action_id}` lookup now live in
`src/classes/api_v1_actions.py`.

`FastAPIHandler` keeps thin route-method wrappers only. This preserves current
route registration, method names, compatibility call sites, and test fixtures
while removing the action execution body from the handler monolith.

No public route, route order, handler method name, response model name, request
model name, action confirmation/idempotency/dry-run policy, legacy command
action-audit behavior, SITL enablement default, dashboard route, runtime MCP
endpoint, `tools/list`, `tools/call`, callable tool, PX4/SITL/HIL behavior,
service installation, deployment, or field behavior changed in this slice.

## Files Changed

- `src/classes/api_v1_actions.py`
- `src/classes/fastapi_handler.py`
- `tests/test_api_route_inventory.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `docs/agent-context/README.md`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## What Changed

- Moved typed action route execution helpers into `api_v1_actions.py`:
  - `start_offboard_action()`;
  - `start_offboard_action_unlocked()`;
  - `operator_abort_action()`;
  - `operator_abort_action_unlocked()`;
  - `get_action_resource()`.
- Kept the existing safety policy unchanged:
  - confirmed dangerous actions still require `confirm=true` and an
    `idempotency_key`;
  - dry-runs still return validated action records without executing the
    legacy command route;
  - idempotent replays still return the prior action record;
  - execution exceptions are still captured in action records;
  - action records remain process-local and carry the same claim boundary.
- Updated `FastAPIHandler` so the typed action route methods are one-call
  migration wrappers that delegate to `api_v1_actions.py`.
- Regenerated
  `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`.
  - `total_declared_http_routes`: 129.
  - `api_v1_routes`: 14.
  - `candidate_count`: 14.
  - `eligible_read_only_candidates`: 6.
  - `blocked_or_guarded_candidates`: 8.
  - `callable_tools`: 0.
  - `mcp_exposed_tools`: 0.
- Updated docs to identify `api_v1_actions.py` as the owner for process-local
  action resources, guarded action execution, action lookup, idempotency replay,
  and legacy action audit behavior.
- Extended static route-inventory tests so:
  - action route helpers are present in `api_v1_actions.py`;
  - handler action route methods stay one-call wrappers;
  - action-store internals and direct UUID record construction remain out of
    `fastapi_handler.py`.
- Added a focused regression test for concurrent idempotent operator-abort
  requests so duplicate abort calls serialize through the same per-key lock and
  only execute the legacy cancel path once.

## Validation

- `.venv/bin/python -m py_compile src/classes/api_v1_actions.py src/classes/fastapi_handler.py tests/test_api_route_inventory.py tools/generate_api_tool_candidates.py tests/test_api_tool_candidates.py`:
  passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_app_controller_offboard_safety.py -k "api_v1_offboard_action or api_v1_operator_abort_action or legacy_cancel_activities_route_records_action_audit" -q`:
  11 passed, 60 deselected.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py -q`:
  30 passed.
- `.venv/bin/python -m py_compile src/classes/api_v1_actions.py src/classes/fastapi_handler.py tests/test_api_route_inventory.py tests/unit/core_app/test_app_controller_offboard_safety.py tools/generate_api_tool_candidates.py tests/test_api_tool_candidates.py`:
  passed after adding operator-abort replay coverage.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_app_controller_offboard_safety.py -k "api_v1 or action or legacy_cancel" -q`:
  19 passed, 53 deselected.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`:
  passed.
- `git diff --check`:
  passed.
- `PYTHON=.venv/bin/python make phase0-check`:
  schema up to date, candidate inventory current, 55 passed.

## Review

Review focus for this slice:

- action confirmation/idempotency/dry-run behavior remains unchanged;
- concurrent duplicate idempotent requests still serialize through per-key
  async locks;
- dry-runs do not consume idempotency keys;
- legacy start/cancel command routes still attach typed action audit records;
- action resource lookup still uses typed `/api/v1` error envelopes;
- action resources remain process-local and do not claim PX4-observed Offboard,
  SITL, HIL, field, or vehicle-response success;
- generated agent candidates remain non-callable and unexposed;
- no runtime MCP endpoint, executor, `tools/list`, or `tools/call` exists.

Independent review completed before commit closure:

- API/MCP contract reviewer: no blockers. Confirmed action execution bodies
  are in `api_v1_actions.py`, `FastAPIHandler` keeps one-call wrappers, the
  generated inventory remains non-callable/unexposed, action/SITL routes remain
  blocked or guarded, and static guardrails cover the delegated wrappers. The
  reviewer flagged one low reporting issue: PXE-0059 was marked done while the
  checkpoint still said final validation/reviewer results were pending. This
  checkpoint and journal now carry final closure results.
- Safety/control-action reviewer: no blockers. Confirmed confirmed
  Offboard/operator-abort mutations require idempotency keys, use per-key locks,
  replay prior executed records, keep dry-runs non-mutating, preserve typed
  `ACTION_NOT_FOUND` lookup errors, keep legacy command audit attachment, and
  avoid unsupported PX4/SITL/HIL/field claims. The reviewer identified missing
  direct operator-abort duplicate/concurrent replay coverage; this slice added
  that regression test and reran the focused action suite.

Residuals accepted for later slices:

- `ApiActionStore` remains process-local and non-durable.
- The typed action route methods still exist as compatibility wrappers in
  `FastAPIHandler` until route/router extraction can remove them safely.
- Runtime PX4/SITL/HIL/field proof remains operator-gated and artifact-driven.

## Risks And Boundaries

- This is a structural extraction only. It does not introduce durable action
  storage, persistent command resources, runtime MCP execution, route removals,
  dashboard migrations, PX4/SITL execution, HIL, field validation, deployment,
  or service installation.
- `ApiActionStore` remains process-local memory. It is suitable for current
  operator/API feedback and validation plans, but it is not durable command
  storage.
- This slice does not prove PX4 Offboard state, setpoint cadence, SITL scenario
  success, tracker scene behavior, follower response, HIL, field behavior, or
  real-aircraft safety.

## Next Slice

Continue Phase 4 API modernization under PXE-0008. Good next candidates are
extracting remaining non-typed route handlers behind narrower services/routers,
designing durable action/command resources as a safety-reviewed slice, or
resuming companion-runtime reconciliation under PXE-0022. PXE-0021 dashboard
toolchain migration, PXE-0040 Gazebo runtime proof, and PXE-0041 final
no-legacy cleanup remain open.

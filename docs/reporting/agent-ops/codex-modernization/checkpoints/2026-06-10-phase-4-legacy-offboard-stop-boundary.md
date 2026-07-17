# Phase 4 Legacy Offboard Stop Boundary Checkpoint

Date: 2026-06-10
Slice: PXE-0062
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: extract legacy Offboard-stop compatibility route execution from
`FastAPIHandler`.

## Outcome

PXE-0062 is implemented at code, docs, and guardrail level. The legacy
`/commands/stop_offboard_mode` compatibility route body now lives in
`src/classes/api_legacy_control_routes.py` beside legacy Offboard start and
operator cancel.

`FastAPIHandler.stop_offboard_mode()` is now a one-call route-method wrapper.
This preserves the existing route, handler method name, legacy payload shape,
inactive idempotency behavior, active disconnect delegation, and emergency
cleanup fallback while removing the remaining large Offboard command body from
the handler monolith.

No public route, route order, handler method name, response model name, request
model name, legacy stop payload shape, typed action confirmation/idempotency/
dry-run policy, legacy action-audit behavior, read-only candidate
classification, SITL enablement default, dashboard route, runtime MCP endpoint,
`tools/list`, `tools/call`, callable tool, PX4/SITL/HIL behavior, service
installation, deployment, or field behavior changed in this slice.

## Files Changed

- `src/classes/api_legacy_control_routes.py`
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

- Moved legacy `/commands/stop_offboard_mode` execution into
  `src/classes/api_legacy_control_routes.py`.
- Updated `FastAPIHandler.stop_offboard_mode()` to delegate to
  `dispatch_legacy_stop_offboard_mode(self)`.
- Kept existing stop semantics:
  - stopping while already inactive returns success without calling
    `disconnect_px4()`;
  - active stops delegate to `AppController.disconnect_px4()`;
  - disconnect exceptions trigger the existing emergency cleanup fallback for
    `offboard_commander`, `setpoint_sender`, and `follower`, then force local
    `following_active=False`;
  - final-state fallback preserves the old catch-all behavior with
    `except BaseException` rather than adding a bare `except`.
- Regenerated
  `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`.
  - `total_declared_http_routes`: 129.
  - `api_v1_routes`: 14.
  - `candidate_count`: 14.
  - `eligible_read_only_candidates`: 6.
  - `blocked_or_guarded_candidates`: 8.
  - `callable_tools`: 0.
  - `mcp_exposed_tools`: 0.
  - Source provenance continues to include
    `src/classes/api_legacy_control_routes.py`.
- Extended static tests so:
  - `stop_offboard_mode()` is present in `api_legacy_control_routes.py`;
  - `FastAPIHandler.stop_offboard_mode()` stays a one-call wrapper;
  - legacy control wrappers pass `self` to their dispatch helpers;
  - Offboard-stop idempotency, success, error, and emergency-cleanup strings
    stay out of `fastapi_handler.py`.
- Added direct route behavior tests for:
  - inactive idempotent stop;
  - active stop delegation through `disconnect_px4()`;
  - emergency cleanup after `disconnect_px4()` raises;
  - cleanup-failure reporting;
  - unreadable final-state fallback.

## Validation

- `.venv/bin/python tools/generate_api_tool_candidates.py`:
  regenerated the candidate inventory.
- `.venv/bin/python -m py_compile src/classes/api_legacy_control_routes.py src/classes/fastapi_handler.py tests/test_api_route_inventory.py tests/unit/core_app/test_app_controller_offboard_safety.py`:
  passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py -q`:
  32 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_app_controller_offboard_safety.py -k "stop_offboard_mode_api or start_offboard_mode or legacy_cancel_activities_route_records_action_audit or api_v1_offboard_action or api_v1_operator_abort_action" -q`:
  19 passed, 58 deselected.
- `.venv/bin/python -m py_compile src/classes/api_legacy_control_routes.py src/classes/fastapi_handler.py tools/generate_api_tool_candidates.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/unit/core_app/test_app_controller_offboard_safety.py`:
  passed.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`:
  passed.
- `git diff --check`:
  passed.
- `PYTHON=.venv/bin/python make phase0-check`:
  schema up to date, candidate inventory current, 57 passed.

## Review

Review focus for this slice:

- route inventory remains unchanged;
- generated agent candidates remain non-callable and unexposed;
- action and SITL routes remain blocked or guarded;
- legacy Offboard stop still stays idempotent when inactive;
- active legacy Offboard stop still delegates to `AppController.disconnect_px4()`;
- disconnect failures still trigger emergency cleanup and force local following
  inactive when cleanup succeeds;
- no runtime MCP endpoint, executor, `tools/list`, or `tools/call` exists;
- no PX4/SITL/HIL/field success is claimed.

Independent reviewer checks found no blockers:

- API/MCP reviewer confirmed route inventory stability, non-callable/unexposed
  candidate inventory, current source-hash provenance for
  `api_legacy_control_routes.py`, zero callable tools, zero MCP-exposed tools,
  and no runtime MCP endpoint, `tools/list`, `tools/call`, callable registry, or
  action-tool promotion.
- Safety/control-action reviewer confirmed inactive idempotency, active
  `disconnect_px4()` delegation, emergency cleanup of commander/sender/follower,
  forced local inactive state on cleanup success, catch-all-equivalent
  final-state fallback, unchanged route registration, and preserved surrounding
  start/cancel behavior.
- Reviewer-noted hardening gaps were addressed before final validation:
  wrapper guardrails now verify `self` delegation, and direct tests now cover
  cleanup-failure reporting plus unreadable final-state fallback.
- Both reviewers kept runtime evidence boundaries explicit and did not claim
  PX4/SITL/HIL/field success.

Local recovery review found no blockers:

- `FastAPIHandler.stop_offboard_mode()` is a one-call wrapper.
- stop idempotency, success, error, and emergency-cleanup strings live in
  `api_legacy_control_routes.py`, not `fastapi_handler.py`.
- generated candidate inventory still reports 129 declared HTTP routes, 14
  `/api/v1` candidates, six eligible read-only candidates, eight
  blocked/guarded candidates, zero callable tools, and zero MCP-exposed tools.
- no runtime MCP endpoint, executor, `tools/list`, or `tools/call` exists.
- no PX4/SITL/HIL/field success is claimed.

Residuals accepted for later slices:

- `FastAPIHandler` still keeps migration wrappers until route/router extraction
  can remove them safely.
- The legacy `/commands/*` aliases still exist by design for compatibility;
  final alias removal remains gated by PXE-0041.
- PXE-0063 now tracks the typed Offboard-stop action/deprecation decision:
  legacy stop still has no `/api/v1/actions/offboard-stop`, no action audit,
  and no explicit deprecation metadata.
- This is contract/unit evidence only; runtime PX4/SITL/HIL/field validation
  remains operator-gated and artifact-driven.

## Risks And Boundaries

- This is a structural extraction only. It does not add runtime MCP execution,
  durable storage, route removals, dashboard migrations, PX4/SITL execution,
  HIL, field validation, deployment, or service installation.
- Legacy Offboard stop remains an immediate-execution compatibility route. New
  control-plane integrations should continue using reviewed typed action
  resources where they exist; a typed stop-action resource remains a separate
  future API design decision if required.
- Candidate inventory provenance hashes the legacy helper so action candidate
  reviewers can see compatibility-route behavior drift until aliases are
  retired.

## Next Slice

Continue Phase 4 API modernization under PXE-0008. Good next candidates are
extracting remaining legacy command/tracker/follower route families behind
narrower modules, designing durable action/command resources as a
safety-reviewed slice, or resuming companion-runtime reconciliation under
PXE-0022. PXE-0021 dashboard toolchain migration, PXE-0040 Gazebo runtime
proof, and PXE-0041 final no-legacy cleanup remain open.

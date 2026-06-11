# Phase 4 Typed Offboard Stop Action Checkpoint

Date: 2026-06-11
Slice: PXE-0063
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: add the typed Offboard-stop action contract, deprecate and audit the
legacy stop alias, and move dashboard control actions onto typed action routes.

## Outcome

PXE-0063 is implemented at code, dashboard, docs, and guardrail level.

PixEagle now exposes typed `POST /api/v1/actions/offboard-stop` with the same
guarded action-resource semantics as Offboard start and operator abort:
confirmation, dry-run validation, required idempotency for confirmed mutations,
per-key replay locking, process-local action records, structured route metadata,
and generated non-callable API/MCP candidate classification.

Legacy `/commands/stop_offboard_mode` remains for compatibility, but it is now
explicitly deprecated, attaches `action_audit`, and fails closed locally when
delegated cleanup returns warnings/errors, emergency fallback cleanup fails, or
local `following_active` remains true after the stop path.

The dashboard operator control panel now uses typed action endpoints for:

- Start Following: `/api/v1/actions/offboard-start`
- Stop Following: `/api/v1/actions/offboard-stop`
- Cancel Tracker: `/api/v1/actions/operator-abort`

No PX4/SITL/HIL/field success is claimed. This slice is process-local contract,
unit, docs, and frontend build evidence only.

## Files Changed

- `src/classes/api_v1_paths.py`
- `src/classes/fastapi_api_v1_routes.py`
- `src/classes/api_v1_contracts.py`
- `src/classes/api_v1_actions.py`
- `src/classes/api_legacy_control_routes.py`
- `src/classes/fastapi_handler.py`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/components/ActionButtons.js`
- `dashboard/src/components/ActionButtons.test.js`
- `dashboard/src/pages/DashboardPage.js`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `docs/agent-context/README.md`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `tools/sitl_plans/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## What Changed

- Added canonical path constant
  `API_V1_ACTION_OFFBOARD_STOP_PATH = "/api/v1/actions/offboard-stop"`.
- Added `POST /api/v1/actions/offboard-stop` to the static `/api/v1` route
  registry with:
  - handler `stop_offboard_action`;
  - response model `APIActionResponse`;
  - request model `APIActionRequest`;
  - operation ID `stop_offboard_action`;
  - action route response metadata;
  - HTTP 202 accepted status for accepted execution.
- Extended action response/action-store typing to include `offboard_stop`.
- Implemented typed Offboard-stop action execution in
  `src/classes/api_v1_actions.py`:
  - dry-run returns a validated action resource without calling stop;
  - unconfirmed mutation returns structured `ACTION_CONFIRMATION_REQUIRED`;
  - confirmed mutation without idempotency key returns
    `ACTION_IDEMPOTENCY_KEY_REQUIRED`;
  - confirmed requests serialize by `(action_type, idempotency_key)`;
  - repeated confirmed requests with the same key replay the stored action;
  - legacy stop exceptions become failure action records instead of leaking
    route exceptions;
  - cleanup warnings/errors or still-active local following become typed action
    failure, not success.
- Marked legacy `/commands/stop_offboard_mode` as deprecated with explicit
  operation ID `legacy_stop_offboard_mode`.
- Added `action_audit` attachment to legacy Offboard stop results.
- Tightened legacy Offboard stop behavior:
  - cleanup warnings/errors become top-level failure;
  - still-active local following after stop becomes top-level failure;
  - emergency fallback cleanup failures are returned in `details.errors`,
    `details.cleanup_errors`, top-level `error`, and the action audit record.
- Migrated dashboard operator controls to typed action endpoints:
  - Start Following now sends confirmed/idempotent
    `/api/v1/actions/offboard-start`;
  - Stop Following now sends confirmed/idempotent
    `/api/v1/actions/offboard-stop`;
  - Cancel Tracker now sends confirmed/idempotent
    `/api/v1/actions/operator-abort`.
- Updated dashboard POST handling to send JSON bodies for typed actions, read
  legacy details nested inside typed action records, and surface structured
  typed error messages.
- Regenerated the non-callable API/MCP candidate inventory.
  - `total_declared_http_routes`: 130.
  - `api_v1_routes`: 15.
  - `candidate_count`: 15.
  - `eligible_read_only_candidates`: 6.
  - `blocked_or_guarded_candidates`: 9.
  - `callable_tools`: 0.
  - `mcp_exposed_tools`: 0.
- Updated active API, SITL, agent-context, issue-register, and phase-map docs.

## Validation

- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`:
  schema is up to date.
- `.venv/bin/python tools/generate_api_tool_candidates.py`:
  regenerated the candidate inventory.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`:
  candidate inventory is current.
- `.venv/bin/python -m py_compile src/classes/api_v1_actions.py src/classes/api_legacy_control_routes.py src/classes/api_v1_contracts.py src/classes/api_v1_paths.py src/classes/fastapi_api_v1_routes.py src/classes/fastapi_handler.py tests/unit/core_app/test_app_controller_offboard_safety.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py`:
  passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py -q`:
  32 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_app_controller_offboard_safety.py -k "offboard_stop_action or stop_offboard_mode_api or start_offboard_mode or legacy_cancel_activities_route_records_action_audit or api_v1_offboard_action or api_v1_operator_abort_action" -q`:
  29 passed, 58 deselected.
- `CI=true npm test -- --runTestsByPath src/components/ActionButtons.test.js --watchAll=false`:
  4 passed.
- `CI=true npm test -- --watchAll=false`:
  9 suites passed, 54 tests passed.
- `npm run build`:
  production build passed.
- `PYTHON=.venv/bin/python make phase0-check`:
  schema up to date, candidate inventory current, 57 passed.
- `git diff --check`:
  passed.

## Review

The first reviewer attempt was interrupted by the account usage limit before it
produced usable findings. Replacement API/MCP and safety/control reviewers ran
after recovery.

API/MCP review found no blockers:

- typed stop route uses typed request/response contracts and structured route
  metadata;
- generated inventory includes 15 `/api/v1` candidates, with the stop action
  classified as `guarded_control_action`;
- all candidates remain `callable: false`, `mcp_exposure: none`;
- no runtime MCP endpoint, `tools/list`, `tools/call`, or callable action tool
  was added;
- legacy stop has visible deprecation metadata and action-audit wiring.

Safety/control review found no blockers and raised three useful residuals:

- emergency fallback cleanup failures were log-only;
- different idempotency keys can still create multiple action records, although
  actual disconnect remains serialized by `AppController`;
- typed stop currently delegates through the legacy compatibility route, so the
  typed record can contain a nested legacy `action_audit`.

Actions taken after review:

- emergency fallback cleanup failures are now returned in the stop payload and
  action audit error;
- dashboard Start Following and Cancel Tracker were migrated to existing typed
  action endpoints, so all dashboard operator action controls now use typed
  action routes;
- transition boundaries are recorded below.

## Risks And Boundaries

- Action records and idempotency replay are process-local and bounded; they are
  not durable flight logs and are not multi-process command storage.
- Typed action execution still delegates through legacy compatibility bodies
  until final alias removal. This can create a typed action record that contains
  a nested legacy `action_audit`; candidate provenance hashes the legacy helper
  so this remains reviewable until aliases are retired.
- Different idempotency keys can produce distinct action records. Confirmed
  duplicate retries must reuse the same key; actual follower state transitions
  remain protected by the controller's state lock.
- Legacy `/commands/*` aliases still exist for older clients and scripts.
  Removal remains gated by the no-legacy cleanup track.
- No PX4/SITL/HIL/runtime/field pass is claimed from this slice.

## Next Slice

Continue Phase 4 API modernization under PXE-0008. Good next candidates are
extracting remaining legacy command/tracker/follower route families behind
narrower modules, resuming companion-runtime reconciliation under PXE-0022, or
starting the dashboard toolchain migration under PXE-0021. PXE-0040 Gazebo
runtime proof and PXE-0041 final no-legacy cleanup remain open.

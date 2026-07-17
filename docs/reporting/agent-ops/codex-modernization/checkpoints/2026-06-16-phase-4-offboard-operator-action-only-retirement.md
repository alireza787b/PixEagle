# Phase 4 Offboard/Operator Action-Only Alias Retirement

Date: 2026-06-16  
Issue: PXE-0064 partial  
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

This slice retired the public HTTP registrations for the three dangerous
Offboard/operator legacy command aliases:

- `POST /commands/start_offboard_mode`
- `POST /commands/stop_offboard_mode`
- `POST /commands/cancel_activities`

The canonical public surfaces for those actions are now the typed,
confirmed/idempotent action resources:

- `POST /api/v1/actions/offboard-start`
- `POST /api/v1/actions/offboard-stop`
- `POST /api/v1/actions/operator-abort`

The existing execution bodies remain available only as internal compatibility
executors behind typed actions until the lower-level control executor is
refactored. No PX4, MAVSDK, SITL, HIL, field, service-install, deployment,
runtime MCP, callable tool, or real-aircraft behavior is claimed by this slice.

## Changes

- Removed FastAPI public route registration for the three retired
  `/commands/*` aliases.
- Renamed FastAPI handler wrappers to private internal executors:
  `_execute_offboard_start_action`, `_execute_offboard_stop_action`, and
  `_execute_operator_abort_action`.
- Updated typed `/api/v1/actions/*` handlers to call internal executors rather
  than former HTTP route methods.
- Replaced route-like action metadata (`would_call`,
  `legacy_compatibility_route`) with internal-handler metadata
  (`would_execute`, `internal_compatibility_handler`).
- Changed internal compatibility audit source from `legacy_compatibility` to
  `internal_compatibility`.
- Removed the retired paths from the API security policy legacy command rule.
- Removed legacy endpoint constants from the dashboard endpoint registry and
  kept Start/Stop/Abort dashboard classification on typed action endpoints.
- Updated route inventory expectations and added an explicit retired-path
  absence test.
- Regenerated the non-callable API/MCP candidate inventory after source-hash
  and route-count drift.
- Updated active operator/API/security/streaming/config docs to state that
  Offboard start/stop/operator abort are typed-action-only over HTTP, while
  remaining legacy tracking/control mutations still need typed replacement and
  retirement.
- Updated the SITL validation contract guard so executable scenario plans
  reject all three retired command aliases.
- Updated the phase map and issue register so PXE-0064 remains open only for
  operator credential/TLS hardening, typed replacement/retirement of remaining
  legacy tracking/control mutations, and broader adversarial
  browser/session/media tests.

## Files Changed

- `src/classes/fastapi_handler.py`
- `src/classes/api_v1_actions.py`
- `src/classes/api_legacy_control_routes.py`
- `src/classes/api_security_policy.py`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/pages/DashboardPage.js`
- `tests/test_api_route_inventory.py`
- `tests/test_sitl_validation_contract.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-security-policy.md`
- `docs/apis/api-exposure-boundary.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/apis/route-inventory.md`
- `docs/agent-context/README.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/CONFIGURATION.md`
- `docs/INSTALLATION.md`
- `docs/WINDOWS_SETUP.md`
- `docs/drone-interface/04-infrastructure/port-configuration.md`
- `docs/video/04-streaming/websocket.md`
- `docs/video/04-streaming/webrtc.md`
- `README.md`
- `dashboard/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Reviewer Findings

Two read-only reviewer agents checked the slice.

- First-party/dashboard/SITL callers were already on typed action endpoints;
  no current dashboard or checked-in SITL plan required the retired command
  aliases.
- The generated API/MCP candidate inventory was stale after route removal; it
  needed route-count and source-hash regeneration.
- Active API/MCP docs still implied guarded typed actions delegated through
  public aliases until retirement. Those docs now state the public aliases are
  retired and only internal compatibility executors remain.
- `docs/apis/route-inventory.md` and API security verification text had stale
  route counts. They now match the current route inventory.
- External clients that still call the three removed `/commands/*` paths will
  receive no control action. This is the intended compatibility break for
  typed-action-only enforcement, but it remains a release-note/operator
  communication item.

## Validation

Passed:

- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/test_api_tool_candidates.py tests/test_sitl_validation_contract.py::test_phase2_plan_declares_executable_scenario_actions tests/unit/core_app/test_app_controller_offboard_safety.py::test_api_v1_offboard_action_dry_run_does_not_execute_legacy_route tests/unit/core_app/test_app_controller_offboard_safety.py::test_api_v1_offboard_action_executes_once_with_idempotency_key tests/unit/core_app/test_app_controller_offboard_safety.py::test_api_v1_offboard_stop_action_dry_run_does_not_execute_legacy_route tests/unit/core_app/test_app_controller_offboard_safety.py::test_api_v1_offboard_stop_action_executes_once_with_idempotency_key tests/unit/core_app/test_app_controller_offboard_safety.py::test_api_v1_operator_abort_action_records_safe_cancel_result tests/unit/core_app/test_app_controller_offboard_safety.py::test_stop_offboard_mode_api_is_idempotent_when_inactive tests/unit/core_app/test_app_controller_offboard_safety.py::test_legacy_cancel_activities_route_records_action_audit -q`
  - 61 passed.
- `PYTHONPATH=src .venv/bin/python -m py_compile src/classes/fastapi_handler.py src/classes/api_v1_actions.py src/classes/api_legacy_control_routes.py src/classes/api_security_policy.py tests/test_api_route_inventory.py tests/test_sitl_validation_contract.py tests/unit/core_app/test_app_controller_offboard_safety.py`
  - passed.
- `npm test -- --runTestsByPath src/components/ActionButtons.test.js --watchAll=false`
  - 1 suite passed, 5 tests passed.
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`
  - schema current, 548 parameters.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`
  - candidate inventory current.
- `npm run build`
  - compiled successfully.
- `PYTHON=.venv/bin/python make phase0-check`
  - schema current, candidate inventory current, 185 Python tests passed with
    the existing Starlette/httpx `TestClient` deprecation warning.
- `git diff --check`
  - passed.
- Active stale-text scan for old typed-action-only/route-count wording
  - clean outside historical checkpoint, journal, and audit records.

## Risks And Limits

- This is a deliberate compatibility break for external clients still calling
  the three retired `/commands/*` paths. First-party dashboard code and
  checked-in validation plans use typed actions.
- Internal compatibility executors still preserve legacy result payload shapes
  such as `legacy_result` for dashboard/SITL compatibility. They are not public
  HTTP routes and should be removed after the lower-level typed control
  executor is refactored.
- Remaining legacy tracking/control mutations still exist and remain tracked
  under PXE-0064 and broader Phase 4 route modernization.
- No PX4/SITL/HIL/field validation was run or claimed.

## Next Slice

Continue PXE-0064 with one of:

1. Operator credential rotation tooling and TLS deployment guidance.
2. Typed replacements and retirement plan for remaining legacy tracking/control
   mutations.
3. Broader adversarial browser-session/media tests around expiry, multi-tab
   logout, large protected media playback, and role-denied UX.

Related open follow-ups remain PXE-0065 for SITL sidecar evidence hardening
and PXE-0066 for generated API/MCP candidate disposition governance.

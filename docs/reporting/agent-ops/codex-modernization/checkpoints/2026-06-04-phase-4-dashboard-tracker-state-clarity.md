# 2026-06-04 - Phase 4 Dashboard Tracker-State Clarity

## Slice

- Phase: 4 Dashboard API/client normalization
- Primary issue: PXE-0024
- Follow-up opened: PXE-0044
- Claim boundary: dashboard/UI, legacy telemetry serialization, unit/contract,
  lint, and build evidence only. No live PixEagle backend, MAVLink2REST
  runtime, PX4/SITL scenario execution, tracker/video runtime, HIL, field,
  deployment, service installation, or real-aircraft validation was run.

## Changes

- Added `dashboard/src/utils/trackerRuntimeState.js` as the shared dashboard
  normalizer for tracker runtime state.
- Normalized and displayed distinct tracker states:
  - `active_usable` / `Tracking: Active`;
  - `visible_output` / `Tracking: Visible`;
  - `stale_output` / `Tracking: Stale`;
  - `not_usable` / `Tracking: Not Usable`;
  - `no_output` / `Tracking: No Output`;
  - status-hook `Checking` and request-failure `Unavailable`.
- Updated `TrackerStatusCard` and `TrackerDataDisplay` so external tracker
  output can be visible without being presented as active target tracking or
  follower-usable data.
- Updated `useTrackerDataTypes()` to keep schema/field metadata available when
  `has_output=true` even if `active=false`.
- Added `endpoints.trackerCurrentStatus` and moved `useTrackerStatus()` from
  legacy `/telemetry/tracker_data` polling to `/api/tracker/current-status`.
- Updated `OperationalStatusBar` and `NavigationDrawer` to show normalized
  tracker states instead of collapsing state to ON/OFF or Tracking/Idle.
- Updated `ActionButtons` so `Start Following` is disabled unless tracker
  status is fresh and `usable_for_following=true`; `Stop Following`, cancel,
  and tracker stop paths remain available.
- Added the same fail-closed tracker readiness guard to
  `/commands/start_offboard_mode`, which also protects the typed
  `/api/v1/actions/offboard-start` path before `connect_px4()` can run.
- Updated `/api/tracker/current-status` and legacy telemetry output so
  `MULTI_TARGET` detections count as visible output even when no selected target
  is follower-usable.
- Enriched legacy `/telemetry/tracker_data` serialization with
  `has_output`, `usable_for_following`, and `data_is_stale` at the top level
  and inside `tracker_data`.
- Updated API/core docs to state that visible tracker output is not the same as
  a follower-usable target.

## Files Changed

- `dashboard/src/utils/trackerRuntimeState.js`
- `dashboard/src/utils/trackerRuntimeState.test.js`
- `dashboard/src/hooks/useStatuses.js`
- `dashboard/src/hooks/useStatuses.test.js`
- `dashboard/src/hooks/useTrackerSchema.js`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/components/ActionButtons.js`
- `dashboard/src/components/ActionButtons.test.js`
- `dashboard/src/components/NavigationDrawer.js`
- `dashboard/src/components/OperationalStatusBar.js`
- `dashboard/src/components/OperationalStatusBar.test.js`
- `dashboard/src/components/TrackerDataDisplay.js`
- `dashboard/src/components/TrackerDataDisplay.test.js`
- `dashboard/src/components/TrackerStatusCard.js`
- `dashboard/src/components/TrackerStatusCard.test.js`
- `dashboard/src/pages/DashboardPage.js`
- `src/classes/fastapi_handler.py`
- `src/classes/telemetry_handler.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tests/unit/drone_interface/test_telemetry_handler.py`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/core-app/README.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-04-phase-4-dashboard-tracker-state-clarity.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- `npm test -- --watchAll=false --runTestsByPath src/utils/trackerRuntimeState.test.js src/components/TrackerDataDisplay.test.js src/components/TrackerStatusCard.test.js`
  - 3 suites passed, 7 tests passed
- `npm test -- --watchAll=false --runTestsByPath src/utils/trackerRuntimeState.test.js src/components/TrackerDataDisplay.test.js src/components/TrackerStatusCard.test.js src/components/ActionButtons.test.js src/components/OperationalStatusBar.test.js src/hooks/useStatuses.test.js`
  - 6 suites passed, 23 tests passed
- `PYTHONPATH=src .venv/bin/pytest tests/unit/drone_interface/test_telemetry_handler.py`
  - 33 tests passed
- `PYTHONPATH=src .venv/bin/pytest tests/unit/core_app/test_app_controller_offboard_safety.py::test_start_offboard_mode_api_reports_failure_when_controller_returns_errors tests/unit/core_app/test_app_controller_offboard_safety.py::test_start_offboard_mode_api_blocks_unusable_tracker_output tests/unit/core_app/test_app_controller_offboard_safety.py::test_api_v1_offboard_action_blocks_unusable_tracker_output tests/unit/core_app/test_app_controller_offboard_safety.py::test_current_tracker_status_treats_multi_target_detections_as_visible_output`
  - 4 tests passed
- `PYTHONPATH=src .venv/bin/pytest tests/unit/core_app/test_app_controller_offboard_safety.py`
  - 47 tests passed
- `PYTHONPATH=src .venv/bin/python -m py_compile src/classes/fastapi_handler.py src/classes/telemetry_handler.py`
  - passed
- `npm run lint`
  - passed
- `npm test -- --watchAll=false`
  - 7 suites passed, 24 tests passed
- `PYTHONPATH=src .venv/bin/pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py tests/unit/core_app/test_app_controller_offboard_safety.py tests/unit/drone_interface/test_telemetry_handler.py`
  - 97 tests passed
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`
  - schema up to date
- `npm run build`
  - compiled successfully

Environment note: `bash scripts/check_schema.sh` without `PYTHON=.venv/bin/python`
used the system `python3`, which lacks `ruamel.yaml` on this host. The project
virtualenv contains the dependency and is the validation path used above.

## Independent Review

- First-pass explorer found four risks:
  - legacy tracker polling collapsed state to `tracker_started`;
  - follow controls did not use tracker runtime usability;
  - tracker selector/current API remained active/configured only;
  - target-loss/direct follower helper paths still had active-only pockets.
- Fixes made in this slice:
  - dashboard status polling now consumes `/api/tracker/current-status`;
  - operational/nav chips use normalized tracker runtime status;
  - follow engagement is blocked unless output is `usable_for_following=true`;
  - legacy tracker telemetry now serializes `has_output`,
    `usable_for_following`, and `data_is_stale`.
- Final independent review found two additional blockers:
  - start-follow gating was UI-only and direct API/MCP callers could still
    reach `connect_px4()`;
  - targets-only SmartTracker `MULTI_TARGET` detections could be reported as
    no output.
- Final-review fixes made:
  - both legacy and typed Offboard-start paths now fail closed before
    `connect_px4()` unless tracker output is present, fresh, and
    follower-usable;
  - `targets` now contributes to backend/API and legacy telemetry `has_output`
    detection.
- Remaining selector/runtime-contract and deeper direct-follower active-only
  cleanup is not hidden; it is tracked as PXE-0044.

## Risks And Follow-Ups

- PXE-0044 remains open for typed `/api/v1` tracker runtime status, selector
  adoption, and target-loss/direct follower cleanup so `tracking_active=True`
  with stale or unusable metadata cannot be treated as a live target in future
  direct paths.
- PXE-0008 remains open for broader `/api/v1` migration and MCP-friendly route
  contracts.
- PXE-0021 remains open for dashboard toolchain migration away from CRA.
- PXE-0022 remains open for companion-runtime/API sidecar reconciliation.
- PXE-0040 remains open for official Gazebo visual runtime evidence on a
  suitable operator-gated host.

## Next Slice

Continue Phase 4 with one of:

- PXE-0044 typed tracker runtime API/internal cleanup;
- PXE-0008 broader `/api/v1` API/MCP migration;
- PXE-0022 companion-runtime/API reconciliation;
- PXE-0021 dashboard toolchain migration.

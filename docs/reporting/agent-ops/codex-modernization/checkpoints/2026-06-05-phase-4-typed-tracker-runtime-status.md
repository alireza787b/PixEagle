# 2026-06-05 - Phase 4 Typed Tracker Runtime Status

## Slice

- Phase: 4 dashboard/API typed runtime modernization
- Issue closed: PXE-0044
- Scope: tracker runtime API contract, dashboard selector/status consumers,
  TargetLossHandler active/stale semantics, docs, tests, and report updates.

## Claim Boundary

This checkpoint is unit, static contract, dashboard build, and documentation
evidence only. It does not claim a live PixEagle backend run, PX4/SITL/HIL
interaction, Gazebo/X-Plane pass, tracker/video runtime pass, deployment,
service installation, field operation, or real-aircraft validation.

## What Changed

- Added `src/classes/tracker_runtime_status.py` as the shared evaluator for
  tracker output visibility and fail-closed follower usability.
- Added typed `GET /api/v1/tracking/runtime-status` with:
  - `has_output`;
  - `active_tracking`;
  - fail-closed `usable_for_following`;
  - `data_is_stale`;
  - `status` and `consumer_guidance`;
  - stale/degraded reason;
  - configured/active tracker IDs;
  - provider/protocol/status metadata;
  - target count and selected target ID;
  - output field names;
  - claim boundary.
- Replaced duplicated Offboard-start readiness logic with the shared runtime
  snapshot so legacy `/commands/start_offboard_mode` and typed
  `/api/v1/actions/offboard-start` use the same tracker gate.
- Enriched compatibility routes `/api/tracker/current` and
  `/api/tracker/current-status` with the typed runtime fields while preserving
  existing configured-tracker and schema-driven field payloads.
- Updated `TargetLossHandler` so `tracking_active=True` is not a live target
  when output is stale or `usable_for_following=false`.
- Migrated dashboard `useTrackerStatus()` to
  `/api/v1/tracking/runtime-status`.
- Updated tracker dashboard hooks to use `endpoints.*` instead of rebuilding
  direct `protocol://host:port` URLs, improving reverse-proxy consistency.
- Updated `TrackerSelector` to display normalized runtime status, including
  visible, stale, not-usable, unavailable, and follower-usability chips.
- Fixed independent review findings before commit:
  - custom trackers must explicitly set `usable_for_following=true` before
    active output can drive following;
  - frontend boolean parsing is field-specific so provider string tokens such
    as `stale`, `not_usable`, and `unusable` cannot invert runtime safety
    state;
  - tracker runtime polling ignores stale out-of-order responses;
  - selector pending-selection state clears when backend state converges to the
    pending value before the user clicks switch.
- Updated API docs, FastAPI component docs, developer schema guide, issue
  register, and phase map.

## Files Changed

- `src/classes/tracker_runtime_status.py`
- `src/classes/fastapi_handler.py`
- `src/classes/target_loss_handler.py`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/hooks/useStatuses.js`
- `dashboard/src/hooks/useTrackerSchema.js`
- `dashboard/src/utils/trackerRuntimeState.js`
- `dashboard/src/components/TrackerSelector.js`
- `tests/test_api_route_inventory.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tests/unit/followers/test_target_loss_runtime_status.py`
- `dashboard/src/hooks/useStatuses.test.js`
- `dashboard/src/utils/trackerRuntimeState.test.js`
- `dashboard/src/components/TrackerSelector.test.js`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/core-app/README.md`
- `docs/developers/SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- `PYTHONPATH=src .venv/bin/python -m py_compile src/classes/tracker_runtime_status.py src/classes/fastapi_handler.py src/classes/target_loss_handler.py`
- `PYTHONPATH=src .venv/bin/pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py tests/unit/core_app/test_app_controller_offboard_safety.py tests/unit/followers/test_target_loss_runtime_status.py tests/unit/followers/test_target_loss_safe_publication.py -q`
  - 83 passed
- `CI=true npm test -- --watchAll=false --runTestsByPath src/hooks/useStatuses.test.js src/utils/trackerRuntimeState.test.js src/components/TrackerSelector.test.js`
  - 3 suites, 23 tests passed
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`
  - schema up to date
- `npm run lint`
  - passed
- `npm test -- --watchAll=false`
  - 8 suites, 33 tests passed
- `npm run build`
  - compiled successfully
- `git diff --check`
  - passed

## Companion Refs

Rechecked on 2026-06-05 before reporting:

- MavlinkAnywhere `/home/alireza/mavlink-anywhere`:
  `origin/main` `7643d4d`, `v3.0.14-2-g7643d4d`.
- Smart Wi-Fi Manager `/home/alireza/smart-wifi-manager`:
  `origin/main` `a5414fc`, `v2.1.14-2-ga5414fc`.
- `mavsdk_drone_show` `/home/alireza/mavsdk_drone_show`:
  `origin/main` `9cfeb367`,
  `v5.5.61-simurgh-web-search-trace-truth`.

## Review Notes

- Backend/API/safety review focus:
  - one canonical evaluator now owns `has_output`, `active_tracking`,
    `data_is_stale`, and `usable_for_following`;
  - `usable_for_following` requires explicit tracker/provider opt-in,
    active tracking, output presence, and non-stale data even if raw provider
    metadata is otherwise optimistic;
  - typed route is in route inventory and typed error-envelope scope;
  - TargetLossHandler no longer treats active stale or active not-usable output
    as a live target.
- Frontend/UI review focus:
  - dashboard status polling now consumes the typed route;
  - tracker selector chips distinguish visible/stale/not-usable runtime output;
  - tracker hooks now use the endpoint registry for proxy-safe URLs;
  - tests cover typed field names, provider string tokens, stale-response
    ordering, selector chips, and selector pending-selection convergence.

## Risks And Follow-Ups

- PXE-0008 remains open for broader `/api/v1` route migration, durable action
  storage, OpenAPI client contract work, and MCP-friendly typed resources.
- PXE-0021 remains open for dashboard migration away from deprecated CRA.
- PXE-0022 remains open for deeper companion sidecar/MCP standards alignment.
- PXE-0040 remains open for official Gazebo visual runtime evidence on a
  suitable host or proven official-image startup workaround.
- PXE-0041 remains the final no-legacy cleanup gate for compatibility routes,
  stale docs, redundant configs/scripts, and remaining deprecated surfaces.

## Next Planned Slice

Continue Phase 4 API/MCP modernization under PXE-0008/PXE-0022 unless the
maintainer prioritizes dashboard toolchain migration (PXE-0021) or Gazebo L4
runtime proof (PXE-0040).

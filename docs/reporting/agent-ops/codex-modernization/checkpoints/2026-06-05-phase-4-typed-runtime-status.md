# Phase 4 Checkpoint: Typed Runtime Status

Date: 2026-06-05  
Slice: Phase 4 API/MCP modernization  
Primary issue: PXE-0045  
Related open issues: PXE-0008, PXE-0021, PXE-0022, PXE-0040, PXE-0041  
Claim boundary: unit/contract/frontend evidence only. No live PixEagle backend,
PX4/SITL/HIL, tracker/video runtime, field, deployment, service, or
real-aircraft validation is claimed.

## Summary

This slice moved dashboard smart-mode polling off the legacy flat `/status`
surface and added a typed, inventory-tested runtime status contract:

- `GET /api/v1/runtime/status`
- response model: `APIRuntimeStatusResponse`
- operation ID: `get_runtime_status`
- tag: `runtime`
- structured `/api/v1` error envelope
- explicit claim boundary

The route reports PixEagle process-local mode/subsystem state only. It does not
claim PX4-observed Offboard mode, setpoint cadence, SITL success, HIL success,
field success, or follower-response success.

## Files Changed

- `src/classes/fastapi_handler.py`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/hooks/useStatuses.js`
- `dashboard/src/hooks/useStatuses.test.js`
- `tests/test_api_route_inventory.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `docs/core-app/README.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Implementation Notes

- Added `API_V1_RUNTIME_STATUS_PATH = "/api/v1/runtime/status"`.
- Added `RUNTIME_STATUS_CLAIM_BOUNDARY`.
- Added typed Pydantic models:
  - `APIRuntimeModesStatus`
  - `APIRuntimeSubsystemStatus`
  - `APIRuntimeStatusResponse`
- Added `RUNTIME_STATUS_ERROR_RESPONSES`.
- Replaced direct legacy `/status` assembly with
  `_get_legacy_runtime_status_snapshot()`.
- Added `_get_runtime_status_snapshot()` as the typed `/api/v1` source.
- Added `_classify_runtime_status()`:
  - commander failures become `degraded/operator_attention`;
  - local following with stopped/non-running commander publication,
    inactive commander task, stale command intent, or active failsafe defaults
    becomes `degraded/operator_attention`;
  - local following with missing/unknown command-publication fields also becomes
    `degraded/operator_attention`;
  - active following becomes `active/following_active`;
  - active smart/tracking/segmentation mode becomes `active/vision_active`;
  - otherwise the status is `idle/idle`.
- Preserved legacy `/status` compatibility fields.
- Migrated `useSmartModeStatus()` to `endpoints.runtimeStatus` and
  `modes.smart_mode_active`.
- Added route fallback to legacy `/status` only when the typed runtime route is
  missing during rolling updates.
- Added stale out-of-order response protection to smart-mode polling.
- Kept top-level `smart_mode_active` payload parsing only as a compatibility
  fallback.

## Companion Reference Refresh

The companion repositories were fast-forwarded before reporting:

- MDS / `mavsdk_drone_show`: `04e53b1f`,
  `v5.5.64-simurgh-mcp-smoke-heuristic`
- MavlinkAnywhere: `7643d4d`, `v3.0.14-2-g7643d4d`
- Smart Wi-Fi Manager: `a5414fc`, `v2.1.14-2-ga5414fc`

Observations carried into PXE-0022:

- MDS now has stronger agent-context/MCP material, generated non-callable
  OpenAPI tool-candidate review, and explicit MCP auth defaults.
- MDS uses `/api/v1/system/runtime-status` for GCS host/admin posture.
- PixEagle uses `/api/v1/runtime/status` here because this route is
  process-local flight-adjacent mode/subsystem status, matching the approved
  PixEagle API blueprint.
- MavlinkAnywhere and Smart Wi-Fi Manager continue to reinforce token or Basic
  Auth guarded remote mutations, dry-run/apply profile APIs, and local sidecar
  scope.

## Focused Validation

Completed before the final review gate:

- `PYTHONPATH=src .venv/bin/python -m py_compile src/classes/fastapi_handler.py`
  - passed
- `PYTHONPATH=src .venv/bin/pytest tests/test_api_route_inventory.py tests/unit/core_app/test_app_controller_offboard_safety.py -q`
  - 66 passed after reviewer fixes and fail-closed unknown-field hardening
- `CI=true npm test -- --watchAll=false --runTestsByPath src/hooks/useStatuses.test.js`
  - 1 suite, 14 tests passed after reviewer fixes

## Review Gate

Completed first-pass reviewers:

- backend/API safety reviewer found a blocker: `following_active=true` with a
  stopped/non-running Offboard commander could classify as
  `active/following_active`. Fixed with degraded classification for
  non-running commander, inactive task, stale intent, active failsafe defaults,
  and missing commander while following.
- frontend/dashboard reviewer found two blockers: the rolling-update fallback
  did not call legacy `/status` when `/api/v1/runtime/status` was missing, and
  smart-mode polling accepted stale out-of-order responses. Fixed with route
  fallback and request-sequence/mounted guards.
- docs/API/MCP reviewer found the runtime example used non-emitted
  `healthy` subsystem states and the consumer note omitted the route fallback
  and stale-response guard. Fixed the example to use `running` and `fresh`, and
  documented the fallback behavior.

Final review status:

- backend/API blocker fixed and focused backend suite passed.
- frontend/dashboard blockers fixed and focused frontend suite passed.
- docs/API/MCP findings fixed and route inventory recheck passed.

## Final Validation

- `PYTHONPATH=src .venv/bin/python -m py_compile src/classes/fastapi_handler.py`
  - passed
- `PYTHONPATH=src .venv/bin/pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py tests/unit/core_app/test_app_controller_offboard_safety.py -q`
  - 76 passed
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`
  - schema up to date
- `npm run lint`
  - passed
- `CI=true npm test -- --watchAll=false`
  - 8 suites, 35 tests passed
- `npm run build`
  - compiled successfully
- `git diff --check`
  - passed
- post-doc-fix route inventory recheck:
  - `PYTHONPATH=src .venv/bin/pytest tests/test_api_route_inventory.py -q`
  - 9 passed
- docs infrastructure consistency:
  - `PYTHONPATH=src .venv/bin/pytest tests/test_docs_infrastructure_consistency.py -q`
  - 10 passed

## Risks And Open Questions

- PXE-0008 remains open: the broader API is still mixed and only some surfaces
  have moved to typed `/api/v1`.
- PXE-0021 remains open: dashboard is still on CRA/react-scripts.
- PXE-0022 remains open: a dedicated companion sidecar source-of-truth and
  token/profile management slice is still needed.
- PXE-0040 remains open: official Gazebo visual runtime evidence still needs a
  capable host or proven startup workaround.
- PXE-0041 remains open: final compatibility alias cleanup waits until typed
  replacements are proven.

## Next Planned Slice

Continue Phase 4 API/MCP modernization. Recommended next candidates:

1. Add typed following or flight status resource under `/api/v1/following/*` or
   `/api/v1/flight/*`, then migrate one dashboard/status consumer.
2. Start the PixEagle MCP/agent-context inventory pattern inspired by current
   MDS, using generated review-only OpenAPI tool candidates rather than a
   callable MCP surface.
3. Continue dashboard API-client consolidation ahead of the CRA/Vite toolchain
   migration.

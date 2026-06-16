# Phase 4 Typed Tracking Actions

Date: 2026-06-16  
Issue: PXE-0064 partial  
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

This slice adds typed guarded action resources for manual tracking start/stop:

- `POST /api/v1/actions/tracking-start`
- `POST /api/v1/actions/tracking-stop`

The first-party dashboard ROI workflow now uses those typed actions with
confirmed idempotent requests. The legacy `/commands/start_tracking` and
`/commands/stop_tracking` routes remain registered as local-only compatibility
aliases for one migration window, pending a later retirement gate.

This is a PixEagle local API/control-path change only. No PX4, MAVSDK, SITL,
HIL, field, service-install, deployment, runtime MCP, callable tool, or
real-aircraft behavior is claimed by this slice.

## Changes

- Added canonical path constants and typed route specs for tracking-start and
  tracking-stop action resources.
- Added typed `APITrackingBoundingBox` and `APITrackingStartRequest` contracts.
- Added tracking action dispatch helpers with:
  - dry-run validation;
  - explicit confirmation before mutation;
  - required idempotency keys for confirmed mutations;
  - per-key idempotent replay;
  - process-local action records and audit events;
  - local tracking/following state capture;
  - guarded non-callable API/MCP candidate classification.
- Split legacy tracking route bodies into internal FastAPIHandler executors and
  kept the legacy methods as thin compatibility aliases.
- Added typed tracking action routes to the default-deny security policy under
  `actions:execute`.
- Migrated dashboard ROI start/stop and toolbar stop calls to the typed action
  routes.
- Added a shared dashboard action-request helper for confirmed idempotent
  payloads.
- Regenerated the non-callable API/MCP candidate inventory. The inventory now
  has 20 `/api/v1` candidates, with tracking start/stop blocked as guarded
  control actions.
- Updated API/security/exposure/core docs, route inventory counts, phase map,
  and issue register.

## Files Changed

- `src/classes/api_v1_paths.py`
- `src/classes/api_v1_contracts.py`
- `src/classes/api_v1_actions.py`
- `src/classes/fastapi_api_v1_routes.py`
- `src/classes/fastapi_handler.py`
- `src/classes/api_security_policy.py`
- `dashboard/src/services/actionRequests.js`
- `dashboard/src/services/actionRequests.test.js`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/hooks/useBoundingBoxHandlers.js`
- `dashboard/src/pages/DashboardPage.js`
- `dashboard/src/components/ActionButtons.js`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- active API/exposure/core/config/streaming docs
- modernization phase map and issue register

## Reviewer Findings

A read-only reviewer checked the tracking route surface before the slice was
completed.

- The only first-party production callers of `/commands/start_tracking` and
  `/commands/stop_tracking` were dashboard ROI/toolbar paths.
- No checked-in SITL helper, script, or other production caller was found for
  those exact legacy routes.
- Immediate alias retirement would break external/local operator scripts that
  still call the raw command routes, so this slice keeps aliases local-only and
  migrates first-party callers first.
- The reviewer flagged that route specs referenced missing handler methods at
  the time of review. This slice added the missing FastAPIHandler wrappers and
  executor split before validation.
- The reviewer recommended typed action tests, route/security/candidate
  updates, generated inventory regeneration, and docs updates. Those items are
  included in this checkpoint.

## Validation

Passed:

- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/unit/core_app/test_app_controller_offboard_safety.py -q`
  - 136 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_tool_candidates.py -q`
  - 9 passed.
- `PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_v1_actions.py src/classes/api_v1_contracts.py src/classes/api_v1_paths.py src/classes/fastapi_api_v1_routes.py src/classes/fastapi_handler.py src/classes/api_security_policy.py tools/generate_api_tool_candidates.py`
  - passed.
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`
  - schema current, 548 parameters.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`
  - candidate inventory current.
- `CI=true npm test -- --watchAll=false`
  - 12 suites passed, 63 tests passed.
- `npm run build`
  - compiled successfully, with the existing Node `fs.F_OK` deprecation warning.
- `PYTHON=.venv/bin/python make phase0-check`
  - schema current, candidate inventory current, 185 Python tests passed with
    the existing Starlette/httpx `TestClient` deprecation warning.
- `git diff --check`
  - passed.

## Risks And Limits

- Legacy `/commands/start_tracking` and `/commands/stop_tracking` remain
  registered local-only aliases in this slice. They must be retired after
  external/operator migration notes are ready.
- Tracking start/stop now have typed action replacements, but segmentation,
  redetect, smart-mode toggle, and smart-click still need typed migration.
- Tracking action resources record local PixEagle execution only. They do not
  prove target quality, follower response, PX4 behavior, SITL, HIL, field, or
  vehicle response.
- The dashboard Start Tracking button still enables the ROI selection workflow;
  actual backend tracking start happens when the operator selects an ROI.

## Next Slice

Recommended next PXE-0064 slices:

1. Typed replacement for `redetect` and segmentation/smart-mode mutations.
2. Retirement gate for `/commands/start_tracking` and `/commands/stop_tracking`
   after release-note/operator compatibility review.
3. Operator credential rotation and TLS deployment guidance.
4. Broader adversarial browser-session/media tests.

PXE-0065 remains open for SITL sidecar evidence hardening, and PXE-0066 remains
open for generated API/MCP candidate disposition governance.

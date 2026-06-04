# 2026-06-04 - Phase 4 Typed MAVLink Telemetry Health

## Slice

- Phase: 4 API/MCP modernization
- Primary issue: PXE-0036
- Follow-up opened: PXE-0043 for dashboard/client adoption of typed telemetry
  health and normalized payload fields
- Claim boundary: backend/API unit and contract evidence only. No live
  PixEagle backend, MAVLink2REST runtime, PX4/SITL scenario execution, HIL,
  field, deployment, service installation, or real-aircraft validation was run.

## Changes

- Added typed `GET /api/v1/telemetry/health` with response models, operation
  ID, route-inventory coverage, telemetry tag, and structured `/api/v1` error
  envelope.
- Added `MavlinkDataManager.get_telemetry_health()` to separate:
  - latest MAVLink2REST request result;
  - last successful request freshness;
  - cached payload availability;
  - validation-timeout state;
  - consumer guidance;
  - claim boundary.
- Preserved legacy `/status.mavlink_telemetry` compatibility while forcing
  disabled telemetry freshness false for fail-closed behavior.
- Tracked `last_request_result` so a fresh cached payload with a failed latest
  request is reported as typed `degraded` instead of being hidden behind
  `fresh=true`.
- Tightened request-attempt timestamp writes under the manager lock.
- Updated API, FastAPI component, MAVLink manager, configuration, and
  troubleshooting docs to prefer the typed health resource and avoid
  PX4/SITL/HIL/field overclaims.
- Refreshed companion refs before this API slice:
  - MavlinkAnywhere `origin/main` latest tag `v3.0.14` at `7643d4d`;
  - Smart Wi-Fi Manager `origin/main` latest tag `v2.1.14` at `a5414fc`;
  - `mavsdk_drone_show` `origin/main` latest tag
    `v5.5.55-simurgh-evidence-followups` at `56d5b24b`.

## Files Changed

- `src/classes/mavlink_data_manager.py`
- `src/classes/fastapi_handler.py`
- `tests/unit/drone_interface/test_mavlink_data_manager.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tests/test_api_route_inventory.py`
- `docs/core-app/03-api/README.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/drone-interface/02-components/mavlink-data-manager.md`
- `docs/drone-interface/05-configuration/mavlink-config.md`
- `docs/drone-interface/07-troubleshooting/telemetry-gaps.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/drone_interface/test_mavlink_data_manager.py tests/unit/core_app/test_app_controller_offboard_safety.py::test_status_exposes_mavlink_telemetry_freshness tests/unit/core_app/test_app_controller_offboard_safety.py::test_typed_telemetry_health_endpoint_forwards_manager_snapshot tests/unit/core_app/test_app_controller_offboard_safety.py::test_typed_telemetry_health_endpoint_reports_unavailable_without_manager tests/unit/core_app/test_app_controller_offboard_safety.py::test_typed_telemetry_health_endpoint_returns_structured_error tests/test_api_route_inventory.py -q`
  - 57 passed
- `.venv/bin/python -m py_compile src/classes/mavlink_data_manager.py src/classes/fastapi_handler.py`
  - passed
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py tests/unit/drone_interface/test_mavlink_data_manager.py tests/unit/core_app/test_app_controller_offboard_safety.py::test_status_exposes_mavlink_telemetry_freshness tests/unit/core_app/test_app_controller_offboard_safety.py::test_typed_telemetry_health_endpoint_forwards_manager_snapshot tests/unit/core_app/test_app_controller_offboard_safety.py::test_typed_telemetry_health_endpoint_reports_unavailable_without_manager tests/unit/core_app/test_app_controller_offboard_safety.py::test_typed_telemetry_health_endpoint_returns_structured_error tests/test_docs_infrastructure_consistency.py -q`
  - 77 passed
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`
  - schema up to date
- `git diff --check`
  - passed

## Independent Review

- API/MCP reviewer first pass found:
  - `/api/v1/telemetry/health` documented structured errors but returned a
    plain FastAPI `HTTPException` body;
  - disabled telemetry could still expose fresh cached data;
  - `Any` payload fields are a residual compatibility bridge.
- Drone telemetry/safety reviewer first pass independently found:
  - disabled telemetry could still expose fresh cached data;
  - typed validation-timeout health needed direct tests;
  - request-attempt timestamp writes should be locked to reduce mixed snapshots.
- Fixes made:
  - telemetry-health failures now return `_api_v1_error_response(...)` with
    `path=/api/v1/telemetry/health` and `pixeagle-api-*` request IDs;
  - disabled telemetry forces legacy and typed freshness false even with cached
    payload;
  - validation-timeout typed health is tested with and without prior success;
  - request-attempt timestamp writes now happen under lock;
  - docs mention disabled fail-closed freshness and typed error envelope.
- Second-pass API/MCP and drone telemetry/safety reviews both reported no
  blockers.

## Risks And Follow-Ups

- PXE-0043 remains open: dashboard/client status polling still uses legacy
  `/status` and should adopt `/api/v1/telemetry/health` for operator-visible
  degraded/stale/disabled distinctions.
- Broader PXE-0008 remains open: later `/api/v1` modernization should normalize
  payload fields for generated clients/MCP where practical instead of exposing
  broad compatibility `Any` fields indefinitely.
- PXE-0022 remains open: companion-runtime/API standards need a dedicated slice
  against the refreshed MavlinkAnywhere, Smart Wi-Fi Manager, and
  `mavsdk_drone_show` refs.
- PXE-0040 remains open for operator-gated official Gazebo visual runtime
  evidence on a suitable host; this slice does not change that runtime status.

## Next Slice

Continue Phase 4 with either:

- PXE-0043 dashboard/client adoption of typed telemetry health; or
- PXE-0008/PXE-0022 broader `/api/v1` router, MCP, and companion-runtime
  reconciliation.

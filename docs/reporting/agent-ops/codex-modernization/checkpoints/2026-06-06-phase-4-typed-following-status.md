# Phase 4 Checkpoint: Typed Following Status

Date: 2026-06-06

## Slice

PXE-0046: typed process-local following status and dashboard follower-status
migration.

## Scope

Added the first typed `/api/v1/following/*` status contract:

- `GET /api/v1/following/status`
- response model: `APIFollowingStatusResponse`
- operation ID: `get_following_status`
- structured `/api/v1` error envelope
- route inventory coverage

This endpoint reports PixEagle process-local following state, follower profile
identity, OffboardCommander command-publication state, health issues, and an
explicit claim boundary. It does not claim PX4-observed Offboard, SITL, HIL,
field, or follower-response success.

## Backend Changes

- Added `API_V1_FOLLOWING_STATUS_PATH`.
- Added `FOLLOWING_STATUS_CLAIM_BOUNDARY`.
- Added typed Pydantic response models:
  - `APIFollowingProfileStatus`
  - `APIFollowingCommandPublicationStatus`
  - `APIFollowingStatusResponse`
- Added `FOLLOWING_STATUS_ERROR_RESPONSES`.
- Added `FastAPIHandler.get_following_status()`.
- Added `_get_following_status_snapshot()`:
  - `status`: `inactive`, `active`, `degraded`, or `unavailable`
  - `consumer_guidance`: `inactive`, `following_active`,
    `operator_attention`, or `unavailable`
  - profile summary from `Parameters.FOLLOWER_MODE`, active follower manager,
    concrete follower, and schema metadata
  - command-publication summary from `OffboardCommander.get_status()`
  - `health_issues` and `reason`
- Factored active-following OffboardCommander checks into
  `_classify_following_commander_degradation()` and reused it from typed
  runtime status.
- Added following-specific detection for inactive local following while the
  commander still appears to be running.

Fail-closed following classification now covers:

- local following active but follower instance missing;
- invalid configured follower profile;
- local following active with missing OffboardCommander status;
- commander failure/degraded/error state;
- commander stopped/non-running/unknown running state;
- commander task inactive/unknown;
- stale or unknown latest command intent freshness;
- active or unknown failsafe-default publication;
- inactive local following while command publication still appears active.

## Dashboard Changes

- Added `endpoints.followingStatus`.
- Migrated `useFollowerStatus()` from legacy `/telemetry/follower_data` to
  `/api/v1/following/status`.
- Kept the hook return type as a boolean for existing UI consumers.
- Added rolling-update fallback to legacy `/telemetry/follower_data` only when
  the typed following route is missing.
- Added mounted/request-sequence guards so stale out-of-order responses cannot
  overwrite newer following state.

Detailed follower telemetry cards still use `/telemetry/follower_data`; that
legacy payload remains until a later richer typed follower telemetry route is
designed and migrated.

## Documentation

- `docs/core-app/README.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/followers/07-integration/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

The follower integration guide also corrected the stale direct
`SetpointHandler -> MAVSDK` diagram text to the current
`CommandIntent -> OffboardCommander -> MAVSDK -> PX4` boundary.

## Evidence

Focused validation completed before checkpoint draft:

```bash
PYTHONPATH=src .venv/bin/python -m py_compile src/classes/fastapi_handler.py
PYTHONPATH=src .venv/bin/pytest tests/test_api_route_inventory.py tests/unit/core_app/test_app_controller_offboard_safety.py -q
CI=true npm test -- --watchAll=false --runTestsByPath src/hooks/useStatuses.test.js
```

Results:

- Python syntax compile: passed.
- Route inventory plus AppController Offboard safety: 72 passed.
- Dashboard status hook suite: 1 suite, 17 tests passed.

Local independent review after the usage-limit pause found one API wording risk:
the draft typed route exposed `commands_sent_to_px4`, but the signal was only a
PixEagle-local successful MAVSDK publication counter. The field was renamed to
`local_successful_publish_observed`, and the API docs now state that it is not
PX4-observed Offboard or vehicle-response proof.

Final validation completed:

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py tests/unit/core_app/test_app_controller_offboard_safety.py -q
PYTHON=.venv/bin/python bash scripts/check_schema.sh
PYTHONPATH=src .venv/bin/pytest tests/test_docs_infrastructure_consistency.py -q
git diff --check
npm run lint
CI=true npm test -- --watchAll=false
npm run build
```

Results:

- route inventory, parameters reload, and AppController Offboard safety:
  82 passed;
- schema check: up to date;
- docs infrastructure consistency: 10 passed;
- whitespace check: passed;
- dashboard lint: passed;
- full dashboard tests: 8 suites, 38 tests passed;
- dashboard build: compiled successfully.

## Risks And Open Follow-Ups

- This is unit/contract evidence only. No runtime PX4/SITL/HIL/field pass is
  claimed.
- `/telemetry/follower_data` still carries richer detailed follower telemetry
  for cards/pages. A later PXE-0008 slice should add a richer typed follower
  telemetry contract before removing that legacy dependency.
- The endpoint reports process-local command publication health. It is not a
  substitute for PX4-observed Offboard mode, tlog/ULog evidence, or SITL
  scenario assertions.

## Next Slice Candidates

- Continue PXE-0008 with richer typed follower telemetry/setpoint status.
- Continue PXE-0022 companion/API/MCP reconciliation and sidecar contract
  verification.
- Continue PXE-0021 dashboard toolchain modernization.
- Keep PXE-0040 official Gazebo L4 runtime proof open for suitable host
  evidence.

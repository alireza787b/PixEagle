# Phase 1 Checkpoint - Gimbal Provider Boundary

Date: 2026-05-21  
Slice: Phase 1 gimbal provider abstraction  
Primary issue: PXE-0016  
Follow-up issue: PXE-0023

## Resume Reconciliation

Before closing this slice, the current plan and issue state were reconciled
against:

- `README.md`
- `docs/README.md`
- `docs/reporting/agent-ops/codex-modernization/audits/2026-04-29-proposed-improvement-plan.md`
- `docs/architecture/pixeagle-modernization-blueprint.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`

Companion repositories were fetched again on resume. The latest checked pins
remain:

- MavlinkAnywhere: `v3.0.10`, local checkout behind `origin/main` by 4 commits.
- MAVSDK Drone Show: `v5.5.6-sitl-image-refresh`, local checkout behind
  `origin/main` by 74 commits.
- Smart Wi-Fi Manager: `v2.1.11`, local checkout aligned with `origin/main`.

That companion drift is recorded under PXE-0022 and does not block PXE-0016.

## Work Completed

- Added neutral gimbal DTOs in `src/classes/gimbal_types.py`:
  `CoordinateSystem`, `TrackingState`, `GimbalAngles`, `TrackingStatus`, and
  `GimbalData`.
- Added `src/classes/gimbal_provider.py` with:
  - `GimbalInputProvider` protocol;
  - `GimbalProviderConfig`;
  - `SipUdpGimbalProvider`;
  - provider alias normalization;
  - unsupported-provider fail-closed errors;
  - provider metadata and supported-provider listing.
- Kept the current Topotek SIP-series UDP implementation as the first provider,
  while leaving `GimbalTracker` dependent on provider output rather than a
  concrete vendor client.
- Added `GimbalTracker.PROVIDER` and passed `CONNECTION_TIMEOUT` through to the
  provider freshness logic.
- Split gimbal state semantics:
  - `tracking_active`: true only when the provider reports active tracking;
  - `has_output`: true when angle/status output exists for display;
  - `usable_for_following`: true only when external data is fresh and active;
  - `gimbal_tracking_active`: raw provider tracking state for status surfaces.
- Fixed stale tracking-state reuse: angle packets no longer inherit old
  `TRACKING_ACTIVE` status after the tracking-status freshness window expires.
- Fixed external-gimbal fail-closed behavior in `GMVelocityVectorFollower`,
  the `Follower` manager wrapper, and `AppController`: unusable or stale
  external output now produces immediate zero body velocity and yaw-speed
  commands, and the real AppController path routes this explicit fail-closed
  case through to PX4 command dispatch.
- Fixed a `GimbalInterface` deadlock exposed by provider health testing by
  switching its lock to `threading.RLock`.
- Updated backend tracker status output to include provider/protocol,
  `has_output`, `usable_for_following`, `gimbal_tracking_active`, and
  coordinate-system metadata.
- Updated dashboard tracker display so angle output remains visible when it is
  not usable for following.
- Updated schema generation overrides and regenerated `configs/config_schema.yaml`
  so `GimbalTracker.PROVIDER` is enumerated and gimbal UDP ports/timeouts have
  bounded validation metadata.
- Updated active gimbal docs, simulator docs, tracker parameter docs, tuning
  docs, and external-system integration docs to describe the provider boundary
  and current Topotek-only support.
- Added PXE-0023 for future MAVLink Gimbal v2/vendor provider adapters so the
  remaining hardware-specific work is tracked without keeping the boundary
  slice open.

## Files Changed

Core gimbal and follower path:

- `src/classes/gimbal_types.py`
- `src/classes/gimbal_provider.py`
- `src/classes/gimbal_interface.py`
- `src/classes/trackers/gimbal_tracker.py`
- `src/classes/followers/gm_velocity_vector_follower.py`
- `src/classes/followers/base_follower.py`
- `src/classes/follower.py`
- `src/classes/app_controller.py`
- `src/classes/fastapi_handler.py`

Config and schema:

- `configs/config_default.yaml`
- `configs/config_schema.yaml`
- `scripts/generate_schema.py`

Dashboard:

- `dashboard/src/components/TrackerDataDisplay.js`

Tests:

- `tests/unit/trackers/test_gimbal_provider.py`
- `tests/unit/trackers/test_gimbal_interface_status_freshness.py`
- `tests/unit/trackers/test_gimbal_tracker.py`
- `tests/unit/trackers/test_tracker_factory.py`
- `tests/unit/core_app/test_app_controller_gimbal_fail_closed.py`
- `tests/unit/followers/test_gm_velocity_vector_control.py`

Docs and reporting:

- `docs/trackers/02-reference/gimbal-tracker.md`
- `docs/trackers/04-configuration/parameter-reference.md`
- `docs/trackers/04-configuration/tuning-guide.md`
- `docs/trackers/06-integration/external-systems.md`
- `docs/gimbal_simulator.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-05.md`

## Validation

Completed:

- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/unit/core_app/test_app_controller_gimbal_fail_closed.py tests/unit/followers/test_gm_velocity_vector_control.py tests/unit/trackers/test_gimbal_provider.py tests/unit/trackers/test_gimbal_interface_status_freshness.py tests/unit/trackers/test_gimbal_tracker.py tests/unit/trackers/test_tracker_factory.py tests/unit/followers/test_config_consistency.py tests/unit/drone_interface/test_telemetry_handler.py -q --timeout=20`
  - Result: 125 passed, 2 skipped.
- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m py_compile src/classes/app_controller.py src/classes/follower.py src/classes/followers/base_follower.py src/classes/followers/gm_velocity_vector_follower.py src/classes/gimbal_types.py src/classes/gimbal_interface.py src/classes/gimbal_provider.py src/classes/trackers/gimbal_tracker.py src/classes/fastapi_handler.py`
  - Result: passed.
- `PYTHON=/tmp/pixeagle-audit-venv/bin/python bash scripts/check_schema.sh`
  - Result: schema up-to-date.
- `PYTHON=/tmp/pixeagle-audit-venv/bin/python make phase0-check`
  - Result: schema check passed and 22 tests passed.
- `npm run lint -- --format unix`
  - Result: passed.
- `CI=true npm test -- --watchAll=false`
  - Result: 1 passed.
- `npm run build`
  - Result: compiled successfully.
- `git diff --check`
  - Result: passed.

No SITL, HIL, real-aircraft, or field validation was run in this slice.

## Review Gate

Independent reviewer findings from the gimbal slice were resolved as follows:

- Drone/GNC safety:
  - stale `TRACKING_ACTIVE` reuse fixed with a separate tracking-status
    freshness window and tests;
  - unusable external gimbal output now reaches the follower through the real
    AppController and `Follower` manager path and dispatches zero body
    velocity/yaw commands.
- Architecture/API/config:
  - provider DTOs moved out of the Topotek network client;
  - provider protocol no longer requires UDP-specific attributes;
  - schema now enumerates the current provider and bounds gimbal ports/timeouts.
- CV/tracker:
  - operator-visible angle output is separated from follower-usable output;
  - tracker raw metadata now exposes canonical `has_output`,
    `usable_for_following`, `gimbal_tracking_active`, provider, protocol, and
    coordinate-system fields;
  - capabilities now advertise `GIMBAL_ANGLES` first while preserving legacy
    `ANGULAR` compatibility.
- Docs/devops/product:
  - `CONNECTION_TIMEOUT` is now connected to provider freshness behavior;
  - simulator and external-system docs no longer teach direct Topotek client
    construction as the extension model;
  - this checkpoint, journal, issue register, and slice map record the closure.

Final reviewer status:

- Drone/PX4/GNC safety: signed off after the AppController and `Follower`
  manager fail-closed dispatch path was fixed and covered by a regression test.
- Architecture/API/config: signed off with non-blocking notes about future
  provider registry centralization and later compatibility-surface cleanup.
- CV/tracker/data contract: signed off with non-blocking notes about future
  dashboard emphasis for degraded/stale output.
- Docs/devops/product: signed off after the checkpoint, issue register, journal,
  and slice map were updated.

## Risks And Open Items

- PXE-0023 remains open for actual MAVLink Gimbal v2, SIYI, Gremsy, Viewpro,
  serial SDK, simulator, replay, or other hardware-specific providers. The
  boundary is now in place, but those adapters still require selected hardware
  or protocol evidence.
- PXE-0007/PXE-0013 remain open: Offboard heartbeat and command publication
  still need their own commander/safety truth slice.
- PXE-0018/PXE-0019 remain open: PX4-in-loop and tracker-in-loop validation
  harnesses are still planned, not complete.
- PXE-0024 tracks a non-blocking dashboard follow-up: tracker summary cards
  should emphasize degraded/stale visible output through `has_output` and
  `usable_for_following`, not only `active`.
- Current validation is unit/schema/dashboard validation only; no flight claim
  is made from this slice.

## Next Slice

Move to Phase 2 Offboard commander and safety truth (PXE-0007/PXE-0013). The
first action should be a narrow audit of current command publication paths in
`app_controller`, `setpoint_sender`, `px4_interface_manager`, follower outputs,
and operator abort/status surfaces, followed by tests that freeze the current
behavior before refactor.

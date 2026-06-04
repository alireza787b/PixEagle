# Phase 2 Checkpoint - Target-Loss Safe Publication

Date: 2026-05-22  
Slice: Phase 2 Offboard commander and safety truth  
Primary issue: PXE-0031  
Umbrella issues: PXE-0007, PXE-0013

## Scope

This checkpoint closes the target-loss/inactive follower publication gap found
in the Phase 2 Offboard safety audit. It does not implement the future
independent Offboard commander.

## Work Completed

- Added an explicit inactive-output opt-in contract on `BaseFollower`.
- Kept inactive tracker output rejected by default unless a concrete follower
  can publish an intentional stop, hover, orbit, coasting, or RTL-stop policy.
- Updated `AppController` coverage so inactive output accepted by the follower
  still reaches the real PX4 send branch.
- Updated `GMVelocityVectorFollower` to:
  - initialize `failed_updates`;
  - zero yaw as well as body velocity on stale/unusable input and target-loss
    timeout;
  - avoid stale external gimbal input crashing before zero command publication.
- Updated `GMVelocityChaseFollower` to:
  - publish only callback-generated target-loss commands;
  - stop publication when RTL is requested;
  - emit a deterministic zero velocity/yaw command when a loss action has no
    command-producing callback.
- Updated `MCVelocityChaseFollower` and `MCAttitudeRateFollower` so inactive
  position outputs publish explicit stop/hover commands instead of normal
  pursuit commands, even when last-known coordinates are still present.
- Updated `FWAttitudeRateFollower` so inactive position outputs enter
  fixed-wing target-loss policy without normal pursuit math.
- Updated follower integration/development/testing docs to explain the inactive
  output publication contract.

## Review Gate

Independent reviewer roles checked the first implementation from:

- PX4/MAVSDK/GNC safety perspective;
- follower architecture and code hygiene perspective;
- test/release-gate perspective.

The review gate found blockers:

- GM vector stale-input zero command could raise before dispatch because
  `failed_updates` was not initialized.
- GM vector timeout stopped body velocity but did not clear yaw rate.
- GM chase treated broad loss states as publishable without proving a safe
  command had been generated.
- Position followers accepted inactive output too broadly and could run normal
  pursuit math using last-known valid coordinates.
- Tests needed real manager/AppController dispatch coverage and actual command
  field assertions.

All blockers above were fixed before this checkpoint was recorded.

## Files Changed

- `src/classes/followers/base_follower.py`
- `src/classes/followers/gm_velocity_chase_follower.py`
- `src/classes/followers/gm_velocity_vector_follower.py`
- `src/classes/followers/mc_velocity_chase_follower.py`
- `src/classes/followers/mc_attitude_rate_follower.py`
- `src/classes/followers/fw_attitude_rate_follower.py`
- `tests/unit/followers/test_target_loss_safe_publication.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `docs/core-app/02-components/app-controller.md`
- `docs/followers/05-development/creating-followers.md`
- `docs/followers/05-development/testing-followers.md`
- `docs/followers/07-integration/tracker-integration.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-05.md`

## Validation

Completed:

- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/unit/followers/test_target_loss_safe_publication.py tests/unit/core_app/test_app_controller_offboard_safety.py -q --timeout=20`
  - Result: 16 passed.
- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/unit/core_app/test_app_controller_offboard_safety.py tests/unit/core_app/test_app_controller_gimbal_fail_closed.py tests/unit/drone_interface/test_px4_interface_manager.py tests/unit/drone_interface/test_setpoint_sender.py tests/unit/followers/test_gm_velocity_vector_control.py tests/unit/followers/test_target_loss_safe_publication.py tests/unit/trackers/test_gimbal_provider.py tests/unit/trackers/test_gimbal_interface_status_freshness.py tests/unit/trackers/test_gimbal_tracker.py tests/unit/trackers/test_tracker_factory.py tests/unit/followers/test_config_consistency.py tests/unit/drone_interface/test_telemetry_handler.py -q --timeout=20`
  - Result: 207 passed, 2 skipped.
- `PYTHON=/tmp/pixeagle-audit-venv/bin/python make phase0-check`
  - Result: schema check passed and 22 tests passed.
- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m py_compile src/classes/followers/base_follower.py src/classes/followers/gm_velocity_chase_follower.py src/classes/followers/gm_velocity_vector_follower.py src/classes/followers/mc_velocity_chase_follower.py src/classes/followers/mc_attitude_rate_follower.py src/classes/followers/fw_attitude_rate_follower.py src/classes/app_controller.py tests/unit/followers/test_target_loss_safe_publication.py tests/unit/core_app/test_app_controller_offboard_safety.py`
  - Result: passed.
- `git diff --check`
  - Result: passed.

No SITL, HIL, real-aircraft, or field validation was run.

## Remaining Phase 2 Work

- PXE-0007 remains in progress: command publication is still frame-loop coupled
  until the independent Offboard commander exists.
- PXE-0013 remains in progress: docs still need to stop overstating independent
  heartbeat behavior.
- PXE-0030 remains open for rate config units and publish cadence.
- PXE-0032 remains open for video/frame freshness as command freshness.
- PXE-0033 remains open for unified safety truth and fail-closed validation.

## Next Step

Continue Phase 2 with PXE-0032 video/frame freshness as a command-freshness
contract, then PXE-0030 rate semantics and PXE-0033 unified safety truth before
introducing the full Offboard commander design for PXE-0007.

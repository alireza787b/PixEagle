# Phase 2 Checkpoint - Offboard Fail-Open Fixes

Date: 2026-05-21  
Slice: Phase 2 Offboard commander and safety truth  
Primary issues: PXE-0025, PXE-0026, PXE-0028, PXE-0029  
Umbrella issues: PXE-0007, PXE-0013

## Scope

This checkpoint closes the first bounded fail-open fixes discovered during the
Phase 2 Offboard safety audit. It does not implement the full independent
Offboard commander yet.

## Work Completed

- `AppController.connect_px4()` now treats returned Offboard-start errors from
  `PX4InterfaceManager.start_offboard_mode()` as activation failures.
- Failed initial setpoint publication now aborts follow-mode activation instead
  of continuing toward Offboard start.
- PX4 command send methods now return explicit booleans:
  - `send_velocity_body_offboard_commands()`
  - `send_body_velocity_commands()`
  - `send_attitude_rate_commands()`
  - `send_commands_unified()`
  - `send_initial_setpoint()`
- `AppController.follow_target()` now returns `False` when the selected PX4 send
  method reports a failed MAVSDK publication.
- `SetpointSender.get_status()` now exists, so disconnect/status paths can
  inspect the sender without raising before `stop()`.
- Offboard-exit handling is now scheduled safely from worker threads:
  - async app-loop paths use `create_task()`;
  - worker-thread paths use `asyncio.run_coroutine_threadsafe()`;
  - no-loop fallback clears `following_active=False` synchronously.
- The gimbal fail-closed regression now asserts the real
  `velocity_body_offboard` sender for `gm_velocity_vector`.

## Files Changed

- `src/classes/app_controller.py`
- `src/classes/px4_interface_manager.py`
- `src/classes/setpoint_sender.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tests/unit/core_app/test_app_controller_gimbal_fail_closed.py`
- `tests/unit/drone_interface/test_px4_interface_manager.py`
- `tests/unit/drone_interface/test_setpoint_sender.py`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-05.md`

## Validation

Completed:

- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/unit/core_app/test_app_controller_offboard_safety.py tests/unit/core_app/test_app_controller_gimbal_fail_closed.py tests/unit/drone_interface/test_px4_interface_manager.py tests/unit/drone_interface/test_setpoint_sender.py -q --timeout=20`
  - Result: 71 passed.
- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/unit/core_app/test_app_controller_offboard_safety.py tests/unit/core_app/test_app_controller_gimbal_fail_closed.py tests/unit/drone_interface/test_px4_interface_manager.py tests/unit/drone_interface/test_setpoint_sender.py tests/unit/followers/test_gm_velocity_vector_control.py tests/unit/trackers/test_gimbal_provider.py tests/unit/trackers/test_gimbal_interface_status_freshness.py tests/unit/trackers/test_gimbal_tracker.py tests/unit/trackers/test_tracker_factory.py tests/unit/followers/test_config_consistency.py tests/unit/drone_interface/test_telemetry_handler.py -q --timeout=20`
  - Result: 195 passed, 2 skipped.
- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m py_compile src/classes/app_controller.py src/classes/px4_interface_manager.py src/classes/setpoint_sender.py`
  - Result: passed.
- `PYTHON=/tmp/pixeagle-audit-venv/bin/python make phase0-check`
  - Result: schema check passed and 22 tests passed.
- `git diff --check`
  - Result: passed.

No SITL, HIL, real-aircraft, or field validation was run.

## Remaining Phase 2 Work

- PXE-0007 remains in progress: command publication is still frame-loop coupled
  until an independent Offboard commander exists.
- PXE-0013 remains in progress: docs still need to stop overstating independent
  heartbeat behavior.
- PXE-0027 remains open for operator cancel/stop paths.
- PXE-0030 remains open for rate config units and publish cadence.
- PXE-0031 remains open for target-loss/inactive safe publication.
- PXE-0032 remains open for video/frame freshness as command freshness.
- PXE-0033 remains open for unified safety truth and fail-closed validation.

## Next Step

Continue Phase 2 by freezing and fixing operator cancel/stop behavior (PXE-0027)
and target-loss safe publication behavior (PXE-0031), then proceed to the full
Offboard commander design for PXE-0007.

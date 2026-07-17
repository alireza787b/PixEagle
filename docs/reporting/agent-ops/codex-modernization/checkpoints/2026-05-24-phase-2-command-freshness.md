# Phase 2 Checkpoint - Command Freshness

Date: 2026-05-24  
Slice: Phase 2 Offboard commander and safety truth  
Primary issue: PXE-0032  
Umbrella issues: PXE-0007, PXE-0013

## Scope

This checkpoint closes the video/frame freshness gap identified in the Phase 2
Offboard safety audit. It does not implement the future independent Offboard
commander; command publication is still coupled to the current runtime loop
until PXE-0007 is completed.

## Work Completed

- Added frame freshness state to `VideoHandler` and `VideoHandlerMock`:
  - fresh frames are command-usable;
  - cached frames are display/streaming continuity only;
  - missing frames are unusable for following.
- Added hard video-stall handling in `FlowController` so following calls
  `AppController.handle_video_frame_unavailable()` when `get_frame()` returns
  `None`.
- Added `AppController` command-freshness enforcement:
  - stale/cached/prediction-only tracker output becomes inactive fail-closed
    follower input;
  - inactive output can reach a follower only through explicit
    `should_process_inactive_tracker_output()` opt-in;
  - external trackers bypass video-frame freshness only when capabilities
    explicitly declare `requires_video: false`.
- Fixed skipped safe-publication paths found by review:
  - first classic tracker update failure now dispatches fail-closed inactive
    output immediately;
  - classic recovery prediction and timeout paths dispatch inactive output;
  - failed always-reporting gimbal updates with inactive `TrackerOutput` still
    reach follower/PX4 safe publication.
- Updated tracker freshness metadata:
  - `BaseTracker` marks estimator/prediction-only output stale and not
    command-usable;
  - `SmartTracker` marks prediction-only, tentative, or missing selected-target
    detections stale even when other detections remain visible;
  - `GimbalTracker` clears active state when fresh angle packets lack fresh
    tracking status.
- Updated follower inactive opt-ins:
  - multicopter velocity chase/distance/position/ground modes publish zero
    body velocity/yaw or hold commands;
  - multicopter attitude-rate publishes hover;
  - fixed-wing attitude-rate immediately applies orbit, RTL stop, or
    wings-level cruise;
  - stale SmartTracker `MULTI_TARGET` output is eligible only for those
    fail-closed commands, not normal pursuit math.
- Expanded docs and guardrails:
  - active docs describe command freshness, cached-frame semantics, SmartTracker
    stale multi-target behavior, gimbal status freshness, and follower opt-ins;
  - broken active Markdown links were fixed;
  - docs guard now checks local links across `README.md` and all `docs/**/*.md`
    while ignoring code fences and inline code;
  - CI Phase 0 guardrail tests include `test_parameters_reload.py`.

## Review Gate

Independent reviewer roles checked the implementation from:

- PX4/MAVSDK/GNC safety perspective;
- computer vision, tracker, and video freshness perspective;
- tests/docs/release-gate perspective.

The review gate found blockers before closure:

- first classic tracker loss started a timer without dispatching a safe command;
- gimbal provider no-data output could be logged without follower dispatch;
- stale SmartTracker `MULTI_TARGET` output did not match follower inactive
  opt-ins;
- docs still had broken active links and incomplete VideoHandler freshness
  contract coverage;
- CI Phase 0 guardrails omitted the parameters reload test.

All blockers above were fixed before this checkpoint was recorded.

## Files Changed

- `src/classes/video_handler.py`
- `tests/fixtures/mock_video.py`
- `src/classes/flow_controller.py`
- `src/classes/app_controller.py`
- `src/classes/trackers/base_tracker.py`
- `src/classes/smart_tracker.py`
- `src/classes/trackers/gimbal_tracker.py`
- `src/classes/followers/fw_attitude_rate_follower.py`
- `src/classes/followers/mc_velocity_chase_follower.py`
- `src/classes/followers/mc_velocity_distance_follower.py`
- `src/classes/followers/mc_velocity_ground_follower.py`
- `src/classes/followers/mc_velocity_position_follower.py`
- `src/classes/followers/mc_attitude_rate_follower.py`
- `tests/unit/video/test_video_handler.py`
- `tests/unit/trackers/test_base_tracker.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tests/unit/core_app/test_flow_controller_frame_freshness.py`
- `tests/unit/followers/test_target_loss_safe_publication.py`
- `tests/unit/trackers/test_smart_tracker_freshness.py`
- `tests/unit/trackers/test_gimbal_tracker.py`
- `tests/test_docs_infrastructure_consistency.py`
- `.github/workflows/tests.yml`
- active docs under `docs/core-app/`, `docs/video/`, `docs/trackers/`, and
  `docs/followers/`
- modernization reports: issue register, phase map, and journal

## Validation

Completed:

- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m py_compile ...`
  - Result: passed for touched command-freshness modules and tests.
- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/unit/trackers/test_gimbal_tracker.py tests/unit/core_app/test_app_controller_offboard_safety.py tests/unit/core_app/test_flow_controller_frame_freshness.py tests/unit/followers/test_target_loss_safe_publication.py tests/unit/trackers/test_smart_tracker_freshness.py tests/test_docs_infrastructure_consistency.py -q --timeout=20`
  - Result: 68 passed.
- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/unit/video/test_video_handler.py tests/unit/trackers/test_base_tracker.py tests/unit/core_app/test_app_controller_offboard_safety.py tests/unit/core_app/test_flow_controller_frame_freshness.py tests/unit/followers/test_target_loss_safe_publication.py tests/unit/trackers/test_smart_tracker_freshness.py tests/unit/core_app/test_app_controller_gimbal_fail_closed.py tests/unit/drone_interface/test_px4_interface_manager.py tests/unit/drone_interface/test_setpoint_sender.py tests/unit/followers/test_gm_velocity_vector_control.py tests/unit/trackers/test_gimbal_provider.py tests/unit/trackers/test_gimbal_interface_status_freshness.py tests/unit/trackers/test_gimbal_tracker.py tests/unit/trackers/test_tracker_factory.py tests/unit/followers/test_config_consistency.py tests/unit/drone_interface/test_telemetry_handler.py tests/test_docs_infrastructure_consistency.py -q --timeout=20`
  - Result: 357 passed, 2 skipped.
- `PYTHON=/tmp/pixeagle-audit-venv/bin/python make phase0-check`
  - Result: schema check passed and 22 tests passed.
- `git diff --check`
  - Result: passed.
- `npm run lint -- --format unix`
  - Result: passed.
- `CI=true npm test -- --watchAll=false`
  - Result: 1 passed.
- `npm run build`
  - Result: compiled successfully.

No SITL, HIL, real-aircraft, or field validation was run.

## Remaining Phase 2 Work

- PXE-0007 remains in progress: command publication is still frame-loop coupled
  until the independent Offboard commander exists.
- PXE-0013 remains in progress: safety docs still need final alignment after
  the dedicated commander and unified safety truth land.
- PXE-0030 remains open for rate config units and publish cadence.
- PXE-0033 remains open for unified safety truth and fail-closed validation.
- PXE-0014 remains open for MAVLink telemetry freshness.

## Next Step

Continue Phase 2 with PXE-0030 rate config units and publish cadence, then
PXE-0033 unified safety truth before the full independent Offboard commander
slice for PXE-0007.

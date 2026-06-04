# Phase 3 Checkpoint: Tracker-In-Loop Validation

Date: 2026-06-01  
Slice: Phase 3, PXE-0019  
Status: done at deterministic L3 tracker/follower contract level

## Scope

PXE-0019 adds deterministic tracker-in-loop validation without requiring PX4,
Docker, real video streams, or field hardware. The slice proves that synthetic
visual frames and replayed gimbal samples produce real `TrackerOutput` objects
and that those outputs reach public follower/control contracts.

This checkpoint does not claim full visual SITL, PX4 SITL, HIL, field, real
detector accuracy, camera latency, or real gimbal protocol success.

## Files Changed

- `tests/fixtures/synthetic_tracker_scene.py`
- `tests/fixtures/tracker_clips/linear_green_target.json`
- `tests/unit/trackers/test_tracker_in_loop_validation.py`
- `docs/trackers/05-development/testing-trackers.md`
- `tests/fixtures/mock_safety.py`
- `tests/unit/followers/test_config_consistency.py`
- `tests/unit/drone_interface/test_setpoint_handler.py`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## What Changed

- Added a deterministic synthetic tracker fixture layer:
  - generated BGR frames with known target bboxes;
  - normalized-center expectations;
  - a test-only `ColorBlobTrackerProbe` built on `BaseTracker`;
  - replayable gimbal-angle samples with explicit freshness and follower
    usability metadata.
- Added a text-based simulated clip manifest at
  `tests/fixtures/tracker_clips/linear_green_target.json`.
- Added tests proving:
  - visual target trace determinism from pixels to `TrackerOutput`;
  - active visual output drives `MCVelocityPositionFollower.follow_target(...)`
    into a normal command intent;
  - visual occlusion can keep display output while AppController converts it to
    inactive command input and submits `mc_velocity_position_inactive_hold`;
  - active gimbal replay drives `GMVelocityVectorFollower.follow_target(...)`
    into normal vector pursuit;
  - stale gimbal replay goes through AppController and submits
    `gm_velocity_vector_unusable_external_input`.
- Updated tracker testing docs to separate `has_output`, `tracking_active`,
  `data_is_stale` / `freshness_reason`, and `usable_for_following`.
- Repaired stale test schema cache debt and added a drift guard against
  `configs/follower_commands.yaml`.

## Review Gate

Independent PX4/MAVSDK/GNC review initially blocked closure because stale
visual and stale gimbal paths were only partly proven:

- visual occlusion asserted stale metadata but did not prove fail-closed command
  behavior through the public route;
- stale gimbal replay called private helpers directly.

Both blockers were fixed. The tests now route stale visual and stale gimbal
outputs through `AppController._follow_tracker_output(...)`, public follower
methods, and an OffboardCommander capture stub. The CV/tracker review agent
failed to run because of an external usage limit and produced no findings.

## Validation

Commands run:

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/unit/trackers/test_tracker_in_loop_validation.py -ra --tb=short --strict-config
```

Result: 5 passed.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/unit/trackers/test_tracker_in_loop_validation.py tests/unit/followers/test_config_consistency.py tests/unit/drone_interface/test_setpoint_handler.py tests/unit/followers/test_gm_velocity_vector_control.py tests/unit/followers/test_mc_velocity_position_control.py tests/unit/followers/test_target_loss_safe_publication.py tests/unit/core_app/test_app_controller_gimbal_fail_closed.py -ra --tb=short --strict-config
```

Result: 103 passed.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/test_docs_infrastructure_consistency.py tests/unit/trackers/test_tracker_in_loop_validation.py -ra --tb=short --strict-config
```

Result: 15 passed.

```bash
/tmp/pixeagle-audit-venv/bin/python -m py_compile tests/fixtures/synthetic_tracker_scene.py tests/unit/trackers/test_tracker_in_loop_validation.py
git diff --check
```

Result: passed.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/ -m "not sitl and not px4 and not e2e and not hardware and not manual" -ra --tb=short --strict-config
```

Result: 1772 passed, 40 skipped, 1 deselected.

## Risks And Open Questions

- PXE-0019 proves deterministic L3 probe/replay contracts only. It does not
  prove production tracker accuracy, full AppController video-loop behavior,
  PX4-in-loop behavior, real gimbal protocols, or field behavior.
- PXE-0038 tracks production tracker or SmartTracker-backed deterministic smoke
  and normalized trace artifact export.
- PXE-0037 remains the next SITL validation gap: active scenario stimuli,
  fault injection, structured route/profile parsing, PX4 params, ULog/tlog
  manifests, image digest/container metadata, and complete evidence manifests.

## Next Slice

Active slice moves to PXE-0037: PX4/SITL scenario executor and artifact
automation.

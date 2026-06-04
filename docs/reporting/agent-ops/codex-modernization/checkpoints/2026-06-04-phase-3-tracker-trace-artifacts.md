# Phase 3 Checkpoint: Tracker Trace Artifacts

Date: 2026-06-04  
Phase/slice: Phase 3, PXE-0038  
Status: done for normalized trace artifact contract and guarded AppController
runtime trace hook  
Claim boundary: deterministic tracker/follower/AppController trace evidence
only. This is not PX4 runtime, SITL runtime, Gazebo, HIL, field, deployment,
service-install, or real-aircraft validation.

## Summary

PixEagle now has a reusable normalized JSONL trace contract for
tracker-to-follower command evidence:

- `trace/tracker_command_trace.jsonl`
- `trace/offboard_publish_trace.jsonl`

The deterministic smoke drives a generated green-target clip through:

```text
ColorBlobTrackerProbe -> TrackerOutput -> AppController._follow_tracker_output()
-> MCVelocityPositionFollower -> CommandIntent -> capturing OffboardCommander
```

`AppController.configure_tracker_trace_artifacts(...)` now enables append-only
runtime capture at the normal follower dispatch boundary. The hook is inert
unless explicitly configured; when enabled, it writes tracker-command records
for dispatch attempts and Offboard publish records when a `CommandIntent`
exists. This closes PXE-0038's trace-export implementation and strengthens the
future PXE-0040 Gazebo visual evidence package. The Gazebo harness now rejects
weak trace JSONL that lacks the normalized schema.

## Files Changed

- `src/classes/tracker_trace.py`
  - Added stable trace helpers for tracker output summaries, command intent
    summaries, tracker-command records, Offboard publish records, and JSONL
    writing.
  - Trace records include schema version, record type, frame index or sequence,
    timestamps, source, tracker geometry/position/angles, freshness fields,
    command intent reason/fields, optional frame status, optional commander
    status, and explicit claim boundaries.
  - JSONL writing uses `allow_nan=false`, so non-finite payloads fail closed.
- `src/classes/app_controller.py`
  - Added `configure_tracker_trace_artifacts(...)` and
    `disable_tracker_trace_artifacts()`.
  - Added best-effort trace recording inside
    `_dispatch_tracker_output_to_follower()` for accepted and rejected dispatch
    paths.
  - The hook does not start PX4, change follow mode, publish commands, install
    services, or mutate routing.
- `tests/unit/trackers/test_tracker_in_loop_validation.py`
  - Added deterministic AppController/follower/CommandIntent trace smoke using
    the configured runtime hook.
  - Added non-finite JSONL rejection regression.
- `tools/run_sitl_validation_suite.py`
  - Tightened visual trace validators so Gazebo `tracker_command_trace.jsonl`
    and `offboard_publish_trace.jsonl` require normalized record schemas, not
    arbitrary JSONL with timestamps.
- `tests/test_sitl_validation_contract.py`
  - Updated visual evidence fixtures to use normalized trace records.
  - Added a regression proving non-normalized trace JSONL is rejected.
- `docs/trackers/05-development/testing-trackers.md`
  - Documented normalized trace artifacts, required fields, schema validation,
    and no-overclaim boundaries.

## Validation

Passed:

```bash
/tmp/pixeagle-audit-venv/bin/python -m py_compile \
  src/classes/app_controller.py \
  src/classes/tracker_trace.py \
  tools/run_sitl_validation_suite.py \
  tests/unit/trackers/test_tracker_in_loop_validation.py \
  tests/test_sitl_validation_contract.py
```

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src \
pytest tests/unit/trackers/test_tracker_in_loop_validation.py \
  tests/test_sitl_validation_contract.py \
  tests/test_docs_infrastructure_consistency.py -q
```

Result: 65 passed.

Earlier focused tracker smoke before reviewer fixes:

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src \
pytest tests/unit/trackers/test_tracker_in_loop_validation.py -q
```

Result: 8 passed, then 9 passed after adding non-finite JSON rejection.

```bash
git diff --check
```

Result: passed with only the existing CRLF normalization warning for
`src/tools/gstreamer_tests/gstreamdl_receiver_rtp.bat`, no whitespace errors.

Broader focused suite after strict trace validator and AppController hook
changes:

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  tests/test_docs_infrastructure_consistency.py \
  tests/test_sitl_validation_contract.py \
  tests/sitl/test_px4_validation_harness.py \
  tests/test_udp_video_receiver_proof.py \
  tests/unit/video/test_gstreamer_pipelines.py \
  tests/unit/video/test_video_handler.py \
  tests/unit/core_app/test_flow_controller_frame_freshness.py \
  tests/unit/trackers/test_tracker_in_loop_validation.py \
  tests/unit/core_app/test_sitl_injection_api.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py -q
```

Result: 250 passed, 1 skipped.

Not run:

- live SmartTracker/YOLO model runtime
- production camera/video runtime
- Docker/PX4/Gazebo
- SITL runtime scenario execution
- HIL, field, real aircraft, deployment, or service installation

## Review Gate

Independent review found blockers in the first pass:

- Gazebo trace acceptance only checked for JSON objects and loose timing
  evidence;
- `write_trace_jsonl()` could have emitted Python's non-standard NaN/Infinity
  JSON;
- trace summary omitted some future geometry/motion fields;
- trace generation still needs runtime proof in a real Gazebo/visual run.

Fixes applied:

- Gazebo harness now validates normalized trace schemas with required
  `record_type`, `schema_version`, `frame_index`/`sequence`, tracker geometry
  or position, freshness metadata, command intent reason, and non-empty command
  fields.
- Trace JSONL writer now uses `allow_nan=false`.
- Tracker summary now includes geometry type, oriented bbox, polygon,
  normalized polygon, velocity, acceleration, and targets.
- Added the guarded AppController runtime hook and kept runtime Gazebo proof as
  a separate open evidence gate.

A second quick read-only reviewer reported no blockers after these fixes and
noted the expected residual risks around full AppController initialization,
synthetic happy-path coverage, and fail-closed non-finite payload behavior.

## Risks And Open Questions

- The AppController hook is implemented but has not been exercised in a real
  Gazebo/visual runtime. Future PXE-0040 work must attach the generated JSONL
  artifacts to a full evidence package and let the harness validate them.
- The smoke uses `AppController.__new__` with controlled dependencies, so it
  proves the follower dispatch path but not full application initialization.
- SmartTracker/YOLO runtime remains unexecuted; this slice validates the trace
  contract with deterministic generated pixels.
- The normalized trace schema is versioned at `schema_version=1`; future
  changes should either preserve compatibility or bump the schema.

## Next Planned Slice

Continue with either:

1. PXE-0040 official Gazebo runtime proof on a Docker-capable validation host;
   or
2. PXE-0042 typed `/api/v1` command/action migration, which will improve SITL
   action safety and MCP/API readiness before more runtime validation.

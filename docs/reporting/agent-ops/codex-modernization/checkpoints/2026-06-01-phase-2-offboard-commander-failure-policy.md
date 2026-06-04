# Phase 2 Offboard Commander Failure Policy Checkpoint

Date: 2026-06-01  
Slice: Phase 2 Offboard commander failure policy  
Issue: PXE-0035  
Status: Complete at unit/mock/docs level; no PX4-in-loop evidence claimed.

## Summary

`OffboardCommander` now has a local publish-failure policy. Repeated
`PX4InterfaceManager.send_commands_unified()` failures cross a typed threshold,
surface a failed commander health state, stop the local command heartbeat loop,
and ask `AppController` to stop follow mode through the normal Offboard
disconnect path.

This checkpoint does not claim SITL, HIL, real-aircraft, deployment, or field
success.

## Files Changed

- Runtime/API:
  - `src/classes/offboard_commander.py`
  - `src/classes/app_controller.py`
  - `src/classes/fastapi_handler.py`
- Config/schema:
  - `configs/config_default.yaml`
  - `configs/config_schema.yaml`
  - `scripts/generate_schema.py`
- Tests:
  - `tests/unit/drone_interface/test_offboard_commander.py`
  - `tests/unit/core_app/test_app_controller_offboard_safety.py`
  - `tests/unit/test_generate_schema.py`
- Docs/reporting:
  - `docs/drone-interface/02-components/offboard-commander.md`
  - `docs/drone-interface/05-configuration/px4-config.md`
  - `docs/core-app/03-api/README.md`
  - `docs/reporting/agent-ops/codex-modernization/issue-register.md`
  - `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
  - `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Behavioral Changes

- Added `Setpoint.OFFBOARD_COMMAND_FAILURE_THRESHOLD` with generated schema
  type `integer`, bounds `1..100`, and `follower_restart` reload tier.
- `OffboardCommander` tracks `health_state`, consecutive failures, failure
  threshold, failure-policy reason, trigger count, and failure action in
  `get_status()`.
- A successful publish resets `consecutive_failures`; transient failures below
  threshold do not stop following.
- Reaching the threshold sets `failure_policy_triggered`, marks health
  `failed`, stops the local commander loop, and invokes the AppController
  failure callback once. Configuration/dependency validation failures also
  participate in the threshold policy.
- AppController records `last_offboard_commander_failure` and stops follow mode
  through `_disconnect_px4_internal(commander_publish_final=False)` so a failed
  final publish during failure cleanup does not recurse into the same policy.
- Normal operator disconnect still performs the best-effort final default
  setpoint publish, but that final publish does not trigger the sustained
  failure policy.
- Commander publishes are serialized with a publish lock; `stop()` waits for the
  heartbeat task to finish before the final best-effort publish, preventing
  concurrent MAVSDK publishes during operator stop.
- Successful publishes clear stale `last_error`, and follower health reports a
  running commander with transient failures as degraded.
- `/status` now includes `offboard_commander_failure` in addition to the live
  `offboard_commander` status.

## Validation

Commands run:

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest \
  tests/unit/drone_interface/test_offboard_commander.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/unit/test_generate_schema.py \
  tests/test_docs_infrastructure_consistency.py -q
```

Result: 77 passed.

```bash
PYTHON=/tmp/pixeagle-audit-venv/bin/python bash scripts/check_schema.sh
```

Result: schema is up to date.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m py_compile \
  src/classes/offboard_commander.py \
  src/classes/app_controller.py \
  src/classes/fastapi_handler.py \
  tests/unit/drone_interface/test_offboard_commander.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/unit/test_generate_schema.py
```

Result: passed.

```bash
git diff --check
```

Result: passed.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest \
  tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -q
```

Result: 13 passed.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest \
  tests/unit/drone_interface/test_offboard_commander.py \
  tests/unit/drone_interface/test_px4_interface_manager.py \
  tests/unit/drone_interface/test_setpoint_handler.py \
  tests/unit/drone_interface/test_setpoint_sender.py \
  tests/integration/drone_interface/test_safety_integration.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/test_docs_infrastructure_consistency.py \
  tests/unit/test_generate_schema.py -q
```

Result: 253 passed.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest -q tests
```

Result: 1759 passed, 40 skipped.

## Review Gate

Independent PXE-0035 reviewers found two blockers and several related
non-blocking truth gaps. The blockers were fixed before closure:

- Concurrent MAVSDK publishes were possible during `OffboardCommander.stop()`
  because the final publish could race with an in-flight heartbeat publish. A
  publish lock plus stop-before-final ordering now serializes MAVSDK sends.
- The `/status` API docs did not match the legacy route's actual response
  shape. The docs now use `smart_mode_active`, `tracking_started`,
  `segmentation_active`, `following_active`, `video_status`, and
  `smart_tracker_runtime`, plus commander and MAVLink telemetry status.

Related reviewer concerns were also fixed in this slice:

- Validation failures inside `_publish_once()` now participate in the threshold
  policy.
- Successful publish recovery clears stale `last_error`.
- Follower health marks a running but degraded commander as degraded.
- The follower setpoints API docs include the returned
  `command_publication.offboard_commander` block.

Post-fix local review checked:

- typed threshold config/schema/defaults;
- transient failure recovery below threshold;
- sustained failure callback fires once;
- AppController stops following through the Offboard disconnect path;
- normal operator stop does not falsely trigger the sustained-failure policy;
- stop/final-publish serialization prevents concurrent commander publishes;
- status/API fields expose commander health and last local failure;
- docs avoid PX4/SITL/HIL/field claims.

## Evidence Limits

- Current evidence is unit/mock/integration Python evidence only.
- No live MAVLink2REST, PX4 SITL, HIL, real-aircraft, deployment, or field
  validation was run.
- The local failure policy proves PixEagle stops claiming active local command
  publication after repeated local send failures. It does not prove PX4 received
  a final setpoint, exited Offboard, or executed a vehicle failsafe.

## Risks And Follow-Ups

- PXE-0018 must add PX4-in-loop scenarios for commander publish failure,
  Offboard heartbeat loss, target loss, video stall, MAVSDK disconnect,
  operator abort, and MAVLink2REST timeout.
- Typed `/api/v1` status and command resources remain PXE-0008/PXE-0022/PXE-0036
  work; this slice only improves the legacy status surface.

## Next Slice

Continue Phase 2 with PXE-0018: executable PX4-in-loop validation harness.

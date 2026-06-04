# Phase 2 Offboard Commander Boundary Checkpoint

Date: 2026-06-01  
Slice: Phase 2 Offboard commander boundary  
Issues: PXE-0007, PXE-0013  
Status: Code/mock-test/docs slice complete; PX4-in-loop evidence remains open.

## Summary

PixEagle now has a dedicated async `OffboardCommander` that owns MAVSDK
Offboard setpoint publication independently of the camera/tracker frame loop.
Followers emit atomic `CommandIntent` snapshots; `AppController` submits those
snapshots to the commander; the commander applies the accepted intent to the
active `SetpointHandler` and publishes through
`PX4InterfaceManager.send_commands_unified()` at `OFFBOARD_COMMAND_RATE_HZ`.

This checkpoint does not claim SITL, HIL, real-aircraft, or field success.

## Files Changed

- Runtime command boundary:
  - `src/classes/offboard_commander.py`
  - `src/classes/app_controller.py`
  - `src/classes/follower.py`
  - `src/classes/fastapi_handler.py`
  - `src/classes/setpoint_handler.py`
  - `src/classes/setpoint_sender.py`
- Follower docstring cleanup:
  - `src/classes/followers/base_follower.py`
  - `src/classes/followers/fw_attitude_rate_follower.py`
  - `src/classes/followers/mc_attitude_rate_follower.py`
  - `src/classes/followers/mc_velocity_chase_follower.py`
  - `src/classes/followers/mc_velocity_position_follower.py`
- Tests:
  - `tests/unit/drone_interface/test_offboard_commander.py`
  - `tests/unit/core_app/test_app_controller_offboard_safety.py`
  - `tests/integration/drone_interface/test_safety_integration.py`
  - `tests/test_docs_infrastructure_consistency.py`
- Active docs:
  - `docs/drone-interface/README.md`
  - `docs/drone-interface/02-components/offboard-commander.md`
  - `docs/drone-interface/02-components/setpoint-sender.md`
  - `docs/drone-interface/03-protocols/mavsdk-offboard.md`
  - `docs/drone-interface/05-configuration/px4-config.md`
  - `docs/drone-interface/05-configuration/safety-integration.md`
  - `docs/drone-interface/07-troubleshooting/offboard-mode.md`
  - `docs/followers/01-architecture/README.md`
  - `docs/followers/01-architecture/base-follower.md`
  - `docs/followers/05-development/creating-followers.md`
  - `docs/followers/05-development/testing-followers.md`
  - `docs/followers/07-integration/README.md`
  - `docs/followers/07-integration/mavlink-integration.md`
  - `docs/followers/07-integration/tracker-integration.md`
- Reporting:
  - `docs/reporting/agent-ops/codex-modernization/issue-register.md`
  - `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
  - `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Behavioral Changes

- `OffboardCommander` owns fixed-rate MAVSDK Offboard publication and reports
  publish counters, intent freshness, stale-intent resets, failures, and command
  publication source.
- `submit_intent()` validates control type and exact field set, atomically
  applies accepted intent fields to the active setpoint handler, preserves the
  original intent freshness timestamp, and rejects invalid intents without
  frame-loop PX4 fallback.
- `AppController.follow_target()` no longer awaits PX4 send methods from the
  frame/tracker path. It only computes follower output and submits the latest
  `CommandIntent` to the commander.
- `connect_px4()` fails closed if the commander cannot start.
- Disconnect, shutdown, emergency cleanup, and follower health paths stop or
  expose the commander explicitly.
- `/commands/start_offboard_mode` now returns `failure` if controller startup
  reports errors or final state is not active.
- `/api/follower/setpoints-status` unwraps the concrete follower handler and
  reports commander publication truth instead of treating circuit-breaker state
  as proof of PX4 sends.
- `SetpointSender` is documented and reported as a legacy monitor, not a MAVSDK
  publisher.

## Independent Review

Three independent review slices were requested.

- PX4/MAVSDK review initially blocked closure because accepted intents were not
  applied before publish, the start-Offboard API could report success after
  controller errors, and docs still contradicted the new boundary.
- Docs/API review found stale `/api/follower/setpoints-status`,
  `mavsdk-offboard.md`, follower integration docs, and `SetpointSender`
  comments.
- Companion-reference review found drift since the previous pins:
  - MavlinkAnywhere latest tag on `origin/main`: `v3.0.14`
  - Smart Wi-Fi Manager latest tag on `origin/main`: `v2.1.14`
  - MDS latest tag on `origin/main`:
    `v5.5.23-simurgh-readonly-operator-coverage`

The OffboardCommander blockers were fixed before this checkpoint. Companion
drift is recorded under PXE-0022 and does not block this slice.

## Validation

Commands run:

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest \
  tests/unit/drone_interface/test_offboard_commander.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/test_docs_infrastructure_consistency.py -q
```

Result: 38 passed.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest \
  tests/unit/drone_interface/test_offboard_commander.py \
  tests/unit/drone_interface/test_setpoint_sender.py \
  tests/unit/drone_interface/test_px4_interface_manager.py \
  tests/integration/drone_interface/test_command_flow.py \
  tests/integration/drone_interface/test_safety_integration.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/unit/core_app/test_app_controller_gimbal_fail_closed.py \
  tests/unit/followers/test_command_intent_atomicity.py \
  tests/unit/followers/test_target_loss_safe_publication.py \
  tests/test_docs_infrastructure_consistency.py
```

Result: 197 passed.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest \
  tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py
```

Result: 13 passed.

```bash
PYTHON=/tmp/pixeagle-audit-venv/bin/python bash scripts/check_schema.sh
```

Result: schema is up to date.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m py_compile \
  src/classes/offboard_commander.py \
  src/classes/app_controller.py \
  src/classes/fastapi_handler.py \
  src/classes/setpoint_handler.py \
  src/classes/setpoint_sender.py \
  src/classes/followers/base_follower.py \
  src/classes/followers/fw_attitude_rate_follower.py \
  src/classes/followers/mc_attitude_rate_follower.py \
  src/classes/followers/mc_velocity_chase_follower.py \
  src/classes/followers/mc_velocity_position_follower.py \
  tests/unit/drone_interface/test_offboard_commander.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/test_docs_infrastructure_consistency.py
```

Result: passed.

```bash
rg -n 'Current MAVSDK dispatch source|no independent fixed-rate|future Offboard commander|Recommended future Offboard commander|current command dispatch source is `AppController\.follow_target\(\)`|frame/tracker loop coupled|SetpointHandler\.set_field\(\)|app_controller\.follow_target|Indoor testing without risk|action\.terminate\(|\bPX4Controller\b' \
  docs/drone-interface docs/followers src/classes/setpoint_sender.py src/classes/followers -S
```

Result: no matches in active drone/follower docs and touched runtime comments.

```bash
git diff --check
```

Result: passed.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest -q tests
```

Result: 1743 passed, 40 skipped.

## Evidence Limits

- No SITL, HIL, real-aircraft, deployment, or field validation was run.
- Current evidence is unit/mock/integration-level Python evidence only.
- PX4 Offboard timing, Offboard acceptance, transport latency, PX4 failsafe
  behavior, and MAVSDK disconnect behavior still need executable PX4-in-loop
  evidence under PXE-0018.

## Risks And Follow-Ups

- PXE-0035 added: repeated commander publish failures are observable but do not
  yet trigger a local commander failure policy or operator-visible abort/degrade
  transition independent of PX4 Offboard-exit detection.
- PXE-0018 remains open for headless PX4/MavlinkAnywhere validation and evidence
  artifacts.
- PXE-0022 remains open because companion repos moved to newer API/MCP/devops
  standards that must be re-reviewed before PixEagle's API/MCP phase.

## Next Slice

Continue Phase 2 with PXE-0014: MAVLink telemetry freshness. The next slice
should make MAVLink2REST timeout/retry/staleness behavior typed, tested, and
honestly documented before moving into PX4-in-loop validation.

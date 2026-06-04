# Phase 2 Rate/Cadence Truth Checkpoint

Date: 2026-05-29

## Slice

- Phase: 2, Offboard commander and safety truth
- Issue closed: PXE-0030
- Related open issues: PXE-0007, PXE-0013, PXE-0033

## Outcome

PXE-0030 is closed as a rate/config/docs truth slice.

`FOLLOWER_DATA_REFRESH_RATE` is now a telemetry refresh frequency in Hz at the
runtime boundary. `PX4InterfaceManager` validates the value, clamps it to a
safe positive range, and sleeps for `1 / rate` seconds. The old behavior used
the raw value as seconds, so the default `5` meant one telemetry update every
five seconds instead of 5 Hz.

`SETPOINT_PUBLISH_RATE_S` is now explicitly a `SetpointSender` monitor-loop
period in seconds. `SetpointSender` still validates/logs current setpoints; it
does not publish MAVSDK commands. Its status now reports:

- `sends_mavsdk_commands: false`
- `command_publication_source: app_controller.follow_target`

`CONTROL_UPDATE_RATE` is documented/schemaed as follower math/update cadence,
not MAVSDK Offboard heartbeat cadence.

The true fixed-rate independent PX4 Offboard commander remains open under
PXE-0007/PXE-0013.

## Files Changed

- `src/classes/px4_interface_manager.py`
- `src/classes/setpoint_sender.py`
- `configs/config_default.yaml`
- `configs/config_schema.yaml`
- `scripts/generate_schema.py`
- `tests/unit/drone_interface/test_px4_interface_manager.py`
- `tests/unit/drone_interface/test_setpoint_sender.py`
- `tests/integration/drone_interface/test_command_flow.py`
- `tests/integration/drone_interface/test_safety_integration.py`
- `tests/unit/test_generate_schema.py`
- `tests/test_docs_infrastructure_consistency.py`
- `tests/unit/drone_interface/__init__.py`
- `docs/drone-interface/README.md`
- `docs/drone-interface/01-architecture/README.md`
- `docs/drone-interface/01-architecture/data-flow.md`
- `docs/drone-interface/02-components/px4-interface-manager.md`
- `docs/drone-interface/02-components/setpoint-sender.md`
- `docs/drone-interface/03-protocols/mavsdk-offboard.md`
- `docs/drone-interface/07-troubleshooting/offboard-mode.md`
- `docs/followers/07-integration/README.md`
- `docs/followers/07-integration/mavlink-integration.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-05.md`

## Review Gate

Independent read-only reviewers found and helped close these blockers:

- integration tests treated `SETPOINT_PUBLISH_RATE_S` as a PX4 Offboard
  heartbeat;
- docs still implied current fixed 20 Hz command dispatch;
- `SetpointSender` docs showed the wrong AppController dispatch method;
- schema tests lacked max-bound assertions;
- runtime accepted `SETPOINT_PUBLISH_RATE_S` above the generated schema max.

All blockers were fixed before this checkpoint.

## Validation

- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m py_compile ...`
  passed for touched Python modules/tests.
- `PYTHON=/tmp/pixeagle-audit-venv/bin/python bash scripts/check_schema.sh`
  passed; schema is up to date.
- Focused PXE-0030 suite passed: 167 passed.
- Broader affected backend/Phase 2 suite passed: 237 passed.
- `PYTHON=/tmp/pixeagle-audit-venv/bin/python make phase0-check` passed:
  schema up to date and 23 passed.
- `git diff --check` passed.
- Dashboard gates passed:
  - `npm run lint -- --format unix`
  - `CI=true npm test -- --watchAll=false`
  - `npm run build`

## Evidence Notes

- No SITL, HIL, real-aircraft, or field validation was run.
- No claim is made that PixEagle now has an independent PX4 Offboard heartbeat.
- The current command dispatch path remains coupled to
  `AppController.follow_target()` and tracker/follower loop execution until
  PXE-0007 lands.

## Risks And Open Questions

- PXE-0007 remains the major flight-control architecture issue: a dedicated
  Offboard commander must own fixed-rate MAVSDK publication, command TTL,
  command age, jitter, target freshness, fail-closed hold/stop behavior, and
  operator abort semantics.
- PXE-0033 remains open for unified safety truth across CircuitBreaker,
  SetpointHandler, SafetyManager, and follower-side limit handling.
- The local system Python in this session did not have `ruamel.yaml`; validation
  used the project audit venv explicitly.

## Next Planned Slice

Continue Phase 2 with PXE-0033 safety truth, then the dedicated Offboard
commander boundary under PXE-0007/PXE-0013.

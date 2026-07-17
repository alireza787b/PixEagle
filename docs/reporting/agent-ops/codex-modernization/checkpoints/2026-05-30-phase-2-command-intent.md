# Phase 2 Command Intent Atomicity Checkpoint

Date: 2026-05-30

## Slice

- Phase: 2, Offboard commander and command-intent boundary
- Issue closed: PXE-0034
- Related open issues: PXE-0007, PXE-0013
- Next active slice: dedicated Offboard commander boundary

## Outcome

PXE-0034 is closed as the follower command-output atomicity slice.

Follower output now crosses a typed atomic boundary before the final PX4 command
dispatch path. `SetpointHandler.set_fields(...)` validates an entire staged
field snapshot before mutating live setpoint state, and returns a `CommandIntent`
with profile name, control type, source, reason, monotonic timestamp, UTC
timestamp, and the complete field snapshot.

`BaseFollower.set_command_fields(...)` is now the concrete-follower publication
path. It records the accepted `CommandIntent` and, when telemetry metadata is
available, exposes the last accepted intent or the most recent intent error.

Concrete followers no longer publish by repeatedly mutating one shared field at
a time. Incomplete or invalid atomic updates return `False`, leave the previous
valid setpoint snapshot intact, and prevent the caller from reporting successful
follower command generation.

The existing single-field helper remains as a legacy/low-level API for direct
tests and debug paths, but active follower development docs now teach only the
atomic command snapshot pattern.

## Files Changed

- `src/classes/command_intent.py`
- `src/classes/setpoint_handler.py`
- `src/classes/followers/base_follower.py`
- `src/classes/followers/fw_attitude_rate_follower.py`
- `src/classes/followers/gm_velocity_chase_follower.py`
- `src/classes/followers/gm_velocity_vector_follower.py`
- `src/classes/followers/mc_attitude_rate_follower.py`
- `src/classes/followers/mc_velocity_chase_follower.py`
- `src/classes/followers/mc_velocity_distance_follower.py`
- `src/classes/followers/mc_velocity_ground_follower.py`
- `src/classes/followers/mc_velocity_position_follower.py`
- `tests/unit/followers/test_command_intent_atomicity.py`
- `tests/unit/drone_interface/test_setpoint_handler.py`
- `tests/unit/followers/test_target_loss_safe_publication.py`
- `tests/unit/followers/test_gm_velocity_vector_control.py`
- `tests/unit/followers/test_mc_velocity_position_control.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tests/unit/core_app/test_app_controller_gimbal_fail_closed.py`
- `tests/test_docs_infrastructure_consistency.py`
- `docs/followers/README.md`
- `docs/followers/01-architecture/base-follower.md`
- `docs/followers/01-architecture/setpoint-handler.md`
- `docs/followers/02-reference/README.md`
- `docs/followers/05-development/best-practices.md`
- `docs/followers/05-development/creating-followers.md`
- `docs/followers/07-integration/README.md`
- `docs/drone-interface/02-components/setpoint-handler.md`
- `docs/developers/SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-05.md`

## Review Gate

Expert-review criteria applied locally because external subagent review was
attempted but unavailable in this session due tool usage limits. The review was
run against the same Phase 2 criteria:

- drone/PX4/MAVSDK safety: no partial follower update can silently leave stale
  command fields as a new successful command;
- GNC/follower behavior: velocity, attitude-rate, fixed-wing, and gimbal-motion
  followers publish complete command snapshots;
- backend contract hygiene: `CommandIntent` is a typed handoff object suitable
  for the upcoming commander queue;
- docs and developer experience: active guidance teaches complete command
  snapshots and guards reject stale field-by-field examples;
- regression safety: unusable external gimbal output still dispatches a zero
  velocity command through the real AppController/PX4 path.

Findings fixed before checkpointing:

- The first full backend run exposed a stale external-gimbal fail-closed test
  that still used a pre-PXE-0034 handler stub and asserted calls to
  `set_command_field(...)`. The test now asserts the atomic zero-command intent.
- Documentation examples still needed to teach `set_command_fields(...)` as the
  normal follower publication path.
- Concrete follower source needed a hygiene guard so direct single-field
  publication cannot return unnoticed.

## Validation

- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py`
  passed: 13 passed.
- `PYTHON=/tmp/pixeagle-audit-venv/bin/python bash scripts/check_schema.sh`
  passed; schema is up to date.
- Affected follower/drone-interface/docs suite passed: 261 passed.
- Targeted fail-closed and command-intent rerun passed: 8 passed.
- Full backend suite passed:
  `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest -q tests`
  produced 1729 passed, 40 skipped.
- Touched-module `py_compile` passed.
- `git diff --check` passed.

## Evidence Notes

- No SITL, HIL, real-aircraft, or field validation was run.
- No claim is made that PixEagle now has an independent PX4 Offboard heartbeat.
- No claim is made that the new `CommandIntent` queue or commander service is
  complete. PXE-0007/PXE-0013 remain active for that work.
- No dashboard validation was required for this slice because frontend code was
  not changed.

## Risks And Open Questions

- PXE-0007 remains the primary flight-control architecture risk: MAVSDK Offboard
  publication is still coupled to `AppController.follow_target()` until the
  dedicated commander boundary lands.
- PXE-0013 remains open until docs, telemetry, status output, and runtime
  behavior describe the final commander/failsafe state exactly.
- The current `CommandIntent` is an in-process handoff object. The next slice
  must decide how it enters a commander-owned queue, how freshness is enforced,
  how operator abort clears the queue, and what telemetry/event record is
  emitted for each accepted, rejected, expired, or superseded intent.
- PX4-in-loop proof is still planned under PXE-0018; this checkpoint proves
  unit/mock/integration behavior only.

## Next Planned Slice

Continue Phase 2 with PXE-0007/PXE-0013: introduce or design the dedicated
Offboard commander that consumes atomic `CommandIntent` snapshots, owns
heartbeat cadence independently of the frame loop, publishes fail-closed
commands on stale/abort/disconnect paths, and exposes truthful runtime evidence
without claiming SITL success until artifacted PX4-in-loop tests exist.

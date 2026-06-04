# Phase 2 Safety Truth Checkpoint

Date: 2026-05-29

## Slice

- Phase: 2, Offboard commander and safety truth
- Issue closed: PXE-0033
- Follow-up issue opened: PXE-0034
- Related open issues: PXE-0007, PXE-0013

## Outcome

PXE-0033 is closed as a safety-truth and fail-closed behavior slice.

PixEagle now has one shared command safety helper for finite-value validation,
field-to-limit mapping, and schema fallback limits. `SetpointHandler` and the
final PX4 command send boundary both call this path, so command values are
validated close to follower output and again immediately before MAVSDK objects
are created.

PX4 command gating no longer fails open when circuit-breaker infrastructure is
missing or raises. An unavailable circuit breaker, circuit-breaker exception,
or command audit/logging exception blocks or degrades command dispatch unless
the operator explicitly enables:

- `FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES: true`

That bypass is defaulted to `false` and documented as a bench/SITL-only escape
hatch, not a production default.

`BaseFollower.check_safety()` now treats `SafetyManager` exceptions as unsafe
emergency-stop violations. The only exception is the already explicit
circuit-breaker test bypass path, which remains visible in code and tests.

Limit truth is now centralized through `FIELD_LIMIT_MAPPING`. Pitch and roll
attitude-rate fields map to their own limits instead of the yaw-rate limit, and
deprecated yaw aliases remain tracked explicitly.

## Files Changed

- `src/classes/command_safety.py`
- `src/classes/px4_interface_manager.py`
- `src/classes/setpoint_handler.py`
- `src/classes/safety_types.py`
- `src/classes/followers/base_follower.py`
- `configs/config_default.yaml`
- `configs/config_schema.yaml`
- `docs/drone-interface/02-components/px4-interface-manager.md`
- `docs/drone-interface/02-components/setpoint-handler.md`
- `docs/drone-interface/05-configuration/safety-integration.md`
- `docs/drone-interface/06-development/testing-without-drone.md`
- `docs/followers/01-architecture/setpoint-handler.md`
- `tests/unit/drone_interface/test_px4_interface_manager.py`
- `tests/unit/drone_interface/test_setpoint_handler.py`
- `tests/unit/test_base_follower.py`
- `tests/unit/test_safety_manager.py`
- `tests/integration/drone_interface/test_safety_integration.py`
- `tests/integration/drone_interface/test_command_flow.py`
- `tests/test_docs_infrastructure_consistency.py`
- `tests/unit/core_app/test_smart_click.py`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-05.md`

## Review Gate

Independent reviewer findings fixed in this slice:

- Circuit-breaker unavailable paths were fail-open in code and tests.
- `SafetyManager` exceptions in followers returned safe status.
- The final PX4 command boundary lacked finite-value validation.
- `SetpointHandler` mapped pitch and roll attitude-rate limits through yaw.
- Docs still taught fail-open behavior, stale `Parameters.SafetyLimits`
  sources, and stale pitch/roll limit semantics.

Reviewer finding recorded as follow-up debt:

- Concrete followers still mutate shared `SetpointHandler` state field by
  field. Some call sites can ignore failed field updates, which can retain old
  field values until the final PX4 gate blocks the command. PXE-0034 tracks the
  atomic command-intent boundary needed before the dedicated Offboard commander
  owns publication.

## Validation

- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m py_compile ...`
  passed for touched Python modules/tests.
- `PYTHON=/tmp/pixeagle-audit-venv/bin/python bash scripts/check_schema.sh`
  passed; schema is up to date.
- Focused PXE-0033 suite passed: 233 passed.
- Phase 0 API/reload gate passed: 13 passed.
- `PYTHON=/tmp/pixeagle-audit-venv/bin/python make phase0-check` passed:
  schema up to date and 24 passed.
- Broader affected schema/follower hygiene suite passed: 62 passed.
- `tests/unit/core_app/test_smart_click.py` passed after Python 3.12 async test
  cleanup: 11 passed.
- Full backend suite passed: 1718 passed, 40 skipped.
- `git diff --check` passed.

## Evidence Notes

- No SITL, HIL, real-aircraft, or field validation was run.
- No claim is made that PixEagle now has an independent PX4 Offboard heartbeat.
- No claim is made that follower command production is fully atomic yet; that
  is tracked as PXE-0034.
- No dashboard validation was required for this slice because frontend code was
  not changed.

## Risks And Open Questions

- PXE-0007 remains the main flight-control architecture risk: MAVSDK Offboard
  publication is still coupled to `AppController.follow_target()` until the
  dedicated commander boundary lands.
- PXE-0034 must remove follower field-by-field mutation before the commander can
  safely consume command intents as a queue/heartbeat source.
- Legacy PX4 command methods and compatibility aliases should be reviewed during
  the command-intent/commander slice so there is no permanent duplicated command
  path.
- This slice proves mock/unit/integration behavior only. PX4-in-loop evidence
  remains planned under PXE-0018.

## Next Planned Slice

Continue Phase 2 with PXE-0034 and PXE-0007/PXE-0013: introduce an atomic
command-intent boundary for follower output, then use that contract for the
dedicated Offboard commander design/implementation.

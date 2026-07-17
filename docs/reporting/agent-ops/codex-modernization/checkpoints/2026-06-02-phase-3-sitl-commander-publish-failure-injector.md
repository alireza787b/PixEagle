# Phase 3 Checkpoint: SITL Commander Publish-Failure Injector

Date: 2026-06-02  
Slice: Phase 3, PXE-0037 sub-slice  
Status: done for the third owned fault injector; PXE-0037 remains in progress

## Scope

This sub-slice replaces the `commander_publish_failure` `manual_fault`
placeholder in the Phase 2 PX4-in-loop plan with a validation-only PixEagle
OffboardCommander failure-policy injector.

It does not run Docker, PX4, MavlinkAnywhere, MAVLink2REST, PixEagle, SITL
runtime scenarios, HIL, real aircraft, deployment, service installation, or
field tests.

No runtime SITL, MAVSDK disconnect, PX4 failsafe, HIL, or field success is
claimed from this checkpoint.

## Files Changed

- `src/classes/offboard_commander.py`
- `src/classes/app_controller.py`
- `src/classes/fastapi_handler.py`
- `tools/sitl_plans/phase2_follower_validation.json`
- `tools/sitl_plans/README.md`
- `tests/test_api_route_inventory.py`
- `tests/test_sitl_validation_contract.py`
- `tests/unit/drone_interface/test_offboard_commander.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tests/unit/core_app/test_sitl_injection_api.py`
- `docs/core-app/02-components/app-controller.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/drone-interface/02-components/offboard-commander.md`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## What Changed

- Added `OffboardCommander.inject_publish_failures_for_validation()`:
  - records bounded synthetic failed publishes under the commander publish lock;
  - uses the existing failure counter and threshold policy;
  - does not synthesize MAVSDK setpoint publishes or mutate the PX4 interface;
  - can suppress the async failure callback so AppController can await cleanup
    deterministically in the validation route.
- Added `AppController.inject_commander_publish_failure_for_validation()`:
  - refuses inactive following, missing commander, or non-running commander;
  - defaults the injected failure count to the remaining configured threshold;
  - records failures inside the active commander;
  - awaits `_handle_offboard_commander_failure()` so the response proves
    fail-closed follow-mode cleanup through the normal Offboard stop path;
  - returns before/after commander evidence, retained failure evidence, and the
    disconnect result.
- Added validation-only
  `POST /api/v1/sitl/injections/commander-publish-failure`:
  - disabled unless `PIXEAGLE_ENABLE_SITL_INJECTIONS=1`;
  - typed request and response models;
  - `operation_id`, tags, `202` success metadata, route-inventory tests;
  - shared structured `/api/v1` error envelopes and route-specific request
    validation envelopes;
  - dry-run support.
- Updated the `commander_publish_failure` scenario so it:
  - posts to the new validation route;
  - remains a gated control action unless `--allow-control-actions` is passed;
  - asserts before/after commander state, threshold crossing, retained
    `/status` failure evidence, `disconnect_result.errors == []`, and inactive
    follow mode after cleanup.
- Reduced Phase 2 dry-run `manual_fault` blockers from 3 to 2. Remaining
  blockers are MAVSDK disconnect and MAVLink2REST timeout.

## Review Gate

Independent pre-implementation reviewers agreed that the next owned route
should be:

- disabled by `PIXEAGLE_ENABLE_SITL_INJECTIONS` unless explicitly enabled;
- typed under `/api/v1`;
- routed through the existing OffboardCommander failure policy;
- blocked from starting/stopping Docker, PX4, MAVLink routing, MAVLink2REST,
  video, or services;
- asserted through concrete runtime fields, not request acceptance alone.

Reviewer concern adopted: scheduled failure cleanup could race scenario
assertions. The implementation directly awaits AppController cleanup after
recording the commander threshold crossing.

Implementation decision: this slice records synthetic failed publishes inside
the running commander rather than monkey-patching a live
`send_commands_unified()` method. That keeps the validation path deterministic
and avoids racing the heartbeat loop. True MAVSDK transport-break evidence
remains the MAVSDK disconnect slice.

Final independent recheck found no reporting alignment blockers and identified
two code/claim issues before closure:

- the route should not be described as making no MAVSDK calls at all, because
  awaited cleanup intentionally calls the normal Offboard stop path;
- a heartbeat task already waiting on the publish lock could publish after
  synthetic failures were recorded if `running=False` was not set before the
  lock was released.

Both were fixed before closure. Documentation now says the injector does not
synthesize MAVSDK setpoint publishes while cleanup still uses the normal
Offboard stop path. `OffboardCommander` now marks the failure policy under the
publish lock, and heartbeat publishes that wake after the commander is stopped
return without sending.

## Validation

Commands run:

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src pytest \
  tests/unit/drone_interface/test_offboard_commander.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/unit/core_app/test_sitl_injection_api.py \
  tests/test_api_route_inventory.py \
  tests/test_sitl_validation_contract.py \
  tests/unit/core_app/test_flow_controller_frame_freshness.py -q
```

Result: 78 passed.

After final recheck fixes, the same focused suite was re-run with the added
heartbeat-lock regression:

Result: 79 passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src \
  python tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --dry-run \
  --run-scenarios \
  --json
```

Result: passed. Dry-run reported 9 scenarios, 28 actions, 5 gated control
actions, and 2 remaining manual fault blockers. This is plan validation only,
not runtime evidence.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH python -m json.tool \
  tools/sitl_plans/phase2_follower_validation.json >/tmp/pixeagle_phase2_plan.json
```

Result: passed.

## Remaining PXE-0037 Work

PXE-0037 remains active. Next cuts:

- replace `manual_fault` placeholders for MAVSDK disconnect and MAVLink2REST
  timeout;
- automate PX4 params, ULog, and tlog collection where the runtime stack
  supports it;
- improve operator-managed PX4 image/container metadata capture;
- strengthen structured MavlinkAnywhere route/profile parsing where available;
- add trace artifacts correlating tracker output, video frame status, follower
  intent, commander acceptance/publication/failure, and PX4 observations.

## Claim Boundary

This checkpoint proves a typed, gated, unit-tested commander publish-failure
injection contract and a stricter SITL scenario plan. It proves PixEagle's
local OffboardCommander failure-policy path in unit/mock validation only. It
does not prove MAVSDK transport failure behavior, PX4 Offboard behavior,
runtime SITL success, HIL behavior, field behavior, real gimbal behavior, or
real aircraft safety.

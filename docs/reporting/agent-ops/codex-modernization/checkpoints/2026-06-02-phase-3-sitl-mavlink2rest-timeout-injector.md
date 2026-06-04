# Phase 3 Checkpoint: SITL MAVLink2REST Timeout Injector

Date: 2026-06-02  
Slice: Phase 3, PXE-0037 sub-slice  
Status: done for the fourth owned fault injector; PXE-0037 remains in progress

## Scope

This sub-slice replaces the `mavlink2rest_timeout` `manual_fault` placeholder
in the Phase 2 PX4-in-loop plan with a validation-only PixEagle-local
MAVLink2REST client timeout injector.

It does not run Docker, PX4, MavlinkAnywhere, MAVLink2REST, PixEagle, SITL
runtime scenarios, HIL, real aircraft, deployment, service installation, or
field tests.

No runtime SITL, MAVSDK disconnect, real MAVLink2REST service outage, PX4
failsafe, HIL, or field success is claimed from this checkpoint.

## Files Changed

- `src/classes/mavlink_data_manager.py`
- `src/classes/app_controller.py`
- `src/classes/fastapi_handler.py`
- `tools/sitl_plans/phase2_follower_validation.json`
- `tools/sitl_plans/README.md`
- `tests/test_api_route_inventory.py`
- `tests/test_sitl_validation_contract.py`
- `tests/unit/drone_interface/test_mavlink_data_manager.py`
- `tests/unit/core_app/test_sitl_injection_api.py`
- `docs/core-app/02-components/app-controller.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/drone-interface/02-components/mavlink-data-manager.md`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## What Changed

- Added `MavlinkDataManager.inject_timeout_for_validation()`:
  - records bounded local MAVLink2REST client timeout state;
  - can age existing telemetry stale for validation without creating fake
    prior-success history;
  - increments local connection error evidence;
  - causes PixEagle-local `_request_json()` calls to raise before
    `requests.get()` during the bounded timeout window;
  - leaves MAVLink2REST, PX4, Docker, MavlinkAnywhere, routing, and network
    interfaces running.
- Hardened `MavlinkDataManager` connection/validation status with a reentrant
  lock so injection state, polling updates, success/error counters, and
  `/status` snapshots do not race each other.
- Added `AppController.inject_mavlink2rest_timeout_for_validation()`:
  - rejects missing or unsupported `mavlink_data_manager`;
  - delegates to the manager hook;
  - returns typed injection metadata and current `mavlink_telemetry`.
- Added validation-only
  `POST /api/v1/sitl/injections/mavlink2rest-timeout`:
  - disabled unless `PIXEAGLE_ENABLE_SITL_INJECTIONS=1`;
  - typed request and response models;
  - `operation_id`, tags, `202` success metadata, route-inventory tests;
  - shared structured `/api/v1` error envelopes and route-specific request
    validation envelopes;
  - dry-run support.
- Updated the `mavlink2rest_timeout` scenario so it:
  - first asserts fresh PixEagle `mavlink_telemetry` with a real last-success
    age;
  - posts to the new validation route;
  - remains a gated control action unless `--allow-control-actions` is passed;
  - asserts stale/error `mavlink_telemetry`, preserved endpoint, exact timeout
    reason, and `validation_timeout_active = true`;
  - probes MAVLink2REST directly after injection to avoid claiming a real
    service outage.
- Reduced Phase 2 dry-run `manual_fault` blockers from 2 to 1. The remaining
  blocker is MAVSDK disconnect.

## Review Gate

Independent pre-implementation reviewers recommended this route be a
PixEagle-local timeout/freshness injector, not a service/network kill switch.
The implementation follows that decision: it validates PixEagle's local
telemetry stale/error behavior while keeping external services untouched.

Reviewer concern adopted: healthy background polling could overwrite a
once-only timeout state. The final implementation uses a bounded local timeout
window where `_request_json()` raises before HTTP, and status snapshots report
the validation timeout while the window is active.

First broad validation found one stale test assumption: the MAVLink data
manager's thread-safety test asserted the concrete lock class was
`threading.Lock()`. The implementation intentionally uses `threading.RLock()`
for nested status snapshots, so the test now checks lock protocol and
non-blocking acquire/release behavior instead of pinning the implementation
class.

Independent code/safety recheck found one closure blocker before final
approval: the first implementation could set
`last_successful_fetch_monotonic_s` when it was `None`, fabricating stale
history without a real successful PixEagle MAVLink2REST poll. Fixed before
closure: `force_stale` only ages an existing successful timestamp; a fresh
manager now reports timeout as `error` with `last_success_age_s = null`; the
Phase 2 plan now asserts fresh PixEagle telemetry before the timeout injection;
and a regression test covers the no-prior-success case.

Targeted recheck after that fix found no blockers. Residual risks remain
documented: the 5-second post-injection assertion can still fail if a runtime
scenario runner stalls beyond the timeout window, and the direct MAVLink2REST
probe proves HTTP service reachability rather than PX4/MAVLink freshness.

## Validation

Commands run:

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src python -m py_compile \
  src/classes/mavlink_data_manager.py \
  src/classes/app_controller.py \
  src/classes/fastapi_handler.py \
  tests/unit/drone_interface/test_mavlink_data_manager.py \
  tests/unit/core_app/test_sitl_injection_api.py \
  tests/test_sitl_validation_contract.py \
  tests/test_api_route_inventory.py
```

Result: passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src pytest \
  tests/unit/drone_interface/test_mavlink_data_manager.py \
  tests/unit/core_app/test_sitl_injection_api.py \
  tests/test_api_route_inventory.py \
  tests/test_sitl_validation_contract.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py -q
```

Result after the lock-test and no-fabricated-history fixes: 115 passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  tests/test_docs_infrastructure_consistency.py -q
```

Result: 24 passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH bash scripts/check_schema.sh
```

Result: passed; schema is up to date.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src \
  python tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --dry-run \
  --run-scenarios \
  --json
```

Result: passed. Dry-run reported 9 scenarios, 29 actions, 6 gated control
actions, and 1 remaining manual fault blocker. This is plan validation only,
not runtime evidence.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH python -m json.tool \
  tools/sitl_plans/phase2_follower_validation.json >/tmp/pixeagle_phase2_plan.json
```

Result: passed.

```bash
git diff --check
```

Result: passed.

## Remaining PXE-0037 Work

PXE-0037 remains active. Next cuts:

- replace the MAVSDK disconnect `manual_fault` placeholder with an owned
  automated disconnect injector or explicit evidence-import path;
- automate PX4 params, ULog, and tlog collection where the runtime stack
  supports it;
- improve operator-managed PX4 image/container metadata capture;
- strengthen structured MavlinkAnywhere route/profile parsing where available;
- add trace artifacts correlating tracker output, video frame status, follower
  intent, commander acceptance/publication/failure, telemetry freshness, and
  PX4 observations.

## Claim Boundary

This checkpoint proves a typed, gated, unit-tested MAVLink2REST local timeout
injection contract and a stricter SITL scenario plan. It proves PixEagle's
local MAVLink2REST client stale/error response path in unit/mock validation and
dry-run plan validation only. It does not prove a real MAVLink2REST service
failure, network outage, route break, MAVSDK disconnect, PX4 Offboard
behavior, runtime SITL success, HIL behavior, field behavior, real gimbal
behavior, or real aircraft safety.

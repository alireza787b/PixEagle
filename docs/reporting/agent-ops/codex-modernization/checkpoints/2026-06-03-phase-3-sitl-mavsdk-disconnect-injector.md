# Phase 3 SITL MAVSDK Disconnect Injector Checkpoint

Date: 2026-06-03  
Slice: Phase 3 / PXE-0037  
Scope: replace the last checked-in Phase 2 `manual_fault` blocker with an owned
PixEagle-local MAVSDK command-path disconnect injector.

## Summary

Completed the MAVSDK disconnect validation slice without adding an external
service, network, Docker, or PX4 kill switch. The new route proves PixEagle's
local fail-closed behavior only:

- `POST /api/v1/sitl/injections/mavsdk-disconnect` is env-gated by
  `PIXEAGLE_ENABLE_SITL_INJECTIONS=1`, typed, route-inventory tested, and
  returns `/api/v1` structured errors.
- `AppController.inject_mavsdk_disconnect_for_validation()` requires active
  follow mode plus a running `OffboardCommander`, marks `PX4InterfaceManager`
  validation-disconnected, records bounded commander publish failures, and
  awaits the normal fail-closed cleanup path.
- The hook applies at least the number of failures needed to cross the active
  commander threshold even if the caller requests a lower `failure_count`.
- Commander failures are recorded before the PX4 validation-disconnect state is
  set, which prevents the running heartbeat loop from racing the exact failure
  counters before cleanup.
- `/status` now exposes `px4_connection` so the local command-path disconnect
  is operator-visible after the injection response.
- The Phase 2 SITL plan now has zero `manual_fault` actions. The
  `mavsdk_disconnect` scenario asserts before/after PX4 command-path state,
  commander failure state, inactive following, retained `/status` failure
  evidence, and the expected failed Offboard stop error.
- Destructive scenarios now include explicit active-follow re-entry actions
  where needed so prior stop/failure scenarios do not silently poison later
  scenario evidence.

## Claim Boundary

This slice does not prove a real PX4 process outage, MAVSDK server outage,
Docker fault, MavlinkAnywhere route break, MAVLink2REST outage, network outage,
or PX4 failsafe action. It proves that PixEagle reacts fail-closed when its
local MAVSDK command path is marked disconnected.

No Docker/PX4 runtime, SITL scenario execution, HIL, real-aircraft, deployment,
service installation, or field validation was run.

## Files Changed

- `src/classes/fastapi_handler.py`
- `src/classes/app_controller.py`
- `src/classes/px4_interface_manager.py`
- `tools/sitl_plans/phase2_follower_validation.json`
- `tools/sitl_plans/README.md`
- `tests/test_api_route_inventory.py`
- `tests/test_sitl_validation_contract.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tests/unit/core_app/test_sitl_injection_api.py`
- `tests/unit/drone_interface/test_px4_interface_manager.py`
- `docs/core-app/02-components/app-controller.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/drone-interface/02-components/offboard-commander.md`
- `docs/drone-interface/02-components/px4-interface-manager.md`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

Passed:

```bash
/tmp/pixeagle-audit-venv/bin/python -m py_compile \
  src/classes/fastapi_handler.py \
  src/classes/app_controller.py \
  src/classes/px4_interface_manager.py \
  tests/unit/core_app/test_sitl_injection_api.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/unit/drone_interface/test_px4_interface_manager.py \
  tests/test_sitl_validation_contract.py \
  tests/test_api_route_inventory.py
```

Passed:

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src pytest \
  tests/unit/drone_interface/test_px4_interface_manager.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/unit/core_app/test_sitl_injection_api.py \
  tests/test_api_route_inventory.py \
  tests/test_sitl_validation_contract.py -q
```

Result: 142 passed.

Passed:

```bash
/tmp/pixeagle-audit-venv/bin/python tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --dry-run \
  --run-scenarios \
  --json
```

Result: 9 scenarios, 32 actions, 10 gated control actions, 0 manual fault
actions.

Passed:

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  tests/test_docs_infrastructure_consistency.py -q
```

Result: 24 passed.

Passed:

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH bash scripts/check_schema.sh
```

Result: schema is up to date.

Passed:

```bash
/tmp/pixeagle-audit-venv/bin/python -m json.tool \
  tools/sitl_plans/phase2_follower_validation.json >/tmp/pixeagle_phase2_plan.json
git diff --check
```

## Reviewer Notes

Pre-implementation reviewers agreed the slice must stay PixEagle-local and must
not stop PX4, Docker, routing, network interfaces, or external services. The
implementation follows that boundary by using `PX4InterfaceManager` validation
disconnect state plus `OffboardCommander` failure policy evidence.

Final safety review found no blockers. Final API/contract review found two
blockers before closure:

- under-threshold `failure_count` requests could be accepted without forcing
  cleanup;
- marking PX4 validation-disconnected before recording commander failures could
  allow a running heartbeat loop to race the exact failure counters.

Both were fixed before closure. The hook now clamps applied failures to the
threshold needed for fail-closed cleanup and records commander failures before
marking the PX4 command path validation-disconnected.

## Remaining PXE-0037 Work

- Automate PX4 params/ULog/tlog collection where the runtime stack supports it.
- Improve operator-managed stack metadata capture.
- Keep accepted SITL evidence incomplete when required PX4 logs, params,
  container metadata, route data, logs, or config snapshots are missing or
  placeholders.

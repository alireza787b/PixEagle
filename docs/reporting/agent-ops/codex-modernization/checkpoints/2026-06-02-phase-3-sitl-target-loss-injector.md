# Phase 3 Checkpoint: SITL Target-Loss Injector

Date: 2026-06-02  
Slice: Phase 3, PXE-0037 sub-slice  
Status: done for the first owned tracker-output fault injector; PXE-0037 remains in progress

## Scope

This sub-slice replaces the target-loss `manual_fault` placeholder in the
Phase 2 PX4-in-loop plan with a validation-only PixEagle tracker-output
injector. It does not run Docker, PX4, MavlinkAnywhere, MAVLink2REST, PixEagle,
SITL runtime scenarios, HIL, real aircraft, deployment, service installation, or
field tests.

No runtime SITL success is claimed from this checkpoint.

## Files Changed

- `src/classes/app_controller.py`
- `src/classes/fastapi_handler.py`
- `tools/sitl_plans/phase2_follower_validation.json`
- `tools/sitl_plans/README.md`
- `tests/test_api_route_inventory.py`
- `tests/test_sitl_validation_contract.py`
- `tests/unit/core_app/test_sitl_injection_api.py`
- `tests/unit/trackers/test_tracker_in_loop_validation.py`
- `docs/core-app/02-components/app-controller.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/followers/07-integration/tracker-integration.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## What Changed

- Added `AppController.inject_tracker_output_for_validation()`, a narrow test
  hook that refuses inactive follow mode, applies the existing
  command-freshness contract, dispatches through the existing inactive-output
  follower opt-in gate, and submits the resulting `CommandIntent` through
  `OffboardCommander`.
- Added validation-only `POST /api/v1/sitl/injections/tracker-output`:
  - disabled unless `PIXEAGLE_ENABLE_SITL_INJECTIONS=1`;
  - typed request and response models;
  - `operation_id`, tags, route-inventory metadata checks, and documented
    `202` success status;
  - structured `/api/v1` error envelope for disabled, invalid, unavailable,
    rejected, and request-body validation errors;
  - legacy route validation errors remain on the default `{detail: ...}` shape
    until the broader API migration.
- Updated `tools/sitl_plans/phase2_follower_validation.json` so the target-loss
  scenario now:
  - declares `PIXEAGLE_ENABLE_SITL_INJECTIONS=1`;
  - requires `Follower.FOLLOWER_MODE=mc_velocity_position`;
  - posts an unusable synthetic `TrackerOutput` to the validation route;
  - remains a gated control action unless `--allow-control-actions` is passed;
  - asserts inactive processed output, `mc_velocity_position_inactive_hold`,
    zero hold fields, and active `OffboardCommander` publication metadata;
  - checks post-loss setpoints and commander publication state.
- Reduced Phase 2 dry-run `manual_fault` blockers from 5 to 4. The remaining
  blockers are video stall, MAVSDK disconnect, MAVLink2REST timeout, and
  commander publish failure.
- Updated docs so developers do not interpret target loss as permission to
  pursue last-known coordinates; loss behavior must publish explicit
  hold/stop/orbit commands or request Offboard exit.

## Review Gate

Independent reviewers checked the repaired slice:

- PX4/SITL safety and evidence reviewer: no remaining safety/evidence blockers;
  control-action gating remains intact; full Phase 2 evidence still cannot be
  accepted while remaining `manual_fault` scenarios exist.
- Tracker/follower freshness reviewer: no remaining freshness or command-intent
  blockers; the injection hook uses the normal freshness, follower opt-in, and
  commander path; target-loss docs no longer suggest stale pursuit.
- API/MCP contract reviewer initially blocked closure because the route used
  FastAPI default error responses, did not declare the required injection env in
  the plan, did not assert enough command evidence, and later advertised default
  `200` success plus non-enveloped body-validation errors. Fixes landed:
  structured error envelope, required env/config declarations, command/commander
  assertions, typed success metadata, `status_code=202`, and route-specific
  request validation envelope. Final re-review found no remaining blockers.

Non-blocking API note: `dry_run=true` returns `200`; adding explicit OpenAPI
metadata for that auxiliary response can be handled in a later `/api/v1`
contract polish slice.

## Validation

Commands run:

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m py_compile \
  src/classes/app_controller.py \
  src/classes/fastapi_handler.py \
  tools/run_sitl_validation_suite.py \
  tests/unit/core_app/test_sitl_injection_api.py \
  tests/test_api_route_inventory.py \
  tests/test_sitl_validation_contract.py \
  tests/unit/trackers/test_tracker_in_loop_validation.py
```

Result: passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src pytest \
  tests/test_api_route_inventory.py \
  tests/test_sitl_validation_contract.py \
  tests/unit/core_app/test_sitl_injection_api.py \
  tests/unit/trackers/test_tracker_in_loop_validation.py -q
```

Result: 28 passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  tests/test_docs_infrastructure_consistency.py -q
```

Result: 24 passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src pytest \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/unit/core_app/test_flow_controller_frame_freshness.py \
  tests/unit/followers/test_target_loss_safe_publication.py \
  tests/unit/trackers/test_smart_tracker_freshness.py -q
```

Result: 42 passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH bash scripts/check_schema.sh
```

Result: schema up to date.

```bash
git diff --check
```

Result: passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src \
  python tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --dry-run \
  --run-scenarios \
  --json
```

Result: passed. Dry-run reported 9 scenarios, 26 actions, 3 gated control
actions, and 4 remaining manual fault blockers. This is a plan validation only,
not runtime evidence.

## Remaining PXE-0037 Work

PXE-0037 remains active. Next cuts:

- replace `manual_fault` placeholders for video stall, MAVSDK disconnect,
  MAVLink2REST timeout, and commander publish failure;
- automate PX4 params, ULog, and tlog collection where the runtime stack
  supports it;
- improve operator-managed PX4 image/container metadata capture;
- strengthen structured MavlinkAnywhere route/profile parsing where available;
- add trace artifacts correlating tracker output, follower intent, commander
  acceptance/publication, and PX4 observations.

## Claim Boundary

This checkpoint proves a typed, gated, unit-tested target-loss injection
contract and a stricter SITL scenario plan. It does not prove PX4 Offboard
behavior, runtime SITL success, HIL behavior, field behavior, real gimbal
behavior, or real aircraft safety.

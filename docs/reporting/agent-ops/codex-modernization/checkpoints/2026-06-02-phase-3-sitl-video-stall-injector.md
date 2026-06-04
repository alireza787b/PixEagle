# Phase 3 Checkpoint: SITL Video-Stall Injector

Date: 2026-06-02  
Slice: Phase 3, PXE-0037 sub-slice  
Status: done for the second owned fault injector; PXE-0037 remains in progress

## Scope

This sub-slice replaces the video-stall `manual_fault` placeholder in the
Phase 2 PX4-in-loop plan with a validation-only PixEagle frame-status
injector. It builds on the target-loss injector from
`2026-06-02-phase-3-sitl-target-loss-injector.md`.

It does not run Docker, PX4, MavlinkAnywhere, MAVLink2REST, PixEagle, SITL
runtime scenarios, HIL, real aircraft, deployment, service installation, or
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
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `docs/core-app/02-components/app-controller.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## What Changed

- Added `AppController.inject_video_stall_for_validation()`, which:
  - refuses inactive follow mode;
  - normalizes validation frame-status metadata;
  - reuses `handle_video_frame_unavailable()`;
  - preserves the existing external non-video tracker behavior;
  - returns command-intent and stable `OffboardCommander` evidence.
- Added validation-only `POST /api/v1/sitl/injections/video-stall`:
  - disabled unless `PIXEAGLE_ENABLE_SITL_INJECTIONS=1`;
  - typed request and response models;
  - typed `SITLFrameStatusSummary` response model for frame freshness evidence;
  - `operation_id`, tags, `202` success metadata, and route-inventory tests;
  - shared structured `/api/v1` error envelopes and route-specific request
    validation envelopes.
- Updated the `video_stall` scenario so it:
  - posts frame-status metadata to the validation route;
  - remains a gated control action unless `--allow-control-actions` is passed;
  - asserts video-stall freshness metadata, `mc_velocity_position_inactive_hold`,
    zero hold fields, and active `OffboardCommander` publication metadata;
  - includes a post-stall `/api/follower/setpoints-status` probe with the same
    zero hold and commander publication assertions.
- Reduced Phase 2 dry-run `manual_fault` blockers from 4 to 3. Remaining
  blockers are MAVSDK disconnect, MAVLink2REST timeout, and commander publish
  failure.

## Review Gate

Independent reviewers checked the initial video-stall slice:

- PX4/SITL safety and evidence reviewer: no blockers; route is env-gated, does
  not start/stop services, and remains a control action; full SITL success still
  requires runtime artifacts.
- API/MCP contract reviewer: no blockers; noted that `frame_status` should be
  typed before stable MCP treatment and that `dry_run=true` still returns `200`.
- Tracker/video freshness reviewer: no blockers; noted that a post-stall
  setpoints-status probe would make evidence stronger.

Hardening before closure:

- Added `SITLFrameStatusSummary` so video-stall response evidence is typed.
- Added `post_stall_setpoints` assertions mirroring the target-loss
  post-condition proof.
- Re-ran focused and Phase 0 validation.

Final recheck after hardening found no blockers. The reviewer verified the
typed frame-status response, `/api/v1` route gating, post-stall setpoint
assertions, and controller/API coverage by inspection. The reviewer shell did
not have `pytest` installed, so validation authority remains the main-shell
test runs listed below. A reporting reviewer initially read stale files while
the journal/issue-register patch was landing; the on-disk phase map, issue
register, journal, and this checkpoint were rechecked before closure.

Non-blocking API note retained from the target-loss checkpoint:
`dry_run=true` returns `200`; explicit OpenAPI metadata for auxiliary dry-run
responses can be handled in a later `/api/v1` contract-polish slice.

## Validation

Commands run:

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m py_compile \
  src/classes/fastapi_handler.py \
  tests/test_sitl_validation_contract.py
```

Result: passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src pytest \
  tests/test_api_route_inventory.py \
  tests/test_sitl_validation_contract.py \
  tests/unit/core_app/test_sitl_injection_api.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/unit/core_app/test_flow_controller_frame_freshness.py -q
```

Result: 58 passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src \
  python tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --dry-run \
  --run-scenarios \
  --json
```

Result: passed. Dry-run reported 9 scenarios, 27 actions, 4 gated control
actions, and 3 remaining manual fault blockers. This is plan validation only,
not runtime evidence.

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

Result: schema up to date.

```bash
git diff --check
```

Result: passed.

## Remaining PXE-0037 Work

PXE-0037 remains active. Next cuts:

- replace `manual_fault` placeholders for MAVSDK disconnect, MAVLink2REST
  timeout, and commander publish failure;
- automate PX4 params, ULog, and tlog collection where the runtime stack
  supports it;
- improve operator-managed PX4 image/container metadata capture;
- strengthen structured MavlinkAnywhere route/profile parsing where available;
- add trace artifacts correlating tracker output, video frame status, follower
  intent, commander acceptance/publication, and PX4 observations.

## Claim Boundary

This checkpoint proves a typed, gated, unit-tested video-stall injection
contract and a stricter SITL scenario plan. It does not prove PX4 Offboard
behavior, runtime SITL success, HIL behavior, field behavior, real gimbal
behavior, or real aircraft safety.

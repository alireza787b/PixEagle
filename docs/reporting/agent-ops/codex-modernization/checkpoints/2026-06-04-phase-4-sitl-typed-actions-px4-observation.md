# Phase 4 Checkpoint: SITL Typed Actions And PX4 Observation Gate

Date: 2026-06-04
Phase/slice: Phase 4, PXE-0042
Status: done for typed SITL control actions and fail-closed PX4 observation
artifact contract
Claim boundary: API, harness, dry-run, unit, and contract evidence only. No
PixEagle runtime stack, PX4 scenario execution, accepted SIH/Gazebo pass, HIL,
field, deployment, service-install, or real-aircraft validation was run.

## Summary

The checked-in Phase 2 SITL plan no longer drives Offboard start or operator
abort through legacy mutating `/commands/*` routes. Scenario control actions
now use typed `/api/v1/actions/offboard-start` and
`/api/v1/actions/operator-abort` resources with:

- explicit `confirm=true`;
- required `idempotency_key` for confirmed mutations;
- dry-run support;
- structured `/api/v1` error envelopes;
- per-key concurrency serialization;
- bounded process-local action records;
- local following state before/after;
- an explicit claim boundary stating that PX4-observed mode/cadence requires
  separate evidence artifacts.

Legacy `/commands/start_offboard_mode` and `/commands/cancel_activities`
remain compatibility aliases only. They now attach an `action_audit` pointer
to a process-local action record and are marked deprecated in route metadata.
New SITL, MCP, agent, and operator-control integrations should use the typed
action resources.

The SITL harness now writes `px4/offboard_observation.json`. Accepted evidence
requires both:

- MAVLink2REST PX4 autopilot HEARTBEAT with `custom_mode=393216`, autopilot
  component `1`, PX4 autopilot identity, and the MAVLink custom-mode flag set
  in `base_mode`;
- parsed tlog setpoint cadence for the same accepted PX4 system ID and
  component `1`, inside a scenario-local Offboard-start observation window,
  with at least 3 setpoint messages over at least 1 second and at least 2 Hz.

Missing tlogs, missing `pymavlink`, parse errors, malformed heartbeat
identity, mixed PX4 system IDs, missing scenario timing, or cadence outside
the scenario window keep the artifact incomplete. PixEagle local API counters
are no longer accepted as PX4-observed Offboard/cadence proof.

## Files Changed

- `src/classes/fastapi_handler.py`
  - Added `APIActionRequest`, `APIActionResponse`, `APIActionAuditEvent`, typed
    action error/response metadata, and `/api/v1/actions/*` routes.
  - Added required idempotency keys for confirmed dangerous actions and
    per-idempotency-key async locks.
  - Added stored failure records for denied precondition attempts.
  - Added deprecated metadata and action-audit pointers for legacy start/cancel
    compatibility aliases.
- `tools/run_sitl_validation_suite.py`
  - Added `px4/offboard_observation.json` artifact generation.
  - Added heartbeat identity/base-mode parsing and tlog cadence parsing.
  - Bound accepted tlog setpoints to the accepted heartbeat PX4 system and
    scenario-local Offboard-start windows.
- `tools/sitl_plans/phase2_follower_validation.json`
  - Replaced remaining legacy start/abort actions with typed action resources.
  - Added a scenario-local Offboard-start action for heartbeat/cadence
    observation.
  - Added `px4/offboard_observation.json` to the evidence contract.
- `tools/sitl_plans/gazebo_visual_validation.json`
  - Added `px4/offboard_observation.json` to the shared evidence contract.
- `tests/test_api_route_inventory.py`
  - Added typed action route inventory, OpenAPI response metadata checks, and
    deprecated legacy control route metadata checks.
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
  - Added typed action dry-run, confirmation, required idempotency, replay,
    concurrency, exception-wrapping, abort-state, and legacy-audit regressions.
- `tests/test_sitl_validation_contract.py`
  - Added heartbeat identity/base-mode, same-system tlog filtering,
    scenario-window cadence, parse-error, and no-tlog fail-closed regressions.
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `tools/sitl_plans/README.md`
  - Updated action and evidence contracts.

## Review Gate

API/MCP reviewer first pass found:

- confirmed dangerous actions could execute without idempotency keys;
- OpenAPI did not document normal `200` dry-run/replay action responses;
- legacy start/cancel aliases lacked explicit deprecated route metadata;
- denied action attempts were not stored as action records.

Fixes:

- confirmed action requests without `idempotency_key` now return structured
  `409 ACTION_IDEMPOTENCY_KEY_REQUIRED`, store a failed action record, and do
  not execute;
- action routes use response metadata that includes `200` action-resource
  responses;
- legacy start/cancel aliases are marked deprecated with explicit operation IDs
  and `legacy-commands` tags;
- confirmation/idempotency precondition failures now include an `action_id`.

Second API/MCP pass: no blockers.

PX4/SITL reviewer first pass found:

- tlog cadence was not tied to the same PX4 system as the accepted HEARTBEAT;
- heartbeat eligibility accepted numeric `base_mode` without checking the
  custom-mode flag;
- cadence was measured across the whole tlog rather than a scenario window;
- wrapped `base_mode.bits` could fail closed on common MAVLink2REST payloads.

Fixes:

- accepted heartbeat system IDs now constrain tlog setpoint target filtering;
- `base_mode.bits` is parsed and `MAV_MODE_FLAG_CUSTOM_MODE_ENABLED` is
  required;
- tlog cadence is filtered to scenario-local Offboard-start observation windows;
- the heartbeat scenario now includes its own typed Offboard-start action so
  the observation window is deliberate.

The PX4 reviewer then flagged the first window implementation as too broad
because it used the run-level finish time. This was fixed by ending each
window at the containing scenario finish, with action-finish fallback. The
reviewer returned no additional message after that final narrow fix; local
tests below cover the corrected behavior.

## Validation

Passed:

```bash
.venv/bin/python -m py_compile \
  src/classes/fastapi_handler.py \
  tools/run_sitl_validation_suite.py \
  tests/test_sitl_validation_contract.py \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py
```

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/test_sitl_validation_contract.py \
  tests/test_docs_infrastructure_consistency.py -q
```

Result: 118 passed.

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py -q
```

Result: 16 passed.

```bash
PYTHON=.venv/bin/python bash scripts/check_schema.sh
```

Result: schema up to date.

```bash
.venv/bin/python tools/run_sitl_validation_suite.py \
  --plan-file tools/sitl_plans/phase2_follower_validation.json \
  --dry-run --json
```

Result: passed dry-run, no processes started, no scenarios executed, 9
scenarios, 33 total actions, 11 control actions, 0 manual faults, plan hash
`ab69b6939a5a009f8366c7f8f917505d835cea2d1b0f263ef45e40ebcf030835`.

```bash
.venv/bin/python tools/run_sitl_validation_suite.py \
  --plan-file tools/sitl_plans/gazebo_visual_validation.json \
  --dry-run --json
```

Result: passed dry-run, no processes started, no scenarios executed, 3
scenarios, 3 GET actions, 0 control actions, 0 manual faults, plan hash
`b80f52540b1fa92a4f6bb43eef3954b7d1b243cc9eac3d22cacbff82cd4da73d`.

```bash
git diff --check
```

Result: passed.

## Not Run

- live PixEagle backend runtime
- MAVLink2REST runtime
- MavlinkAnywhere prepared route/profile runtime
- PX4 scenario execution
- accepted SIH or Gazebo runtime pass
- tracker/video runtime
- dashboard tests/build, because this slice did not touch frontend files
- HIL, field, deployment, service installation, or real aircraft

## Risks And Open Questions

- Action records are process-local and bounded; durable audit/event storage
  remains part of broader API/MCP modernization.
- Tests still call handler methods directly plus static route inventory. A
  future API slice should add FastAPI `TestClient`/OpenAPI contract tests for
  `/api/v1` resources.
- `px4/offboard_observation.json` currently parses tlog MAVLink setpoint
  cadence. ULog-level setpoint/vehicle-mode correlation remains a future
  strengthening path when a stable ULog parser contract is selected.
- Runtime accepted evidence remains open until the full stack produces
  scenario results, route/profile evidence, PixEagle logs, PX4 logs, params,
  ULog/tlog, and accepted observation artifacts.

## Next Planned Slice

Continue Phase 4 API/MCP modernization:

- typed telemetry-health semantics (PXE-0036);
- broader `/api/v1` route family extraction and structured errors (PXE-0008);
- sidecar standards reconciliation with current MavlinkAnywhere,
  `mavsdk_drone_show`, and Smart Wi-Fi Manager (PXE-0022);
- dashboard/client normalization and operator-visible stale/degraded state
  (PXE-0021/PXE-0024).

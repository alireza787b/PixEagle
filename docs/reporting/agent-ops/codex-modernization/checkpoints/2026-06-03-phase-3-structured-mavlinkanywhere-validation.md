# Phase 3 Structured MavlinkAnywhere Validation Checkpoint

Date: 2026-06-03  
Phase/slice: Phase 3, PXE-0037 closure  
Scope: Structured MavlinkAnywhere route/profile evidence for the Phase 2
PX4-in-loop validation harness

## Summary

This slice closes the remaining PXE-0037 implementation debt: the SITL harness
no longer accepts required MavlinkAnywhere outputs by string containment.
Accepted route evidence now requires structured MavlinkAnywhere API artifacts:

- `route_map/mavlink_anywhere_endpoints.json` from `/api/v1/endpoints`;
- `route_map/mavlink_anywhere_config.json` from `/api/v1/config`;
- `route_map/mavlink_anywhere_profiles_summary.json` from
  `/api/v1/profiles/summary`.

Each required local output must appear in all three sources as a full
endpoint-shaped object with MavlinkAnywhere fields. The endpoint must be
enabled, type `UdpEndpoint`, mode `normal`, and match the expected address and
port. Incidental response text, arbitrary nested `address`/`port` JSON, disabled
endpoints, and server-mode endpoints no longer satisfy the evidence contract.

The profile summary is also gated as a real MavlinkAnywhere summary:
`backend=mavlink-anywhere` and `present=true` are required for the route check
to pass.

## Companion References

Companion repositories were refreshed with `git fetch --tags origin` but not
pulled or modified.

- MavlinkAnywhere local checkout: behind `origin/main` by 10 commits.
  Structured API shapes were read from `origin/main` at `7643d4d9bc75`
  (`v3.0.14-2-g7643d4d`).
- MAVSDK Drone Show local checkout: behind `origin/main` by 114 commits after
  fetch. Latest checked `origin/main`: `2c60d8e403c4`
  (`v5.5.45-simurgh-active-tools-panel`).
- Smart Wi-Fi Manager local checkout: behind `origin/main` by 5 commits.
  Latest checked `origin/main`: `a5414fc7d7df` (`v2.1.14-2-ga5414fc`).

The MavlinkAnywhere `origin/main` API confirms:

- `GET /api/v1/endpoints` returns `{"endpoints": [...]}`;
- endpoint objects include `name`, `type`, `mode`, `address`, `port`,
  `category`, and `enabled`;
- `GET /api/v1/config` returns parsed config with the same endpoint object
  shape;
- `GET /api/v1/profiles/summary` returns a MavlinkAnywhere profile summary with
  sanitized endpoint objects and metadata.

## Files Changed

- `tools/run_sitl_validation_suite.py`
- `tools/sitl_plans/phase2_follower_validation.json`
- `tools/sitl_plans/README.md`
- `tests/test_sitl_validation_contract.py`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Behavior Added

- Added required artifact `route_map/mavlink_anywhere_endpoints.json`.
- Added `/api/v1/endpoints` to MavlinkAnywhere probe collection and core probe
  gating.
- Replaced route substring matching with structured endpoint parsing.
- Required endpoint-shaped records to include MavlinkAnywhere endpoint fields:
  `name`, `type`, `mode`, `address`, `port`, `category`, and `enabled`.
- Required each plan output to match as enabled `UdpEndpoint` in `normal` mode.
- Required matches in the endpoints, config, and profile-summary sources.
- Added profile-summary metadata gating for `backend=mavlink-anywhere` and
  `present=true`.
- Updated docs so operator preflight curls include `/api/v1/endpoints` and
  `/api/v1/config`.
- Updated tests for happy path, text-only rejection, address/port-only JSON
  rejection, disabled/server-route rejection, and profile metadata rejection.

## Review Notes

Independent review found one closure blocker before finalization: the first
structured parser rejected text-only matches but could still accept incidental
address/port-only JSON. Fixed before closure by requiring full
MavlinkAnywhere endpoint-shaped records and adding a regression test.

The final reviewer found no blockers after that fix. A remaining non-blocking
risk was that profile-summary metadata was recorded but not acceptance-gated.
That was tightened before closure: the check now requires
`backend=mavlink-anywhere` and `present=true`.

PXE-0042 remains deliberately separate: the Phase 2 plan still uses legacy
`/commands/*` start/abort actions and local PixEagle counters for some
heartbeat/setpoint evidence. That future slice must introduce typed `/api/v1`
command/action resources and parsed PX4 ULog/tlog or telemetry assertions for
Offboard mode and setpoint cadence.

## Validation

Commands run from `/home/alireza/PixEagle`:

```bash
/tmp/pixeagle-audit-venv/bin/python -m py_compile \
  tools/run_sitl_validation_suite.py \
  tests/test_sitl_validation_contract.py
```

Result: passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src \
  pytest tests/test_sitl_validation_contract.py \
  tests/sitl/test_px4_validation_harness.py -q
```

Result: 32 passed, 1 skipped.

```bash
/tmp/pixeagle-audit-venv/bin/python \
  tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --dry-run \
  --run-scenarios \
  --json
```

Result: passed; reported 9 scenarios, 32 actions, 10 gated control actions, and
0 manual fault actions. Plan hash:
`1e6bae1acc67421176119eb295e4778d0dee69d4bd4987e000a84d6f1d10be7d`.

```bash
/tmp/pixeagle-audit-venv/bin/python -m json.tool \
  tools/sitl_plans/phase2_follower_validation.json \
  >/tmp/pixeagle_phase2_plan.json
```

Result: passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src \
  pytest tests/test_api_route_inventory.py \
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

## Not Run

- Docker/PX4 runtime
- SITL scenario execution against a running stack
- HIL
- real-aircraft or motor-enabled validation
- deployment, service installation, or field validation

## Risks And Open Questions

- Structured route validation proves MavlinkAnywhere configuration evidence,
  not actual PX4 packet flow by itself. Runtime accepted evidence still needs
  complete probes, scenario results, logs, PX4 params, ULog/tlog, and container
  metadata.
- PXE-0042 remains open for typed `/api/v1` start/abort actions and PX4-level
  Offboard cadence/flight-mode evidence parsing.
- PXE-0039 is the next active Phase 3 slice: an opt-in official PX4 SIH CI
  profile. SIH should be treated as L2 control-plane evidence only, not tracker,
  visual SITL, HIL, or field evidence.

## Claim Boundary

This checkpoint proves harness contract behavior, structured MavlinkAnywhere
evidence parsing, tests/docs/reporting alignment, and safety wording. It does
not prove a real PX4/SITL run, PX4 failsafe behavior, HIL readiness, or field
readiness.

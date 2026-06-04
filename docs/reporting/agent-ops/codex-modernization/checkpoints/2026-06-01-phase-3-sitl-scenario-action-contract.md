# Phase 3 Checkpoint: SITL Scenario Action Contract

Date: 2026-06-01  
Slice: Phase 3, PXE-0037 sub-slice  
Status: done for scenario action/result contract; PXE-0037 remains in progress

## Scope

This sub-slice extends the PX4/SITL validation harness from plan/probe evidence
into a checked-in scenario action/result contract and adds explicit PX4
evidence import/metadata handling. It does not run PX4, Docker, MavlinkAnywhere,
MAVLink2REST, PixEagle, HIL, real aircraft, deployment, or field tests.

No runtime SITL success is claimed from this checkpoint.

## Files Changed

- `tools/run_sitl_validation_suite.py`
- `tools/sitl_plans/phase2_follower_validation.json`
- `tools/sitl_plans/README.md`
- `tests/test_sitl_validation_contract.py`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/drone-interface/06-development/testing-without-drone.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## What Changed

- Added `actions` to every scenario in
  `tools/sitl_plans/phase2_follower_validation.json`.
- Added `scenarios/scenario_results.json` to the required evidence contract.
- Added `--run-scenarios` to execute checked-in scenario actions against a
  running stack and write a structured result artifact.
- Added `--allow-control-actions` as an explicit operator gate. Non-GET or
  explicitly marked control actions are recorded as blocked unless this flag is
  present.
- Added action types:
  - `http_request`
  - `wait`
  - `manual_fault`
  - `operator_note`
- Added plan validation so non-manual scenarios must include a concrete JSON
  equality assertion. HTTP status and JSON field-existence checks alone are not
  accepted as flight-adjacent evidence.
- Added PX4 evidence import flags:
  - `--px4-params-file`
  - `--px4-ulog`
  - `--px4-tlog`
- Imported PX4 params are copied to `px4/params.txt`; ULog/tlog files are
  copied under `px4/ulog/` and `px4/tlog/`, with size and SHA-256 checksums in
  their manifests.
- Added `px4/container_metadata.json` to the required evidence contract and
  collect it through Docker image/container inspection when available.
- Tightened scenario assertions:
  - Offboard entry requires API success, active final state,
    `following_active=true`, and `offboard_commander.running=true`.
  - Offboard heartbeat and follower-setpoint scenarios assert concrete
    commander/follower state.
  - Operator abort requires API success and `following_active=false`.
- Kept current fault-injection gaps visible as `manual_fault` blockers. These
  make scenario evidence incomplete until replaced by automated injectors or
  explicit evidence-import steps.
- Updated docs so missing PX4 params, ULog, or tlog evidence keeps the run
  incomplete, not accepted.

## Review Gate

Independent SITL/PX4 evidence review initially blocked closure because:

- Offboard entry could pass on HTTP 200 without proving Offboard active.
- Operator abort could pass on field existence without proving following
  inactive.
- Scenario result evaluation was too shallow for flight-safety evidence.
- SITL docs allowed accepted reports with missing ULog/tlog evidence if a reason
  was provided.

Fixes landed before closure:

- The plan now asserts concrete runtime values for Offboard entry, heartbeat,
  follower setpoints, and operator abort.
- The harness rejects scenarios that have neither `manual_fault` blockers nor
  JSON equality assertions.
- Docs require PX4 params and ULog/tlog manifests with checksums for accepted
  evidence.

The same reviewer rechecked the slice and found no remaining blockers.

## Validation

Commands run:

```bash
tools/run_sitl_validation_suite.py --plan-name phase2_follower_validation --dry-run --run-scenarios --json
```

Result: passed. Dry-run reported 9 scenarios, 26 actions, 2 gated control
actions, and 5 manual fault blockers. No artifacts or services were started.

```bash
/tmp/pixeagle-audit-venv/bin/python -m py_compile tools/run_sitl_validation_suite.py
```

Result: passed.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/test_sitl_validation_contract.py tests/test_docs_infrastructure_consistency.py tests/sitl/test_px4_validation_harness.py -ra --tb=short --strict-config
```

Result: 22 passed, 1 skipped. The skipped test is the operator-gated PX4/SITL
entry point requiring `PIXEAGLE_RUN_SITL=1`.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH make phase0-check
```

Result: schema up to date; 28 passed.

## Remaining PXE-0037 Work

PXE-0037 remains active. The next implementation cuts must:

- replace `manual_fault` placeholders with owned automated fault injectors or
  explicit evidence-import steps;
- inject synthetic target loss, video stall, MAVSDK disconnect,
  MAVLink2REST timeout, and commander publish failure against a controlled SITL
  stack;
- replace explicit PX4 evidence imports with automatic PX4 params and ULog/tlog
  collection where the runtime stack supports it;
- capture PX4 image digest and live container metadata for operator-managed
  non-harness stacks, not only harness-managed execute runs or local image
  inspection;
- strengthen structured MavlinkAnywhere route/profile parsing where API
  payloads support it;
- keep accepted evidence impossible when any required artifact is missing,
  placeholder, or semantically inconsistent.

## Claim Boundary

This checkpoint proves the harness can validate and report a scenario action
schedule safely. It does not prove a runtime PX4/SITL pass, Offboard behavior in
PX4, HIL behavior, field behavior, real gimbal behavior, or real aircraft
safety.

# Phase 3 PX4 SIH CI Profile Checkpoint

Date: 2026-06-03  
Phase/slice: Phase 3, PXE-0039  
Scope: Opt-in official PX4 SIH validation profile for local development and
GitHub Actions

## Summary

This slice adds a lightweight PX4 SIH profile on top of the existing
evidence-driven SITL harness. It is intentionally narrow:

- dry-run is the default and has no runtime side effects;
- probe-only collects evidence from an already running operator-approved stack;
- execute-px4 starts only a harness-owned official PX4 SIH container through
  `tools/run_sitl_validation_suite.py --execute --allow-process-start`;
- the profile does not configure MavlinkAnywhere, start PixEagle, start
  MAVLink2REST, install services, run `configure_mavlink_router.sh`, mutate
  host routing, or touch real aircraft.

The GitHub Actions workflow is opt-in through `workflow_dispatch`, with a
scheduled dry-run. It is not attached to `push` or `pull_request`, so normal PR
CI remains free of Docker/PX4 external runtime requirements.

## Files Changed

- `.github/workflows/px4-sih-validation.yml`
- `Makefile`
- `scripts/sitl/run_px4_sih_profile.sh`
- `tests/test_sitl_validation_contract.py`
- `tests/sitl/test_px4_validation_harness.py`
- `tools/sitl_plans/README.md`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Behavior Added

- Added `scripts/sitl/run_px4_sih_profile.sh`.
  - default: `--mode dry-run`;
  - runtime modes: `--mode probe-only` and `--mode execute-px4`;
  - default image/model: `px4io/px4-sitl:v1.17.0` and `sihsim_quadx`;
  - forwards scenario execution, control-action allowance, artifact imports,
    container selectors, timeout, startup wait, and JSON output to the harness;
  - rejects `--px4-container-id` in execute-px4 mode because that selector is
    for operator-managed probe-only containers.
- Added `.github/workflows/px4-sih-validation.yml`.
  - `workflow_dispatch` inputs select mode, image, model, optional image pull,
    scenario execution, control-action allowance, probe-only artifact copying,
    container selectors, and artifact root;
  - scheduled runs execute dry-run only;
  - optional `docker pull` is separate from the harness, which still starts PX4
    with Docker `--pull=never`;
  - artifacts under `reports/sitl/**` are uploaded with `if: always()`;
  - no `push` or `pull_request` trigger is present.
- Added Make targets:
  - `make sitl-sih-dry-run`;
  - `make sitl-sih-probe`;
  - `make sitl-sih-execute-px4`.
- Added tests proving dry-run side effects, explicit runtime modes, no sudo or
  route-configuration command in the wrapper, opt-in workflow triggers,
  artifact upload, optional image pull, and Make target exposure.
- Updated SITL docs and plan docs with the SIH profile commands and claim
  boundaries.

## Review Notes

Local review found one implementation bug before closure: a `pixeagle.log`
assertion from the existing log-import test was accidentally placed inside the
new Makefile target test, where `run_dir` was out of scope. The focused suite
caught it; the assertion was moved back under the log-import test and the suite
then passed.

Two independent subagent review attempts were started for the PX4/SIH/CI
review gate, but both errored because the account hit a usage limit before any
findings were returned. Those failed attempts are not counted as completed
review evidence. Before promoting this profile to a required runtime gate, rerun
an independent review against the merged patch and at least one artifacted
runtime execution on a prepared validation runner.

## Validation

Commands run from `/home/alireza/PixEagle`:

```bash
bash -n scripts/sitl/run_px4_sih_profile.sh \
  && bash -n scripts/sitl/start_px4_sitl.sh \
  && bash -n scripts/sitl/stop_px4_sitl.sh
```

Result: passed.

```bash
/tmp/pixeagle-audit-venv/bin/python -m py_compile \
  tools/run_sitl_validation_suite.py \
  tests/test_sitl_validation_contract.py \
  tests/sitl/test_px4_validation_harness.py
```

Result: passed.

```bash
PYTHON_BIN=/tmp/pixeagle-audit-venv/bin/python \
  bash scripts/sitl/run_px4_sih_profile.sh \
  --mode dry-run \
  --run-scenarios \
  --json
```

Result: passed; output was valid JSON. It reported dry-run mode, no process
start, 9 scenarios, 32 actions, 10 gated control actions, 0 manual fault
actions, and plan hash
`1e6bae1acc67421176119eb295e4778d0dee69d4bd4987e000a84d6f1d10be7d`.

```bash
PYTHON=/tmp/pixeagle-audit-venv/bin/python make sitl-sih-dry-run
```

Result: passed; output was valid dry-run JSON.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src \
  pytest tests/test_sitl_validation_contract.py \
  tests/sitl/test_px4_validation_harness.py -q
```

Result: 36 passed, 1 skipped.

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
- PX4 SIH container execution
- SITL scenario execution against a running stack
- GitHub Actions hosted workflow execution
- HIL
- real-aircraft or motor-enabled validation
- deployment, service installation, or field validation

## Risks And Open Questions

- The workflow syntax is statically checked by tests and shell syntax checks,
  but it has not yet been executed on GitHub Actions in this workspace.
- Runtime `execute-px4` still requires the selected image to be present or
  explicitly pre-pulled. Accepted evidence must record image/container metadata
  and digest through the harness artifacts.
- Complete SIH evidence still depends on a prepared MavlinkAnywhere,
  MAVLink2REST, and PixEagle stack with route/profile data, PixEagle probes,
  scenario results, logs, PX4 params, ULog/tlog manifests, and container
  metadata.
- PXE-0042 remains open for typed `/api/v1` start/abort scenario actions and
  PX4-level Offboard mode/setpoint cadence parsing.

## Claim Boundary

This checkpoint proves the local/GitHub opt-in profile contract, dry-run
behavior, safety gates, documentation, and tests. It does not prove a real PX4
SIH run, PX4 failsafe behavior, tracker behavior, visual SITL, HIL readiness,
or field readiness.

## Next Slice

Next active slice: PXE-0040 generated RTP/UDP video receiver proof. This should
prove deterministic generated video ingest through PixEagle's existing
UDP/GStreamer path before accepting Gazebo camera evidence.

# Phase 3 PX4 Artifact Auto-Collection Checkpoint

Date: 2026-06-03  
Phase/slice: Phase 3, PXE-0037 partial  
Scope: PX4 params, ULog, tlog, and container metadata evidence automation

## Summary

This slice adds best-effort automatic PX4 evidence collection to the SITL
harness while preserving the existing safety boundary: no accepted SITL claim is
made unless the run manifest, configs, route/probe data, logs, PX4 params, and
ULog/tlog manifests exist with checksums.

Automatic collection is now supported in two modes:

- harness-owned `--execute --allow-process-start` PX4 containers, only after
  PixEagle labels and run ID verify ownership;
- operator-managed probe-only containers, only when the operator provides
  `--px4-container-name` or `--px4-container-id` plus
  `--auto-px4-container-artifacts`.

The auto path uses `docker exec` to run `find` in configured search roots and
`docker cp` to copy matching files. It does not stop containers, restart
services, mutate MavlinkAnywhere routes, command PX4, or edit files inside the
container. Operator-managed containers are never stopped by the harness.

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

- Plan-level `stack.px4.artifact_collection` declares container search roots,
  params filename patterns, ULog/tlog patterns, and per-kind file limit.
- `--px4-log` and `--pixeagle-log` import operator-managed PX4/PixEagle logs
  into the required `logs/px4_sitl.log` and `logs/pixeagle.log` artifacts.
- `--px4-container-id` identifies an operator-managed PX4 container for
  probe-only metadata and optional artifact copy.
- `--auto-px4-container-artifacts` enables read-only container artifact copy in
  probe-only only when a PX4 container selector is present.
- Harness-owned `--execute` runs attempt automatic collection only after
  `org.pixeagle.sitl.managed=true` and matching
  `org.pixeagle.sitl.run_id=<run_dir>` labels verify ownership.
- Explicit imports via `--px4-params-file`, `--px4-ulog`, and `--px4-tlog`
  remain supported and take precedence for their supplied files.
- `manifest.json` records `px4_artifact_collection` with explicit import
  counts, auto-copy state, selected container reference, and collection mode.
- ULog/tlog manifests record container source paths, copied artifact paths,
  sizes, SHA-256 checksums, and copy/find command results.
- Missing files, failed `docker exec`, failed `docker cp`, or no matching
  artifacts still produce placeholders or incomplete manifests and keep the run
  incomplete.
- Failed scenario assertions now take precedence over missing/incomplete
  artifacts in `manifest.json`; a failing safety scenario is reported as
  `failed`, not hidden as artifact-only `incomplete`.
- The Offboard heartbeat and follower-setpoint scenarios now assert PixEagle
  commander counters, successful publish metadata, finite command rate, finite
  active setpoint fields, and active publication source where current APIs
  expose them.

## Review Notes

Pre-implementation independent review flagged the non-negotiable safety rules:

- no Docker auto-copy in dry-run;
- no probe-only auto-copy without a container selector and explicit flag;
- no fallback from explicit missing evidence to an accepted auto-copy pass;
- no stopping operator-managed containers;
- no service mutation, log rotation, route edits, PX4 commands, or destructive
  Docker operations.

The implemented CLI, manifest semantics, tests, and docs follow those rules.

Final independent review found additional blockers before closure:

- scenario failures could be masked by incomplete artifact status;
- plain `--probe-only` was documented too much like accepted evidence even
  though `scenarios/scenario_results.json` is required;
- `logs/pixeagle.log` had no documented import path;
- heartbeat and follower-setpoint scenarios were too weak for their stated L2
  claims;
- the plan still uses legacy `/commands/*` start/abort routes and does not yet
  parse PX4 ULog/tlog cadence.

Fixed in this slice: scenario-failure precedence, log import flags/docs, plain
probe-only wording, stronger local commander/setpoint assertions, and tests for
numeric expectations. Tracked for later: legacy `/commands/*` migration and
PX4-level cadence/flight-mode parsing are now PXE-0042.

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

Result: 27 passed, 1 skipped.

```bash
/tmp/pixeagle-audit-venv/bin/python \
  tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --dry-run \
  --run-scenarios \
  --json
```

Result: passed; reported 9 scenarios, 32 actions, 10 gated control actions, and
0 manual fault actions.

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

- Automatic collection depends on the selected PX4 image/runtime layout. If the
  container does not expose params, ULog, or tlog files in the configured roots,
  the run correctly remains incomplete and the operator should use explicit
  imports.
- tlog files may be produced by GCS/routing tools outside the PX4 container in
  some stacks. Explicit `--px4-tlog` import remains the reliable path for those
  layouts.
- PXE-0037 is still active because MavlinkAnywhere route/profile checks are
  still string-containment based. The next slice should parse structured
  dashboard status, diagnostics, config, and profile-summary payloads.
- PXE-0042 tracks remaining L2 proof debt: replace legacy `/commands/*`
  start/abort actions with typed `/api/v1` command/action resources and add
  parsed PX4 ULog/tlog or telemetry assertions for Offboard mode and setpoint
  cadence.

## Claim Boundary

This checkpoint proves mocked harness behavior, plan validation, docs/tests
alignment, and safety gating. It does not prove a real PX4/SITL run, PX4
failsafe behavior, HIL readiness, or field readiness.

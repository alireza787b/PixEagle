# Phase 2 Checkpoint: PX4-In-Loop Validation Harness

Date: 2026-06-01  
Slice: Phase 2, PXE-0018  
Status: Complete as validation-harness foundation. Runtime scenario execution,
structured route/profile validation, image/container metadata capture, and
automatic PX4 flight-log collection remain PXE-0037.

## Scope

This slice added the checked-in PX4/SITL validation contract for PixEagle
without making any unproven SITL, HIL, field, or real-aircraft claim.

Implemented:

- a plan library under `tools/sitl_plans/`
- a harness at `tools/run_sitl_validation_suite.py`
- safe PX4 container helper scripts under `scripts/sitl/`
- opt-in pytest markers for `sitl`, `px4`, `e2e`, `hardware`, and `manual`
- CI/Make marker filters so normal gates do not start external runtimes
- docs for the evidence ladder and current operator workflow
- static contract tests for plan coverage, dry-run behavior, evidence reuse
  prevention, managed-container labeling, missing-stack incompleteness, and
  marker hygiene

## Files Changed

- `.github/workflows/tests.yml`
- `Makefile`
- `pytest.ini`
- `scripts/sitl/start_px4_sitl.sh`
- `scripts/sitl/stop_px4_sitl.sh`
- `tools/run_sitl_validation_suite.py`
- `tools/sitl_plans/README.md`
- `tools/sitl_plans/phase2_follower_validation.json`
- `tests/test_sitl_validation_contract.py`
- `tests/sitl/test_px4_validation_harness.py`
- `docs/drone-interface/04-infrastructure/README.md`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/drone-interface/06-development/testing-without-drone.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Evidence Contract

The Phase 2 plan covers these required scenarios:

- `offboard_entry`
- `offboard_heartbeat`
- `follower_setpoints`
- `target_loss`
- `video_stall`
- `mavsdk_disconnect`
- `mavlink2rest_timeout`
- `operator_abort`
- `commander_publish_failure`

The harness writes a manifest, plan copy, git/runtime versions, config
snapshots, MavlinkAnywhere route-map probes, PixEagle status/current-config and
follower-setpoint probes, MAVLink2REST probes, harness logs, PixEagle/PX4 log
slots, and PX4 params/ULog/tlog evidence slots.

Important safety behavior:

- dry-run validates only and creates no evidence directory
- probe-only collects from an already running stack and starts nothing
- execute mode requires both `--execute` and `--allow-process-start`
- execute mode starts only a pinned PX4 Docker container with `--pull=never`
- execute mode labels managed containers, rejects pre-existing container names,
  verifies the harness-owned container ID, and stops only that verified ID
- existing artifact directories are refused to prevent stale evidence reuse
- manual helper output directories must be new; fixed reused evidence paths are
  refused
- missing or placeholder evidence makes the result `incomplete`
- route/config semantic mismatches make the result `incomplete`
- the manifest claim boundary explicitly excludes HIL, field, and real-aircraft
  success

## Validation Run

Commands run:

```bash
tools/run_sitl_validation_suite.py --dry-run --json
/tmp/pixeagle-audit-venv/bin/python -m py_compile tools/run_sitl_validation_suite.py
bash -n scripts/sitl/start_px4_sitl.sh
bash -n scripts/sitl/stop_px4_sitl.sh
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/test_sitl_validation_contract.py tests/test_docs_infrastructure_consistency.py tests/sitl/test_px4_validation_harness.py -ra --tb=short --strict-config
PATH=/tmp/pixeagle-audit-venv/bin:$PATH make phase0-check
PATH=/tmp/pixeagle-audit-venv/bin:$PATH bash scripts/check_schema.sh
git diff --check
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/ -m "not sitl and not px4 and not e2e and not hardware and not manual" -ra --tb=short --strict-config
```

Results:

- dry-run JSON passed
- Python syntax check passed
- shell syntax checks passed
- focused SITL/docs/contract suite: 17 passed, 1 skipped
- `make phase0-check`: 28 passed
- schema check passed
- diff whitespace check passed
- full non-SITL backend suite: 1766 passed, 40 skipped, 1 deselected

## External References

Companion repositories were refreshed on 2026-06-01:

- MavlinkAnywhere `origin/main`: latest tag `v3.0.14`, commit `7643d4d`
- Smart Wi-Fi Manager `origin/main`: latest tag `v2.1.14`, commit `a5414fc`
- `mavsdk_drone_show`/MDS `origin/main`: latest tag
  `v5.5.36-simurgh-swarm-readiness-routing`, commit `e0f565d4`

Local companion checkouts remain behind those refs. PXE-0022 remains open so
the API/MCP/devops phase can re-review the current sidecar standards before
PixEagle migrates public APIs.

## Review Gate

Independent review previously blocked closure on:

- incomplete required evidence being able to look like a pass
- route and runtime config identity not being checked
- stale artifact directories being reusable
- execute mode being able to stop a container the harness did not start
- manual helper output being able to reuse fixed evidence directories
- the opt-in SITL pytest entry point demanding a pass while PX4 params/ULog/tlog
  evidence is intentionally placeholder-only until PXE-0037
- the hard required evidence set being weaker than the checked-in plan
- normal filters not excluding the `manual` marker
- overly broad execute-mode claim boundaries

Those blockers were fixed before closure. Remaining non-blocking debt is
tracked as PXE-0037.

## Risks And Open Questions

- PXE-0037 is required before this harness can produce accepted runtime SITL
  pass evidence automatically. Current runs with placeholder PX4 params, ULog,
  tlog, PixEagle logs, or PX4 logs correctly return `incomplete`.
- The harness starts only PX4 in guarded execute mode. MavlinkAnywhere,
  MAVLink2REST, and PixEagle startup remain operator-managed until PXE-0037 or
  a later orchestrator slice.
- No Docker/PX4 runtime, SITL scenario, HIL, field, service install, deployment,
  or real-aircraft validation was run in this slice.
- The optional unofficial `jonasvautherin/px4-gazebo-headless` path remains
  documentation-only; the checked-in plan prefers the official PX4 prebuilt
  image path.
- Structured MavlinkAnywhere route/profile parsing and image digest/container
  metadata capture should be added when PXE-0037 makes accepted runtime
  evidence fully automated.

## Next Slice

Phase 3 PXE-0019: tracker-in-loop validation.

The next slice should add deterministic synthetic scene and gimbal-provider
replay fixtures that drive tracker output into follower/control contracts. The
tests should distinguish `has_output`, `active`, `fresh`, and
`usable_for_following`, and should keep full visual SITL/X-Plane/Gazebo evidence
operator-gated unless a complete artifacted runtime stack is provided.

# Phase 0 Checkpoint - Infrastructure Docs And Guardrails

Date: 2026-04-30  
Status: completed for Phase 0 Slice 2

## Scope

This slice aligned PixEagle's source-of-truth infrastructure documentation and
low-risk startup guardrails with the approved modernization plan, current
MavlinkAnywhere behavior, and the `mavsdk_drone_show` API/MCP standards.

## Expert Review Inputs

- Docs staleness review: confirmed stale MavlinkAnywhere/MAVLink2REST split,
  old `14541`/`14551` defaults, broken docs index links, and stale entrypoints.
- Companion-project review: confirmed current MavlinkAnywhere topology and
  `mavsdk_drone_show` API/MCP conventions.
- DevOps/bootstrap review: confirmed launcher, service, config, firewall, and
  shell-validation gaps.

## Work Completed

- Rewrote `docs/drone-interface/04-infrastructure/mavlink-anywhere.md` around
  current MavlinkAnywhere install/configure/update/dashboard behavior.
- Rewrote `docs/drone-interface/04-infrastructure/mavlink-router.md` as an
  advanced manual reference that points normal installs to MavlinkAnywhere.
- Rewrote `docs/drone-interface/04-infrastructure/port-configuration.md` with
  the current app and MAVLink port matrix.
- Updated the infrastructure overview, install guide, README, and docs index.
- Rewrote PX4 and MAVLink config docs around current schema-backed keys:
  `PX4.*`, `MAVLink.*`, `Follower.USE_MAVLINK2REST`, and `Setpoint.*`.
- Rewrote MAVLink2REST API docs around `/v1/mavlink/...`.
- Corrected circuit-breaker docs to describe it as a test guard, not a
  replacement for PX4 failsafes.
- Changed `scripts/components/mavlink2rest.sh` to bind HTTP to
  `127.0.0.1:8088` by default.
- Added `bash scripts/run.sh --no-dashboard` and corrected the README's stale
  `-d` dashboard-skip claim.
- Made `scripts/run.sh` and `scripts/lib/ports.sh` fall back to
  `configs/config_default.yaml` when `configs/config.yaml` is absent.
- Fixed `scripts/service/run.sh` to point operators at `pixeagle-service logs -f`.
- Fixed `scripts/check_schema.sh` to use `$PYTHON`, then `python3`, then
  `python`.
- Added `tests/test_docs_infrastructure_consistency.py`.
- Added docs guardrails and shell syntax checks to CI.
- Added `make phase0-check`.
- Recorded remaining stale secondary docs in a dedicated audit inventory and
  issue-register entry.

## Validation

Completed:

- `bash -n install.sh scripts/init.sh scripts/run.sh scripts/stop.sh scripts/components/mavlink2rest.sh scripts/lib/ports.sh scripts/service/run.sh scripts/check_schema.sh`
  - Result: passed.
- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/test_docs_infrastructure_consistency.py tests/test_api_route_inventory.py tests/test_test_hygiene.py tests/unit/core_app/test_config_clean_clone.py tests/unit/core_app/test_parameters_reload.py -ra --tb=short --strict-config`
  - Result: 19 passed.
- `PATH=/tmp/pixeagle-audit-venv/bin:$PATH bash scripts/check_schema.sh`
  - Result: passed.
- `PYTHON=/tmp/pixeagle-audit-venv/bin/python make phase0-check`
  - Result: passed, 19 tests passed.
- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/ -ra --tb=short --strict-config`
  - Result: 1615 passed, 40 skipped, 7 warnings.
- `git diff --check`
  - Result: passed.

## Evidence Paths

- Audit inventory:
  `docs/reporting/agent-ops/codex-modernization/audits/2026-04-30-docs-infrastructure-staleness-inventory.md`
- Journal:
  `docs/reporting/agent-ops/codex-modernization/journal/2026-04.md`
- Issue register:
  `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- Offline copy:
  `/home/alireza/pixeagle_phase0_slice2_infrastructure_docs_2026-04-30.md`

## Risks And Open Items

- PXE-0012 tracks remaining stale secondary docs in SITL, hardware,
  companion-computer, custom telemetry, testing-without-drone, and
  troubleshooting guides.
- PXE-0013 tracks Offboard/safety docs that still need to be reconciled with
  current code and the future dedicated Offboard commander.
- PXE-0011 remains: full Python tests still emit 7 `PytestReturnNotNoneWarning`
  warnings from `tests/test_gimbal_vector_body.py`.
- Dashboard npm audit vulnerabilities and build warnings remain tracked as
  PXE-0009 and PXE-0010 from Slice 1.

## Plan Reconciliation

The approved plan's Phase 0 docs/MavlinkAnywhere goals are now implemented for
the source-of-truth docs, with explicit guardrails and follow-up debt tracking.
The next planned slice should finish the remaining secondary docs or move into
the Phase 1 runtime spine only after deciding whether documentation cleanup must
be fully closed first.

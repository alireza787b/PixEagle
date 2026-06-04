# Phase 0 Checkpoint - Secondary Drone-Interface Docs

Date: 2026-04-30  
Status: completed for Phase 0 Slice 3

## Scope

This slice closed PXE-0012 by reconciling secondary drone-interface docs with
the source-of-truth infrastructure and configuration baseline from Slice 2.

## Expert Review Input

- Secondary docs review: confirmed stale examples in SITL setup, hardware
  connection, companion computer setup, custom telemetry, no-drone testing, and
  troubleshooting docs.

## Work Completed

- Updated SITL docs from the old direct `mavlink-routerd`/Docker flow to the
  current MavlinkAnywhere + PixEagle wrapper flow.
- Updated hardware and troubleshooting docs from old `14541`/`14551` examples
  to current `14540`/`14569` routing.
- Replaced old `/mavlink/...` examples with `/v1/mavlink/...`.
- Replaced stale lowercase config snippets with schema-backed keys:
  `PX4.SYSTEM_ADDRESS`, `MAVLink.*`, `Safety.GlobalLimits`,
  `Setpoint.SETPOINT_PUBLISH_RATE_S`, and `FOLLOWER_CIRCUIT_BREAKER`.
- Removed stale direct `python main.py`, Docker-first MAVLink2REST,
  `localhost:8000`, and old circuit-breaker API examples from the covered docs.
- Corrected companion-computer guidance to use PixEagle service scripts,
  current AI dependency scripts, and `VideoSource.*`.
- Corrected telemetry troubleshooting to avoid documenting timeout/retry config
  that does not exist yet.
- Extended `tests/test_docs_infrastructure_consistency.py` to guard the
  secondary drone-interface docs against stale ports, paths, config keys, and
  nonexistent API examples.
- Updated the modernization journal, issue register, and docs staleness
  inventory.

## Files Changed In This Slice

- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/drone-interface/04-infrastructure/hardware-connection.md`
- `docs/drone-interface/04-infrastructure/companion-computer.md`
- `docs/drone-interface/05-configuration/safety-integration.md`
- `docs/drone-interface/06-development/adding-control-types.md`
- `docs/drone-interface/06-development/custom-telemetry.md`
- `docs/drone-interface/06-development/testing-without-drone.md`
- `docs/drone-interface/07-troubleshooting/connection-issues.md`
- `docs/drone-interface/07-troubleshooting/telemetry-gaps.md`
- `docs/drone-interface/07-troubleshooting/offboard-mode.md`
- `tests/test_docs_infrastructure_consistency.py`
- `docs/reporting/agent-ops/codex-modernization/audits/2026-04-30-docs-infrastructure-staleness-inventory.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-04.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`

## Validation

Completed:

- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/test_docs_infrastructure_consistency.py -ra --tb=short --strict-config`
  - Result: 3 passed.
- `PYTHON=/tmp/pixeagle-audit-venv/bin/python make phase0-check`
  - Result: passed; schema check passed and 20 tests passed.
- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/ -ra --tb=short --strict-config`
  - Result: 1616 passed, 40 skipped, 7 warnings.
- `git diff --check`
  - Result: passed.
- Manual stale-pattern scan across `docs/drone-interface`
  - Result: only explicit legacy notes remain in `port-configuration.md` and
    `px4-config.md`.

## Evidence Paths

- Docs guardrail:
  `tests/test_docs_infrastructure_consistency.py`
- Audit inventory:
  `docs/reporting/agent-ops/codex-modernization/audits/2026-04-30-docs-infrastructure-staleness-inventory.md`
- Journal:
  `docs/reporting/agent-ops/codex-modernization/journal/2026-04.md`
- Issue register:
  `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- Offline copy:
  `/home/alireza/pixeagle_phase0_slice3_secondary_docs_2026-04-30.md`

## Risks And Open Items

- PXE-0011 remains: full Python tests still emit 7
  `PytestReturnNotNoneWarning` warnings from `tests/test_gimbal_vector_body.py`.
- PXE-0013 remains: deeper Offboard/safety docs still need reconciliation with
  the current command heartbeat implementation and future Offboard commander.
- PXE-0014 was added: MAVLink telemetry polling timeout/retry/staleness behavior
  needs typed config/API contracts and tests.
- PXE-0009 and PXE-0010 remain for dashboard audit vulnerabilities and ESLint
  warnings.

## Plan Reconciliation

The Phase 0 documentation baseline now covers both source-of-truth and
secondary drone-interface docs for the MAVLink/MavlinkAnywhere/config topics
touched by this phase. The next Phase 0 cleanup should close test-warning and
dashboard hygiene debt before moving to the larger Phase 1 runtime spine.

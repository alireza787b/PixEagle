# Phase 0 Checkpoint - Baseline Governance

Date: 2026-04-30  
Status: completed for Phase 0 Slice 1

## Scope

Phase 0 establishes guardrails before deeper runtime and API rewrites:

- clean-clone config/import behavior
- current API route inventory
- schema drift CI
- dashboard test/build CI
- root agent operating guide
- modernization reports, journal, and issue register

## Work Completed In This Slice

- Added root `AGENTS.md`.
- Added architecture and API modernization blueprints.
- Added modernization reporting folder structure.
- Copied the approved 2026-04-29 plan into repo-local audit records.
- Started issue register and journal.
- Added clean-clone config fallback for `Parameters` and `ConfigService`.
- Added clean-clone fallback tests.
- Added a static route inventory test for current `FastAPIHandler` route registrations.
- Replaced detector/estimator audit placeholder tests with contract tests.
- Added a test hygiene guard for placeholder/audit-stub patterns.
- Isolated config persistence tests so they write to `tmp_path`, not live ignored runtime config.
- Made schema generation deterministic and changed schema check mode to avoid mutating the working tree.
- Wired schema drift, guardrail tests, stricter backend pytest, broader syntax checks, and dashboard install/test/build into CI.
- Fixed the existing dashboard smoke test so the new frontend gate can run under CI.

## Validation

Completed:

- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_test_hygiene.py tests/unit/core_app/test_config_clean_clone.py tests/unit/core_app/test_parameters_reload.py tests/unit/detectors/test_detector_contract.py tests/unit/estimators/test_estimator_contract.py -ra --tb=short --strict-config`
  - Result: 28 passed.
- `PATH=/tmp/pixeagle-audit-venv/bin:$PATH bash scripts/check_schema.sh`
  - Result: passed.
- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/integration/core_app/test_config_flow.py tests/unit/test_generate_schema.py tests/test_api_route_inventory.py tests/test_test_hygiene.py -ra --tb=short --strict-config`
  - Result: 56 passed.
- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/ -ra --tb=short --strict-config`
  - Result: 1613 passed, 40 skipped, 7 warnings.
- `npm ci`
  - Result: passed; reported 64 npm audit vulnerabilities.
- `CI=true npm test -- --watchAll=false`
  - Result: passed; emitted React Testing Library deprecation warning from old CRA/testing stack.
- `npm run build`
  - Result: passed with ESLint unused-variable warnings.

## Open Items

- PXE-0006: docs staleness inventory and stale infrastructure docs remain for a later Phase 0 slice.
- PXE-0009: dashboard dependency vulnerabilities need a planned dependency modernization pass.
- PXE-0010: dashboard build warnings need cleanup.
- PXE-0011: `tests/test_gimbal_vector_body.py` should stop returning booleans from tests.
- Phase 2 still owns the major Offboard command publisher redesign.

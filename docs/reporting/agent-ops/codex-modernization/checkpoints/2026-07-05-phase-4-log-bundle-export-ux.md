# Phase 4 Log Bundle Export UX Checkpoint

- Date: 2026-07-05
- Phase: 4
- Issue: PXE-0083
- Slice: runtime log evidence export metadata UX
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

The runtime Logs page now shows export metadata after a successful evidence
bundle download:

- filename;
- run ID;
- size;
- SHA-256 digest;
- claim boundary;
- download time.

This answers the operator question about whether the bundle can be exported and
read offline. The downloaded tarball remains an offline evidence artifact. The
live dashboard does not import, replay, or execute bundle contents in this
slice.

## Changed Files

- `dashboard/src/pages/LogsPage.js`
- `dashboard/src/pages/LogsPage.test.js`
- `src/classes/fastapi_handler.py`
- `tests/unit/core_app/test_api_exposure_policy.py`
- `docs/core-app/03-api/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
- `/home/alireza/PIXEAGLE_LOG_BUNDLE_EXPORT_UX_2026-07-05.md`

## Behavior

- `GET /api/v1/logs/sessions/{run_id}/export` already returned export
  metadata headers. The FastAPI CORS middleware now exposes them:
  - `Content-Disposition`
  - `X-PixEagle-Run-ID`
  - `X-PixEagle-Log-Export-Sha256`
  - `X-PixEagle-Log-Export-Size`
  - `X-PixEagle-Claim-Boundary`
- The dashboard reads those headers and renders a compact success panel after
  download.
- The dashboard falls back to blob size, selected run ID, and known session
  claim boundary if a deployment strips optional headers.

## Boundary

Runtime log bundles are process-local PixEagle evidence only. They are not
PX4, SITL, HIL, QGC receiver, field, follower-response, or real-aircraft proof.

No runtime log bundle import/replay/viewer was added. That future feature must
be a typed evidence contract with schema/version checks, redaction guarantees,
and clear separation from live runtime logs.

## Validation

Passed:

```bash
CI=true npm test -- --runTestsByPath src/pages/LogsPage.test.js --watchAll=false

PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_api_exposure_policy.py tests/test_api_route_inventory.py

CI=true npm run build

bash scripts/check_schema.sh

PYTHONPATH=src .venv/bin/python -m pytest tests/test_docs_infrastructure_consistency.py

PYTHONPATH=src .venv/bin/python -m py_compile src/classes/fastapi_handler.py

git diff --check
```

Results:

- Logs page tests: 5 passed;
- API exposure plus route inventory tests: 124 passed;
- production dashboard build: passed;
- schema check: passed, schema up to date;
- docs consistency tests: 23 passed;
- backend syntax check: passed;
- whitespace diff check: passed.

## Remaining Slices

- PXE-0079: final clean setup walkthrough evidence.
- PXE-0084: typed About/System/update-status.
- PXE-0085: SIH Dev/Training validation surface.
- PXE-0086: safe demo cleanup/rotation and safe update workflow.

# 2026-07-05 Phase 4 Runtime Logging Frontend Ingestion

## Phase / Slice

- Phase 4 runtime observability and evidence follow-up
- Issue: PXE-0079
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

PixEagle can now capture dashboard browser-side runtime errors into the active
runtime log session without granting log-read access to ordinary users. The new
typed route is:

```http
POST /api/v1/logs/frontend-errors
```

The route appends to the fixed `frontend` component as
`components/frontend.jsonl`. It requires authenticated `runtime:report` scope
and browser-session CSRF, while the read routes still require `debug:read`.

## Changes

- Added `runtime:report` as a write-only scope granted to viewer, operator, and
  admin roles.
- Added typed request/response contracts for bounded frontend error reports.
- Added `POST /api/v1/logs/frontend-errors` with:
  - `202 Accepted` response metadata;
  - strict request model and `extra = forbid`;
  - fixed server-owned `frontend` component;
  - server-side context byte limit;
  - per-principal rate limiting plus bounded key growth;
  - existing runtime log redaction before storage.
- Added dashboard `frontendErrorReporter` service:
  - installs global `error` and `unhandledrejection` listeners;
  - waits until auth mode is known;
  - requires `runtime:report` for browser-session clients;
  - strips query/hash values before sending URL/route fields;
  - uses the central API client so cookies, CSRF, and auth-failure handling stay
    consistent.
- Updated the Logs page so frontend error entries expose compact error name,
  route, kind, and stack diagnostics instead of hiding all browser context in
  raw `extra`.
- Regenerated the non-callable API/MCP candidate inventory. The new route is
  present as blocked, non-callable, and not MCP-exposed.
- Added `api_v1_log_routes.py` to candidate provenance because it owns runtime
  log read/report dispatch semantics.

## Validation

Passed:

```bash
PYTHONPATH=src .venv/bin/python -m py_compile \
  src/classes/api_security_types.py \
  src/classes/api_security_policy.py \
  src/classes/api_v1_paths.py \
  src/classes/fastapi_api_v1_routes.py \
  src/classes/api_v1_contracts.py \
  src/classes/api_v1_log_routes.py \
  src/classes/fastapi_handler.py

PYTHONPATH=src .venv/bin/pytest \
  tests/unit/core_app/test_runtime_logging.py \
  tests/unit/core_app/test_api_v1_log_routes.py \
  tests/test_api_security_policy.py \
  tests/test_api_route_inventory.py \
  tests/test_api_tool_candidates.py \
  tests/test_docs_infrastructure_consistency.py \
  -q

PYTHONPATH=src .venv/bin/python tools/generate_api_tool_candidates.py

cd dashboard && CI=true npm test -- --watchAll=false --runTestsByPath \
  src/services/frontendErrorReporter.test.js \
  src/services/apiClient.test.js \
  src/pages/LogsPage.test.js

bash scripts/check_schema.sh
PYTHONPATH=src .venv/bin/pytest tests/unit/core_app/test_parameters_reload.py -q
cd dashboard && npm run build
git diff --check
```

Observed results:

- backend log/security/route/candidate/docs focused gate: 113 tests passed;
- dashboard frontend reporter/API client/Logs page tests: 12 tests passed.
- schema check reported up to date;
- parameter reload tests: 10 passed;
- dashboard production build passed as `main.c2803765.js`;
- whitespace diff check passed.

Live demo restart/smoke passed:

- restarted the existing public quick demo without rotating credentials;
- active run: `pixeagle_20260705T023426Z_785310`;
- local dashboard returned HTTP 200;
- public dashboard `http://204.168.181.45:3040/` returned HTTP 200;
- unauthenticated `GET /api/v1/logs/status` returned HTTP 401;
- unauthenticated `POST /api/v1/logs/frontend-errors` returned HTTP 401;
- dashboard `asset-manifest.json` references `main.c2803765.js`;
- active runtime manifest lists `backend`, `main_app`, and `dashboard`.
  `frontend.jsonl` is created when an authenticated browser error is reported.

## Review Closure

Read-only review agreed with the typed endpoint, write-only scope, CSRF, fixed
component, and central dashboard API client approach. Reviewer notes adopted in
this slice:

- do not let browsers choose the runtime log component;
- add log-route dispatcher provenance to the generated candidate inventory;
- avoid reporting before auth mode is known;
- strip URL query/hash values before sending reports;
- cap server-side rate-limit bucket growth.

## Claim Boundary

Frontend runtime reports are process-local PixEagle diagnostic evidence only.
They do not prove PX4, SITL, HIL, QGC receiver, MAVLink routing, deployment
hardening, field behavior, or real-aircraft behavior. Security audit remains a
separate subsystem.

## Next Planned Slice

- PXE-0079 live log streaming/export evidence bundle.
- PXE-0074/PXE-0068 clean setup/update walkthrough and public demo credential
  cleanup after user testing.

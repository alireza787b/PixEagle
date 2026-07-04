# 2026-07-04 Phase 4 Runtime Logging Foundation

## Phase / Slice

- Phase 4 runtime observability and evidence foundation
- Issue: PXE-0079
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

PixEagle now has a durable backend runtime logging foundation and a restricted
operator/debug view. The implementation follows useful ideas from
`mavsdk_drone_show` - session IDs, JSONL, retention, redaction, and UI/API
access - but keeps PixEagle's security audit and flight-evidence boundaries
separate.

## Changes

- Added `RuntimeLogSessionManager` in `src/classes/runtime_logging.py`.
- Backend startup configures runtime logging from `src/main.py`.
- `scripts/run.sh` exports one `PIXEAGLE_RUN_ID` and
  `PIXEAGLE_RUNTIME_LOG_DIR` for a launched run.
- Direct `scripts/components/main.sh` now runs from the repo root and uses an
  absolute default runtime-log path.
- Runtime sessions write:

```text
logs/runtime/<run_id>/
  manifest.json
  components/backend.jsonl
```

- Added read-only typed API routes:
  - `GET /api/v1/logs/status`
  - `GET /api/v1/logs/sessions`
  - `GET /api/v1/logs/sessions/{run_id}`
- Log routes require `debug:read`, not generic `system:read`.
- Run IDs and component names reject dot-only and path-like values.
- Write-time and read-time redaction cover common credentials, including
  Authorization, Cookie, Set-Cookie, CSRF, password, token, secret, and URL
  credentials.
- Active backend log writing uses bounded rotation.
- Invalid level filters return typed `422` errors instead of failing open.
- Added dashboard `Backend Runtime Logs` navigation/page with active session,
  retained sessions, component/minimum-level filters, bounded entries, and
  process-local evidence boundary.
- Logs navigation is hidden for browser-session users without `debug:read`.

## Files Changed

- `src/classes/runtime_logging.py`
- `src/classes/api_v1_log_routes.py`
- `src/classes/api_v1_contracts.py`
- `src/classes/api_v1_paths.py`
- `src/classes/fastapi_api_v1_routes.py`
- `src/classes/fastapi_handler.py`
- `src/classes/api_security_policy.py`
- `src/main.py`
- `scripts/run.sh`
- `scripts/components/main.sh`
- `dashboard/src/App.js`
- `dashboard/src/components/NavigationDrawer.js`
- `dashboard/src/pages/LogsPage.js`
- `dashboard/src/pages/LogsPage.test.js`
- `dashboard/src/services/apiEndpoints.js`
- `tests/unit/core_app/test_runtime_logging.py`
- `tests/unit/core_app/test_api_v1_log_routes.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_security_policy.py`
- `docs/apis/api-security-policy.md`
- `docs/core-app/02-components/logging-manager.md`
- `docs/core-app/03-api/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

Passed:

```bash
PYTHONPATH=src .venv/bin/pytest \
  tests/unit/core_app/test_runtime_logging.py \
  tests/unit/core_app/test_api_v1_log_routes.py \
  tests/test_api_security_policy.py \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  -q

bash -n scripts/run.sh scripts/components/main.sh

.venv/bin/python -m py_compile \
  src/classes/runtime_logging.py \
  src/classes/api_v1_log_routes.py \
  src/classes/api_security_policy.py \
  src/classes/api_security_types.py \
  src/main.py

CI=true npm test -- --watchAll=false --runTestsByPath src/pages/LogsPage.test.js

bash scripts/check_schema.sh

.venv/bin/python tools/generate_api_tool_candidates.py

PYTHONPATH=src .venv/bin/pytest \
  tests/test_api_tool_candidates.py \
  tests/test_docs_infrastructure_consistency.py \
  tests/unit/core_app/test_runtime_logging.py \
  tests/unit/core_app/test_api_v1_log_routes.py \
  tests/test_api_security_policy.py \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  -q

CI=true npm test -- --watchAll=false

npm run build

git diff --check
```

Observed results:

- backend/API/security route/config gate: 82 tests passed;
- dashboard Logs page test: 1 test passed;
- shell syntax and Python compile checks passed.
- schema check reported up to date;
- generated API/MCP candidate inventory includes the three log routes as
  blocked, unregistered, non-callable, and unexposed;
- broader Python governance/docs/logging gate: 115 tests passed;
- full dashboard suite: 24 suites, 138 tests passed;
- production dashboard build passed as `main.e0a87d66.js`;
- whitespace diff check passed.

## Independent Review Closure

Backend/API review found blockers: dot-only run IDs, incomplete redaction,
read-time unredacted returns, generic `system:read` access, active log growth,
and invalid level fail-open behavior. These were fixed before validation.

Frontend/operator review found non-blocking clarity issues: backend-only capture
was not explicit, level filter meant minimum severity, long run IDs could stress
mobile headers, and direct `main.sh` could place relative logs under caller cwd.
These were fixed before validation.

## Claim Boundary

Runtime logs are process-local PixEagle evidence only. They do not prove PX4,
SITL, HIL, QGC receiver, MAVSDK/MAVLink2REST routing, field behavior,
deployment hardening, or real-aircraft behavior. Security-audit JSONL remains
separate.

## Remaining PXE-0079 Work

- Capture dashboard process stdout/stderr into the same run ID.
- Capture selected sidecar stdout/stderr when sidecars are enabled.
- Add frontend error ingestion with redaction and rate limits.
- Add live log streaming only after the static read path remains stable.
- Add an export/evidence bundle that includes manifests and bounded logs.
- Exercise the feature from a fresh setup walkthrough before final handoff.

## Next Slice

After this foundation is committed and the live demo is refreshed, continue one
of these based on maintainer priority:

1. PXE-0079 follow-up for frontend error ingestion and evidence export.
2. PXE-0074 clean setup/update walkthrough.
3. Public-demo retest cleanup: stop/rotate/delete the temporary HTTP credential
   and firewall exposure after the user finishes testing.

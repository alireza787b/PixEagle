# Phase 4 Runtime Logging Evidence Export

- Date: 2026-07-05
- Issues: PXE-0079
- Branch: `codex/modernization-pxe0040-runtime-20260604`
- Slice status: implementation complete; focused validation and live demo smoke
  passed

## Summary

PixEagle runtime logging now has a sanitized, admin/debug-scoped evidence export
for retained runtime sessions. The new route is:

- `GET /api/v1/logs/sessions/{run_id}/export`

It returns a temporary `application/gzip` tarball containing:

- `README.txt`;
- session `manifest.json`;
- sanitized `components/*.jsonl` files;
- `export_manifest.json` with exported component files and skipped malformed
  JSONL line counts.

The response includes `Cache-Control: no-store`, the exported run ID, bundle
size, SHA-256 digest, and the runtime-log claim boundary. Temporary archive
files are removed by the response background cleanup hook after serving.

## Safety And Security Boundary

- Export requires the same `debug:read` scope as runtime log reads.
- Viewer/operator roles remain unable to read or export runtime logs by default.
- The default quick-demo admin account can use the Logs page export for
  maintainer diagnostics.
- Browser frontend error reporting remains write-only through `runtime:report`
  and does not grant log-read or export access.
- Security audit events remain outside runtime log exports.
- Runtime exports are PixEagle process-local diagnostics only. They are not PX4,
  SITL, HIL, QGC receiver, follower-response, field, or real-aircraft proof.

## Files Changed

- `src/classes/runtime_logging.py`
- `src/classes/api_v1_log_routes.py`
- `src/classes/api_v1_contracts.py`
- `src/classes/api_v1_paths.py`
- `src/classes/fastapi_api_v1_routes.py`
- `src/classes/fastapi_handler.py`
- `src/classes/api_security_policy.py`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/pages/LogsPage.js`
- `dashboard/src/pages/LogsPage.test.js`
- `tests/unit/core_app/test_runtime_logging.py`
- `tests/unit/core_app/test_api_v1_log_routes.py`
- `tests/test_api_security_policy.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `docs/core-app/02-components/logging-manager.md`
- `docs/core-app/03-api/README.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`

## Validation

Passed:

```bash
PYTHONPATH=src .venv/bin/python -m py_compile src/classes/runtime_logging.py src/classes/api_v1_log_routes.py src/classes/api_v1_contracts.py src/classes/api_v1_paths.py src/classes/fastapi_api_v1_routes.py src/classes/fastapi_handler.py src/classes/api_security_policy.py tools/generate_api_tool_candidates.py
PYTHONPATH=src .venv/bin/pytest tests/unit/core_app/test_runtime_logging.py tests/unit/core_app/test_api_v1_log_routes.py tests/test_api_security_policy.py tests/test_api_route_inventory.py -q
cd dashboard && CI=true npm test -- --watchAll=false --runTestsByPath src/pages/LogsPage.test.js
PYTHONPATH=src .venv/bin/python tools/generate_api_tool_candidates.py
PYTHONPATH=src .venv/bin/pytest tests/test_api_tool_candidates.py tests/test_docs_infrastructure_consistency.py -q
bash scripts/check_schema.sh
PYTHONPATH=src .venv/bin/pytest tests/unit/core_app/test_parameters_reload.py -q
cd dashboard && npm run build
```

Observed results:

- Python compile passed.
- Backend route/security/inventory focused gate: 84 passed.
- Dashboard Logs page focused gate: 2 passed.
- API candidate/docs focused gate: 33 passed.
- Schema check reported up to date.
- Parameter reload gate: 10 passed.
- Dashboard production build passed as `main.97292de5.js`.

Live demo restart/smoke passed without rotating the existing demo password:

- active runtime run: `pixeagle_20260705T025407Z_795121`;
- local dashboard returned HTTP 200;
- public dashboard `http://204.168.181.45:3040/` returned HTTP 200;
- served dashboard manifest references `./static/js/main.97292de5.js`;
- unauthenticated `GET /api/v1/logs/sessions/{run_id}/export` returned HTTP
  401;
- authenticated login using the private handoff credential returned HTTP 200;
- authenticated export returned HTTP 200;
- `X-PixEagle-Log-Export-Sha256` matched the downloaded bundle hash;
- `X-PixEagle-Log-Export-Size` matched the downloaded bundle size;
- archive listing contained `README.txt`, `manifest.json`,
  `export_manifest.json`, `components/backend.jsonl`,
  `components/dashboard.jsonl`, and `components/main_app.jsonl`.

## Reviewer Notes

Internal review stance for this slice:

- The export must not include raw security-audit records.
- The browser must not choose export paths or components directly.
- Run IDs remain path-safe and are validated before filesystem access.
- The archive contains sanitized JSONL only; malformed lines are skipped and
  counted in `export_manifest.json`.
- The generated API/MCP inventory records the route as blocked, non-callable,
  and not MCP-exposed.

## Remaining PXE-0079 Work

- Live log streaming/tail behavior for active component logs.
- Final clean setup/update walkthrough evidence under PXE-0068/PXE-0074 after
  the current public demo session is no longer needed.

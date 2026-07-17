# 2026-06-26 Phase 4 Legacy Config Defaults-Sync Boundary

## Phase / Slice

- Phase 4 API/MCP modernization
- Issue: PXE-0008 partial
- Scope: behavior-preserving extraction of legacy `/api/config/defaults-sync*`
  helper logic from `FastAPIHandler` without changing public routes, security
  policy, config mutation semantics, or adding runtime MCP/tool exposure.

## Summary

- Added `src/classes/api_legacy_config_sync.py`.
- Moved legacy defaults-sync request model and pure helper logic out of the
  handler:
  - `ConfigSyncOperation`
  - `ConfigSyncPlanRequest`
  - `build_defaults_sync_report()`
  - `build_defaults_sync_plan()`
- `FastAPIHandler` imports helpers and keeps existing route registration
  unchanged, legacy response payload shape unchanged, and defaults-sync apply
  execution/save/rollback/reload behavior in place.
- Added static API guardrails and direct helper tests.
- Added `src/classes/api_legacy_config_sync.py` to generated API/MCP candidate
  provenance after independent review found the initial extraction only updated
  the `fastapi_handler.py` hash.
- Updated API modernization blueprint and reports.
- Recorded independent API review recommendation for next PXE-0008 slice:
  extract `/api/models/*` and `/api/yolo/*` model route bodies into a helper
  without changing routes, aliases, or auth/security policy.

## Files Changed

- `src/classes/api_legacy_config_sync.py`
- `src/classes/fastapi_handler.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `tests/unit/core_app/test_api_legacy_config_sync.py`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-26-phase-4-legacy-config-sync-boundary.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- `.venv/bin/python -m py_compile src/classes/fastapi_handler.py src/classes/api_legacy_config_sync.py tests/unit/core_app/test_api_legacy_config_sync.py`
  passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_api_legacy_config_sync.py tests/test_api_route_inventory.py tests/test_api_security_policy.py`
  passed: 51 tests.
- `.venv/bin/python -m py_compile src/classes/fastapi_handler.py src/classes/api_legacy_config_sync.py tools/generate_api_tool_candidates.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/unit/core_app/test_api_legacy_config_sync.py`
  passed after provenance hardening.
- `.venv/bin/python tools/generate_api_tool_candidates.py` updated the
  non-callable API/MCP candidate inventory source hash for
  `src/classes/fastapi_handler.py` and added
  `src/classes/api_legacy_config_sync.py` to generated provenance.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_api_legacy_config_sync.py tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/test_api_tool_candidates.py`
  passed: 60 tests after provenance hardening.
- `git diff --check` passed.
- `PYTHON=.venv/bin/python make phase0-check` passed with schema current,
  API/MCP candidate inventory current, and 380 tests passing with the existing
  Starlette/httpx warning.

## Evidence Boundary

- This slice proves import syntax, helper behavior, static route inventory, and
  route-security policy coverage only.
- It does not add `/api/v1/config`, retire legacy
  `/api/config/defaults-sync*`, change config mutation behavior, expose MCP
  tools, run PX4/SITL/HIL, perform service/deployment work, or claim
  field/real-aircraft behavior.

## Remaining API Work

1. Extract legacy `/api/models/*` and `/api/yolo/*` bodies into
   `api_legacy_model_routes.py` with route inventory/security unchanged.
2. Continue legacy config mutation/apply extraction only after focused
   rollback/save/reload tests.
3. Add typed `/api/v1/config/*` contracts only in a separate design slice with
   structured errors, deprecation tracking, and MCP non-promotion evidence.

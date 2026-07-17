# 2026-06-26 Phase 4 Legacy Model Route Boundary

## Phase / Slice

- Phase 4 API/MCP modernization
- Issue: PXE-0008 partial
- Scope: behavior-preserving extraction of legacy `/api/models/*` and
  deprecated `/api/yolo/*` route bodies from `FastAPIHandler` without changing
  public route registration, route security policy, response payload shape, or
  model-manager behavior.

## Summary

- Added `src/classes/api_legacy_model_routes.py`.
- Moved model-management helper and route-body logic out of `FastAPIHandler`:
  - runtime/configured model discovery helpers;
  - active-model summary builder;
  - label pagination/search;
  - standby SmartTracker model persistence;
  - model file download, switch, upload, download, and delete handlers.
- `FastAPIHandler` keeps the same `/api/models/*` and `/api/yolo/*`
  registrations and delegates public handler methods to the helper.
- Added static route-inventory guardrails preventing model/yolo route bodies
  and helper strings from drifting back into `FastAPIHandler`.
- Added direct helper tests for active-model summary shape, runtime model
  resolution through NCNN sibling naming, force-rescan propagation, label
  search/pagination, and NCNN standby-path preference.
- Added the helper to generated non-callable API/MCP candidate provenance and
  expanded candidate tests accordingly.

## Files Changed

- `src/classes/api_legacy_model_routes.py`
- `src/classes/fastapi_handler.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `tests/unit/core_app/test_api_legacy_model_routes.py`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-26-phase-4-legacy-model-route-boundary.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- `.venv/bin/python -m py_compile src/classes/fastapi_handler.py src/classes/api_legacy_model_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/unit/core_app/test_api_legacy_model_routes.py tools/generate_api_tool_candidates.py`
  passed.
- `.venv/bin/python tools/generate_api_tool_candidates.py` regenerated the
  non-callable API/MCP candidate inventory with
  `src/classes/api_legacy_model_routes.py` in source provenance.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_api_legacy_model_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py`
  passed: 62 tests.
- `git diff --check` passed.
- `PYTHON=.venv/bin/python make phase0-check` passed with schema current,
  API/MCP candidate inventory current, and 381 tests passing with the existing
  Starlette/httpx warning.

## Evidence Boundary

- This slice proves helper syntax, direct helper behavior, static route
  inventory, route-security policy coverage, and generated candidate provenance.
- It does not add `/api/v1/models/*`, retire `/api/yolo/*`, change model
  upload/download/switch/delete behavior, add runtime MCP tools, run PX4/SITL/
  HIL, perform service/deployment work, or claim field/real-aircraft behavior.

## Remaining API Work

1. Continue legacy config mutation/apply extraction only after focused
   rollback/save/reload tests.
2. Extract recording, OSD, GStreamer, follower, safety, and video/media route
   bodies with route inventory/security unchanged.
3. Add typed `/api/v1/models/*` contracts only in a separate design slice with
   structured errors, deprecation tracking, and MCP non-promotion evidence.

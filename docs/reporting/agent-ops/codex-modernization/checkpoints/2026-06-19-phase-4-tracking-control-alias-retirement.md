# 2026-06-19 Phase 4 Tracking/Control Alias Retirement

## Phase / Slice

- Phase 4 API/MCP modernization
- Issue: PXE-0064 production remote hardening and legacy mutation retirement
- Scope: retire the remaining tracking/control `/commands/*` compatibility
  aliases after typed `/api/v1/actions/*` replacements and dashboard migration.

## Summary

- Removed public FastAPI HTTP registration for:
  - `POST /commands/start_tracking`
  - `POST /commands/stop_tracking`
  - `POST /commands/redetect`
  - `POST /commands/toggle_segmentation`
  - `POST /commands/toggle_smart_mode`
  - `POST /commands/smart_click`
- Removed the six alias handler methods from `FastAPIHandler`.
- Kept the internal `_execute_*` methods used by typed action dispatchers, so
  `/api/v1/actions/tracking-start`, `/api/v1/actions/tracking-stop`,
  `/api/v1/actions/tracking-redetect`, `/api/v1/actions/segmentation-toggle`,
  `/api/v1/actions/smart-mode-toggle`, and `/api/v1/actions/smart-click` remain
  intact.
- Removed the `legacy_commands` security-policy rule and the unused
  `LOCAL_LEGACY_CONTROL` policy. Retired tracking/control command paths now
  resolve to `DENY_UNCLASSIFIED`.
- Updated route inventory from 59 POST routes to 53 POST routes.
- Regenerated the generated API/MCP candidate inventory. `/api/v1` candidate
  count remains 25 and read-only candidate count remains 7; total declared HTTP
  routes dropped from 137 to 131.
- Updated active README, setup, API/security/exposure/component/config, SITL,
  video, issue-register, phase-slice-map, and journal resume notes so they no
  longer say the tracking/control aliases remain callable or list alias
  retirement as future work.

## Files Changed

- `src/classes/fastapi_handler.py`
- `src/classes/api_security_policy.py`
- `src/classes/api_v1_contracts.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_security_policy.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tests/unit/core_app/test_sitl_injection_api.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `README.md`
- `docs/CONFIGURATION.md`
- `docs/INSTALLATION.md`
- `docs/WINDOWS_SETUP.md`
- `docs/apis/api-exposure-boundary.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/apis/api-security-policy.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/video/04-streaming/websocket.md`
- `docs/video/04-streaming/webrtc.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `tools/sitl_plans/README.md`

## Validation

- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/unit/core_app/test_sitl_injection_api.py tests/unit/core_app/test_app_controller_offboard_safety.py -q`
  - Result: 172 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/test_docs_infrastructure_consistency.py tests/test_api_tool_candidates.py tests/test_test_hygiene.py tests/unit/core_app/test_sitl_injection_api.py tests/unit/core_app/test_app_controller_offboard_safety.py -q`
  - Result after reviewer fixes: 205 passed.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`
  - Initial result: failed only for expected source-hash and declared-route-count
    drift after removing six routes.
- `.venv/bin/python tools/generate_api_tool_candidates.py`
  - Result: regenerated `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`
  - Result: current.
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`
  - Result: schema current, 41 sections, 549 parameters.
- `.venv/bin/python -m py_compile src/classes/fastapi_handler.py src/classes/api_security_policy.py src/classes/api_v1_contracts.py`
  - Result: passed.
- `git diff --check`
  - Result: passed after reviewer fixes.
- `PYTHON=.venv/bin/python make PYTHON=.venv/bin/python phase0-check`
  - Result: schema current, API tool candidate inventory current, 247 passed
    with the existing Starlette/httpx `TestClient` deprecation warning.

## Independent Review

- API/security reviewer confirmed the six aliases are removed from FastAPI
  registration and security policy, typed `/api/v1/actions/*` replacements are
  intact, and tests no longer imply the aliases are callable. The reviewer found
  stale active docs in API, SITL, and security guidance; those were fixed.
- Docs/reporting reviewer found that active README/setup/exposure/video docs
  still listed alias retirement as a remaining gate, the active phase-slice
  resume text lagged the new row, the older 2026-06-17 journal entry needed a
  supersession note, and one API sentence could imply current callable MCP/agent
  action control. Those issues were fixed.

## Evidence Boundary

- No service install/start, deployment, Docker/PX4/SITL/HIL, QGC branch
  mutation/build, sidecar mutation, runtime MCP endpoint, callable tool
  exposure, field test, or real-aircraft control was performed or claimed.
- This slice proves source-level route retirement plus focused Python guardrails.
  It does not prove runtime browser, QGC, PX4, SITL, HIL, or field behavior.
- Historical checkpoint files from 2026-06-16 and 2026-06-17 still describe the
  temporary alias state that existed on those dates. Active docs and resume
  anchors now point to this retirement slice.

## Risks / Open Questions

- PXE-0064 remains open for operator credential/TLS hardening and broader
  adversarial browser-session/media tests.
- Deprecated `/api/yolo/*` aliases remain intentionally local-only and are
  tracked separately from tracking/control alias retirement.
- `/commands/quit` remains a local-only process-administration route and is not
  an operator control/tracking API.

## Next Planned Slice

- Continue Phase 4 hardening with PXE-0064 adversarial browser/session/media
  tests and operator credential/TLS hardening, unless PXE-0068 production
  remote-profile setup hardening is selected first based on risk ordering.

# 2026-06-17 Phase 4 Typed Tracking Utility Actions

## Slice

PXE-0064 partial: replace the remaining first-party tracking utility command
callers with typed `/api/v1/actions/*` resources while retaining the legacy
routes as local-only compatibility aliases until the alias-retirement gate.

## Completed

- Added typed action resources:
  - `POST /api/v1/actions/tracking-redetect`
  - `POST /api/v1/actions/segmentation-toggle`
  - `POST /api/v1/actions/smart-mode-toggle`
  - `POST /api/v1/actions/smart-click`
- Added canonical path constants, route specs, typed smart-click request
  contract, route inventory coverage, typed error-envelope coverage, and
  non-callable API/MCP candidate inventory entries.
- Implemented action records with dry-run, confirmation, required
  idempotency keys for confirmed mutations, per-key serialization, idempotent
  replay, local runtime state capture, and explicit failure classification.
- Migrated first-party dashboard callers for redetect, segmentation toggle,
  smart-mode toggle, and smart-click to the typed action resources.
- Kept `/commands/redetect`, `/commands/toggle_segmentation`,
  `/commands/toggle_smart_mode`, and `/commands/smart_click` as local-only
  compatibility aliases pending the alias-retirement slice.
- Fixed reviewer-found smart-click truthfulness debt:
  - `AppController.handle_smart_click()` now returns explicit applied/not
    applied detail;
  - the FastAPI executor validates finite in-frame coordinates and returns
    `applied: true` only when a target override is applied;
  - the typed action classifier records no-target smart-clicks as
    `status: "failure"` instead of false success.
- Fixed typed action replay semantics so idempotent replay is checked after
  dry-run and confirmation validation.
- Aligned dashboard scope gates with backend action policy by using
  `actions:execute` for typed tracking utility actions.
- Added visible smart-click failure feedback in the video overlay.
- Updated active API/security/exposure/core docs, generated API/MCP candidate
  inventory, route inventory counts, phase map, and issue register.

## Files Changed

- Backend/API:
  - `src/classes/api_v1_actions.py`
  - `src/classes/api_v1_contracts.py`
  - `src/classes/api_v1_paths.py`
  - `src/classes/fastapi_api_v1_routes.py`
  - `src/classes/fastapi_handler.py`
  - `src/classes/api_security_policy.py`
  - `src/classes/app_controller.py`
- Dashboard:
  - `dashboard/src/services/apiEndpoints.js`
  - `dashboard/src/components/ActionButtons.js`
  - `dashboard/src/components/BoundingBoxDrawer.js`
  - `dashboard/src/components/TrackerModeToggle.js`
  - `dashboard/src/pages/DashboardPage.js`
  - removed unused `dashboard/src/services/apiService.js`
- Tests and generated inventory:
  - `tests/test_api_route_inventory.py`
  - `tests/test_api_tool_candidates.py`
  - `tests/unit/core_app/test_app_controller_offboard_safety.py`
  - `tests/unit/core_app/test_smart_click.py`
  - `dashboard/src/components/ActionButtons.test.js`
  - `dashboard/src/components/BoundingBoxDrawer.test.js`
  - `dashboard/src/components/TrackerModeToggle.test.js`
  - `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- Docs/reporting:
  - `README.md`
  - `docs/CONFIGURATION.md`
  - `docs/INSTALLATION.md`
  - `docs/WINDOWS_SETUP.md`
  - `docs/apis/api-exposure-boundary.md`
  - `docs/apis/api-security-policy.md`
  - `docs/apis/route-inventory.md`
  - `docs/core-app/02-components/fastapi-handler.md`
  - `docs/core-app/03-api/README.md`
  - `docs/video/04-streaming/webrtc.md`
  - `docs/video/04-streaming/websocket.md`
  - `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
  - `docs/reporting/agent-ops/codex-modernization/issue-register.md`

## Validation

- `PYTHONPATH=src .venv/bin/python -m py_compile src/classes/app_controller.py src/classes/api_v1_actions.py src/classes/api_v1_contracts.py src/classes/api_v1_paths.py src/classes/fastapi_api_v1_routes.py src/classes/fastapi_handler.py src/classes/api_security_policy.py tools/generate_api_tool_candidates.py`: passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_smart_click.py tests/unit/core_app/test_app_controller_offboard_safety.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py -q`: 162 passed.
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`: schema current, 548 parameters.
- `.venv/bin/python tools/generate_api_tool_candidates.py`: inventory regenerated.
- `CI=true npm --prefix dashboard test -- --watchAll=false`: 14 suites passed, 71 tests passed.
- `npm --prefix dashboard run build`: compiled successfully with the existing Node `fs.F_OK` deprecation warning.
- `PYTHON=.venv/bin/python make phase0-check`: schema current, candidate inventory current, 185 tests passed with the existing Starlette/httpx `TestClient` deprecation warning.
- `git diff --check`: passed.

## Reviewer Disposition

- Backend/API safety review initially found smart-click false-success risk,
  replay-before-confirmation semantics, and unrestricted coordinate concerns.
  All were fixed and re-reviewed with no remaining blockers.
- Dashboard/API-client review initially found action-scope mismatches and
  operator-invisible smart-click failures. Both were fixed and re-reviewed with
  approval.
- Docs/devops governance review initially found missing checkpoint/journal/home
  reporting and one stale phase-map paragraph. The stale paragraph was fixed;
  this checkpoint, journal entry, and home report close the reporting gap.

## Evidence Paths

- Generated non-callable API/MCP candidate inventory:
  `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- Route/security guards:
  `tests/test_api_route_inventory.py`, `tests/test_api_security_policy.py`,
  `tests/test_api_tool_candidates.py`
- Smart-click truthfulness regression:
  `tests/unit/core_app/test_smart_click.py`,
  `tests/unit/core_app/test_app_controller_offboard_safety.py`
- Dashboard action-scope and smart-click feedback regression:
  `dashboard/src/components/ActionButtons.test.js`,
  `dashboard/src/components/BoundingBoxDrawer.test.js`,
  `dashboard/src/components/TrackerModeToggle.test.js`

## Risks And Open Questions

- The legacy tracking utility command routes remain registered as local-only
  compatibility aliases. They are now documented and should be retired in a
  dedicated compatibility-release slice.
- The action store remains process-local and is not durable command storage or
  a runtime MCP executor.
- No PX4, SITL, HIL, field, vehicle-response, or follower-response success is
  claimed by this slice.
- `QuitButton` still uses the existing quit endpoint and is outside this
  typed tracking-control slice; it should be reviewed during broader legacy
  administration route retirement.

## Next Planned Slice

PXE-0064 remains open for operator credential/TLS hardening, retirement of the
remaining local-only tracking/control compatibility aliases, and broader
adversarial browser-session/media tests. The recommended next slice is a
compatibility-alias retirement preflight: inventory external/operator usage,
add deprecation/removal notes, then retire the remaining local-only tracking
command routes behind release-review evidence.

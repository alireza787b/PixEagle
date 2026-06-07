# Phase 4 API v1 Contract Extraction Checkpoint

Date: 2026-06-06
Slice: PXE-0053
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: extract typed `/api/v1` Pydantic contracts and response metadata from
`FastAPIHandler`.

## Outcome

PXE-0053 is complete at code, contract, docs, and guardrail level. Typed
`/api/v1` request/response models, claim boundaries, and response metadata now
live in `src/classes/api_v1_contracts.py`.

No public route, route order, handler method, response model name, request model
name, action confirmation/idempotency behavior, SITL injection gate, dashboard
route, runtime MCP endpoint, `tools/list`, `tools/call`, callable tool,
PX4/SITL/HIL behavior, service installation, deployment, or field behavior
changed in this slice.

## Files Changed

- `src/classes/api_v1_contracts.py`
- `src/classes/fastapi_handler.py`
- `tools/generate_api_tool_candidates.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `docs/agent-context/README.md`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## What Changed

- Added `src/classes/api_v1_contracts.py` for:
  - typed action request/response/error models;
  - typed runtime/following/tracking/telemetry response models;
  - validation-only SITL injection request/response models;
  - `/api/v1` error response metadata;
  - process-local claim-boundary strings.
- Removed those `API*` and `SITL*` class definitions from
  `src/classes/fastapi_handler.py`.
- Imported/re-exported the moved names from `fastapi_handler.py` during
  migration so existing imports remain compatible.
- Extended `tools/generate_api_tool_candidates.py` and regenerated
  `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`.
  - `total_declared_http_routes`: 129.
  - `api_v1_routes`: 14.
  - `candidate_count`: 14.
  - `eligible_read_only_candidates`: 6.
  - `blocked_or_guarded_candidates`: 8.
  - `callable_tools`: 0.
  - `mcp_exposed_tools`: 0.
  - Source provenance now includes `src/classes/api_v1_contracts.py`.
- Added a static route-inventory guard that prevents `API*` and `SITL*`
  contracts from drifting back into `fastapi_handler.py`.
- Updated active docs to distinguish:
  - route metadata: `src/classes/fastapi_api_v1_routes.py`;
  - typed contracts: `src/classes/api_v1_contracts.py`;
  - handler methods: `src/classes/fastapi_handler.py`.

## Validation

- `.venv/bin/python -m py_compile src/classes/api_v1_contracts.py src/classes/fastapi_handler.py src/classes/fastapi_api_v1_routes.py tools/generate_api_tool_candidates.py tests/test_api_tool_candidates.py tests/test_api_route_inventory.py`:
  passed.
- `PYTHONPATH=src .venv/bin/python -c "from classes.fastapi_handler import APIActionRequest, APIRuntimeStatusResponse, SITLTrackerOutputInjection, FastAPIHandler; from classes.api_v1_contracts import APIActionRequest as DirectAPIActionRequest; assert APIActionRequest is DirectAPIActionRequest"`:
  passed with expected clean-clone/default-config and optional AI dependency
  warnings only.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`: passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py -q`:
  23 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_sitl_injection_api.py tests/unit/core_app/test_app_controller_offboard_safety.py -k "api_v1 or sitl" -q`:
  49 passed, 50 deselected.
- `PYTHON=.venv/bin/python make phase0-check`: schema up to date, candidate
  inventory current, 48 passed.

## Independent Review

Review focus for this slice:

- no change to action confirmation/idempotency/dry-run behavior;
- SITL injection models and gates remain validation-only and disabled by
  default;
- route inventory and candidate counts remain unchanged;
- generated agent candidates remain non-callable and unexposed;
- existing `fastapi_handler` imports continue to work during migration;
- docs do not claim PX4/SITL/HIL/field success from this structural change.

Independent review completed with no blockers:

- API/MCP review confirmed contract imports/re-exports remain compatible,
  route registry resolution still uses the moved response models, generated
  candidate provenance includes the contracts module, and `callable_tools`,
  `mcp_exposed_tools`, and `runtime_promoted_candidates` remain zero.
- Safety/runtime review confirmed action confirmation/idempotency/dry-run
  semantics are unchanged, SITL injection gates remain disabled by default, and
  claim boundaries still avoid PX4/SITL/HIL/field success claims.
- Docs/maintainability review confirmed the active docs identify the new
  contract module and the checkpoint keeps the structural-only scope honest.

Residual follow-up risks:

- `fastapi_handler.py` still imports/re-exports moved contracts for migration
  compatibility; a later API/router cleanup should migrate internal and external
  imports before removing that compatibility.
- The generated inventory distinguishes unpromoted read-only candidates from
  registered docs-stage candidates, which remains correct while runtime MCP
  promotion is absent but may need clearer naming in a later MCP-runtime slice.

## Risks And Boundaries

- This is a structural extraction only. It does not introduce FastAPI routers,
  persistent action storage, runtime MCP execution, or broader legacy route
  removal.
- `fastapi_handler.py` still re-exports the moved names for compatibility; a
  later cleanup can remove that compatibility only after internal and external
  imports are migrated.
- Status/telemetry routes remain PixEagle process-local snapshots. They do not
  prove PX4 Offboard state, SITL scenario success, tracker scene behavior,
  follower response, HIL, field behavior, or real-aircraft safety.

## Next Slice

Continue Phase 4 API modernization under PXE-0008. Good next candidates are
extracting focused route handler groups, moving shared API error helpers into
an API module, or migrating the next legacy dashboard/API consumer to a typed
`/api/v1` contract. PXE-0022 companion-runtime reconciliation, PXE-0021
dashboard toolchain migration, PXE-0040 Gazebo runtime proof, and PXE-0041
final no-legacy cleanup remain open.

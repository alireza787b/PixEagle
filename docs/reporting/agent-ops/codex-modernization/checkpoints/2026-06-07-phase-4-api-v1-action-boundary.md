# Phase 4 API v1 Action Boundary Checkpoint

Date: 2026-06-07
Slice: PXE-0055
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: extract typed `/api/v1` action-resource storage and helper behavior
from `FastAPIHandler`.

## Outcome

PXE-0055 is complete at code, contract, docs, and guardrail level. The
process-local action store, idempotency replay lookup, action record factory,
legacy action audit attachment, and action precondition failure helper now live
in `src/classes/api_v1_actions.py`.

No public route, route order, handler method, response model name, request model
name, action confirmation/idempotency/dry-run behavior, SITL injection gate,
dashboard route, runtime MCP endpoint, `tools/list`, `tools/call`, callable
tool, PX4/SITL/HIL behavior, service installation, deployment, or field
behavior changed in this slice.

## Files Changed

- `src/classes/api_v1_actions.py`
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

- Added `src/classes/api_v1_actions.py` for:
  - `ApiActionStore` process-local action records;
  - per-idempotency-key async locks;
  - idempotent replay lookup;
  - bounded in-memory action history;
  - typed action record construction and action claim boundary;
  - legacy command action-audit attachment;
  - confirmation/idempotency precondition failure responses.
- Updated `FastAPIHandler` so it owns a single `ApiActionStore` instance and
  retains migration wrappers for `_ensure_action_store`,
  `_action_lock_for_key`, `_lookup_idempotent_action`,
  `_store_action_record`, `_new_api_action_record`,
  `_attach_legacy_action_audit`, and `_action_precondition_failed_response`.
  The wrappers now delegate to `api_v1_actions.py`.
- Updated `get_action_resource()` to read through `ApiActionStore` rather than
  direct handler dictionaries.
- Extended `tools/generate_api_tool_candidates.py` and regenerated
  `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`.
  - `total_declared_http_routes`: 129.
  - `api_v1_routes`: 14.
  - `candidate_count`: 14.
  - `eligible_read_only_candidates`: 6.
  - `blocked_or_guarded_candidates`: 8.
  - `callable_tools`: 0.
  - `mcp_exposed_tools`: 0.
  - Source provenance now includes `src/classes/api_v1_actions.py`.
- Added static tests that prevent:
  - direct action-store dictionaries, idempotency indexes, history queues, and
    action locks drifting back into `fastapi_handler.py`;
  - direct UUID-based action record construction drifting back into
    `fastapi_handler.py`;
  - generated candidate provenance omitting the action-helper source file.

## Validation

- `.venv/bin/python -m py_compile src/classes/api_v1_actions.py src/classes/fastapi_handler.py tools/generate_api_tool_candidates.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py`:
  passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/unit/core_app/test_app_controller_offboard_safety.py -k "api_v1 or action or legacy_cancel" -q`:
  35 passed, 63 deselected.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`: passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py -q`:
  27 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_sitl_injection_api.py tests/unit/core_app/test_app_controller_offboard_safety.py -k "api_v1 or sitl" -q`:
  49 passed, 50 deselected.
- `PYTHON=.venv/bin/python make phase0-check`: schema up to date, candidate
  inventory current, 52 passed.

## Independent Review

Review focus for this slice:

- action confirmation/idempotency/dry-run behavior remains unchanged;
- concurrent duplicate idempotent requests still serialize through per-key
  async locks;
- dry-runs do not consume idempotency keys;
- legacy start/cancel command routes still attach typed action audit records;
- action resources remain process-local and do not claim PX4-observed Offboard,
  SITL, HIL, field, or vehicle-response success;
- generated agent candidates remain non-callable and unexposed;
- no runtime MCP endpoint, executor, `tools/list`, or `tools/call` exists.

Independent review completed before commit closure:

- API/MCP reviewer: no blockers. Confirmed the action helpers are extracted to
  `api_v1_actions.py`, handler wrappers delegate without changing route call
  sites, candidate provenance includes the action-helper source file, generated
  inventory remains non-callable, and tests guard against action-store internals
  drifting back into `fastapi_handler.py`.
- Safety/runtime reviewer: no blockers. Confirmed action confirmation,
  idempotency, and dry-run semantics remain unchanged; confirmed duplicate
  confirmed idempotent requests still serialize through per-key locks; confirmed
  dry-runs do not consume idempotency keys; confirmed legacy command routes still
  attach typed action audit records; and confirmed no PX4/SITL/HIL/field success
  is claimed.
- Docs/maintainability pass: completed locally after the dedicated docs reviewer
  was unavailable. No blocking doc drift found. The active docs identify
  `api_v1_actions.py` as the action-resource owner, keep the candidate inventory
  non-callable, and retain the process-local/durability boundary.

Residuals accepted for later slices:

- `ApiActionStore` is intentionally process-local and non-durable.
- Executed failed mutations continue to consume idempotency keys because any
  executed record is indexed for replay; this conservative policy is unchanged
  and should be revisited explicitly in the durable action-resource design.
- `FastAPIHandler` still keeps migration wrappers until route handlers and
  downstream call sites are narrower.
- Candidate provenance hashes `api_v1_actions.py`; behavior semantics remain
  guarded by action tests rather than semantic parsing in the generator.

## Risks And Boundaries

- This is a structural extraction only. It does not introduce durable action
  storage, persistent command resources, runtime MCP execution, or broader
  legacy route removal.
- `fastapi_handler.py` still keeps migration wrappers for action helpers; a
  later cleanup can remove those wrappers only after internal and external
  uses are migrated.
- The action store is process-local memory. It is suitable for current operator
  feedback and validation plans, but it is not durable command storage and does
  not prove PX4 Offboard state, SITL scenario success, tracker scene behavior,
  follower response, HIL, field behavior, or real-aircraft safety.

## Next Slice

Continue Phase 4 API modernization under PXE-0008. Good next candidates are
extracting typed runtime/following/tracking snapshot builders into focused API
service modules, extracting a route-family router adapter once handler
dependencies are narrower, or designing durable action/command resources as a
separate safety-reviewed slice. PXE-0022 companion-runtime reconciliation,
PXE-0021 dashboard toolchain migration, PXE-0040 Gazebo runtime proof, and
PXE-0041 final no-legacy cleanup remain open.

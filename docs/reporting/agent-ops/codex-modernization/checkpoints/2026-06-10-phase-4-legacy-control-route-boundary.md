# Phase 4 Legacy Control Route Boundary Checkpoint

Date: 2026-06-10
Slice: PXE-0061
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: extract legacy Offboard start and operator-cancel compatibility route
execution bodies from `FastAPIHandler`.

## Outcome

PXE-0061 is implemented at code, docs, and guardrail level. The legacy
`/commands/start_offboard_mode` and `/commands/cancel_activities`
compatibility route bodies now live in
`src/classes/api_legacy_control_routes.py`.

`FastAPIHandler` keeps one-call route-method wrappers only. This preserves the
existing registered routes, operation IDs, handler method names, legacy payload
shapes, typed action delegation path, and action-audit behavior while removing
another safety-adjacent execution body from the handler monolith.

No public route, route order, handler method name, response model name, request
model name, action confirmation/idempotency/dry-run policy, legacy
action-audit behavior, read-only candidate classification, SITL enablement
default, dashboard route, runtime MCP endpoint, `tools/list`, `tools/call`,
callable tool, PX4/SITL/HIL behavior, service installation, deployment, or
field behavior changed in this slice.

## Files Changed

- `src/classes/api_legacy_control_routes.py`
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

- Added `src/classes/api_legacy_control_routes.py` for:
  - legacy operator cancel via `/commands/cancel_activities`;
  - legacy Offboard start via `/commands/start_offboard_mode`.
- Updated `FastAPIHandler.cancel_activities()` and
  `FastAPIHandler.start_offboard_mode()` to one-call migration wrappers.
- Kept guarded typed action behavior unchanged:
  - `/api/v1/actions/offboard-start` still enforces confirmation,
    idempotency, and dry-run/replay policy in `api_v1_actions.py`;
  - `/api/v1/actions/operator-abort` still enforces the same action policy and
    calls the legacy cancel wrapper for compatibility execution;
  - legacy compatibility calls still attach an `action_audit` pointer.
- Regenerated
  `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`.
  - `total_declared_http_routes`: 129.
  - `api_v1_routes`: 14.
  - `candidate_count`: 14.
  - `eligible_read_only_candidates`: 6.
  - `blocked_or_guarded_candidates`: 8.
  - `callable_tools`: 0.
  - `mcp_exposed_tools`: 0.
  - Source provenance now includes
    `src/classes/api_legacy_control_routes.py` because guarded typed action
    candidates still delegate through these compatibility bodies.
- Extended static tests so:
  - legacy control helpers are present in `api_legacy_control_routes.py`;
  - handler legacy control methods stay one-call wrappers;
  - dangerous compatibility-route validation/error strings stay out of
    `fastapi_handler.py`;
  - generated candidate provenance includes the legacy-control-helper source
    file.

## Validation

- `.venv/bin/python -m py_compile src/classes/api_legacy_control_routes.py src/classes/fastapi_handler.py tools/generate_api_tool_candidates.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py`:
  passed.
- `.venv/bin/python tools/generate_api_tool_candidates.py`:
  regenerated the candidate inventory.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py -q`:
  32 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_app_controller_offboard_safety.py -k "start_offboard_mode or legacy_cancel_activities_route_records_action_audit or api_v1_offboard_action or api_v1_operator_abort_action" -q`:
  14 passed, 58 deselected.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`:
  passed.
- `git diff --check`:
  passed.
- `PYTHON=.venv/bin/python make phase0-check`:
  schema up to date, candidate inventory current, 57 passed.

## Review

Review focus for this slice:

- route inventory remains unchanged;
- generated agent candidates remain non-callable and unexposed;
- action and SITL routes remain blocked or guarded;
- legacy Offboard start still fails closed on unusable tracker output;
- legacy operator cancel still records action audit and propagates failures as
  HTTP 500 compatibility responses;
- typed action confirmation, dry-run, idempotency, replay, and action-resource
  lookup stay owned by `api_v1_actions.py`;
- no runtime MCP endpoint, executor, `tools/list`, or `tools/call` exists;
- no PX4/SITL/HIL/field success is claimed.

Independent reviewer checks found no blockers:

- API/MCP reviewer confirmed public route inventory remains stable, generated
  provenance includes `api_legacy_control_routes.py`, action candidates remain
  blocked/guarded with `callable: false` and `mcp_exposure: none`, policy still
  denies MCP/action exposure, and no runtime MCP/tool exposure was introduced.
- Safety/control-action reviewer confirmed typed action delegation still reaches
  the legacy wrappers, route registration still binds the deprecated legacy
  metadata, cancel preserves `operator_abort` audit plus HTTP 500 compatibility
  failure behavior, Offboard start still fail-closes before `connect_px4()` on
  missing PX4/tracker/video/tracker-readiness, and typed action idempotency and
  delegation stay in `api_v1_actions.py`.
- The safety reviewer noted a minor extraction parity difference where the
  moved final-state fallback used `except Exception` instead of the previous
  catch-all behavior; that was fixed with `except BaseException` before final
  validation so the legacy catch-all semantics are preserved without adding a
  bare `except` to the new helper.
- Both reviewers kept runtime evidence boundaries explicit and did not claim
  PX4/SITL/HIL/field success.

Local recovery review found no blockers:

- `FastAPIHandler` legacy control route methods are one-call wrappers.
- legacy control validation/error strings live in
  `api_legacy_control_routes.py`, not `fastapi_handler.py`.
- generated candidate inventory still reports 129 declared HTTP routes, 14
  `/api/v1` candidates, six eligible read-only candidates, eight
  blocked/guarded candidates, zero callable tools, and zero MCP-exposed tools.
- no runtime MCP endpoint, executor, `tools/list`, or `tools/call` exists.
- no PX4/SITL/HIL/field success is claimed.

Residuals accepted for later slices:

- `FastAPIHandler` still keeps migration wrappers until route/router extraction
  can remove them safely.
- The legacy `/commands/*` aliases still exist by design for compatibility;
  final alias removal remains gated by PXE-0041.
- This is contract/unit evidence only; runtime PX4/SITL/HIL/field validation
  remains operator-gated and artifact-driven.

## Risks And Boundaries

- This is a structural extraction only. It does not add runtime MCP execution,
  durable storage, route removals, dashboard migrations, PX4/SITL execution,
  HIL, field validation, deployment, or service installation.
- The legacy compatibility routes are still immediate-execution routes. New
  control-plane integrations must use typed `/api/v1/actions/*` resources with
  confirmation, dry-run, idempotency, and audit records.
- Candidate inventory provenance now includes the legacy helper so action
  candidate reviewers can see compatibility-route behavior drift until aliases
  are retired.

## Next Slice

Continue Phase 4 API modernization under PXE-0008. Good next candidates are
extracting remaining large legacy route families behind narrower modules,
designing durable action/command resources as a safety-reviewed slice, or
resuming companion-runtime reconciliation under PXE-0022. PXE-0021 dashboard
toolchain migration, PXE-0040 Gazebo runtime proof, and PXE-0041 final
no-legacy cleanup remain open.

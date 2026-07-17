# Phase 4 Docs-Stage Agent Registry And Policy Checkpoint

Date: 2026-06-06
Slice: PXE-0051
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: docs-stage review registry and policy for non-callable read-only API/MCP candidates.

## Outcome

PXE-0051 is complete at docs, contract, and guardrail level. PixEagle now has a
docs-stage agent registry and policy file for the six already reviewed
process-local status/telemetry GET candidates.

This slice does not add an MCP endpoint, runtime tool executor, `tools/list`,
`tools/call`, callable tools, live PixEagle backend proof, PX4/SITL/HIL proof,
field validation, deployment, service changes, or real-aircraft validation.

## Files Changed

- `tools/generate_api_tool_candidates.py`
- `tests/test_api_tool_candidates.py`
- `docs/agent-context/agent_tools.yaml`
- `docs/agent-context/agent_policy.yaml`
- `docs/agent-context/README.md`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## What Changed

- Added `docs/agent-context/agent_tools.yaml`.
  - Registry stage is `docs_review_only`.
  - `runtime_loaded: false`.
  - `mcp_exposed: false`.
  - `default_registry_exposure: exclude`.
  - Only six reviewed process-local typed GET routes are registered:
    - `/api/v1/runtime/status`;
    - `/api/v1/following/status`;
    - `/api/v1/following/telemetry`;
    - `/api/v1/telemetry/health`;
    - `/api/v1/tracking/runtime-status`;
    - `/api/v1/tracking/telemetry`.
- Added `docs/agent-context/agent_policy.yaml`.
  - `agent_enabled: false`.
  - `mcp_enabled: false`.
  - `registry_runtime_loaded: false`.
  - `unknown_tool_policy: deny`.
  - `allow_openapi_autopromotion: false`.
  - `allow_action_tools: false`.
  - `allow_sitl_injection_tools: false`.
  - `auto_promote_generated_candidates: false`.
  - Denies action, SITL injection, operate, admin, destructive, guarded control,
    validation-stimulus, and unreviewed mutation risk classes.
- Extended the static candidate generator so registry coverage now reports:
  - docs registry presence;
  - policy presence;
  - registered eligible read-only candidate count;
  - runtime promoted candidate count;
  - callable and MCP-exposed registry matches;
  - unsafe registry metadata/tool/policy setting counts;
  - invalid or unregistered candidate previews.
- Regenerated
  `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`.
  - All 14 `/api/v1` routes remain represented exactly once.
  - Six status/telemetry GET routes are `registry_reviewed_unexposed`.
  - Action routes, action-resource GET, and SITL injection routes remain
    unregistered and blocked from read-only MCP promotion.
- Expanded candidate tests so the Phase 0 guardrail proves:
  - every registry tool maps to an eligible generated candidate;
  - all registry tools are `callable: false`;
  - all registry tools have `mcp_exposure: none`;
  - every registry tool uses `default_registry_exposure: exclude`;
  - policy defaults deny execution, auto-promotion, action tools, and SITL
    injection tools.

## Validation

- `python3 -m py_compile tools/generate_api_tool_candidates.py`: passed.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`: passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_api_tool_candidates.py tests/test_api_route_inventory.py -q`:
  20 passed.
- `PYTHON=.venv/bin/python make phase0-check`: schema up to date, candidate
  inventory current, 45 passed.
- `git diff --check`: passed.

## Independent Review

Pre-implementation safety/API reviewers required:

- no runtime MCP endpoint, executor, `tools/list`, or `tools/call`;
- only the six typed process-local GET routes in the docs-stage registry;
- all action/control/SITL/config/service routes excluded;
- every registered tool `callable: false`, `mcp_exposure: none`, and
  `default_registry_exposure: exclude`;
- policy default-deny for unknown tools, action tools, SITL injection tools,
  direct drone/PX4 exposure, and OpenAPI auto-promotion.

Post-implementation review found no blockers after the generator was tightened
to report unsafe registry metadata, unsafe registry tool fields, extra registry
routes, and unsafe policy defaults as incomplete or unsafe coverage.

## Risks And Boundaries

- This is still docs-stage governance. PixEagle still does not expose a runtime
  MCP tool surface.
- `registry_reviewed_unexposed` means the candidate has a matching docs-stage
  registry entry, not runtime promotion.
- Status/telemetry routes remain PixEagle process-local snapshots. They do not
  prove PX4 Offboard state, SITL scenario success, tracker scene behavior,
  follower response, HIL, field behavior, or real-aircraft safety.
- Broader `/api/v1` migration and router extraction remain PXE-0008.
- Companion-runtime sidecar policy, auth, token handling, fleet profiles, and
  version pin reconciliation remain PXE-0022.
- Dashboard CRA/toolchain debt remains PXE-0021.
- Full Gazebo visual runtime proof remains PXE-0040.
- Final no-legacy cleanup remains PXE-0041.

## Next Slice

Continue Phase 4 with a broader API modernization slice. The strongest next
step is to start extracting typed `/api/v1` route families out of the
monolithic `fastapi_handler.py` while preserving route inventory, structured
errors, compatibility aliases, dashboard fallbacks, and the non-callable
agent-context boundary.

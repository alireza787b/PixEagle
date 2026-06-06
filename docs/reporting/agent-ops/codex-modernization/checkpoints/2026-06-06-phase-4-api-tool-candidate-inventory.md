# Phase 4 API/MCP Candidate Inventory Checkpoint

Date: 2026-06-06
Slice: PXE-0050
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: non-callable `/api/v1` candidate inventory and drift gate.

## Outcome

PXE-0050 is complete at contract/docs/test level. PixEagle now has a generated
agent-context inventory for all current `/api/v1` HTTP routes, but it does not
expose MCP execution.

No MCP endpoint, MCP registry, `tools/list`, `tools/call`, callable tool,
runtime PixEagle backend, PX4/SITL/HIL, field, deployment, service, or
real-aircraft validation was added or run.

## Files Changed

- `.github/workflows/tests.yml`
- `Makefile`
- `tools/generate_api_tool_candidates.py`
- `tests/test_api_tool_candidates.py`
- `docs/agent-context/README.md`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/core-app/03-api/README.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/drone-interface/02-components/mavlink-data-manager.md`
- `docs/drone-interface/05-configuration/mavlink-config.md`
- `docs/followers/07-integration/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## What Changed

- Added `tools/generate_api_tool_candidates.py`.
  - Parses `src/classes/fastapi_handler.py` with AST only.
  - Does not instantiate FastAPI, AppController, Uvicorn, video, MAVLink, PX4,
    or runtime services.
  - Supports `--check` drift detection.
- Added generated inventory:
  - `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`.
- Inventory records:
  - source file and SHA-256;
  - route method/path/operation ID/tags/handler;
  - request and response model metadata where statically detectable;
  - typed-contract state;
  - `callable: false`;
  - `mcp_exposure: none`;
  - `default_registry_exposure: exclude`;
  - `promotion_status: unpromoted`;
  - risk class, sensitivity, side effects, blocked reasons, and required
    review gates;
  - repeated claim boundary that the file is candidate inventory only, not MCP
    execution.
- Inventory classification:
  - 14 current `/api/v1` HTTP routes represented exactly once;
  - 6 typed process-local GET routes are unpromoted read-only candidates;
  - 8 routes are blocked or guarded, including action POSTs, action-resource
    GET, and SITL injection POSTs.
- CI/guardrails:
  - `.github/workflows/tests.yml` runs
    `python3 tools/generate_api_tool_candidates.py --check` in the Phase 0
    guardrail job.
  - `make phase0-check` runs the same generator check and
    `tests/test_api_tool_candidates.py`.
- Docs:
  - Added `docs/agent-context/README.md`.
  - Updated API blueprint and REST API docs to state MCP-friendly typed routes
    are not callable MCP tools until registry, policy, docs, tests, and
    reviewer gates are complete.
  - Clarified existing API/MCP wording in FastAPI, MAVLink, and follower docs
    so it points to candidate inventory only, not MCP execution.

## Companion Standard Reconciliation

Before implementation, companion references were refreshed:

- `mavsdk_drone_show`: `623bb3fa`,
  `v5.5.71-simurgh-readonly-closure`.
- MavlinkAnywhere: `7643d4d`, `v3.0.14-2-g7643d4d`.
- Smart Wi-Fi Manager: `a5414fc`, `v2.1.14-2-ga5414fc`.

The adopted standard is the Simurgh pattern: generated candidates are reviewer
coverage only. A route can become callable only after curated registry entry,
policy classification, typed contract review, operator docs, tests/evals, and
independent approval.

## Validation

- `python3 -m py_compile tools/generate_api_tool_candidates.py`: passed.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`: passed.
- `.venv/bin/python -m pytest tests/test_api_tool_candidates.py -ra --tb=short --strict-config`:
  6 passed.
- `.venv/bin/python -m pytest tests/test_api_tool_candidates.py tests/test_docs_infrastructure_consistency.py -ra --tb=short --strict-config`:
  16 passed.
- `PYTHON=.venv/bin/python make phase0-check`: schema up to date, candidate
  inventory current, 43 passed.
- Independent reviewer read-only validation:
  - generator `--check`: passed;
  - `git diff --check`: passed;
  - route inventory plus candidate tests: 18 passed.
- `git diff --check`: passed.

## Independent Review

Pre-implementation API/MCP and safety reviewers required:

- non-callable artifact only;
- no MCP endpoint or auto-generated tools;
- only the six typed process-local status/telemetry GETs eligible as
  unpromoted read-only candidates;
- action POSTs, action-resource GET, and SITL injection routes blocked from
  read-only promotion;
- source hash, route coverage, registry coverage, risk/sensitivity/side-effect
  fields, and docs that say candidate inventory only, not MCP execution.

Post-implementation reviewer result: no blockers. A non-blocking note about
existing "API/MCP consumers" docs wording was fixed before closure.

## Risks And Boundaries

- This does not complete PXE-0008. The API surface still needs broader
  `/api/v1` migration, router extraction, typed schemas, and legacy alias
  removal gates.
- This does not complete PXE-0022. Companion-runtime, sidecar auth/profile
  policy, and version pin reconciliation remain open.
- This does not create a curated PixEagle agent registry or policy file.
- This does not create callable MCP tooling.
- This does not prove PX4, SITL, HIL, field, tracker, follower, or
  real-aircraft behavior.

## Next Slice

Continue Phase 4 with either:

- curated agent registry/policy design for reviewed read-only tools, still with
  no callable action tools; or
- broader `/api/v1` migration and FastAPI router extraction to shrink the
  monolithic `fastapi_handler.py`; or
- dashboard toolchain modernization (PXE-0021) if maintainer priority shifts to
  frontend debt.

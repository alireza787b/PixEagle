# 2026-06-30 Phase 4 Typed Tracker Catalog

## Summary

Continued PXE-0008 by adding a typed tracker catalog/configuration read surface:
`GET /api/v1/tracking/catalog`.

This is a process-local API contract for dashboard/API consumers. It does not
claim tracker runtime success, follower response, QGC playback, PX4, SITL, HIL,
field, deployment, or real-aircraft behavior.

## Behavior

- Added typed catalog contracts:
  - `APITrackingCatalogEntry`
  - `APITrackingCatalogResponse`
  - `TRACKING_CATALOG_ERROR_RESPONSES`
  - `TRACKING_CATALOG_CLAIM_BOUNDARY`
- Added `API_V1_TRACKING_CATALOG_PATH` and included it in the typed
  error-envelope route predicate without adding it to the reviewed
  process-local MCP-candidate allowlist.
- Added route metadata for `GET /api/v1/tracking/catalog` with operation ID
  `get_tracking_catalog`, response model `APITrackingCatalogResponse`, and
  `tracking` tag.
- Added the read-route error boundary in `api_v1_read_routes.py`.
- Added the snapshot builder in `api_v1_snapshots.py`.
- Added a migration wrapper in `FastAPIHandler`.
- Classified the route as a `control_reads` API surface in the security policy.
- Regenerated the non-callable generated API/MCP candidate inventory.

## Catalog Semantics

The route returns:

- schema-manager UI tracker entries from `get_available_classic_trackers()`;
- built-in compatibility tracker types: `CSRT`, `ParticleFilter`, `Gimbal`,
  and `SmartTracker`;
- configured and active tracker identity;
- smart-mode/tracking flags;
- embedded typed runtime status from the existing tracker runtime snapshot;
- health issues when the schema manager is unavailable;
- an explicit claim boundary.

If schema-manager catalog loading fails, the response degrades while preserving
the built-in compatibility tracker type list. That gives clients a stable
metadata shape without pretending runtime selection is proven.

## Preserved Compatibility

- Legacy tracker routes are still registered.
- Existing dashboard consumers are not migrated in this slice.
- No compatibility alias was retired.
- No runtime MCP endpoint, `tools/list`, `tools/call`, callable tool registry,
  or agent execution path was added.

## Governance

The generated candidate entry `pixeagle.tracking.catalog.read` is:

- `callable: false`
- `mcp_exposure: none`
- `eligible_read_only_mcp_candidate: false`
- `review_disposition.state: blocked`
- `registry_review_status: unregistered`

Promotion requires a separate output-sensitivity review, policy review,
operator docs review, route contract review, and independent safety review.

## Files Changed

- `src/classes/api_v1_contracts.py`
- `src/classes/api_v1_paths.py`
- `src/classes/api_v1_read_routes.py`
- `src/classes/api_v1_snapshots.py`
- `src/classes/fastapi_api_v1_routes.py`
- `src/classes/fastapi_handler.py`
- `src/classes/api_security_policy.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/agent-context/README.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/apis/route-inventory.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/developers/SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md`
- `docs/trackers/06-integration/README.md`
- `docs/trackers/06-integration/external-systems.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Validation

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile ...`
  passed for touched backend modules and tests.
- Focused typed catalog/API/security/candidate gate passed with 11 tests:
  - catalog schema plus built-in type response;
  - schema-manager failure degradation;
  - structured catalog error response;
  - route inventory and method counts;
  - typed error-envelope predicate;
  - typed route metadata;
  - security policy exact route coverage;
  - generated candidate inventory summary;
  - blocked/unregistered candidate disposition.
- Generated API/MCP candidate inventory check passed:
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python tools/generate_api_tool_candidates.py --check`.
- Broader typed catalog/API/security/docs gate passed with 73 tests:
  `tests/test_api_route_inventory.py`,
  `tests/test_api_tool_candidates.py`,
  `tests/test_api_security_policy.py`,
  `tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist`,
  and the three focused typed catalog tests.
- Stale tracker API pattern scan returned no matches after removing old
  dedicated tracker WebSocket examples from tracker integration docs.
- `git diff --check` passed.
- `PYTHON=.venv/bin/python make phase0-check` passed with schema current,
  generated API/MCP candidate inventory current, 393 tests passed, and one
  existing Starlette/httpx deprecation warning.

## Independent Review

- Initial independent read-only review found no runtime/API correctness
  blockers, but identified two governance/documentation fixes:
  - `docs/apis/route-inventory.md` still showed the previous route counts;
  - generated `pixeagle.tracking.catalog.read` disposition still used the
    default `2026-06-18` review date instead of the slice date.
- Fixed both findings:
  - route inventory docs now show 134 total route pairs, 132 HTTP route pairs,
    and 75 `GET` routes;
  - `tools/generate_api_tool_candidates.py` now carries a route-specific
    `2026-06-30` disposition review date for
    `GET /api/v1/tracking/catalog`, and `tests/test_api_tool_candidates.py`
    asserts it.
- Reviewer recheck found no blockers and independently verified the route
  counts, generated candidate date, candidate inventory check, narrow
  route/candidate tests, and `git diff --check`.

## Remaining Before Dashboard Demo

- Migrate dashboard tracker catalog consumers away from legacy
  `/api/tracker/available` and related legacy catalog/config routes once the
  client contract is selected.
- Tracker switch was later promoted to typed
  `POST /api/v1/actions/tracker-switch` in the 2026-07-01 checkpoint. Design
  typed tracker restart/configuration actions with confirmation, idempotency,
  audit, and fail-closed behavior before retiring remaining legacy mutation
  routes.
- Run backend, dashboard, schema, API/MCP candidate, docs-link, and independent
  review gates on a clean branch before starting a maintained demo stack for
  testers.

## Remaining Before Fresh Setup Handoff

- Complete the PXE-0074 clean temporary-checkout setup walkthrough using public
  docs only.
- Capture commands, generated files, ports, credential handoff, and validation
  outputs.
- Remove or update any stale setup/config/bootstrap docs found during that
  walkthrough.
- Do not tag or release until the clean setup walkthrough and maintained demo
  stack gates pass.

## Residual Risks

- The typed route is metadata-only. It does not prove that a tracker can start,
  reacquire, drive a follower, or control PX4.
- Built-in compatibility type metadata is intentionally minimal and must be
  reconciled with richer tracker plugin/provider metadata during the later
  tracker architecture cleanup.
- Dashboard consumers still use legacy catalog routes, so this slice introduces
  a replacement surface but not user-visible dashboard behavior.

## Next Slice

Continue PXE-0008 with dashboard tracker catalog migration, then typed tracker
restart/configuration mutation design and compatibility retirement planning,
depending on which creates the least legacy compatibility risk after review.

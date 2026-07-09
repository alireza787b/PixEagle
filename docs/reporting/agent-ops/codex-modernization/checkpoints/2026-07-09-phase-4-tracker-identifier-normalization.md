# 2026-07-09 Phase 4 Tracker Identifier Normalization

## Phase / Slice

- Phase 4 API/MCP modernization
- Issue: PXE-0008 partial
- Scope: fix tracker switch/restart identifier drift between schema-manager
  keys, existing factory-key config values, and dashboard request values.

## Outcome

- `SchemaManager` now resolves tracker identifiers through one canonical path.
  It accepts schema-manager keys such as `CSRTTracker` and existing
  factory-key/config values such as `CSRT`, `KCF`, `dlib`, and `Gimbal`.
- `AppController.switch_tracker_type()` normalizes successful switches to the
  schema-manager tracker key while preserving the factory key used by
  `tracker_factory.py`.
- Typed tracker catalog entries expose `request_tracker_type` and `factory_key`
  so clients can send the reviewed request identifier and still inspect the
  lower-level factory mapping.
- Dashboard tracker selector sends `request_tracker_type` instead of inventing
  its own action value.
- Typed tracker restart validation accepts existing factory-key defaults, which
  closes the `ACTION_TRACKER_SWITCH_INVALID`/restart-invalid class of issue
  caused by mixed identifier families.
- Generated API/MCP candidate provenance was regenerated. Candidates remain
  docs-stage, blocked/unregistered/non-callable where previously blocked.

## Files Changed

- `src/classes/schema_manager.py`
- `src/classes/app_controller.py`
- `src/classes/api_legacy_tracker_routes.py`
- `src/classes/api_v1_contracts.py`
- `src/classes/api_v1_snapshots.py`
- `dashboard/src/hooks/useTrackerSchema.js`
- `dashboard/src/components/TrackerSelector.js`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/core-app/03-api/README.md`
- `docs/trackers/06-integration/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
- this checkpoint

## Validation

- `git diff --check`: passed.
- Focused tracker catalog/action regression selection: 5 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_api_legacy_tracker_routes.py -q`:
  6 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_app_controller_offboard_safety.py tests/unit/core_app/test_api_legacy_tracker_routes.py -q`:
  120 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py -q`:
  79 passed after regenerating API tool candidates.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -q`:
  54 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_docs_infrastructure_consistency.py -q`:
  23 passed.
- `bash scripts/check_schema.sh`: schema current, 41 sections and 549
  parameters.
- `python3 tools/generate_api_tool_candidates.py`: regenerated candidate
  inventory.
- `PYTHONPATH=src .venv/bin/python -m py_compile src/classes/schema_manager.py src/classes/app_controller.py src/classes/api_legacy_tracker_routes.py src/classes/api_v1_contracts.py src/classes/api_v1_snapshots.py`:
  passed.
- `CI=true npm test -- --runInBand --watchAll=false` in `dashboard/`: 28 test
  suites and 161 tests passed.
- `CI=true npm run build` in `dashboard/`: compiled successfully,
  `build/static/js/main.77a9c7d5.js`.

## Independent Review

- PXE-0008 sidecar audit confirmed tracker reads/actions are mostly modernized
  and that the next broader API slice should be typed tracker configuration
  mutation, not another legacy alias pass.
- Highest-risk remaining tracker API gap: legacy generic config writes still
  cover tracker parameter saves. The future typed tracker-config action must
  hard-reject unknown/no-schema params, distinguish `tracker_restart` from
  `system_restart` reload tiers, fail closed while following is active, and stay
  non-callable for MCP until a separate promotion review.

## Remaining Work

- PXE-0008 remains open for typed tracker configuration mutation design,
  proposed as `POST /api/v1/actions/tracker-config-update` with dry-run plan,
  confirmed/idempotent mutation, tracking-category-only schema validation,
  explicit restart policy, and generated candidate guardrails.
- PXE-0070 QGC Windows package proof remains open. Corrected run
  `28998523729` was still in progress during this checkpoint; no QGC
  packaged-runtime, playback, remote PixEagle media, PX4/SITL/HIL, field, or
  real-aircraft success is claimed here.

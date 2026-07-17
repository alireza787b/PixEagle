# Phase 4 Checkpoint: Typed Tracker Telemetry History

Date: 2026-06-06

## Slice

PXE-0049: add a typed tracker telemetry/geometry snapshot and migrate the
Follower visualization page's tracker center/bounding-box plots off direct
legacy tracker telemetry.

## Scope

This slice adds typed process-local tracker telemetry under
`GET /api/v1/tracking/telemetry` and updates one dashboard page to consume it.
It does not claim PX4-observed Offboard, SITL, HIL, field, tracker/video
runtime, deployment, service, follower-response, vehicle-response, or
real-aircraft validation.

## Backend Changes

- Added `API_V1_TRACKING_TELEMETRY_PATH` and
  `TRACKING_TELEMETRY_CLAIM_BOUNDARY`.
- Added `APITrackingTelemetryResponse` with:
  - readiness classification copied from the typed tracker runtime snapshot;
  - chart-compatible `center` and `bounding_box`;
  - `fields`, `tracker_data`, and `field_source`;
  - embedded typed `runtime_status`;
  - `tracking_active` and `tracker_started` compatibility aliases;
  - legacy payload key inventory;
  - structured claim boundary and timestamp.
- Added `GET /api/v1/tracking/telemetry` with route inventory metadata:
  response model, operation ID, tracking tag, and structured error envelope.
- The snapshot prefers live `TrackerOutput` serialization for geometry and
  fields, then falls back to legacy tracker telemetry only as a compatibility
  source.
- Top-level `bounding_box` is normalized-only; pixel boxes remain under
  explicit fields such as `fields.bbox`.
- Top-level geometry rejects malformed, wrong-length, non-finite, or
  out-of-range normalized bounding-box arrays instead of fabricating plot data.

## Dashboard Changes

- Added `endpoints.trackingTelemetry`.
- Added `normalizeTrackingTelemetry()` and a shared
  `normalizeTelemetryTimestamp()` helper.
- `FollowerPage` now polls typed tracker telemetry for tracker history samples.
- Legacy `endpoints.trackerData` (`/telemetry/tracker_data`) is used only when
  the typed tracker telemetry route is missing with `404`, `405`, or `501`
  during rolling updates.
- The page continues to bound history/raw-log growth and ignore stale
  out-of-order responses.

## Tests

- Route inventory now freezes `GET /api/v1/tracking/telemetry` and its typed
  FastAPI metadata.
- Backend tests cover live `TrackerOutput` geometry snapshots, legacy telemetry
  compatibility fallback, live output independence from legacy cache failures,
  malformed geometry rejection, normalized-only top-level bounding boxes, and
  structured API error responses.
- Frontend tests cover typed tracker polling, legacy tracker fallback only when
  the typed route is missing, tracker telemetry normalization, timestamp
  normalization, no-output geometry preservation, and the existing stale
  out-of-order page guard.

## Documentation

- `docs/core-app/README.md`
- `docs/core-app/03-api/README.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/developers/SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md`
- `docs/followers/07-integration/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Evidence

Focused validation completed before final gates:

```bash
PYTHONPATH=src .venv/bin/python -m py_compile src/classes/fastapi_handler.py
PYTHONPATH=src .venv/bin/pytest tests/test_api_route_inventory.py tests/unit/core_app/test_app_controller_offboard_safety.py -q
CI=true npm test -- --watchAll=false --runTestsByPath src/hooks/useStatuses.test.js src/pages/FollowerPage.test.js
```

Results:

- touched Python syntax compile: passed;
- route inventory plus AppController Offboard safety: 83 passed;
- focused dashboard status/page suites: 2 suites, 31 tests passed.

Independent review findings fixed before final gates:

- Backend/API review found that legacy cached geometry could override live
  `TrackerOutput` geometry. The route is now live-first and has a conflicting
  live-vs-legacy regression test.
- Backend/API review found that top-level `bounding_box` could contain pixel
  coordinates. The route now exposes top-level normalized boxes only and keeps
  pixel boxes in explicit fields.
- Backend/API review found malformed/non-finite geometry could enter top-level
  fields. Strict geometry helpers and tests now reject those top-level values.
- Frontend review found typed no-output snapshots could normalize to
  `undefined` geometry and be plotted as zero. The normalizer now preserves
  `null` geometry and tests cover the no-output case.
- Frontend review found the raw log now stored only normalized payloads. It now
  keeps both the wire payload under `data` and the chart-compatible payload
  under `normalized`.
- Second-pass backend review found that live `TrackerOutput` telemetry could
  still fail if legacy telemetry retrieval raised. Live-output snapshots now
  avoid legacy telemetry retrieval entirely, and a regression test proves the
  route succeeds when the legacy cache raises.
- Second-pass frontend/docs review found legacy pixel `bbox`/`bbox_pixel` could
  still be promoted to normalized `bounding_box` during frontend fallback. The
  tracker telemetry normalizer now uses only `normalized_bbox` for
  `bounding_box`, and pixel boxes remain under explicit fields.

Final validation completed:

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py tests/unit/core_app/test_app_controller_offboard_safety.py -q
PYTHON=.venv/bin/python bash scripts/check_schema.sh
PYTHONPATH=src .venv/bin/pytest tests/test_docs_infrastructure_consistency.py -q
git diff --check
npm run lint -- --format unix
CI=true npm test -- --watchAll=false
npm run build
```

Results:

- route inventory, parameters reload, and AppController Offboard safety:
  93 passed;
- schema check: up to date;
- docs infrastructure consistency: 10 passed;
- whitespace check: passed;
- dashboard lint: passed;
- full dashboard tests: 9 suites, 52 tests passed;
- dashboard build: compiled successfully.

## Risks And Open Follow-Ups

- This is unit/contract/frontend evidence only. No runtime PX4/SITL/HIL/field
  pass is claimed.
- The new tracker telemetry route is a current snapshot, not server-side
  history. Dashboard pages append bounded client-side history from successive
  snapshots.
- Broader typed safety/circuit-breaker APIs, MCP resources, companion-runtime
  reconciliation, dashboard toolchain modernization, and final no-legacy
  cleanup remain separate tracked work.

## Next Slice Candidates

- Continue PXE-0008 with broader API/MCP route modernization.
- Continue PXE-0022 companion/API/MCP reconciliation and sidecar contract
  verification.
- Continue PXE-0021 dashboard toolchain modernization.
- Keep PXE-0040 official Gazebo L4 runtime proof open for suitable host
  evidence.

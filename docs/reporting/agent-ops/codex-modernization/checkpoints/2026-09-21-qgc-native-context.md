# PXE-0174: native QGC integration — backend connection context

Date: 2026-09-21. Slice: 1 (backend contract and observational discovery).
Branch: `feature/qgc-native-integration`, base
`989d9662173b364de03b307f4208e9d0ca96451f`.

Slice 1 is complete for the local Linux connection/identity gate: backend
contracts and the paired custom QGC builds, tests, and simulated UI checks pass.
The paired QGC checkpoint is
`/home/alireza/qgroundcontrol-pixeagle/custom-pixeagle/SLICE-1.md`.
This report does not claim aircraft, SITL/HIL, deployment, camera geometry,
or following success.
Slice-0 documents and the original clean PixEagle checkout were preserved.

## Result and changed files

- Typed `GET /api/v1/integration/context` and explicit observational
  `POST /api/v1/integration/connection` (`{}` body). Real session/bearer,
  status+telemetry scopes, POST CSRF/audit, no-store success responses,
  structured failures, and blocked non-callable candidate inventory.
- `api_v1_integration.py`, API contracts/paths, route registry/handler, and
  security policy provide process/runtime identity, version/capabilities,
  observed aircraft identities, permissions, reasons, and permanently false
  slice-1 following authorization. Video identity/geometry remains unknown.
- `aircraft_identity.py`, `mavlink_data_manager.py`, and
  `px4_interface_manager.py` preserve uint64 UIDs as decimal strings,
  compare observed MAVSDK legacy UID with telemetry AUTOPILOT_VERSION UID,
  require heartbeat progression, and invalidate on loss, stale recovery,
  identity change, counter reset, or observed boot-time rollback.
- `app_controller.py` runs observation on its existing flight owner and
  lifecycle barrier; cancellation/generation guards prevent stale completion.
  Observation cannot steal an uninitialized owner loop or restart/reconfigure
  telemetry belonging to active following. It never invokes follow-start.
- Defaults, schema generator, and generated schema add explicit
  `MAVLINK_SYSTEM_ID`/`MAVLINK_COMPONENT_ID` (1–255, default 1). All aggregate
  paths and four follower message reads use this route. Existing custom path
  prefixes require the documented two-setting migration.
- Route/candidate inventory tests and generation, native integration tests,
  existing manager fixtures, API/security/routing docs, and the loopback-only
  `tools/native_integration_fixture.py` validation launcher were updated.

The public contract, limitations, scopes, response semantics, configuration
migration, and test fixture are documented in
[Native integration context](../../../../apis/native-integration-context.md).

## Validation and local evidence

From `/home/alireza/PixEagle-qgc-integration`, using its isolated `.venv` from
slice 0 (no dependency mutation in the original checkout):

```bash
.venv/bin/python tools/generate_api_tool_candidates.py
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/core_app/test_api_v1_integration.py \
  tests/test_api_route_inventory.py tests/test_api_security_policy.py \
  tests/test_api_tool_candidates.py tests/unit/core_app/test_parameters_reload.py \
  tests/unit/drone_interface/test_mavlink_data_manager.py \
  tests/unit/drone_interface/test_px4_interface_manager.py \
  tests/unit/core_app/test_api_auth_runtime.py \
  tests/unit/core_app/test_api_exposure_policy.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/test_docs_infrastructure_consistency.py \
  --junitxml=reports/qgc-slice1/contracts-regression.xml -q
PYTHON=.venv/bin/python bash scripts/check_schema.sh
.venv/bin/python tools/generate_api_tool_candidates.py --check
PYTHONPATH=src .venv/bin/python -m compileall -q \
  src/classes/aircraft_identity.py src/classes/api_v1_integration.py \
  src/classes/api_v1_contracts.py src/classes/api_v1_paths.py \
  src/classes/api_security_policy.py src/classes/fastapi_api_v1_routes.py \
  src/classes/fastapi_handler.py src/classes/app_controller.py \
  src/classes/px4_interface_manager.py src/classes/mavlink_data_manager.py \
  tools/native_integration_fixture.py
git diff --check
```

- **660 tests passed**, including **43 native tests**; four existing Starlette
  deprecation warnings. Log/JUnit: ignored local
  `reports/qgc-slice1/contracts-regression.log` and `.xml`.
- Schema matches **43 sections / 606 parameters**, intentionally increased
  from baseline 604. Log: `reports/qgc-slice1/schema.log`.
- Candidate inventory, syntax/import compilation, and diff checks passed.
- The fixture uses production login, session, CSRF, scope, integration-route,
  logout/revocation, and durable audit behavior; only aircraft/provider/runtime
  observation is mocked. Tests assert the synthetic password and CSRF token
  do not appear in its security audit.
- Independent read-only review found the explicit observation, UID/generation,
  heartbeat freshness, and routing requirements addressed. Subsequent own
  lifecycle review added tests for avoiding API-loop ownership and active-follow
  telemetry reconfiguration.

Dashboard code was not changed; its slice-0 471-test/build evidence and known
lint/CI baseline blockers remain applicable. This is not a new green full-CI
claim. No real server/aircraft provider was contacted by these tests.

## Paired QGC gate completion

The QGC slice-1 gate passed with evidence under
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-1-2026-09-21/`:

- Custom Linux Debug and Release builds and boot checks passed.
- Standard QGC `Unit|Integration` selection excluding `Flaky|Network` passed
  **406/406 CTest targets**, including all **three StockUI** targets.
- Native Qt suites reported **67 client** and **4 manager** passes, including
  initialization/cleanup cases. The final copy-only native/StockUI focused
  regression passed **5/5 CTest targets**.
- Two-endpoint interactive checks in Debug and the actual Release application
  exercised matching aircraft association, deliberate endpoint mismatch,
  sign-out/address correction, and disconnect/restart recovery. Providers and
  MAVLink aircraft were synthetic; production FastAPI authentication and
  integration routes were used. No aircraft control was exercised.
- Raw simulated operator reviews and their dispositions are preserved in
  `custom-pixeagle/reviews/` in the QGC worktree. Prior reviewer context is
  disclosed; these are not a human operator study or field-usability proof.

The paired `custom-pixeagle/SLICE-1.md` records commands, test logs, screenshot
locations, source/binary provenance, mock/offline limitations, and the next
gate. Stock source did not change in slice 1: separate stock builds retain
their slice-0 evidence, while the updated custom build reran StockUI coverage.
Existing repository lint, dashboard lint, and backend hygiene/CI baseline
qualifiers remain unchanged; completing this local slice does not make full
repository CI or hardware qualification green.

## Limits and next slice

The local-path instance-ID fallback is not globally unique; deployment must
set a unique stable `PIXEAGLE_INSTANCE_ID`. Missing/duplicate identity,
unobserved telemetry route, frozen heartbeat, or UID mismatch prevents
association. MAVSDK-only telemetry cannot currently provide a verified system
ID and remains blocked. Unknown video dimensions/source/geometry remain
explicitly null/unverified. Two physical aircraft with identical on-wire IDs
cannot be distinguished by assertions about those same IDs alone.

The next approved slice adds authenticated native media with provenance and
geometry. Following remains disabled until its separately reviewed readiness,
control ownership, abort, and validation gates are implemented. No current
mock/contract result qualifies that behavior.

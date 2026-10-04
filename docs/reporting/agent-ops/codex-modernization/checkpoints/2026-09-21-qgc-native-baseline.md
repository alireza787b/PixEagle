# PXE-0173: Native QGC integration — backend baseline

Date: 2026-09-21. Slice: 0, workspace and baseline.
Branch: `feature/qgc-native-integration`.
Base: `989d9662173b364de03b307f4208e9d0ca96451f`.

Status: baseline evidence complete with the existing failures below recorded as
blockers to a green full-CI claim. Operational integration remains slice 1.

## Workspace and boundary

Created `/home/alireza/PixEagle-qgc-integration` as a separate worktree.
The original `/home/alireza/PixEagle` checkout remains on clean `main`.
This slice changes reporting documents only; API, runtime, dashboard, defaults,
and gimbal behavior remain at the pinned base. No PixEagle application service or flight runtime
were started. No SITL, HIL, camera, or aircraft evidence is claimed.

The paired QGC workspace is `/home/alireza/qgroundcontrol-pixeagle`, on
`feature/pixeagle-native-integration`. Its `custom-pixeagle/BASELINE.md` owns
the QGC build and transport evidence. The approved operational slices remain
separate from this baseline.

## Reproduction and evidence

Evidence directory on this development host:
`/home/alireza/.cache/pixeagle-qgc-baseline/2026-09-21/`.
It contains logs, JUnit, package versions, and exact-commit CI responses; no
credentials are needed for these tests. Commands run from this worktree:

```bash
uv venv .venv --python /usr/bin/python3
uv pip install --python .venv/bin/python -r requirements-core.txt -r requirements-dev.txt
PYTHONPATH=src .venv/bin/python -m pytest -q -o addopts= \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  tests/unit/core_app/test_api_auth_runtime.py \
  tests/unit/core_app/test_api_legacy_media_routes.py \
  tests/unit/streaming/test_websocket_streaming.py \
  tests/unit/drone_interface/test_px4_interface_manager.py
PYTHON=.venv/bin/python bash scripts/check_schema.sh
```

- Focused backend suite: **268 passed**, three Starlette deprecation warnings.
  Evidence: `backend-isolated-tests.log` and `backend-isolated-tests.xml`.
- Schema check: passed, 43 sections / 604 parameters.
  Evidence: `backend-isolated-schema.log`.
- Fresh test environment resolved package versions are retained in
  `backend-packages.txt`; requirements themselves remain upstream range
  constraints. An initial probe used the original environment read-only, then
  verification was repeated in this worktree's isolated environment.
- Dashboard: `npm ci --no-audit --no-fund`,
  `CI=true npm test -- --watchAll=false --runInBand`, and `npm run build` passed
  with Node 24.18.0. **62 suites / 471 tests passed**. Evidence:
  `dashboard-install.log`, `dashboard-tests.log`, `dashboard-build.log`.

## Existing baseline failures

The exact-base [dashboard CI job](https://github.com/alireza787b/PixEagle/actions/runs/35487068257/job/106015295557)
passed install/tests, failed lint, and skipped build. Locally,
`npm run lint -- --format unix` reproduces four errors: render-result naming
in `BoundingBoxDrawer.test.js:340` and `GimbalControlHold.test.js:25`, plus
conditional expectations in `GimbalControlHold.test.js:106–107`.
The independent local production build passed. Evidence: `dashboard-lint.log`.

The exact-base [backend CI job](https://github.com/alireza787b/PixEagle/actions/runs/35487068257/job/106015295539)
failed its Phase 0 guardrail step and skipped later suites. Running the same
guardrail selection locally with the isolated environment produced **152 passed,
1 failed**. `test_no_placeholder_test_files_or_audit_stubs` textually flags
`or True` in `tests/unit/trackers/test_gimbal_control.py`; those occurrences
are fake-send lambdas, not newly introduced assertions. Evidence:
`backend-ci-guardrails-isolated.log`, `backend-ci-checks.json`, and the two
`ci-job-*.json` records. The initial environment lacked `httpx`; installing the
declared dev dependencies in this worktree removed those environment failures.

Full guardrail command:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_api_route_inventory.py tests/test_api_tool_candidates.py \
  tests/test_test_hygiene.py tests/test_docs_infrastructure_consistency.py \
  tests/test_binary_download_policy.py tests/test_production_remote_browser_e2e.py \
  tests/unit/core_app/test_config_clean_clone.py \
  tests/unit/core_app/test_parameters_reload.py -ra --tb=short --strict-config
```

These are recorded baseline blockers, not a green full-suite claim. They need
focused test maintenance separately from the new integration behavior.

## Paired QGC checkpoint

The pinned JPEG transport merge is `2e6190bafc4f4796e29ae24cbd1d27f73b96d07d`.
Untouched upstream and combined stock/custom Debug builds passed. The custom
suite passed all 404 selected CTest targets, including the three stock-UI
targets. Stock passed 404/405 initially and its known GPS UI timing failure
passed a focused rerun. Both builds passed all 13 existing JPEG transport cases.

Stock/custom Linux release builds, boot tests, and isolated mock-vehicle/video
smoke checks passed: Fly View, vehicle switching, local plan creation/save,
offline map overlays, HTTP/WebSocket rendering, PiP/fullscreen, and native
flight-control access. No mission upload or flight execution was tested.
The simple mock lacks complete parameter/mission responses and online map
tiles were unavailable in the network-isolated UI containers. Existing QGC
repository/imported-transport lint failures are recorded in its checkpoint.

Changed backend files are this checkpoint, its journal entry, and the PXE-0173
issue-register row; no operational source changed. Full paired commands,
toolchain/dependency provenance, checksums, limitations, logs, and screenshots
are indexed by `custom-pixeagle/BASELINE.md` and `baseline-manifest.json` in the
QGC workspace.

## Next slice

Slice 1 adds authenticated per-instance context and verified aircraft association.
It must reconcile MAVSDK command identity with explicit telemetry routing;
existing vehicle-1 assumptions cannot establish that association. Following
controls stay disabled. Session/CSRF, shared control, frame provenance, and
default-off behavior retain the approved handoff requirements. Existing vertical
mounting and full hardware-qualification limits remain unchanged.

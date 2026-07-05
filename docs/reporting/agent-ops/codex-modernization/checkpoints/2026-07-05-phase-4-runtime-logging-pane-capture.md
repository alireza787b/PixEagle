# 2026-07-05 Phase 4 Runtime Logging Pane Capture

## Phase / Slice

- Phase 4 runtime observability and evidence follow-up
- Issue: PXE-0079
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

PixEagle runtime logging now captures launched component process output into the
same per-run runtime log tree. Structured backend Python logging remains in
`components/backend.jsonl`; launcher-piped output from started components is
mirrored to tmux and appended as sanitized JSONL entries such as
`components/main_app.jsonl`, `components/dashboard.jsonl`,
`components/mavlink2rest.jsonl`, and `components/mavsdk_server.jsonl`.

This closes the PXE-0079 dashboard/sidecar stdout capture sub-slice. Frontend
browser error ingestion was closed in
`2026-07-05-phase-4-runtime-logging-frontend-ingestion.md`; live streaming,
export bundles, and clean setup walkthrough evidence remain separate follow-ups.

## Changes

- Extended `RuntimeLogSessionManager` with:
  - multi-component session initialization;
  - component manifest registration;
  - sanitized component-message appends;
  - optional `stream` and `source` metadata for pane/process output.
- Added `tools/runtime_log_pipe.py` for line-oriented JSONL capture using the
  existing runtime log redaction and path validation.
- Added `tools/runtime_log_exec.sh` to run a component command with `pipefail`,
  mirror combined stdout/stderr to the operator pane, append redacted JSONL, and
  preserve the child exit code.
- Updated `scripts/run.sh` to:
  - prepare component log files for started components;
  - pass `PIXEAGLE_RUN_ID` and `PIXEAGLE_RUNTIME_LOG_DIR` explicitly to every
    launched component;
  - wrap component commands with the launcher pipe instead of relying on tmux
    pane history.
- Updated the Logs page to `Runtime Component Logs` and display `stream`/`source`
  chips for launcher-piped entries.
- Updated API contracts and docs so log entries can represent either structured
  Python source fields or launcher-piped component output.

## Validation

Passed:

```bash
bash -n scripts/run.sh tools/runtime_log_exec.sh

PYTHONPATH=src .venv/bin/pytest \
  tests/unit/core_app/test_runtime_logging.py \
  tests/unit/core_app/test_runtime_log_pipe.py \
  tests/unit/core_app/test_api_v1_log_routes.py \
  tests/test_api_route_inventory.py \
  tests/test_api_security_policy.py \
  tests/test_api_tool_candidates.py \
  tests/test_docs_infrastructure_consistency.py \
  tests/unit/core_app/test_parameters_reload.py \
  tests/test_setup_profiles.py::test_runtime_launchers_support_dotvenv_and_venv_fallbacks \
  tests/test_setup_profiles.py::test_run_script_captures_tmux_panes_to_runtime_logs \
  -q

bash scripts/check_schema.sh
git diff --check

cd dashboard && CI=true npm test -- --watchAll=false --runTestsByPath src/pages/LogsPage.test.js
cd dashboard && npm run build
```

Observed results:

- backend/API/docs/logging gate: 124 tests passed;
- schema check reported up to date;
- dashboard Logs page test: 1 test passed;
- dashboard production build passed as `main.69d7439a.js`;
- live public quick-demo restart passed with backend/dashboard ready.

## Live Evidence

Live demo run:

```text
logs/runtime/pixeagle_20260705T021300Z_770558/
  manifest.json
  components/backend.jsonl
  components/dashboard.jsonl
  components/main_app.jsonl
```

Observed locally after restart:

- dashboard returned HTTP 200;
- unauthenticated `/api/v1/logs/status` returned 401;
- manifest components were `backend`, `dashboard`, and `main_app`;
- `main_app` entries began with `Starting PixEagle Main Application`;
- `dashboard` entries began with the expected trusted-LAN warning and dashboard
  server header;
- launcher-piped entries used `stream=combined` and `source=launcher-pipe`.

MAVLink2REST and MAVSDK Server component files were not created in this live
quick-demo run because the demo intentionally started with `-m -k`.

## Review Closure

The launcher/process review recommended avoiding semantic readiness claims from
process logs and preserving operator-visible output. The final implementation
uses a launcher pipe rather than tmux history scraping: it mirrors output,
keeps the child exit code, reuses centralized redaction, and avoids storing
typed shell commands as log entries.

## Claim Boundary

These logs are process-local PixEagle evidence only. They do not prove PX4,
SITL, HIL, QGC receiver, MAVLink routing, follower response, deployment
hardening, field behavior, or real-aircraft behavior. Security audit remains
separate.

## Next Planned Slice

- PXE-0079 live log streaming/export evidence bundle after static reads remain
  stable.
- PXE-0074/PXE-0068 clean setup/update walkthrough and public demo credential
  cleanup after user testing.

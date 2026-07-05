# Phase 4 Runtime Logging Live Tail Checkpoint

- Date: 2026-07-05
- Phase: 4
- Issue: PXE-0079
- Slice: bounded runtime log live tail
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

PixEagle runtime logs now support authenticated bounded live tailing through the
existing typed log-entry route:

- `GET /api/v1/logs/sessions/{run_id}?tail=true`

This is not a new long-lived log-stream transport. The dashboard requests a
latest bounded window with `tail=true`, receives `next_offset`, then polls the
same typed route with `offset=<next_offset>` and appends new entries. The
implementation preserves the existing `debug:read` policy, route inventory, and
API/MCP review boundary.

## Changed Files

- `src/classes/runtime_logging.py`
- `src/classes/api_v1_contracts.py`
- `src/classes/api_v1_log_routes.py`
- `src/classes/fastapi_handler.py`
- `dashboard/src/pages/LogsPage.js`
- `dashboard/src/pages/LogsPage.test.js`
- `tests/unit/core_app/test_runtime_logging.py`
- `tests/unit/core_app/test_api_v1_log_routes.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/core-app/02-components/logging-manager.md`
- `docs/core-app/03-api/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
- `/home/alireza/PIXEAGLE_RUNTIME_LOGGING_LIVE_TAIL_2026-07-05.md`

## Behavior

- Existing `read_entries()` remains available for compatibility.
- New `read_entry_window()` returns:
  - redacted `entries`;
  - effective `offset`;
  - bounded `limit`;
  - `next_offset`;
  - `tail`;
  - `matched_total` when exact;
  - `has_more` when known.
- `tail=true` scans the selected component log, returns the last matching
  window, and sets `next_offset` to the exact matching-entry count.
- Reads use the retained single rotated backup (`<component>.jsonl.1`) plus the
  current component JSONL file in chronological order, so cursors survive normal
  single-file rotation. Entries that age out beyond that retained window are no
  longer available from the read API.
- Normal offset reads avoid a full exact count when the page is capped by
  `limit`; `next_offset` still advances the cursor for follow-up polling.
- The dashboard Live tail switch disables manual offset editing while active and
  polls every two seconds without showing a full-page loading bar for each poll.
- Dashboard requests carry a generation token so stale in-flight poll responses
  cannot append entries after Live tail is disabled or filters/session/component
  choices change.
- Live tail is disabled for sessions without `debug:read`, and live mode
  scrolls the table to the newest appended rows.

## Reviewer Findings Closed

- Backend/API reviewer: live-tail cursors originally read only the current
  JSONL file and could drop post-rotation entries. Fixed by reading the retained
  backup plus current file in chronological order and adding a rotation-cursor
  regression test.
- Backend/API reviewer: the generated candidate artifact originally displayed
  `request_model: Optional[str]` for the log-entry query route. Fixed the
  generator to ignore primitive optional query annotations and added a candidate
  regression test; the candidate now has `request_model: null` and remains
  blocked/non-callable.
- Dashboard reviewer: stale in-flight poll responses could append after Live
  tail was disabled or filters changed. Fixed with request generations and a
  stale-response test.
- Dashboard reviewer: live mode did not surface appended rows and the switch
  was available without `debug:read`. Fixed with newest-row scrolling,
  disabled-switch behavior, and a no-debug-access test.

## Evidence Boundary

Runtime logs are process-local PixEagle diagnostics only. This slice does not
claim PX4, MAVSDK, SITL, HIL, QGC receiver, follower response, deployment, or
real-aircraft success.

## Validation

Validation passed:

```bash
PYTHONPATH=src .venv/bin/python -m py_compile \
  src/classes/runtime_logging.py \
  src/classes/api_v1_log_routes.py \
  src/classes/api_v1_contracts.py \
  src/classes/fastapi_handler.py \
  tools/generate_api_tool_candidates.py

PYTHONPATH=src .venv/bin/pytest \
  tests/unit/core_app/test_runtime_logging.py \
  tests/unit/core_app/test_api_v1_log_routes.py \
  tests/test_api_route_inventory.py \
  tests/test_api_tool_candidates.py \
  tests/test_docs_infrastructure_consistency.py \
  tests/test_api_security_policy.py -q

bash scripts/check_schema.sh

PYTHONPATH=src .venv/bin/pytest \
  tests/unit/core_app/test_parameters_reload.py -q

cd dashboard && CI=true npm test -- --watchAll=false \
  --runTestsByPath src/pages/LogsPage.test.js

cd dashboard && npm run build

git diff --check
```

Results:

- backend/API/log/security/docs focused tests: 121 passed;
- parameter reload gate: 10 passed;
- schema check: up to date;
- dashboard Logs page focused tests: 5 passed;
- dashboard production build: `main.f7c7ec4a.js`;
- whitespace diff check: passed;
- API tool-candidate inventory regenerated, with only expected source-hash
  changes.

## Live Public Demo Smoke

The existing public demo was restarted without rotating the active password:

```bash
bash scripts/stop.sh && bash scripts/run.sh --no-attach -m -k
```

Evidence:

- active runtime run: `pixeagle_20260705T091338Z_881812`;
- local dashboard `http://127.0.0.1:3040/`: HTTP 200;
- public dashboard `http://204.168.181.45:3040/`: HTTP 200;
- served manifest references `./static/js/main.f7c7ec4a.js`;
- unauthenticated `GET /api/v1/logs/sessions/{run_id}?tail=true&limit=5`:
  HTTP 401;
- authenticated login using the private handoff credential over the public
  backend succeeded;
- authenticated `tail=true` read returned HTTP 200 with:
  - `count`: 5;
  - `offset`: 107;
  - `next_offset`: 112;
  - `tail`: true;
  - `matched_total`: 112;
  - `has_more`: true;
- authenticated follow-up read from `offset=112` returned HTTP 200 with
  `count=0`, `next_offset=112`, `tail=false`, and `has_more=false`;
- headless Chromium public dashboard smoke at `390x844` logged in, opened
  `/logs`, toggled Live tail, observed one `tail=true` request, saw the cursor
  chip, had no horizontal overflow, and emitted no browser console/page errors.

## Remaining Work

- Continue PXE-0079 final clean setup walkthrough evidence after this slice.

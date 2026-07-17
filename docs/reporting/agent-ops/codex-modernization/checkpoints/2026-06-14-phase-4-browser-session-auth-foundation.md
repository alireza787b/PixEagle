# 2026-06-14 Phase 4 Browser-Session Auth Foundation

## Slice

- Phase: 4 API/MCP modernization
- Issue: PXE-0064 API authentication and exposure boundary
- Status: completed foundation slice; PXE-0064 remains `in_progress`
- Scope: backend browser-session authentication primitives, typed auth routes,
  session CSRF, auth hardening, config/schema/docs/tests/reporting updates

## Summary

This slice adds the backend browser/operator session foundation without
claiming production remote-browser readiness.

Implemented:

- `API_AUTH_MODE=browser_session` runtime mode.
- External JSON browser/operator user file loading through
  `Streaming.API_SESSION_USER_FILE`.
- PBKDF2-SHA256 password records with enforced iteration, salt, and digest
  bounds.
- Strict rejection of plaintext password fields and non-boolean `enabled`
  values in user and bearer token files.
- Typed `/api/v1/auth/session`, `/api/v1/auth/login`, and
  `/api/v1/auth/logout` routes.
- HttpOnly session cookies and session-bound CSRF validation for browser
  mutations.
- Process-local failed-login throttling with per-key, per-client, and global
  key caps plus expiry pruning.
- Dummy password verification for missing/disabled users to reduce username
  timing leakage.
- Credentialed exact-origin CORS only when `API_AUTH_MODE=browser_session`.
- Typed `/api/v1` middleware error envelopes for pre-route auth/origin
  failures on reviewed v1 paths.
- API/MCP candidate provenance updated for the auth route module; generated
  candidates remain non-callable and unpromoted.

## Files Changed

Runtime and API:

- `src/classes/api_auth_runtime.py`
- `src/classes/api_v1_auth_routes.py`
- `src/classes/api_exposure_policy.py`
- `src/classes/api_security_policy.py`
- `src/classes/api_security_types.py`
- `src/classes/api_v1_contracts.py`
- `src/classes/api_v1_paths.py`
- `src/classes/fastapi_api_v1_routes.py`
- `src/classes/fastapi_handler.py`

Config, schema, and generator:

- `configs/config_default.yaml`
- `configs/config_schema.yaml`
- `scripts/generate_schema.py`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`

Tests:

- `tests/unit/core_app/test_api_auth_runtime.py`
- `tests/unit/core_app/test_api_exposure_policy.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_security_policy.py`
- `tests/test_api_tool_candidates.py`

Docs and reporting:

- `README.md`
- `docs/CONFIGURATION.md`
- `docs/INSTALLATION.md`
- `docs/WINDOWS_SETUP.md`
- `docs/apis/api-exposure-boundary.md`
- `docs/apis/api-security-policy.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/drone-interface/04-infrastructure/port-configuration.md`
- `docs/video/04-streaming/webrtc.md`
- `docs/video/04-streaming/websocket.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Reviewer Findings Resolved

- API/MCP reviewer flagged that pre-route auth failures on typed `/api/v1`
  paths returned legacy error JSON. Fixed by routing reviewed v1 middleware
  failures through the typed API error envelope and adding regression coverage.
- API/MCP reviewer flagged runtime/session TTL bounds diverging from generated
  schema. Fixed by enforcing the same `60..604800` second bounds in runtime.
- Docs/operator reviewer flagged the missing checkpoint file, contradictory
  phase-map rollups, and stale active docs saying browser sessions/CSRF were
  absent. Fixed by adding this checkpoint and narrowing active docs to the
  remaining dashboard/media/audit/TLS/operator gates.
- The first security reviewer attempt hit a usage-limit error. A replacement
  security reviewer found PBKDF2 bounds, login-throttle key growth, username
  timing, and loose `enabled` parsing blockers. Fixed all four and reran
  re-review; verdict was approved with no remaining blockers.

## Validation

Focused API/auth suite:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/core_app/test_api_auth_runtime.py \
  tests/unit/core_app/test_api_exposure_policy.py \
  tests/test_api_security_policy.py \
  tests/test_api_route_inventory.py \
  tests/test_api_tool_candidates.py -q
```

Result: 149 passed, 1 Starlette/httpx `TestClient` deprecation warning.

Schema:

```bash
PYTHON=.venv/bin/python bash scripts/check_schema.sh
```

Result: schema current, 544 parameters.

Candidate inventory:

```bash
.venv/bin/python tools/generate_api_tool_candidates.py
PYTHONPATH=src .venv/bin/python tools/generate_api_tool_candidates.py --check
```

Result: generated inventory current; 18 `/api/v1` candidates, 6 reviewed
read-only candidates, 12 guarded/blocked candidates, 0 callable tools, 0
MCP-exposed tools.

Phase 0:

```bash
PYTHON=.venv/bin/python make phase0-check
```

Result: schema current, candidate inventory current, 177 tests passed, 1
Starlette/httpx `TestClient` deprecation warning.

Hygiene:

```bash
git diff --check
```

Result: passed.

Stale wording scan: active README/docs were checked for obsolete
browser-session/auth-foundation wording, excluding historical checkpoint/journal
records and generated API-candidate output.

Result: clean; historical checkpoint/journal text intentionally remains.

## Boundaries

No PX4/SITL/HIL/field run, deployment, service install, sidecar mutation,
runtime MCP endpoint, callable tool, or real-aircraft control was performed or
claimed.

The backend browser-session foundation is implemented, but production
remote-browser operation is not approved. Remaining gates include dashboard
credential-aware API/media migration, durable audit events, TLS/operator
deployment hardening, typed-action-only enforcement, and final legacy mutation
retirement.

## Remaining PXE-0064 Work

- Dashboard migration to one credential-aware API client.
- Authenticated media strategy for MJPEG, video WebSocket, WebRTC signaling,
  downloads, and playback.
- Durable security/audit events using the authenticated principal.
- Operator credential lifecycle tooling and TLS deployment guidance.
- Typed-action-only enforcement and retirement of immediate legacy mutations.
- Broader adversarial auth/session/browser tests after dashboard migration.

## Next Slice Recommendation

Continue PXE-0064 with dashboard credential-aware API/media migration. Keep
`local_compat` same-host only and treat `browser_session` as a backend
foundation until dashboard media/session flows and deployment evidence are
complete.

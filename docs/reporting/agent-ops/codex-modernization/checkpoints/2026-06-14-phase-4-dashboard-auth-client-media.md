# 2026-06-14 Phase 4 Dashboard Auth Client/Media Foundation

## Slice

- Phase: 4 API/MCP modernization
- Issue: PXE-0064 API authentication and exposure boundary
- Status: completed frontend/client/media foundation slice; PXE-0064 remains
  `in_progress`
- Scope: dashboard session UX, credential-aware API client, browser-session
  media handling, protected downloads/playback, scope-aware controls, backend
  CSRF header discovery, docs/tests/reporting

## Summary

This slice connects the dashboard to the browser-session backend foundation
without approving production remote-browser operation.

Implemented:

- Added dashboard `apiClient` as the single production HTTP/media boundary.
- All production raw `fetch` calls now go through `apiFetch`.
- Production axios users import the dashboard client wrapper instead of the
  `axios` package directly.
- Unsafe HTTP methods receive the session CSRF token and backend-reported CSRF
  header name.
- Auth failures dispatch a dashboard session-refresh event.
- Added `AuthSessionProvider`, `AuthGate`, and `AuthStatusMenu` for
  `/api/v1/auth/session`, login, logout, session state, and local/machine mode
  treatment.
- Native browser media uses cookie-session semantics only; no bearer-header or
  query-token browser fallback was added.
- MJPEG image requests use credentialed media props in browser-session mode.
- Video WebSocket and WebRTC signaling construction goes through the shared
  client and stops retrying on authorization close code `1008`.
- Recording/model protected downloads and playback use authenticated blob
  fetches instead of direct protected endpoint links.
- Action buttons honor session scopes for `control:write` and
  `actions:execute`.
- Source guard tests now fail on new production raw `fetch`, direct axios
  package imports, direct `new WebSocket`, or protected endpoint `href`
  bypasses outside the approved client.

## Files Changed

Backend contract:

- `src/classes/api_v1_contracts.py`
- `src/classes/api_v1_auth_routes.py`

Dashboard:

- `dashboard/src/services/apiClient.js`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/services/apiService.js`
- `dashboard/src/context/AuthSessionContext.js`
- `dashboard/src/components/AuthGate.js`
- `dashboard/src/components/AuthStatusMenu.js`
- `dashboard/src/components/VideoStream.js`
- `dashboard/src/components/ActionButtons.js`
- dashboard API/media consumers under `dashboard/src/components/`,
  `dashboard/src/hooks/`, and `dashboard/src/pages/`

Tests:

- `dashboard/src/services/apiClient.test.js`
- `dashboard/src/components/AuthGate.test.js`
- `dashboard/src/components/ActionButtons.test.js`
- `tests/test_test_hygiene.py`
- `tests/unit/core_app/test_api_auth_runtime.py`

Docs and reporting:

- `dashboard/README.md`
- `README.md`
- `docs/CONFIGURATION.md`
- `docs/apis/api-exposure-boundary.md`
- `docs/apis/api-security-policy.md`
- `docs/core-app/03-api/README.md`
- `docs/drone-interface/04-infrastructure/port-configuration.md`
- `docs/video/04-streaming/websocket.md`
- `docs/video/04-streaming/webrtc.md`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Reviewer Findings Addressed

- Frontend/API reviewer flagged raw `fetch`, fragmented axios imports, direct
  media sockets, direct protected downloads, and incomplete tests. The shared
  client boundary, call-site migration, blob downloads, media helpers, and
  source guard were added.
- Security/API reviewer flagged native browser WebSocket limitations,
  query-token rejection, stale direct media URLs, missing dynamic CSRF header
  discovery, and missing scope-aware controls. The backend auth response now
  exposes `csrf_header_name`, dashboard media remains cookie-session only, and
  operator controls check principal scopes.

## Validation

Completed:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/core_app/test_api_auth_runtime.py::test_auth_session_response_reports_configured_csrf_header_name \
  tests/test_test_hygiene.py -q
```

Result: 4 passed.

```bash
npm test -- --watchAll=false
```

Result: 11 suites passed, 62 tests passed.

```bash
npm run build
```

Result: compiled successfully.

```bash
.venv/bin/python tools/generate_api_tool_candidates.py
PYTHON=.venv/bin/python make phase0-check
```

Result: generated API/MCP candidate provenance updated; schema current,
candidate inventory current, 179 tests passed, with the existing
Starlette/httpx `TestClient` deprecation warning.

```bash
git diff --check
```

Result: passed.

Active stale-wording and dashboard source-boundary scans were clean after the
phase-map wording cleanup. The dashboard source scan confirmed that only
`dashboard/src/services/apiClient.js` owns low-level `fetch`, direct axios
package import, and `new WebSocket` construction.

## Boundaries

No PX4/SITL/HIL/field run, deployment, service install, sidecar mutation,
runtime MCP endpoint, callable tool, or real-aircraft control was performed or
claimed.

The dashboard browser-session client/media foundation is implemented, but
production remote-browser operation is not approved.

## Remaining PXE-0064 Work

- Durable security/audit events using authenticated principals.
- Operator credential lifecycle tooling and TLS deployment guidance.
- Typed-action-only enforcement and retirement of immediate legacy mutations.
- Broader adversarial browser/session/media tests, including expiry, multi-tab
  logout, large protected media, and role-denied UX.

## Next Slice Recommendation

Continue PXE-0064 with durable security/audit events or typed-action-only
legacy retirement. Keep remote browser operation gated until audit, TLS,
legacy-retirement, and evidence requirements are complete.

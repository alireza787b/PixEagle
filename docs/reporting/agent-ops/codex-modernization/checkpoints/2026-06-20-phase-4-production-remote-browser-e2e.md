# 2026-06-20 Phase 4 Production Remote Browser E2E

## Phase / Slice

- Phase 4 API/security, dashboard, and setup modernization
- Issues: PXE-0073, PXE-0064 partial, PXE-0068 partial
- Scope: repeatable local HTTPS/browser evidence, dashboard reverse-proxy
  normalization, and active browser-session media revocation.

## Summary

- Added an explicit local evidence harness for the guarded `production_remote`
  shape:
  - self-signed HTTPS on the reserved `pixeagle.test` host;
  - loopback policy backend and ASGI reverse proxy owned by one harness process;
  - current-checkout dashboard production build under `/pixeagle`;
  - API/media proxying under `/pixeagle-api`;
  - Playwright-managed Chromium with recorded version/revision/hash;
  - exact HTTP/WSS authority, path, and route-specific query allowlists;
  - bounded dashboard build, Playwright process-group, Uvicorn task, and iterator
    cleanup;
  - sanitized local evidence and a fixed upload allowlist.
- Added browser evidence for:
  - invalid login denial and Secure HttpOnly `SameSite=Lax` session cookies;
  - session-bound CSRF denial/success;
  - unauthenticated MJPEG/WebSocket denial;
  - authenticated production MJPEG and video-WebSocket traffic;
  - query-token WebSocket denial;
  - logout closing active MJPEG and video WebSocket sessions;
  - post-logout media denial;
  - exact Host/Origin/cross-site/authority-port adversarial rejection;
  - deep-link operation behind the same HTTPS proxy.
- Added runtime session-lifetime enforcement:
  - active MJPEG iteration and response delivery race against revocation;
  - video WebSockets close with policy code `1008` after logout/expiry;
  - WebRTC signaling closes and its peer is cleaned after logout/expiry;
  - WebRTC peer IDs are server-owned;
  - signaling capacity is atomically reserved before peer allocation.
- Migrated follower, safety, and tracker dashboard calls to the canonical endpoint
  registry so `/pixeagle` deployments cannot reconstruct direct backend URLs.
- Removed the unused client hook and endpoint entry for the already-retired
  `/api/safety/vehicle-profiles` route.
- Added an opt-in Playwright Chromium installer and an early actionable failure
  when the browser is absent.

## Files Changed

- Runtime/security:
  - `src/classes/api_auth_runtime.py`
  - `src/classes/fastapi_handler.py`
  - `src/classes/webrtc_manager.py`
- Dashboard:
  - `dashboard/e2e/production-remote.spec.js`
  - `dashboard/playwright.config.js`
  - `dashboard/package.json`
  - `dashboard/package-lock.json`
  - `dashboard/src/services/apiEndpoints.js`
  - `dashboard/src/hooks/useFollowerSchema.js`
  - `dashboard/src/hooks/useSafetyConfig.js`
  - `dashboard/src/pages/TrackerPage.js`
  - focused frontend tests and lint corrections
- Harness/CI/setup:
  - `tools/run_production_remote_browser_e2e.py`
  - `.github/workflows/production-remote-browser-e2e.yml`
  - `.github/workflows/tests.yml`
  - `Makefile`
  - `scripts/check_schema.sh`
- Tests/contracts:
  - `tests/test_production_remote_browser_e2e.py`
  - `tests/unit/streaming/test_streaming_lifecycle.py`
  - `tests/test_test_hygiene.py`
  - `tests/test_docs_infrastructure_consistency.py`
  - `tests/unit/core_app/test_api_exposure_policy.py`
  - `dashboard/src/services/apiEndpoints.test.js`
- Docs/reporting:
  - API exposure/security docs
  - production remote setup/media docs
  - generated API/MCP candidate inventory
  - issue register, phase map, journal, and this checkpoint

## Validation

- Focused browser/runtime/docs gate:
  - `PYTHONPATH=src .venv/bin/python -m pytest tests/test_production_remote_browser_e2e.py tests/unit/streaming/test_streaming_lifecycle.py tests/test_docs_infrastructure_consistency.py -q`
  - Result: 57 passed.
- Phase 0:
  - `make phase0-check`
  - Result: schema and API/MCP candidate inventory current; 353 passed with the
    existing Starlette/httpx `TestClient` deprecation warning.
- Dashboard:
  - `CI=true npm test -- --watchAll=false --runInBand`
  - Result: 98 passed.
  - `npm run lint`: passed.
  - `npm run build`: passed; relative `./` hosting retained.
  - `npm audit --omit=dev`: zero runtime vulnerabilities.
- Full non-SITL suite:
  - `make test`
  - Result: 2321 passed, 40 skipped because dlib is not installed, 1
    explicitly deselected, and the existing Starlette/httpx warning.
- Static checks:
  - Python compile for touched runtime/harness modules: passed.
  - Playwright spec JavaScript syntax: passed.
  - `git diff --check`: passed.

## Development Browser Evidence

- Accepted development run:
  - `reports/production-remote-browser/20260620T214336Z-d0664d`
  - This run recorded a dirty worktree and is not the final clean-revision gate.
- Results:
  - 202 browser requests, 111 responses, and 9 WebSocket observations;
  - zero page errors and zero unexpected request failures;
  - 94 expected `net::ERR_ABORTED` route-navigation cancellations:
    79 XHR and 15 fetch requests, all exact approved API paths and all inside
    the named `route_navigation` transition;
  - all expected 401/403 outcomes were deliberate authorization/adversarial
    checks; no 404 or 5xx response was accepted;
  - 112 sanitized security-audit events with required allowed/denied event
    types;
  - exact generated-secret scan passed for retained artifacts and the finalized
    upload bundle;
  - harness process cleanup passed.

## Independent Review

- Security/runtime review originally found stale evidence, unbounded subprocess
  cleanup, insufficient active-MJPEG revocation, upload scanning order, and
  client-selected WebRTC peer overwrite. All were fixed.
- Frontend/Playwright review originally found accepted 404s/aborts, broad path
  prefixes, and bypassable dashboard-build provenance. All were fixed.
- Final specialist reviews reported no blockers and requested:
  - route-specific query allowlists;
  - atomic WebRTC signaling capacity;
  - removal of the retired safety vehicle-profile client contract.
  All were fixed with focused regressions.
- Closure review found stale generated API provenance, a WebRTC browser-evidence
  wording overclaim, and missing local Chromium installation guidance. All were
  fixed before the final gates.
- Residual CI hardening for immutable GitHub Action pins and a reproducible
  Python dependency lock is outside this slice and must be tracked separately;
  it is not represented as completed here.

## Evidence Boundary

- The Playwright scenario proves the checked-in local application boundary,
  browser session/CSRF behavior, production MJPEG and video-WebSocket
  authorization/revocation, proxy path discipline, adversarial Host/Origin
  denial, audit generation, artifact sanitization, and process cleanup.
- WebRTC signaling-session revocation and peer cleanup are unit/runtime
  evidence. This Playwright scenario does not establish WebRTC media rendering.
- This is not evidence for a trusted certificate, nginx/Caddy configuration,
  target firewall, service ownership, external reachability, camera/tracker/
  follower behavior, QGC compatibility, Docker/PX4/SITL/HIL, field operation,
  or real-aircraft behavior.

## Exact Clean-Revision Evidence

- Evidence commit:
  - `bf32df19ec7f1e8855c1ea934cfb50128a0cf4ea`
- Accepted run:
  - `reports/production-remote-browser/20260620T215137Z-5ce38f`
- Provenance:
  - `git_worktree_clean: true`;
  - recorded Git commit matches the evidence commit;
  - recorded SHA-256 values match the current harness, auth runtime,
    FastAPI handler, WebRTC manager, Playwright spec, and endpoint registry;
  - Playwright-managed Chromium `149.0.7827.55`, revision `1228`.
- Browser/audit results:
  - 210 requests, 111 responses, 9 WebSocket observations;
  - zero page errors and zero unexpected request failures;
  - 104 expected route-navigation cancellations: 90 XHR and 14 fetch;
  - all browser, adversarial HTTP, process-cleanup, security-audit, retained
    artifact, and finalized upload-bundle checks passed;
  - 115 sanitized security-audit events;
  - no generated secret value was echoed into scan output.
- PXE-0073 is complete. Target deployment evidence remains open only under
  PXE-0064/PXE-0068.

## Next Planned Slices

- PXE-0070: repair/rebase QGroundControl PR #13594 with generic optional
  Authorization/Origin/TLS/redaction support and supported-platform tests.
- PXE-0008/PXE-0021: continue typed API/client normalization and replace the
  deprecated CRA dashboard toolchain.
- PXE-0064/PXE-0068: collect target trusted-certificate, reverse-proxy,
  firewall, service-account, credential-handoff, and operator evidence.

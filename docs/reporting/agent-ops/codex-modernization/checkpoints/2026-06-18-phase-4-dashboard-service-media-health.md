# 2026-06-18 Phase 4 Dashboard/Service Media-Health Adoption

- Phase: 4 API/MCP and setup modernization
- Slice: PXE-0068 dashboard/service adoption of typed media-health
- Branch: `codex/modernization-pxe0040-runtime-20260604`
- Commit: pending at checkpoint write time

## Summary

This slice wires the typed process-local media-health route into the two
operator-facing consumers that were still tied to legacy streaming status:

```text
GET /api/v1/streams/media-health
```

Dashboard streaming status/performance widgets now consume the typed route via a
shared `useStreamingMediaHealth()` hook. The hook preserves typed media fields
for new UI consumers, provides legacy-compatible counters for existing widgets,
uses no-cache requests, ignores stale out-of-order responses, and falls back to
legacy `/api/streaming/status` only when the typed route is missing during a
rolling update. Auth failures such as `401` or `403` remain media-health
failures and are not masked by lower-scope legacy fallback.

`pixeagle-service status` now prints a best-effort `Media health` block after
port checks. It probes loopback by default for same-host `local_compat` and can
use an explicit bearer token file via
`PIXEAGLE_MEDIA_HEALTH_BEARER_TOKEN_FILE` for `machine_bearer` or
`browser_session` deployments. It does not use query-string tokens, browser
cookies, or CLI login, and it reports `401/403` as auth-required rather than
media-down.

The claim boundary remains explicit: this is PixEagle process-local backend
media observability only. It does not prove remote browser, QGC, WebRTC peer,
GCS, PX4, SITL, HIL, or field video receipt.

## Files Changed

- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/hooks/useStatuses.js`
- `dashboard/src/hooks/useStatuses.test.js`
- `dashboard/src/components/StreamingStatusIndicator.js`
- `dashboard/src/components/StreamingStatusIndicator.test.js`
- `dashboard/src/components/StreamingStats.js`
- `dashboard/src/components/StreamingStats.test.js`
- `scripts/service/utils.sh`
- `tests/test_service_status_media_health.py`
- `tests/test_docs_infrastructure_consistency.py`
- `docs/SERVICE_MANAGEMENT.md`
- `docs/TROUBLESHOOTING.md`
- `docs/video/04-streaming/README.md`
- `docs/video/06-configuration/streaming-config.md`
- `docs/KNOWN_ISSUES.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- `bash -n scripts/service/utils.sh`: passed.
- `cd dashboard && CI=true npm test -- --watchAll=false --runTestsByPath src/hooks/useStatuses.test.js src/components/StreamingStatusIndicator.test.js src/components/StreamingStats.test.js`: 39 passed.
- `cd dashboard && CI=true npm test -- --watchAll=false`: 84 passed.
- `cd dashboard && npm run build`: passed; CRA production build compiled successfully.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_service_status_media_health.py tests/test_docs_infrastructure_consistency.py tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -q`: 63 passed.
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`: schema current, 41 sections, 549 parameters.
- `PYTHON=.venv/bin/python make PYTHON=.venv/bin/python phase0-check`: schema current, API tool candidate inventory current, 247 passed with the existing Starlette/httpx warning.
- `git diff --check`: passed.

## Reviewer Notes

Two independent read-only reviewers were used before implementation:

- Dashboard/API reviewer recommended a shared typed hook, no fallback on
  `401/403`, typed-to-legacy normalization for existing widgets, and focused
  frontend tests.
- Service/security reviewer recommended loopback-only default probing, optional
  explicit bearer token file support, no browser-session login/cookie scraping,
  no query-string tokens, and distinct auth-required wording.

The implementation follows those recommendations. No reviewer requested a
blocking rework after validation.

## Risks And Remaining Work

- Dashboard and service status are still process-local health checks. Remote
  receipt evidence remains a future QGC/browser/WebRTC validation task.
- `production_remote` remains gated on TLS/operator hardening, credential
  rollout, adversarial auth/media tests, and evidence.
- PXE-0068 still has runtime cleanup follow-ups: WebRTC peer shutdown,
  GStreamer release on app shutdown, and stale WebSocket lifecycle cleanup.
- No service install/start, deployment, Docker/PX4/SITL/HIL, sidecar mutation,
  QGC branch mutation/build, runtime MCP endpoint, callable tool exposure, or
  real-aircraft control was performed or claimed.

## Next Slice

Continue PXE-0068 runtime cleanup unless a higher-priority review item appears:

1. Harden WebRTC peer shutdown and app shutdown cleanup.
2. Release GStreamer output resources on backend shutdown/restart paths.
3. Add stale WebSocket lifecycle cleanup for never-fed or dead clients.
4. Keep dashboard/service/docs/tests aligned with the typed media-health claim
   boundary.

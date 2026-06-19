# 2026-06-19 Phase 4 Browser Session / Media Adversarial Tests

## Phase / Slice

- Phase 4 API/MCP modernization
- Issue: PXE-0064 production remote hardening
- Scope: add focused backend adversarial regression coverage for browser-session
  expiry, logout invalidation, media read access, and typed action denial.

## Summary

- Added regression coverage proving an expired browser-session cookie:
  - is treated as anonymous for public `/api/v1/auth/session`;
  - is purged from the process-local session store;
  - is rejected with `401 invalid_session` on protected
    `/api/v1/streams/media-health`.
- Added regression coverage proving logout invalidates sibling browser tabs that
  still hold the old session cookie. The same cookie can read media-health
  before logout and receives `401 invalid_session` after logout.
- Added regression coverage proving a `viewer` browser session can read typed
  media health but cannot execute typed tracking actions even with a valid CSRF
  token. The denied action reports `403 insufficient_scope` with
  `actions:execute` missing.
- No runtime code change was required; the tests codify already-present
  fail-closed behavior.

## Files Changed

- `tests/unit/core_app/test_api_auth_runtime.py`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Validation

- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_api_auth_runtime.py -q`
  - Result: 37 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_api_auth_runtime.py tests/test_api_security_policy.py tests/test_docs_infrastructure_consistency.py tests/test_api_route_inventory.py -q`
  - Result: 105 passed.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`
  - Result: current.
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`
  - Result: schema current, 41 sections, 549 parameters.
- `.venv/bin/python -m py_compile tests/unit/core_app/test_api_auth_runtime.py`
  - Result: passed.
- `PYTHON=.venv/bin/python make PYTHON=.venv/bin/python phase0-check`
  - Result: schema current, API tool candidate inventory current, 250 passed
    with the existing Starlette/httpx `TestClient` deprecation warning.

## Evidence Boundary

- This slice is backend unit/contract evidence only.
- No browser automation, dashboard build, service install/start, deployment,
  Docker/PX4/SITL/HIL, sidecar mutation, QGC branch mutation/build, runtime MCP
  endpoint, callable tool exposure, field test, or real-aircraft control was
  performed or claimed.
- It does not close all PXE-0064 adversarial remote-readiness work. Remaining
  work includes TLS/operator credential hardening and broader end-to-end
  browser/session/media evidence.

## Risks / Open Questions

- Browser-session UX coverage for expiry, multi-tab logout refresh, large media
  playback, and role-denied operator controls should still be expanded in the
  dashboard layer.
- Production remote access still needs deployment-level TLS, credential
  rotation/rollout, and evidence collection before approval.

## Next Planned Slice

- Continue PXE-0064 with either dashboard-side adversarial browser/session/media
  tests or production remote-profile credential/TLS hardening, depending on
  risk ordering.

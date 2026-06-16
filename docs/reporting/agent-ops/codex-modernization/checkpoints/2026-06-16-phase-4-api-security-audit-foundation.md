# 2026-06-16 Phase 4 API Security-Audit Foundation

## Slice

- Phase: 4 API/MCP modernization
- Issue: PXE-0064 API authentication and exposure boundary
- Status: completed durable security-audit foundation slice; PXE-0064 remains
  `in_progress`
- Scope: sanitized API security audit events, fail-closed audit behavior for
  allowed mutation/security-critical requests, auth-route outcome events,
  config/schema/provenance/docs/tests/reporting updates

## Summary

This slice adds a durable security-audit event foundation for the API/auth boundary
without approving production remote-browser operation.

Implemented:

- Added `src/classes/api_security_audit.py` as a sanitized append-only JSONL
  writer with bounded local rotation and `fsync` after each written event.
- Added `Streaming.API_SECURITY_AUDIT_ENABLED`,
  `Streaming.API_SECURITY_AUDIT_LOG_PATH`,
  `Streaming.API_SECURITY_AUDIT_MAX_BYTES`, and
  `Streaming.API_SECURITY_AUDIT_BACKUP_COUNT` to checked-in defaults and the
  generated schema.
- HTTP route authorization, browser origin denial, video WebSocket
  authorization, WebRTC signaling authorization, login, and logout now record
  security audit events without raw cookies, bearer token values, passwords, or
  session credential IDs.
- Allowed `mutation` and `security_critical` requests fail closed with
  `503 security_audit_unavailable` if the audit event cannot be recorded.
- Successful login rolls back the newly created session before the cookie is
  returned when the required audit event cannot be written.
- API/MCP candidate provenance now includes `src/classes/api_security_audit.py`.
  Generated candidates remain non-callable and unpromoted.
- Active docs/reporting now treat the audit-event foundation as complete while
  keeping TLS/operator credential hardening, typed-action-only enforcement,
  final legacy mutation retirement, and broader adversarial tests open.

## Files Changed

Runtime and API:

- `src/classes/api_security_audit.py`
- `src/classes/api_auth_runtime.py`
- `src/classes/api_v1_auth_routes.py`
- `src/classes/fastapi_handler.py`
- `src/classes/webrtc_manager.py`
- `src/classes/api_security_policy.py`

Config, schema, and generator:

- `configs/config_default.yaml`
- `configs/config_schema.yaml`
- `scripts/generate_schema.py`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`

Tests:

- `tests/unit/core_app/test_api_security_audit.py`
- `tests/unit/core_app/test_api_auth_runtime.py`
- `tests/unit/core_app/test_api_exposure_policy.py`
- `tests/test_api_tool_candidates.py`

Docs and reporting:

- `README.md`
- `dashboard/README.md`
- `docs/CONFIGURATION.md`
- `docs/INSTALLATION.md`
- `docs/WINDOWS_SETUP.md`
- `docs/agent-context/README.md`
- `docs/apis/api-exposure-boundary.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/apis/api-security-policy.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/drone-interface/04-infrastructure/port-configuration.md`
- `docs/video/04-streaming/webrtc.md`
- `docs/video/04-streaming/websocket.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Reviewer Findings

- Security/auth reviewer blocked closure because
  `API_SECURITY_AUDIT_ENABLED=false` made required allowed
  mutation/security-critical events look successful. Fixed by treating a skipped
  required allowed event the same as an unavailable audit sink, and added HTTP
  and WebRTC helper regression coverage.
- Security/auth reviewer flagged that logout audit failure returned `503` while
  leaving the server session alive. Fixed by revoking the session and clearing
  the browser cookie even when the logout audit event cannot be recorded.
- Docs/config reviewer blocked closure because login audit failure revoked the
  session but could still leave a stale `Set-Cookie` header from the injected
  FastAPI response. Fixed by clearing the session cookie on both the injected
  response and the returned typed error response, with regression coverage.
- Docs/config reviewer flagged active phase-map tab indentation that could
  render as a Markdown code block. Fixed by normalizing the active prose
  indentation.
- Docs/config reviewer flagged missing operator documentation for the new audit
  config knobs. Fixed by documenting enablement, path resolution, rotation,
  retention boundary, and restart expectation in `docs/CONFIGURATION.md`.
- Local review found and fixed ambiguous active wording that still credited the
  dashboard/media slice with closing the audit-event work rather than the later
  security-audit slice.
- Candidate provenance initially failed `--check` because the wording change in
  `api_security_policy.py` changed its source hash. The candidate inventory was
  regenerated and rechecked.

## Validation

Focused security-audit/auth tests:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/core_app/test_api_security_audit.py \
  tests/unit/core_app/test_api_auth_runtime.py::test_login_success_rolls_back_session_when_security_audit_fails \
  tests/unit/core_app/test_api_exposure_policy.py::test_http_middleware_records_denied_auth_event \
  tests/unit/core_app/test_api_exposure_policy.py::test_http_middleware_blocks_allowed_security_critical_without_audit -q
```

Result: 8 passed, with the existing Starlette/httpx `TestClient` deprecation
warning.

After reviewer fixes, the focused command was expanded to include audit-disabled
and logout/login cookie regressions. Result: 11 passed, with the same warning.

Touched-module syntax:

```bash
PYTHONPATH=src .venv/bin/python -m py_compile \
  src/classes/api_security_audit.py \
  src/classes/api_auth_runtime.py \
  src/classes/api_v1_auth_routes.py \
  src/classes/fastapi_handler.py \
  src/classes/webrtc_manager.py \
  src/classes/api_security_policy.py \
  tools/generate_api_tool_candidates.py \
  scripts/generate_schema.py \
  tests/unit/core_app/test_api_security_audit.py \
  tests/unit/core_app/test_api_auth_runtime.py \
  tests/unit/core_app/test_api_exposure_policy.py \
  tests/test_api_tool_candidates.py
```

Result: passed.

Schema:

```bash
PYTHON=.venv/bin/python bash scripts/check_schema.sh
```

Result: schema current, 548 parameters.

Candidate inventory:

```bash
.venv/bin/python tools/generate_api_tool_candidates.py
.venv/bin/python tools/generate_api_tool_candidates.py --check
```

Result: generated API/MCP candidate provenance current.

Phase 0:

```bash
PYTHON=.venv/bin/python make phase0-check
```

Result: schema current, candidate inventory current, 185 tests passed, with the
existing Starlette/httpx `TestClient` deprecation warning.

Hygiene:

```bash
git diff --check
```

Result: passed.

Active stale-wording scan:

```bash
rg -n "durable audit|durable security audit events using|dashboard/media migration|dashboard/media/audit|remaining dashboard/media|security audit events, TLS|until durable audit" \
  README.md docs dashboard/README.md configs scripts src tests \
  --glob '!docs/reporting/agent-ops/codex-modernization/checkpoints/**' \
  --glob '!docs/reporting/agent-ops/codex-modernization/journal/**' \
  --glob '!docs/reporting/agent-ops/codex-modernization/audits/**'
```

Result: clean in active guidance. Historical checkpoints and journal entries are
excluded because they intentionally preserve status at the time they were
written.

## Boundaries

No PX4/SITL/HIL/field run, deployment, service install, sidecar
mutation/update, runtime MCP endpoint, callable tool, or real-aircraft control
was performed or claimed.

The security-audit foundation records auth decisions and auth route outcomes;
it does not make remote browser operation production-approved by itself.

## Remaining PXE-0064 Work

- Operator credential lifecycle tooling and TLS deployment guidance.
- Typed-action-only enforcement and retirement of immediate legacy mutations.
- Broader adversarial browser/session/media tests, including expiry, multi-tab
  logout, large protected media, role-denied UX, audit-log rotation, and audit
  failure behavior across WebSocket/WebRTC paths.

## Next Slice Recommendation

Continue PXE-0064 with typed-action-only enforcement and final legacy mutation
retirement, or with operator credential/TLS hardening if deployment readiness is
the immediate priority. Keep remote browser operation gated until TLS/operator
credential, legacy-retirement, and adversarial test evidence are complete.

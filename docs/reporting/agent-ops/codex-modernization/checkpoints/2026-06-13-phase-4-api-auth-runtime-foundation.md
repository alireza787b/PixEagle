# 2026-06-13 Phase 4 API Auth Runtime Foundation

## Slice

- Phase: 4 API/MCP modernization
- Issue: PXE-0064 API authentication and exposure boundary
- Status: completed foundation slice; PXE-0064 remains `in_progress`
- Scope: backend HTTP/MJPEG/WebSocket/WebRTC runtime authorization foundation,
  config/schema/docs/test/reporting updates

## Summary

This slice turns the declarative API security policy into a runtime guard for
PixEagle's FastAPI transport surfaces.

Implemented:

- `src/classes/api_auth_runtime.py` with:
  - `API_AUTH_MODE=local_compat` and `API_AUTH_MODE=machine_bearer`;
  - external JSON bearer token records with only SHA-256 token hashes stored;
  - exact bearer scopes, no role expansion for machine credentials;
  - query-string token rejection for HTTP and WebSocket transports;
  - route authorization using the existing default-deny policy;
  - same-host `local_compat` only when the immediate socket peer is loopback;
  - refusal to infer local transport from `Host` or proxy-forwarded client
    identity headers.
- FastAPI HTTP middleware authorization before route execution and before
  MJPEG streaming response creation.
- Video WebSocket and WebRTC-signaling authorization before `accept()`.
- Config/schema entries for `Streaming.API_AUTH_MODE` and
  `Streaming.API_BEARER_TOKEN_FILE`.
- API/MCP candidate provenance now includes `api_exposure_policy.py`,
  `api_auth_runtime.py`, `api_security_types.py`, and
  `api_security_policy.py`.
- Active docs no longer imply `/webrtc/offer` exists or that `Host`/reverse
  proxy metadata can make `local_compat` remote-safe.

## Files Changed

Runtime and schema:

- `src/classes/api_auth_runtime.py`
- `src/classes/fastapi_handler.py`
- `src/classes/webrtc_manager.py`
- `configs/config_default.yaml`
- `configs/config_schema.yaml`
- `scripts/generate_schema.py`
- `scripts/run.sh`
- `scripts/service/run.sh`

Tests and generated inventory:

- `tests/unit/core_app/test_api_auth_runtime.py`
- `tests/unit/core_app/test_api_exposure_policy.py`
- `tests/test_api_tool_candidates.py`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `Makefile`

Docs and reporting:

- `README.md`
- `docs/CONFIGURATION.md`
- `docs/INSTALLATION.md`
- `docs/TROUBLESHOOTING.md`
- `docs/WINDOWS_SETUP.md`
- `docs/agent-context/README.md`
- `docs/apis/api-exposure-boundary.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/apis/api-security-policy.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/drone-interface/04-infrastructure/port-configuration.md`
- `docs/video/04-streaming/README.md`
- `docs/video/04-streaming/webrtc.md`
- `docs/video/04-streaming/websocket.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Reviewer Findings Resolved

- API/security reviewer flagged that `local_compat` could trust `Host` as
  loopback proof. Fixed by requiring socket-peer loopback and adding tests that
  deny Host-only local proof.
- Browser/media reviewer flagged reverse-proxy risk. Fixed by rejecting
  proxy-forwarded client identity headers for local compatibility/local-only
  elevation, adding tests, and updating docs to warn against externally
  reachable reverse proxies for `local_compat`.
- Browser/media reviewer flagged that `machine_bearer` would break current
  browser dashboard/media paths. Fixed by documenting that it is for machine API
  clients until browser sessions and authenticated media transport land.
- API/MCP reviewer flagged missing exposure-policy provenance. Fixed by hashing
  `src/classes/api_exposure_policy.py` into the generated candidate inventory.
- Reviewers flagged stale schema and streaming docs. Fixed schema descriptions,
  WebRTC `/ws/webrtc_signaling` docs, and WebSocket pre-accept guard examples.

## Validation

Passed:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/core_app/test_api_auth_runtime.py \
  tests/unit/core_app/test_api_exposure_policy.py \
  tests/test_api_security_policy.py \
  tests/test_api_tool_candidates.py \
  tests/test_docs_infrastructure_consistency.py -q
```

Result: 115 passed, 1 Starlette/httpx `TestClient` deprecation warning.

```bash
PYTHON=.venv/bin/python bash scripts/check_schema.sh
```

Result: schema current, 539 parameters.

```bash
.venv/bin/python tools/generate_api_tool_candidates.py --check
```

Result: generated API candidate inventory current.

```bash
.venv/bin/python -m py_compile \
  src/classes/api_auth_runtime.py \
  src/classes/fastapi_handler.py \
  src/classes/webrtc_manager.py \
  tests/unit/core_app/test_api_auth_runtime.py \
  tests/unit/core_app/test_api_exposure_policy.py \
  tools/generate_api_tool_candidates.py \
  tests/test_api_tool_candidates.py
```

Result: passed.

```bash
PYTHON=.venv/bin/python make phase0-check
```

Result: schema current, candidate inventory current, 154 tests passed, 1
Starlette/httpx `TestClient` deprecation warning.

```bash
git diff --check
bash -n scripts/run.sh scripts/service/run.sh \
  scripts/components/dashboard.sh scripts/components/mavlink2rest.sh \
  src/tools/mavlink2rest/build_mavlink2rest.sh
```

Result: passed.

Stale wording scan:

```bash
rg -n "same-host loopback reverse proxy|Temporary unauthenticated compatibility mode|not runtime authentication|not middleware|/webrtc/offer|/webrtc/ice|WebRTCManager\\(video_handler\\)|trusted_lan_legacy.*unauth|unauthenticated.*trusted_lan_legacy|current unauthenticated backend" \
  README.md docs configs src scripts tests || true
```

Result: clean except intentional dashboard/MAVLink2REST sidecar warnings and
the historical 2026-06-12 checkpoint.

## Boundaries

No PX4/SITL/HIL/field run, deployment, service install, sidecar mutation,
runtime MCP endpoint, callable tool, or real-aircraft control was performed or
claimed.

The new runtime auth foundation does not implement browser sessions or CSRF.
`machine_bearer` is usable for machine/API clients that can send
`Authorization: Bearer ...`; current browser-native WebSocket/MJPEG/download
paths still need the next browser-session/media-auth slice.

## Remaining PXE-0064 Work

- Browser/operator users, password hashing, login/logout/session routes, and
  brute-force controls.
- Session-bound CSRF for browser mutations and credentialed exact-origin CORS.
- Dashboard migration to a credential-aware API client and authenticated media
  transport strategy.
- Durable security/audit event records using the authenticated principal.
- Typed-action-only enforcement and final legacy mutation retirement.
- Broader adversarial auth tests once browser sessions exist.

## Next Slice Recommendation

Continue PXE-0064 with browser session and dashboard client architecture before
expanding remote browser support. Keep `local_compat` same-host only and treat
any reverse-proxy deployment as a separate explicit architecture with its own
auth boundary, not as local compatibility.

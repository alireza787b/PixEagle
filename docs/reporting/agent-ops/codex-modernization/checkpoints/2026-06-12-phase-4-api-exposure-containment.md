# Phase 4 API Exposure Containment Checkpoint

Date: 2026-06-12
Slice: PXE-0064 first containment foundation
Branch: `codex/modernization-pxe0040-runtime-20260604`
Base commit before slice: `790ddf8f3e8f9f2f8626300d60c3546ee4eeaf31`

## Outcome

This slice completes the first PXE-0064 containment foundation. PixEagle no
longer has checked-in defaults, managed launchers, or active docs that normalize
unauthenticated LAN exposure for the backend, dashboard, WebSockets, WebRTC
signaling, or MAVLink2REST HTTP API.

Implemented:

- `Streaming.API_EXPOSURE_MODE` with `local_only` and
  `trusted_lan_legacy`;
- checked-in backend bind default `127.0.0.1:5077`;
- explicit CORS origin allowlist with no wildcard and no credentials;
- startup failure for contradictory `local_only` bind or CORS origins;
- legacy missing-mode remote bind migration to loopback rather than preserving
  old broad exposure;
- HTTP Host authority checks before route execution to reduce DNS-rebinding
  exposure;
- browser `Origin` and `Sec-Fetch-Site` checks before route execution;
- same-site resource and anti-framing response headers;
- WebSocket and WebRTC-signaling Host/Origin checks before `accept()`;
- dashboard and MAVLink2REST Linux/Windows launchers defaulting to loopback;
- launcher rejection of non-loopback dashboard/MAVLink2REST HTTP binds unless
  `trusted_lan_legacy` is explicitly selected;
- active operator docs and troubleshooting guidance updated to local-first
  access and SSH tunnel guidance;
- guardrail tests preventing stale `0.0.0.0`/LAN exposure defaults and docs
  from returning.

This is not full production authentication. PXE-0064 remains open for
authenticated browser/operator sessions, machine bearer tokens, CSRF,
role/scope authorization, authenticated media/WebSocket paths, audit events,
typed-action-only enforcement, and legacy mutation retirement.

## Files Changed

Core runtime and policy:

- `src/classes/api_exposure_policy.py`
- `src/classes/fastapi_handler.py`
- `src/classes/webrtc_manager.py`

Config, schema, launchers, and sidecar helpers:

- `configs/config_default.yaml`
- `configs/config_schema.yaml`
- `scripts/generate_schema.py`
- `dashboard/env_default.yaml`
- `scripts/components/dashboard.sh`
- `scripts/components/dashboard.bat`
- `scripts/components/mavlink2rest.sh`
- `scripts/components/mavlink2rest.bat`
- `scripts/run.sh`
- `scripts/service/run.sh`
- `scripts/service/utils.sh`
- `src/tools/mavlink2rest/build_mavlink2rest.sh`

Docs and generated agent inventory:

- `README.md`
- `docs/apis/api-exposure-boundary.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/README.md`
- `docs/CONFIGURATION.md`
- `docs/INSTALLATION.md`
- `docs/TROUBLESHOOTING.md`
- `docs/WINDOWS_SETUP.md`
- `docs/core-app/README.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/core-app/04-configuration/README.md`
- `docs/drone-interface/03-protocols/mavlink2rest-api.md`
- `docs/drone-interface/04-infrastructure/port-configuration.md`
- `docs/video/04-streaming/websocket.md`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`

Tests and modernization records:

- `tests/unit/core_app/test_api_exposure_policy.py`
- `tests/test_network_exposure_defaults.py`
- `tests/test_docs_infrastructure_consistency.py`
- `docs/reporting/agent-ops/codex-modernization/audits/2026-06-12-api-exposure-containment.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Validation

- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_api_exposure_policy.py tests/test_network_exposure_defaults.py tests/test_docs_infrastructure_consistency.py -q`:
  79 passed, with one Starlette/httpx deprecation warning from `TestClient`.
- `bash -n scripts/run.sh scripts/service/run.sh scripts/service/utils.sh scripts/components/dashboard.sh scripts/components/mavlink2rest.sh src/tools/mavlink2rest/build_mavlink2rest.sh`:
  passed.
- `.venv/bin/python -m py_compile src/classes/api_exposure_policy.py src/classes/fastapi_handler.py src/classes/webrtc_manager.py`:
  passed.
- Stale exposure search for old LAN/default/wildcard patterns:
  clean except intentional negative assertions in guardrail tests.
- `.venv/bin/python tools/generate_api_tool_candidates.py`:
  regenerated candidate inventory.
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`:
  schema current.
- `PYTHON=.venv/bin/python make phase0-check`:
  schema current, candidate inventory current, 60 passed.
- `CI=true npm test -- --watchAll=false` in `dashboard/`:
  9 suites passed, 54 tests passed.
- `npm run build` in `dashboard/`:
  production build compiled successfully.
- `git diff --check`:
  passed, with only expected Git line-ending warnings for the Windows batch
  launchers.

Generated candidate inventory remains non-callable: 130 declared HTTP routes,
15 `/api/v1` candidates, 6 reviewed read-only candidates, 9 guarded/blocked
candidates, 0 callable tools, and 0 MCP-exposed tools.

## Review Notes

Earlier slice review findings were fixed before final validation:

- DNS-rebinding Host/authority checks were added to the HTTP middleware policy.
- Stale service URL helpers, port docs, and launcher display logic were changed
  from LAN-advertising to local-first.
- Dashboard cache-control preflight headers were added to explicit CORS
  headers.
- Empty `trusted_lan_legacy` bind host now fails closed.
- The legacy MAVLink2REST helper example/default was corrected to loopback.
- The legacy MAVLink2REST build/run helper now rejects non-loopback HTTP binds
  unless `PIXEAGLE_MAVLINK2REST_EXPOSURE_MODE=trusted_lan_legacy` is explicit.
- Host/authority enforcement now wraps CORS preflight, so an allowed browser
  origin cannot receive a successful preflight for an unapproved Host.
- Video and WebRTC-signaling WebSockets now validate Host as well as Origin
  before `accept()`.
- Dashboard env docs, configuration docs, and schema descriptions now name
  `5077` as the backend API/streaming port and document `HOST=127.0.0.1`.

Independent final reviewers checked API/security, docs/devops, and
flight-safety/product aspects. The code-level exposure posture had no remaining
API/security blocker after the fixes above. The docs/devops reviewer blocker
was the legacy MAVLink2REST helper bypass; it is fixed and covered by a
subprocess rejection test. The flight-safety/product reviewer initially saw the
checkpoint file before it was added; the checkpoint/audit files now exist and
are included in this slice.

## Risks And Open Work

- A same-host untrusted process can still call local unauthenticated APIs; this
  slice does not implement authentication.
- `trusted_lan_legacy` remains unauthenticated and is not production-approved.
- Browser mutations still need CSRF and authorization in the next PXE-0064
  slices.
- Media/WebSocket paths still need authenticated session/token handling.
- Legacy immediate mutation aliases still exist until the typed-action-only
  retirement slice.
- This slice did not run PX4, SITL, HIL, field validation, service install, or
  sidecar mutation/update.

## Next Slice

Continue PXE-0064 with the real authenticated boundary:

- browser/operator authentication and CSRF;
- machine-token authentication;
- route sensitivity and role/scope policy;
- authenticated MJPEG/WebSocket/WebRTC signaling;
- audit events for sensitive reads and mutations;
- final legacy mutation retirement gates.

PXE-0066 candidate dispositions and PXE-0065 SITL sidecar-evidence hardening
remain the next governance/evidence slices around the API security work.

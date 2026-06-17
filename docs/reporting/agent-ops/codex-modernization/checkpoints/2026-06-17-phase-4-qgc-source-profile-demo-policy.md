# Phase 4 QGC Source Profile And Demo Policy

Date: 2026-06-17  
Slice: PXE-0071  
Status: done  

## Scope

This micro-slice answered the follow-up question raised after the remote media
security policy:

- QGroundControl PR #13594 should continue supporting ordinary non-PixEagle
  HTTP/HTTPS MJPEG and WebSocket sources.
- PixEagle remote HTTP/WS should be a stricter configured source profile on top
  of generic QGC support, not hard-coded QGC behavior.
- Beginner phone/tablet/GCS demos need a clear path that is easy without making
  anonymous remote backend control the default.

No runtime media behavior was changed.

## Decisions

- Keep QGC HTTP/WebSocket source support generic for IP cameras, lab servers,
  and other non-PixEagle sources.
- Do not make QGC require PixEagle authentication for normal non-PixEagle HTTP
  sources.
- Do not hard-code PixEagle-specific mode logic into QGC core video routing.
- Document PixEagle as one source profile that uses generic QGC controls:
  URL, optional Authorization header, optional WebSocket Origin, TLS/WSS policy,
  and credential redaction.
- Full browser-dashboard demos from phone/tablet should use generated
  `browser_session` credentials and explicit Host/CORS allowlists.
- No-password remote demos must be media-only, explicitly unsafe, and never
  selected by default.
- The official repository default remains a same-host beginner demo with no
  manual credential setup. When access leaves loopback, setup must select an
  explicit profile and generate or request the required credentials.
- Future remote PixEagle QGC HTTP/WS uses PixEagle config plus generic QGC
  settings: exact `API_ALLOWED_HOSTS`, a matching QGC URL host authority,
  `Authorization: Bearer <token>`, optional WebSocket Origin, TLS/WSS, and
  credential redaction.
- A QGC video-only token should grant only `media:read`. Additional status,
  telemetry, control, config, model, recording, or safety scopes need separate
  endpoint-specific review.

## Files Changed

- `docs/video/04-streaming/qgc-http-websocket-source-plan.md`
- `docs/video/04-streaming/remote-media-security.md`
- `docs/video/04-streaming/README.md`
- `docs/video/06-configuration/streaming-config.md`
- `docs/video/README.md`
- `docs/CONFIGURATION.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `tests/test_docs_infrastructure_consistency.py`

## QGC PR Disposition

No QGroundControl branch was mutated in this slice. A clarification comment was
posted to the PR so maintainers can see that generic non-PixEagle HTTP/WS source
support remains in scope while PixEagle remote HTTP/WS remains a stricter future
profile:

- <https://github.com/mavlink/qgroundcontrol/pull/13594#issuecomment-4731276373>

PXE-0070 remains open and must:

- preserve generic URL-only HTTP/HTTPS MJPEG and WebSocket support;
- add optional generic auth/header/TLS controls;
- make PixEagle remote HTTP/WS one documented source profile;
- include tests for anonymous generic success, PixEagle-style 401/403,
  missing/wrong Origin, bearer success, TLS behavior, and redaction.

## Bootstrap Disposition

PXE-0068 was expanded to include explicit setup profiles:

- `local_dev`;
- `field_qgc_video`;
- `demo_lan_browser`;
- `production_remote`;
- possible future `unsafe_demo_lan_media_only`.

The accepted direction is generated credentials for full remote browser demos,
not anonymous dashboard/control access.

## Validation

- `.venv/bin/python -m pytest tests/test_docs_infrastructure_consistency.py -ra --tb=short --strict-config`
  - 16 passed.
- `rg -n "/video_feed\\?(quality|resize|osd)=" docs tests README.md`
  - no matches.
- `rg -Un "OSD:\\n\\s+ENABLE:" docs tests README.md`
  - no matches.
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`
  - schema current; 41 sections, 549 parameters.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -ra --tb=short --strict-config`
  - 36 passed.
- `.venv/bin/python -m py_compile tests/test_docs_infrastructure_consistency.py`
  - passed.
- `git diff --check`
  - passed.
- `PYTHON=.venv/bin/python make phase0-check`
  - schema current;
  - API tool candidate inventory current;
  - 196 passed with the existing Starlette/httpx `TestClient` deprecation
    warning.
- After the PixEagle configuration-contract clarification, the focused docs
  suite, schema check, route inventory/parameter reload gate, `git diff --check`,
  and `PYTHON=.venv/bin/python make phase0-check` were rerun. The final
  aggregate result remained 196 passed with the same existing Starlette/httpx
  warning.

## Not Performed

- No QGC branch mutation.
- No QGC build.
- No PX4/SITL/HIL/field run.
- No service install.
- No sidecar mutation/update.
- No deployment.
- No runtime MCP endpoint or callable tool exposure.
- No real-aircraft control.

## Next Slice

Continue PXE-0068 bootstrap/setup UX cleanup unless PXE-0070 is pulled forward
to modify and test the QGroundControl PR branch.

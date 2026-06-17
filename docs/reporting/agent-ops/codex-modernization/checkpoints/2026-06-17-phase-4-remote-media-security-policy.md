# 2026-06-17 Phase 4 Remote Media Security Policy

Slice: PXE-0069  
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

This slice answered the companion-to-ground-station question raised after the
QGC video compatibility reconciliation: PixEagle may run on an onboard
Raspberry Pi/Jetson while QGroundControl or a browser runs on a different
laptop, tablet, or phone, but that must not become anonymous remote access to
PixEagle's backend media endpoints.

The accepted policy is:

- same-host local development remains loopback `local_compat`;
- field QGC video uses PixEagle GStreamer H.264/RTP/UDP output while backend
  API/media remains loopback;
- remote browser access uses SSH tunnel now, and later hardened
  `browser_session` over TLS with exact Host/CORS and audit gates;
- remote native HTTP/WebSocket media is a machine-client profile requiring
  `media:read` bearer credentials, no query tokens, WebSocket Origin support,
  and HTTPS/WSS for non-lab deployments;
- anonymous remote backend HTTP/WebSocket media is not supported.

## Code And Config

Added `Streaming.API_ALLOWED_HOSTS` as an explicit backend Host authority
allowlist, separate from browser CORS origins:

- `src/classes/api_exposure_policy.py`
  - validates `API_ALLOWED_HOSTS`;
  - rejects empty, wildcard, URL, credential, and wildcard-bind entries;
  - rejects non-loopback `API_ALLOWED_HOSTS` in `local_only`;
  - uses explicit allowed hosts for `trusted_lan_legacy`;
  - keeps a compatibility fallback for older trusted-LAN configs that had not
    yet separated Host allowlist from CORS origins.
- `configs/config_default.yaml`
  - adds `API_ALLOWED_HOSTS: []` with a local-only-safe default.
- `configs/config_schema.yaml` and `scripts/generate_schema.py`
  - add generated schema metadata for the new setting.

## Documentation

Added the canonical deployment profile page:

- `docs/video/04-streaming/remote-media-security.md`

Updated active docs:

- `docs/video/04-streaming/README.md`
- `docs/video/04-streaming/http-mjpeg.md`
- `docs/video/04-streaming/websocket.md`
- `docs/video/06-configuration/streaming-config.md`
- `docs/video/03-gstreamer/output-pipeline.md`
- `docs/video/README.md`
- `docs/apis/api-exposure-boundary.md`
- `docs/apis/api-security-policy.md`
- `docs/CONFIGURATION.md`
- `docs/drone-interface/04-infrastructure/port-configuration.md`
- `docs/video/05-osd/README.md`
- `docs/video/05-osd/osd-renderer.md`

The docs now state that:

- `API_ALLOWED_HOSTS` is backend Host allowlisting;
- `API_CORS_ALLOWED_ORIGINS` is browser Origin allowlisting;
- QGC on another machine should use GStreamer UDP/RTP today;
- future direct QGC HTTP/WS needs QGC Authorization/Origin/TLS support;
- Basic authentication is not PixEagle's backend user-management model;
- viewer/operator/admin roles are for browser sessions;
- bearer tokens are for native/machine clients;
- `/video_feed` does not expose per-request `quality`, `resize`, or `osd`
  query parameters.

## QGC Disposition

No QGroundControl branch was mutated in this slice. The open QGC PR #13594
still requires a separate QGC-side slice, now tracked as PXE-0070:

- rebase/repair the dirty PR branch;
- add reviewed video auth settings and credential redaction;
- send `Authorization: Bearer <media:read token>` for HTTP MJPEG via
  GStreamer `souphttpsrc` extra headers;
- send Authorization and Origin for WebSocket via
  `QWebSocket::open(QNetworkRequest)`;
- add TLS/CA strict-validation behavior;
- extend synthetic test servers and tests for 401/403, missing/wrong Origin,
  bearer success, and redaction.

## Independent Review

Two independent reviewers were used before implementing the policy:

- PixEagle API/security/media reviewer: recommended local-only backend by
  default, SSH tunnel or browser-session for browser operation, scoped bearer
  tokens for machine/native clients, and GStreamer H.264/RTP/UDP as the current
  field QGC path.
- QGC/Qt/GStreamer reviewer: confirmed `souphttpsrc` can send extra headers,
  Qt `QWebSocket` can send headers via `QNetworkRequest`, Basic auth is not the
  preferred PixEagle backend model, and PR #13594 lacks remote authenticated
  media support today.

Official references consulted:

- QGroundControl video settings and supported source documentation;
- QGroundControl GStreamer video receiver documentation;
- GStreamer `souphttpsrc` documentation;
- Qt `QWebSocket` documentation.

## Validation

Passed:

```bash
.venv/bin/python -m pytest \
  tests/unit/core_app/test_api_exposure_policy.py \
  tests/test_docs_infrastructure_consistency.py \
  -ra --tb=short --strict-config
```

Result: 92 passed, with the existing Starlette/httpx `TestClient` warning.

```bash
PYTHON=.venv/bin/python bash scripts/check_schema.sh
```

Result: schema current, 41 sections, 549 parameters.

```bash
.venv/bin/python tools/generate_api_tool_candidates.py
```

Result: candidate inventory regenerated; only the
`src/classes/api_exposure_policy.py` provenance hash changed.

```bash
.venv/bin/python -m py_compile \
  src/classes/api_exposure_policy.py \
  tests/unit/core_app/test_api_exposure_policy.py \
  tests/test_docs_infrastructure_consistency.py
```

Result: passed.

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  -ra --tb=short --strict-config
```

Result: 36 passed.

Manual stale-doc scans for `/video_feed?quality|resize|osd`, old streaming
config keys, and old `OSD.ENABLE` examples returned no matches in the active
video/API docs checked in this slice.

```bash
PYTHON=.venv/bin/python make phase0-check
```

Result: schema current, candidate inventory current, 195 passed, with the
existing Starlette/httpx `TestClient` warning.

```bash
git diff --check
```

Result: passed.

## Boundaries

No QGC branch mutation, QGC build, PX4/SITL/HIL/field run, service install,
sidecar mutation/update, deployment, runtime MCP endpoint, callable tool, or
real-aircraft control was performed or claimed.

## Next

Continue PXE-0068 bootstrap/setup UX cleanup, unless the maintainer wants to
pull PXE-0070 forward and fix the QGC PR authentication/header/TLS support
before setup cleanup.

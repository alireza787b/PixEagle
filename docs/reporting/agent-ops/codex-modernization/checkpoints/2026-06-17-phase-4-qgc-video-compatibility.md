# Phase 4 QGC Video Compatibility Reconciliation

- Date: 2026-06-17
- Slice: PXE-0067
- Status: completed PixEagle-side compatibility and documentation slice
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

This slice reconciled PixEagle's current local-first media security boundary
with the open QGroundControl PR for HTTP MJPEG and WebSocket video:

- QGC PR: <https://github.com/mavlink/qgroundcontrol/pull/13594>
- Reviewed PR head: `alireza787b/qgroundcontrol@f0a4feba97f2f563b3edd6cda0d17cfb15269550`
- GitHub merge state during review: `mergeable=false`, `mergeable_state=dirty`,
  `rebaseable=false`

PixEagle now preserves the secure remote/browser behavior while restoring the
local native-client WebSocket use case:

- browser WebSocket clients still require an explicit allowlisted `Origin`;
- remote/native WebSocket clients still fail closed without an allowed Origin
  and normal media authorization;
- same-host native clients may omit `Origin` only when both the socket peer and
  `Host` authority are loopback;
- HTTP/MJPEG and WebSocket media still pass through `media:read` authorization;
- query-string tokens remain rejected.

No QGroundControl branch was mutated in this slice. No QGC build, SITL, HIL,
field run, service installation, deployment, sidecar mutation, or real-aircraft
control was performed or claimed.

## Compatibility Matrix

| Scenario | Current PixEagle Status |
| --- | --- |
| QGC HTTP MJPEG, same host, `http://127.0.0.1:5077/video_feed`, `local_compat` | Supported by policy and protocol; no QGC end-to-end build/run claimed |
| QGC WebSocket, same host, `ws://127.0.0.1:5077/ws/video_feed`, missing `Origin`, `local_compat` | Restored at policy/handler level; no QGC end-to-end build/run claimed |
| QGC HTTP/WS from remote LAN without credentials | Rejected by design |
| QGC HTTP/WS with `machine_bearer` | PixEagle can authorize scoped bearer credentials, but the reviewed QGC PR has no header/origin settings |
| Browser dashboard with `browser_session` | Supported through the credential-aware dashboard client, not through QGC |
| Query credentials such as `?token=`, `?api_key=`, or `?access_token=` | Rejected by design |
| Field QGC video | Use PixEagle GStreamer H.264/RTP/UDP output instead of exposing backend media endpoints |

## Files Changed

- `src/classes/api_exposure_policy.py`
- `src/classes/fastapi_handler.py`
- `src/classes/webrtc_manager.py`
- `tests/unit/core_app/test_api_exposure_policy.py`
- `tests/test_docs_infrastructure_consistency.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/video/04-streaming/README.md`
- `docs/video/04-streaming/http-mjpeg.md`
- `docs/video/04-streaming/websocket.md`
- `docs/video/04-streaming/streaming-optimizer.md`
- `docs/video/06-configuration/README.md`
- `docs/video/06-configuration/streaming-config.md`
- `docs/video/03-gstreamer/README.md`
- `docs/video/03-gstreamer/output-pipeline.md`
- `docs/core-app/03-api/README.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Evidence And Review

Independent review findings were incorporated:

- QGC/Qt/GStreamer reviewer confirmed the PR opens WebSocket with only a URL,
  no configured `Origin`, no `Authorization`, and no HTTP extra headers.
- PixEagle API/security reviewer confirmed same-host HTTP compatibility, remote
  direct HTTP/WS rejection without credentials, query-token rejection, and the
  same-host native missing-Origin WebSocket exception after this patch.
- Installer/bootstrap reviewer confirmed a separate setup cleanup slice is
  needed for script/docs/profile/binary/port-label debt; this is tracked as
  PXE-0068, not mixed into PXE-0067.

External references checked during the slice:

- Qt `QWebSocket::open(QNetworkRequest)` can send request headers in the
  WebSocket upgrade request:
  <https://doc.qt.io/qt-6/qwebsocket.html>
- GStreamer `souphttpsrc` supports HTTP source behavior and header-related
  configuration in the plugin contract:
  <https://gstreamer.freedesktop.org/documentation/soup/souphttpsrc.html>
- QGroundControl developer/contribution guidance remains centered on QGC's
  own build, CMake, Qt, and coding-style process:
  <https://docs.qgroundcontrol.com/master/en/qgc-dev-guide/index.html>

## Validation

Completed:

```bash
.venv/bin/python -m pytest \
  tests/test_docs_infrastructure_consistency.py \
  tests/unit/core_app/test_api_exposure_policy.py \
  tests/unit/core_app/test_api_auth_runtime.py \
  tests/test_api_security_policy.py \
  -ra --tb=short --strict-config
```

Result: 136 passed, with the existing Starlette/httpx `TestClient`
deprecation warning.

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  -ra --tb=short --strict-config
```

Result: 36 passed.

```bash
PYTHON=.venv/bin/python bash scripts/check_schema.sh
```

Result: schema is up-to-date; 41 sections and 548 parameters.

```bash
.venv/bin/python -m py_compile \
  src/classes/api_exposure_policy.py \
  src/classes/fastapi_handler.py \
  src/classes/webrtc_manager.py \
  tests/test_docs_infrastructure_consistency.py \
  tests/unit/core_app/test_api_exposure_policy.py
```

Result: passed.

```bash
.venv/bin/python tools/generate_api_tool_candidates.py
```

Result: API/MCP candidate inventory regenerated for the changed
`fastapi_handler.py` and `api_exposure_policy.py` provenance hashes.

```bash
PYTHON=.venv/bin/python make phase0-check
```

Result: schema current, candidate inventory current, 187 passed, with the
existing Starlette/httpx `TestClient` deprecation warning.

```bash
git diff --check
```

Result: passed.

Not run:

- Dashboard tests/build were not run because no dashboard code changed.
- QGC clone/build was not run; the PR was inspected through GitHub and API
  snapshots. GitHub reported the branch as dirty/not rebaseable.
- PX4/SITL/HIL/field validation was not run and no runtime flight/video success
  is claimed.

## Remaining Risks

- QGC PR #13594 remains not mergeable and still lacks configurable Origin,
  bearer/header, cookie, and secret-redaction behavior for authenticated remote
  PixEagle media.
- PixEagle's `trusted_lan_legacy` Host allowlist still derives remote hosts from
  CORS origins, which is awkward for native clients. A future API exposure slice
  should consider an explicit Host allowlist separate from browser CORS.
- Direct remote QGC HTTP/WS media remains intentionally unsupported without a
  reviewed authenticated design. This is a product/security decision, not a
  missing PixEagle fallback.
- Active setup/bootstrap docs and scripts still need the broader PXE-0068
  cleanup before handoff.

## Next Slice

Proceed with PXE-0068 bootstrap/setup UX cleanup:

1. Define demo/dev, advanced dev, and deployment/service profiles.
2. Make config-copy behavior explicit and reduce default config drift.
3. Fix stale script refs, optional AI/GStreamer install paths, and service
   install/start guidance.
4. Reconcile binary pin/override/checksum policy for MAVSDK and MAVLink2REST.
5. Fix port labels that confuse legacy telemetry WebSocket `5551` with backend
   media WebSocket `/ws/video_feed` on `5077`.
6. Add docs guardrails for stale setup patterns.

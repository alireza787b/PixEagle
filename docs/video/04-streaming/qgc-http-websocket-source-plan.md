# QGC HTTP/WebSocket Source Plan

This note records the PixEagle-side decision for the open QGroundControl
HTTP/HTTPS MJPEG and WebSocket video PR. It exists so PixEagle docs, future QGC
PR comments, and bootstrap profiles do not drift into conflicting guidance.

## Decision

- Keep the QGroundControl feature generic. It should support normal HTTP/HTTPS
  MJPEG and WebSocket video sources that are not PixEagle.
- Do not hard-code PixEagle-only behavior into QGroundControl core video
  routing.
- Treat PixEagle as one configured source profile that uses the generic QGC
  feature set: URL, optional headers, optional WebSocket Origin, TLS policy, and
  credential redaction.
- Do not advertise remote PixEagle HTTP/WebSocket compatibility until QGC can
  send scoped credentials and the PixEagle deployment has a reviewed remote
  media profile.

## Source Profiles

| Source profile | Example | QGC behavior | PixEagle status |
| --- | --- | --- | --- |
| Generic anonymous HTTP MJPEG | IP camera, lab MJPEG server | URL-only HTTP/HTTPS source | Not a PixEagle backend profile |
| Generic WebSocket video | Custom JPEG-frame WebSocket server | URL-only or source-specific headers when implemented | Not a PixEagle backend profile |
| PixEagle same-host development | `http://127.0.0.1:5077/video_feed` and `ws://127.0.0.1:5077/ws/video_feed` | URL-only loopback source | Supported with `local_only` + `local_compat` |
| PixEagle field QGC video | H.264/RTP/UDP to QGC port | QGC UDP h.264 Video Stream | Supported field path |
| PixEagle remote HTTP/WS | Pi/Jetson backend to remote GCS QGC | Bearer header, WebSocket Origin, TLS/WSS, redaction | Deferred to PXE-0070 |
| PixEagle anonymous LAN backend | `http://<pi-ip>:5077/video_feed` without auth | Should not be a QGC compatibility target | Rejected |

## Beginner Demo Policy

PixEagle should be easy to demo from a phone, tablet, or ground-station laptop,
but that convenience must come from an explicit setup profile, not from the
checked-in defaults silently exposing the backend.

Recommended bootstrap profiles for PXE-0068:

| Profile | UX goal | Security boundary |
| --- | --- | --- |
| `local_dev` | Developer starts PixEagle and opens the dashboard on the same host | Loopback backend and dashboard, `local_compat` |
| `field_qgc_video` | Beginner sees video in QGC from another device | GStreamer H.264/RTP/UDP only; backend remains loopback |
| `demo_lan_browser` | Beginner opens the dashboard from a phone/tablet on an isolated lab LAN or private overlay/VPN | `browser_session` with a generated username/password, explicit Host and CORS allowlists, warning banner/docs |
| `production_remote` | Operator access from GCS/mobile | TLS, durable credentials, exact Host/CORS allowlists, audit, role/scopes |
| `unsafe_demo_lan_media_only` | Temporary anonymous viewing in an isolated lab | Media-only, no control/dashboard mutation surface, explicit unsafe name, warnings, tests proving it is never default |

Do not provide a no-password remote control panel. If a demo needs the full web
panel from another device, generate credentials during bootstrap and make the
operator log in. If a demo needs no credentials at all, keep it media-only or
use QGC's UDP/RTP video path on an isolated network.

Private overlays/VPNs such as NetBird are useful reachability controls for lab
and operator-approved test networks, and `demo_lan_browser` accepts shared
private-overlay/CGNAT IPs such as `100.64.0.0/10`. They do not make anonymous
PixEagle backend HTTP/WS safe, and they do not replace production TLS/operator
credential hardening for remote browser operation.

The official repository default should remain a beginner-friendly local demo:
clone, initialize, run, and open the dashboard on the same host without manual
credential work. When the demo leaves loopback, setup must switch to an
explicit profile and explain the tradeoff. "Zero security experience" means the
profile generates or guides the required credentials; it does not mean anonymous
remote backend control.

## PixEagle Configuration Contract

The future generic QGC HTTP/WS implementation will not make PixEagle work
remotely by itself. PixEagle must be configured to allow the specific client
profile.

### Current field QGC video

Use this for companion-to-GCS video today:

```bash
make qgc-video-profile GCS_HOST=<gcs-ip>
```

```yaml
Streaming:
  API_EXPOSURE_MODE: local_only
  HTTP_STREAM_HOST: 127.0.0.1

GStreamer:
  ENABLE_GSTREAMER_STREAM: true
  GSTREAMER_HOST: <gcs-ip>
  GSTREAMER_PORT: 5600
```

QGC uses **UDP h.264 Video Stream** on the same port. The PixEagle backend
stays loopback-only.

### Same-host direct HTTP/WS development

Use this only when QGC and PixEagle are on the same machine:

```yaml
Streaming:
  API_EXPOSURE_MODE: local_only
  HTTP_STREAM_HOST: 127.0.0.1
  API_AUTH_MODE: local_compat
```

QGC can use:

```text
http://127.0.0.1:5077/video_feed
ws://127.0.0.1:5077/ws/video_feed
```

### Future remote QGC HTTP/WS profile

Use this only after QGC supports optional generic headers, WebSocket Origin,
TLS/WSS settings, and credential redaction:

```yaml
Streaming:
  API_EXPOSURE_MODE: trusted_lan_legacy
  HTTP_STREAM_HOST: 0.0.0.0
  API_ALLOWED_HOSTS:
    - pixeagle-pi.local
    - <pixeagle-ip>
  API_AUTH_MODE: machine_bearer
  API_BEARER_TOKEN_FILE: /etc/pixeagle/media-tokens.json
```

The QGC source profile must use the same PixEagle host authority that appears
in `API_ALLOWED_HOSTS`, send `Authorization: Bearer <token>`, and use WSS/HTTPS
with certificate validation for non-lab deployments. For a video-only QGC
client, the token should have `media:read` only. Do not add `telemetry:read`,
`status:read`, control, config, model, recording, or safety scopes unless that
client actually consumes those typed APIs and has a separate reviewed use case.

`API_CORS_ALLOWED_ORIGINS` is for browsers. Native QGC does not become
authorized because its host is listed in CORS, and CORS is not a machine-client
authorization mechanism. If the future QGC WebSocket implementation sends an
`Origin` header, PixEagle must allow that exact Origin as part of the reviewed
remote-media profile.

## QGC PR Follow-Up Requirements

PXE-0070 should keep normal non-PixEagle sources working while adding optional
generic auth controls:

- HTTP/HTTPS MJPEG should keep accepting ordinary anonymous URLs.
- Optional request headers should be supported for authenticated sources, with
  `Authorization: Bearer <token>` as the PixEagle remote profile.
- WebSocket should support opening with a `QNetworkRequest` so Authorization and
  Origin headers can be set when a source requires them.
- HTTPS/WSS should validate certificates by default; any lab-only relaxed mode
  must be explicit and visually marked unsafe.
- Credentials must not be stored in URLs, query strings, screenshots, or logs.
- Synthetic test servers should cover anonymous generic success, PixEagle-style
  401/403 failures, bearer success, wrong/missing Origin, TLS handling, and log
  redaction.

QGC PR clarification posted for this policy:

- <https://github.com/mavlink/qgroundcontrol/pull/13594#issuecomment-4731276373>

Suggested QGC PR update text when PXE-0070 starts changing code:

```text
PixEagle follow-up clarification: the QGC feature should remain generic for
normal HTTP/HTTPS MJPEG and WebSocket sources such as IP cameras or lab test
servers. PixEagle should be documented as one secure source profile, not
hard-coded into QGC. For same-host development, PixEagle loopback URLs still
work without extra headers. For remote PixEagle on a companion computer, QGC
needs optional generic Authorization/Origin/TLS settings and credential
redaction before we can advertise direct HTTP/WS compatibility. Field QGC video
continues to use H.264/RTP/UDP until that authenticated profile is implemented
and tested.
```

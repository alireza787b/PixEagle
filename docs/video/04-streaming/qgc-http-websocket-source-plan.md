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
- QGC PR #13594 now has a repaired implementation for scoped credentials,
  Origin, strict TLS/custom CA, URL redaction, and bounded WebSocket JPEG
  messages. Do not advertise deployment success until QGC CI and a target
  PixEagle-to-QGC receiver test pass.

## Source Profiles

| Source profile | Example | QGC behavior | PixEagle status |
| --- | --- | --- | --- |
| Generic anonymous HTTP MJPEG | IP camera, lab MJPEG server | URL-only HTTP/HTTPS source | Not a PixEagle backend profile |
| Generic WebSocket video | Custom JPEG-frame WebSocket server | URL-only or source-specific headers when implemented | Not a PixEagle backend profile |
| PixEagle same-host development | `http://127.0.0.1:5077/video_feed` and `ws://127.0.0.1:5077/ws/video_feed` | URL-only loopback source | Supported with `local_only` + `local_compat` |
| PixEagle field QGC video | H.264/RTP/UDP to QGC port | QGC UDP h.264 Video Stream | Supported field path |
| PixEagle remote HTTP/WS | Pi/Jetson backend to remote GCS QGC | Bearer header, exact WebSocket Origin, TLS/WSS, custom CA, redaction | Guarded `qgc_direct_media` setup exists; QGC CI and target playback evidence remain required |
| PixEagle unsafe anonymous lab media | `http://<pi-ip>:5077/video_feed` and `ws://<pi-ip>:5077/ws/video_feed` without auth | Generic URL-only HTTP/WS source, lab only | Supported only with `unsafe_demo_lan_media_only` or `ALLOW_UNAUTHENTICATED_MEDIA_STREAMING: true` |

## Beginner Demo Policy

PixEagle should be easy to demo from a phone, tablet, or ground-station laptop,
but that convenience must come from an explicit setup profile, not from the
checked-in defaults silently exposing the backend.

Recommended bootstrap profiles for PXE-0068:

| Profile | UX goal | Security boundary |
| --- | --- | --- |
| `local_dev` | Developer starts PixEagle and opens the dashboard on the same host | Loopback backend and dashboard, `local_compat` |
| `field_qgc_video` | Beginner sees video in QGC from another device | GStreamer H.264/RTP/UDP only; backend remains loopback |
| `qgc_direct_media` | Advanced QGC client consumes MJPEG or WebSocket JPEG through TLS | Generated `media:read` bearer token, exact Host/Origin, loopback backend behind HTTPS/WSS proxy |
| `demo_lan_browser` | Beginner opens the dashboard from a phone/tablet on an isolated lab LAN or private overlay/VPN | `browser_session` with a generated username/password, explicit Host and CORS allowlists, warning banner/docs |
| `production_remote` | Operator access from GCS/mobile | TLS, durable credentials, exact Host/CORS allowlists, audit, role/scopes |
| `unsafe_demo_lan_media_only` | Temporary anonymous viewing in an isolated lab | Media-only, no control/dashboard mutation surface, explicit unsafe name, warnings, tests proving it is never default |

Do not provide a no-password remote control panel. If a demo needs the full web
panel from another device, generate credentials during bootstrap and make the
operator log in. If a demo needs no credentials at all, keep it media-only with
`unsafe_demo_lan_media_only` or use QGC's UDP/RTP video path on an isolated
network.

Private overlays/VPNs such as NetBird are useful reachability controls for lab
and operator-approved test networks, and `demo_lan_browser` accepts shared
private-overlay/CGNAT IPs such as `100.64.0.0/10`. They do not make anonymous
PixEagle dashboard/control APIs safe, and they do not replace production
TLS/operator credential hardening for remote browser operation; in short, they
do not replace production TLS/operator controls.

The official repository default should remain a beginner-friendly local demo:
clone, initialize, run, and open the dashboard on the same host without manual
credential work. When the demo leaves loopback, setup must switch to an
explicit profile and explain the tradeoff. "Zero security experience" means the
profile generates or guides the required credentials; it does not mean anonymous
remote backend control.

## PixEagle Configuration Contract

The generic QGC HTTP/WS implementation does not make PixEagle work remotely by
itself. PixEagle must be configured to allow the specific client profile.

For every PixEagle profile, keep these layers separate:

- `API_ALLOWED_HOSTS` is the request Host authority allowlist for the URL or
  reverse proxy.
- `API_CORS_ALLOWED_ORIGINS` is a browser Origin allowlist.
- selected GCS/source-IP restriction belongs to firewall, VPN/overlay, or
  reverse-proxy rules.
- PixEagle authorization is still bearer token, browser session, same-host
  local compatibility, or the explicit unsafe media-only exception.

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

### Unsafe anonymous lab media

Use this only when no remote dashboard/control panel is needed and anonymous
video viewing is acceptable on the selected lab network:

```bash
make unsafe-demo-lan-media-profile LAN_HOST=<this-pixeagle-lan-ip-or-hostname>
```

The profile sets `ALLOW_UNAUTHENTICATED_MEDIA_STREAMING: true` and opens only
`/video_feed` and `/ws/video_feed` to anonymous clients that pass Host/CORS
checks. It does not make `/ws/webrtc_signaling`, media-health, status,
telemetry, logs, config, or action APIs anonymous. QGC can use URL-only HTTP
MJPEG or WebSocket JPEG in this lane; VLC can use the HTTP MJPEG URL but is not
a raw WebSocket JPEG client.

This is the only PixEagle profile where remote QGC video is intentionally
anonymous. Narrow the reachable client set with firewall or reverse-proxy
source-IP rules when needed; do not treat `API_ALLOWED_HOSTS` as that rule.

### Guarded remote QGC HTTP/WS profile

Generate the PixEagle-side profile:

```bash
make qgc-direct-media-profile PUBLIC_HOST=pixeagle.example
```

The profile keeps PixEagle on loopback, generates a hashed token file with only
`media:read`, writes a one-time owner-only QGC handoff, and configures exact
Host/Origin policy for an external HTTPS/WSS reverse proxy. It does not bind
the backend to `0.0.0.0`. The proxy-facing authority must match the generated
`API_ALLOWED_HOSTS` entry.

QGC must use the generated URL host authority, select **Bearer token**, enter
the generated token as a session credential, and retain strict certificate
validation. For remote HTTPS MJPEG, PixEagle should accept a missing Origin from
the native QGC client but reject a wrong supplied Origin. For remote WSS,
PixEagle should require the exact generated Origin. Select a deployment CA file
in QGC when the proxy certificate is not publicly trusted. For HTTPS MJPEG,
that PEM is the complete trust database; for WSS it augments system trust. For
a video-only QGC client, retain only `media:read`; do not add `telemetry:read`,
`status:read`, control, config, model, recording, or safety scopes unless that
client consumes those typed APIs under a separate reviewed use case.

`API_CORS_ALLOWED_ORIGINS` is for browsers. Native QGC does not become
authorized because its host is listed in CORS, and CORS is not a machine-client
authorization mechanism. The repaired QGC implementation can send an optional
exact Origin; `qgc_direct_media` puts that value in PixEagle's allowlist for
wrong-Origin rejection on HTTP and mandatory-Origin enforcement on WSS.

## QGC PR Implementation And Remaining Gates

The repaired implementation keeps normal non-PixEagle sources working while
adding optional generic controls:

- HTTP/HTTPS MJPEG should keep accepting ordinary anonymous URLs.
- Optional Basic/Bearer authentication is supported, with
  `Authorization: Bearer <token>` as the PixEagle remote profile.
- WebSocket opens with a `QNetworkRequest`; Authorization and Origin are
  configurable.
- HTTPS/WSS validate certificates by default; WSS can add deployment CAs, while
  HTTPS MJPEG can use a deployment PEM as its complete trust database. There is
  no ignore-certificate-errors mode.
- Credentials must not be stored in URLs, query strings, screenshots, or logs.
- Credentials are session-only or loaded from a validated owner-only Unix file;
  settings persist only the optional file path.
- WebSocket handling runs on a dedicated event-loop thread and feeds encoded
  JPEG into QGC's existing parse/tee/decode/recording pipeline.

Remaining gates are a clean QGC CI/build matrix, expanded negative auth/TLS
coverage where practical, and a target receiver test over the reviewed proxy.
PR #13594 is intentionally draft while those gates and user receiver tests are
open.

Use the
[QGC Windows Network Video Receiver Test](qgc-windows-receiver-test.md)
runbook for generic anonymous source smoke, same-host PixEagle checks, guarded
remote PixEagle HTTPS/WSS validation, recording checks, and evidence capture.

QGC PR clarification posted for this policy:

- <https://github.com/mavlink/qgroundcontrol/pull/13594#issuecomment-4731276373>

Leave the PR as draft until the repaired branch has clean CI and target
PixEagle-to-QGC playback evidence. Any later PR comment should distinguish
implemented generic behavior from unverified target deployment playback.

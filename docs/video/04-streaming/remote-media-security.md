# Remote Media Security

PixEagle often runs on an onboard companion computer while QGroundControl or a
browser dashboard runs on a separate ground-station laptop, tablet, or phone.
That deployment is normal. It should not be implemented by exposing the
PixEagle backend media port without authentication.

## Decision

- Do not enable anonymous remote access to `/video_feed`, `/ws/video_feed`, or
  `/ws/webrtc_signaling`.
- Keep the checked-in backend profile local-only.
- Use GStreamer H.264/RTP/UDP for field QGroundControl video today.
- Use authenticated HTTP/WebSocket media only for reviewed clients that can send
  scoped credentials and, for WebSocket, an allowlisted Origin.
- Do not put credentials in URLs or query strings.
- Treat VPNs, trusted RF links, and reverse proxies as transport controls, not
  authorization.

## Profiles

| Profile | Intended user | Backend exposure | Authentication | Status |
| --- | --- | --- | --- | --- |
| Local development | Same-host dashboard, local QGC, CLI smoke tests | `local_only` loopback | `local_compat` loopback only | Supported default |
| Field QGC video | QGC on GCS, PixEagle on companion | Backend remains loopback; video uses UDP/RTP output | No PixEagle API auth because backend is not exposed | Supported video path |
| Remote browser operator | Browser dashboard on GCS/mobile | Exact Host/CORS over TLS or SSH tunnel | `browser_session` with viewer/operator/admin users | SSH tunnel now; production hardening still tracked |
| Remote native media client | Future QGC HTTP/WS or another native client | Explicit non-loopback profile with Host allowlist | Bearer token with `media:read` | Requires reviewed client support |
| Anonymous LAN media | Any remote LAN client | Backend exposed without auth | None | Not supported |

## QGroundControl Field Video

For a Raspberry Pi or Jetson companion streaming to QGroundControl on a laptop,
keep the PixEagle backend on loopback and enable the GStreamer output pipeline:

```yaml
Streaming:
  API_EXPOSURE_MODE: local_only
  HTTP_STREAM_HOST: 127.0.0.1

GStreamer:
  ENABLE_GSTREAMER_STREAM: true
  GSTREAMER_HOST: 192.168.10.20
  GSTREAMER_PORT: 5600
```

In QGroundControl, select **UDP h.264 Video Stream** and use the same UDP port.
This sends compressed one-way video to the ground station without opening the
PixEagle HTTP/WebSocket API/media surface.

UDP/RTP does not provide confidentiality or authentication by itself. Use it on
a controlled vehicle/GCS link, VPN, or other operator-approved network when
video confidentiality matters.

## Remote Browser Dashboard

For operator dashboards on another machine, the safest current workflow is an
SSH tunnel to the companion and the default local-only backend. A future
production remote-browser profile must include:

- TLS with a deployment-managed certificate;
- exact backend Host allowlist through `Streaming.API_ALLOWED_HOSTS`;
- exact browser origins through `Streaming.API_CORS_ALLOWED_ORIGINS`;
- `API_AUTH_MODE: browser_session`;
- an external `API_SESSION_USER_FILE` with PBKDF2-SHA256 hashed users;
- `API_SESSION_COOKIE_SECURE: true` when served over HTTPS;
- durable security audit logging;
- adversarial browser/session/media tests and remaining legacy-alias retirement
  gates under PXE-0064.

Roles are intentionally simple:

| Role | Use |
| --- | --- |
| `viewer` | Status, telemetry, media, recordings, and other read-only operational views |
| `operator` | Viewer authority plus normal tracking/following/media operations |
| `admin` | Full local administrative authority, still subject to local-only and CSRF restrictions |

Do not use HTTP Basic authentication as the PixEagle backend user-management
model. If a reverse proxy adds Basic authentication for a lab deployment, the
PixEagle backend still needs its own session or bearer authorization boundary.

## Remote HTTP/WebSocket Media Clients

Remote direct HTTP MJPEG or WebSocket video is an advanced machine-client path.
The client must be able to send:

- `Authorization: Bearer <token>` where the token has at least `media:read`;
- no query-string token;
- an allowlisted `Origin` for WebSocket handshakes;
- HTTPS/WSS with strict certificate validation for non-lab deployments.

For native-only remote media:

```yaml
Streaming:
  API_EXPOSURE_MODE: trusted_lan_legacy
  HTTP_STREAM_HOST: 0.0.0.0
  API_ALLOWED_HOSTS:
    - pixeagle-pi.local
    - 192.168.10.42
  API_CORS_ALLOWED_ORIGINS:
    - https://qgroundcontrol.local
  API_AUTH_MODE: machine_bearer
  API_BEARER_TOKEN_FILE: /etc/pixeagle/media-tokens.json
```

For a deployment that needs both browser users and a native QGC media client,
use `API_AUTH_MODE: browser_session` with both `API_SESSION_USER_FILE` and
`API_BEARER_TOKEN_FILE` configured. Browser users authenticate through the
session routes; QGC/native clients authenticate with bearer tokens.

Create token records offline and store only the hashed record file on the
companion:

```bash
PYTHONPATH=src python - <<'PY'
import getpass
import json

from classes.api_auth_runtime import make_token_record

token = getpass.getpass("Plaintext media token to hash: ")
record = make_token_record(
    token_id="qgc-media-viewer",
    subject="qgroundcontrol",
    plaintext_token=token,
    scopes=["media:read"],
)
print(json.dumps({"tokens": [record]}, indent=2))
PY
```

Restrict file permissions and keep the plaintext token only in the native
client's secret storage or deployment vault.

The open QGroundControl HTTP/WebSocket PR does not yet implement this remote
authenticated profile. It needs settings and code for Authorization headers,
Origin, TLS/CA handling, credential redaction, and negative auth tests before
PixEagle should advertise remote direct HTTP/WS QGC compatibility.

## Anonymous Demo Requests

If a beginner demo needs easy video on a second machine, use the GStreamer
QGC output path or an SSH tunnel. Do not add an unauthenticated remote backend
media profile. A temporary lab-only exception would need a deliberately named
unsafe mode, warning banners, tests proving it cannot be selected by default,
and a removal/expiry plan; PixEagle does not currently provide that mode.


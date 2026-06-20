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
- Treat private overlays/VPNs, trusted RF links, and reverse proxies as
  transport controls, not authorization.

## Profiles

| Profile | Intended user | Backend exposure | Authentication | Status |
| --- | --- | --- | --- | --- |
| Local development | Same-host dashboard, local QGC, CLI smoke tests | `local_only` loopback | `local_compat` loopback only | Supported default |
| Field QGC video | QGC on GCS, PixEagle on companion | Backend remains loopback; video uses UDP/RTP output | No PixEagle API auth because backend is not exposed | Supported video path |
| Lab/private-overlay browser demo | Browser dashboard on phone/tablet/GCS | Exact Host/CORS over HTTP on isolated LAN or private overlay/VPN | Generated `browser_session` user | Supported by `demo_lan_browser`; not production |
| Remote browser operator | Browser dashboard on GCS/mobile | Backend remains loopback behind HTTPS/WSS reverse proxy or SSH tunnel | `browser_session` with viewer/operator/admin users | Guarded `production_remote` config supported; deployment evidence still required |
| Remote native media client | Future QGC HTTP/WS or another native client | Explicit non-loopback profile with Host allowlist | Bearer token with `media:read` | Requires reviewed client support |
| Anonymous LAN media | Any remote LAN client | Backend exposed without auth | None | Not supported |

## QGroundControl Field Video

For a Raspberry Pi or Jetson companion streaming to QGroundControl on a laptop,
keep the PixEagle backend on loopback and enable the GStreamer output pipeline:

```bash
make qgc-video-profile GCS_HOST=192.168.10.20
```

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

The open QGroundControl HTTP/WebSocket video work should remain generic for
non-PixEagle sources. PixEagle remote HTTP/WS is one stricter source profile on
top of that generic capability, not a reason to require authentication for every
normal HTTP camera or lab MJPEG source. See
[QGC HTTP/WebSocket Source Plan](qgc-http-websocket-source-plan.md).

## Remote Browser Dashboard

For operator dashboards on another machine, the simplest secure workflow remains
an SSH tunnel to the companion and the default local-only backend. For a
reviewed HTTPS/WSS reverse-proxy deployment, use the guarded
`production_remote` setup profile:

```bash
make production-remote-profile \
  PUBLIC_HOST=pixeagle.example \
  SESSION_USER_FILE="$HOME/.config/pixeagle/secrets/browser-users.json" \
  CREDENTIAL_HANDOFF_FILE="$HOME/.config/pixeagle/secrets/initial-credentials.json"
```

That profile generates the PixEagle-side config and browser-session credential
file for a production remote browser profile. It keeps `HTTP_STREAM_HOST:
127.0.0.1`, sets an exact public `API_ALLOWED_HOSTS` entry and a single exact
public CORS origin, enables
`API_SESSION_COOKIE_SECURE: true`, and requires an external hashed
`API_SESSION_USER_FILE`. It does not install the reverse proxy, open firewall
rules, or prove field readiness.

A production remote-browser deployment must include:

- TLS with a deployment-managed certificate;
- exact backend Host allowlist through `Streaming.API_ALLOWED_HOSTS`;
- exact browser origins through `Streaming.API_CORS_ALLOWED_ORIGINS`;
- `API_AUTH_MODE: browser_session`;
- an external `API_SESSION_USER_FILE` with PBKDF2-SHA256 hashed users;
- `API_SESSION_COOKIE_SECURE: true` when served over HTTPS;
- durable security audit logging;
- dashboard served under `/pixeagle` with `/pixeagle-api` proxied to
  `http://127.0.0.1:5077`, or an equivalent reviewed same-origin path;
- broader end-to-end browser/session/media evidence and operator acceptance
  gates under PXE-0064/PXE-0068.

Legacy tracking/control HTTP aliases have been retired. Production remote
browser approval now depends on the deployment trust boundary, proxy/firewall
evidence, credential handoff evidence, and adversarial browser/session/media
tests, not on remaining action-route alias work.

Roles are intentionally simple:

| Role | Use |
| --- | --- |
| `viewer` | Status, telemetry, media, recordings, and other read-only operational views |
| `operator` | Viewer authority plus normal tracking/following/media operations |
| `admin` | Full local administrative authority, still subject to local-only and CSRF restrictions |

Do not use HTTP Basic authentication as the PixEagle backend user-management
model. If a reverse proxy adds Basic authentication for a lab deployment, the
PixEagle backend still needs its own session or bearer authorization boundary.

TLS is not a domain-only concept. Production browser deployments should use
HTTPS/WSS with browser-trusted certificates, whether the endpoint is named by a
DNS name, an internal PKI name, or another reviewed trust anchor. A private
overlay/VPN such as NetBird can be part of the network-security plan, but HTTP
over that overlay remains a lab or operator-approved test profile unless a
separate threat model accepts it with equivalent controls and evidence.

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

For QGC video-only use, grant only `media:read`. Do not use a broad operator or
admin token just to view video. If a future QGC integration consumes typed
PixEagle status or telemetry APIs, grant those scopes separately and document
the exact endpoints and operator reason.

## Anonymous Demo Requests

If a beginner demo needs easy video on a second machine, use the GStreamer QGC
output path or an SSH tunnel. If a beginner demo needs the browser dashboard on
a phone or tablet, use the automated `demo_lan_browser` bootstrap profile:

```bash
make demo-lan-browser-profile LAN_HOST=<this-pixeagle-lan-ip-or-hostname>
```

The profile accepts RFC1918 private LAN addresses, shared private-overlay/CGNAT
addresses such as `100.64.0.0/10`, link-local addresses, IPv6 ULA/link-local
addresses, and local-scope hostnames. It binds only to explicit Host/CORS
allowlists, generates an external PBKDF2-hashed `browser_session`
username/password file, uses `API_AUTH_MODE: browser_session`, and warns the
operator that it is lab-only unless TLS/operator hardening is also configured.
IPv6 zone identifiers such as `%eth0`/`%25eth0` are rejected; use IPv6 ULA or a
local-scope hostname for IPv6 browser demos.

Do not provide a no-password remote control panel. Anonymous remote backend
access to PixEagle routes is not a plug-and-play mode. A temporary anonymous
lab exception would need to be named `unsafe_demo_lan_media_only`, limited to
media viewing rather than dashboard mutations or flight-adjacent actions, show
warning banners, include tests proving it cannot be selected by default, and
carry a removal or expiry plan. PixEagle does not currently provide that mode.

The checked-in default can still be friendly: local same-host demo requires no
manual credential setup. Remote convenience comes from guided profile creation,
generated credentials, and clear warnings, not from hidden anonymous network
exposure.

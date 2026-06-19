# PixEagle Setup Profiles

Setup profiles are the supported way to turn the checked-in defaults into a
host-specific local runtime configuration. They keep beginner onboarding simple
without making remote backend exposure accidental.

## Source Of Truth

- `configs/config_default.yaml` is the checked-in runtime source of truth.
- `configs/config.yaml` is optional, gitignored, and created only for local
  overrides or an explicit setup profile.
- `dashboard/.env` is generated from `dashboard/env_default.yaml` when missing.
- `make reset-config` intentionally creates or replaces local config files after
  making backups; it is a maintenance command, not first-run setup.

Clean clones can run from `configs/config_default.yaml` without creating
`configs/config.yaml`.

MAVSDK Server and MAVLink2REST downloads are governed separately by the
[Binary Download Policy](binary-download-policy.md). Setup profiles change local
PixEagle configuration; they do not change pinned external binary versions or
checksum policy.

## Supported Automated Profiles

### `local_dev`

Use this when you want a local override that restates the safe default:

```bash
make setup-profile PROFILE=local_dev
```

It sets:

```yaml
Streaming:
  API_EXPOSURE_MODE: local_only
  HTTP_STREAM_HOST: 127.0.0.1
  API_CORS_ALLOWED_ORIGINS:
    - http://127.0.0.1:3040
    - http://localhost:3040
    - http://127.0.0.1:5077
    - http://localhost:5077
  API_ALLOWED_HOSTS: []
  API_AUTH_MODE: local_compat

GStreamer:
  ENABLE_GSTREAMER_STREAM: false
  GSTREAMER_HOST: 127.0.0.1
  GSTREAMER_PORT: 5600
```

### `field_qgc_video`

Use this when PixEagle runs on an onboard companion and QGroundControl runs on a
ground-station laptop, tablet, or phone on the vehicle network:

```bash
make qgc-video-profile GCS_HOST=192.168.10.20
```

Optional custom port:

```bash
make qgc-video-profile GCS_HOST=192.168.10.20 GSTREAMER_PORT=5600
```

Windows equivalent:

```cmd
venv\Scripts\python.exe scripts\setup\apply-setup-profile.py --profile field_qgc_video --gcs-host 192.168.10.20
```

This enables PixEagle GStreamer H.264/RTP/UDP output to the GCS host and keeps
the PixEagle backend loopback-only. In QGroundControl, select UDP h.264 video
and use the same port, normally `5600`.

This profile does not expose `/video_feed`, `/ws/video_feed`,
`/ws/webrtc_signaling`, or API routes to the LAN.

### `demo_lan_browser`

Use this only for a lab demo where PixEagle runs on an onboard/companion host
and a phone, tablet, or laptop opens the browser dashboard on the same isolated
LAN or operator-approved private overlay/VPN:

```bash
make demo-lan-browser-profile LAN_HOST=192.168.10.42
```

`LAN_HOST` is the PixEagle host address or hostname that the browser will use,
not the GCS client address. The profile rejects wildcard, loopback, URL,
credential-bearing, public, multicast, documentation, and reserved values. IP
literals must be RFC1918 private LAN, shared private-overlay/CGNAT
`100.64.0.0/10`, link-local, IPv6 ULA, or IPv6 link-local addresses. Hostnames
must be local-scope names: single-label LAN names or names ending in
`.local`/`.lan`, not public DNS names. The dashboard port `3040` serves static
assets and backend port `5077` serves browser API/media calls. IPv6 zone
identifiers such as `%eth0`/`%25eth0` are not accepted because browser
Host/CORS matching is ambiguous; use an IPv6 ULA address or local-scope
hostname for IPv6 demos.

TLS is not only for domain names, but browser-trusted certificates are usually
easier with a DNS name or managed internal PKI. This profile intentionally uses
HTTP for beginner lab/private-overlay testing. That is acceptable only when the
network is isolated and operator-approved; it is not the production remote
browser profile.

The tool creates a local `configs/config.yaml`, writes an external hashed user
file under `configs/secrets/`, and prints the generated password once. The
credential file is gitignored and contains only PBKDF2-SHA256 password hashes,
not plaintext. Re-running the profile refuses to overwrite that file unless the
operator explicitly rotates credentials:

```bash
make demo-lan-browser-profile LAN_HOST=192.168.10.42 ROTATE_DEMO_CREDENTIALS=1
```

A successful run prints `Generated browser-session user file:` and the generated
password once. Keep that password out of issue reports, checkpoint logs, and
screenshots.

It sets:

```yaml
Streaming:
  API_EXPOSURE_MODE: trusted_lan_legacy
  HTTP_STREAM_HOST: 0.0.0.0
  HTTP_STREAM_PORT: 5077
  API_CORS_ALLOWED_ORIGINS:
    - http://127.0.0.1:3040
    - http://localhost:3040
    - http://127.0.0.1:5077
    - http://localhost:5077
    - http://192.168.10.42:3040
    - http://192.168.10.42:5077
  API_ALLOWED_HOSTS:
    - 192.168.10.42
  API_AUTH_MODE: browser_session
  API_SESSION_USER_FILE: /absolute/path/to/configs/secrets/demo-browser-users.json
  API_SESSION_COOKIE_SECURE: false
```

When `make run` sees `trusted_lan_legacy` plus `browser_session`, it binds the
static dashboard server on the LAN and passes the same exposure mode to the
dashboard process. Backend APIs, MJPEG, video WebSocket, and WebRTC signaling
still require login/session credentials, CSRF for browser mutations, exact Host,
and exact Origin checks. The browser dashboard uses port `3040` for static
assets and port `5077` for backend API/media calls, so lab firewalls must allow
both ports only from the trusted demo device/CIDR. A private overlay/VPN such as
NetBird can reduce who can reach those ports, but it is still a transport
control rather than production approval. This profile is HTTP lab convenience,
not production remote access; enable TLS or a reviewed equivalent deployment
boundary plus durable deployment-managed credentials before using PixEagle on
untrusted or production networks.

## Defined But Not Automated Yet

These profiles are part of the product contract, but the setup utility refuses
to apply them until their remaining security and evidence gates are completed.

| Profile | Intent | Current status |
| --- | --- | --- |
| `production_remote` | Hardened remote operator profile with TLS, durable credentials, exact Host/CORS allowlists, role/scopes, and audit evidence | Defined; gated by TLS/operator hardening, adversarial auth/media tests, and deployment evidence |
| `unsafe_demo_lan_media_only` | Explicit anonymous media-only lab exception, never a dashboard/control profile and never default | Not supported |

Do not create a no-password remote control panel. If a beginner needs remote
video quickly, use `field_qgc_video` or an SSH tunnel. If a beginner needs the
full browser dashboard from another device, use `demo_lan_browser` so setup
generates credentials rather than exposing anonymous backend control.

## Tooling

List profiles:

```bash
python scripts/setup/apply-setup-profile.py --list-profiles
```

Preview changes:

```bash
python scripts/setup/apply-setup-profile.py --profile field_qgc_video --gcs-host 192.168.10.20 --dry-run
python scripts/setup/apply-setup-profile.py --profile demo_lan_browser --lan-host 192.168.10.42 --dry-run
```

Apply changes:

```bash
python scripts/setup/apply-setup-profile.py --profile field_qgc_video --gcs-host 192.168.10.20
python scripts/setup/apply-setup-profile.py --profile demo_lan_browser --lan-host 192.168.10.42
```

When the destination `configs/config.yaml` already exists, the tool creates a
timestamped backup before writing unless `--no-backup` is explicitly supplied.

## QGC And Future HTTP/WebSocket Media

The current field QGC path is GStreamer UDP/RTP. Direct remote QGC HTTP/WebSocket
media is not advertised until the QGC client can send generic Authorization,
optional WebSocket Origin, TLS/WSS settings, and redacts credentials in UI/logs.
For PixEagle, that future profile also requires:

- `Streaming.API_EXPOSURE_MODE: trusted_lan_legacy`;
- exact `Streaming.API_ALLOWED_HOSTS`;
- `Streaming.API_AUTH_MODE: machine_bearer` or a reviewed mixed session/bearer
  deployment;
- a bearer token with `media:read` only for video-only QGC use;
- no query-string credentials;
- HTTPS/WSS with deployment-managed trust for production.

See [Remote Media Security](../video/04-streaming/remote-media-security.md) and
[QGC HTTP/WebSocket Source Plan](../video/04-streaming/qgc-http-websocket-source-plan.md).

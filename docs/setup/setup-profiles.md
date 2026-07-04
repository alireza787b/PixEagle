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

`make init` reports setup state separately from profile state. Its final
summary distinguishes `ready`, `skipped`, `degraded`, and `manual follow-up`
items for dashboard dependencies, dashboard `.env`, and MAVSDK/MAVLink2REST
binaries; resolve non-ready items before using the related profile in a demo or
deployment.

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

### `qgc_direct_media`

Use this guarded profile only with a draft/test QGroundControl build that
includes generic HTTP MJPEG/WebSocket JPEG authentication, Origin, and strict
TLS support:

```bash
make qgc-direct-media-profile PUBLIC_HOST=pixeagle.example
```

Optional deployment-managed paths and non-default TLS port:

```bash
make qgc-direct-media-profile \
  PUBLIC_HOST=pixeagle.example \
  PUBLIC_ORIGIN=https://pixeagle.example:8443 \
  QGC_TOKEN_FILE="$HOME/.config/pixeagle/secrets/qgc-media-tokens.json" \
  QGC_HANDOFF_FILE="$HOME/.config/pixeagle/secrets/qgc-media-handoff.json"
```

The tool generates:

- an owner-only token file containing only a SHA-256 token hash, token ID,
  subject, enabled flag, and the single `media:read` scope;
- an owner-only one-time handoff file containing the plaintext bearer token,
  exact QGC HTTP/WebSocket URLs, authentication type, and Origin;
- a loopback PixEagle backend configuration for an external HTTPS/WSS reverse
  proxy.

It sets:

```yaml
Streaming:
  API_EXPOSURE_MODE: trusted_lan_legacy
  HTTP_STREAM_HOST: 127.0.0.1
  HTTP_STREAM_PORT: 5077
  API_ALLOWED_HOSTS:
    - pixeagle.example:443
  API_CORS_ALLOWED_ORIGINS:
    - https://pixeagle.example
  API_AUTH_MODE: machine_bearer
  API_BEARER_TOKEN_FILE: /absolute/path/to/qgc-media-tokens.json
  API_SECURITY_AUDIT_ENABLED: true

GStreamer:
  ENABLE_GSTREAMER_STREAM: false
```

Configure the reverse proxy to strip `/pixeagle-api` and forward it to
`http://127.0.0.1:5077`, including WebSocket upgrades. Configure QGC from the
handoff file:

- source: **HTTP MJPEG Video Stream** or **WebSocket JPEG Video Stream**;
- authentication: **Bearer token**;
- Origin: the exact generated HTTPS origin;
- custom CA file: required when the proxy certificate chains to a private CA.

For WSS, QGC adds the selected CA certificates to system trust. For HTTPS
MJPEG, QGC uses the selected PEM as the complete GIO trust database; include
every deployment root required by that connection. Leave the field blank when
normal system trust is sufficient.

Delete the handoff file after securely transferring the token. Re-running the
profile refuses to overwrite either credential file unless
`ROTATE_QGC_TOKEN=1` is supplied. Rotation keeps an owner-only backup of the
hashed token record but never archives the plaintext handoff. If setup is
interrupted before it reports `Wrote configs/config.yaml`, the previous runtime
configuration remains authoritative; inspect or remove any partial QGC
credential files, or deliberately rerun with rotation. The profile does not
install a reverse proxy, issue certificates, open firewall rules, install QGC,
or prove playback.
QGC/PixEagle integration remains guarded until PR #13594 leaves draft, the QGC
CI/build matrix and loopback transport tests pass, and a target deployment
produces TLS/proxy/firewall and receiver evidence.

PixEagle runtime revalidates generated token/user files before parsing them. On
POSIX they must remain regular, single-link, process-user-owned files with no
group/other permissions, and must not exceed 1 MiB.

### `demo_lan_browser`

Use this only for a lab demo where PixEagle runs on an onboard/companion host
and a phone, tablet, or laptop opens the browser dashboard on the same isolated
LAN or operator-approved private overlay/VPN:

```bash
make demo-lan-browser-profile LAN_HOST=192.168.10.42
```

For the fastest beginner bench path after `make init`, use the wrapper:

```bash
make quick-browser-demo LAN_HOST=192.168.10.42
```

The wrapper applies this profile, writes the generated password to an owner-only
handoff file under the user's PixEagle config directory, handles active UFW when
it can scope access to the trusted local CIDR, starts a minimal dashboard/backend
demo without MAVSDK Server or MAVLink2REST, and prints the browser URL. Use
`START_DEMO=0` to configure only. Use `TRUSTED_CIDR=<cidr>` when the firewall
scope cannot be inferred from the selected host address.

The generated quick-demo user is an `admin` by default so a maintainer can open
Settings and runtime Logs immediately during the first bench check. The account
is still protected by browser-session login, the hashed credential file,
HttpOnly cookie, CSRF checks, and exact Host/Origin policy. If the first demo
account should be less privileged, run the wrapper with
`SESSION_ROLE=operator` or `SESSION_ROLE=viewer`; those roles intentionally do
not expose raw runtime logs.

Before it changes anything, the wrapper prints the selected mode, host scope,
dashboard/backend URLs, hashed credential-store path, one-time handoff path,
minimal-service scope, browser video transport expectation, and cleanup command.
`DRY_RUN=1 START_DEMO=0` is a no-touch preview: it does not create credential
directories, write files, open firewall ports, or start tmux services.

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

For unattended beginner demos, prefer a handoff file instead of terminal
password output:

```bash
make demo-lan-browser-profile LAN_HOST=192.168.10.42 \
  SETUP_PROFILE_ARGS="--credential-handoff-file $HOME/.config/pixeagle/secrets/demo-browser-handoff.json"
```

The quick wrapper uses that handoff-file pattern by default.

Temporary public-IP HTTP demos are supported only through an explicit override
for VPS/lab convenience:

```bash
ALLOW_PUBLIC_HTTP_DEMO=1 OPEN_FIREWALL=1 make quick-browser-demo LAN_HOST=<public-ip>
```

That path is plain HTTP and sends credentials without TLS. It exists only for a
short bench demo where the operator accepts the risk, and it must end with
`make stop` plus credential rotation or deletion. Production remote browser
access must use the guarded TLS/reverse-proxy profile or an equivalent reviewed
deployment boundary.

Public HTTP/IP browser demos also intentionally use WebSocket JPEG in dashboard
Auto mode rather than WebRTC. Earlier local/LAN WebRTC checks only proved that a
browser could negotiate a permissive path; they did not prove a reviewed public
ICE/TURN/TLS path. WebRTC can be re-enabled for serious remote testing after the
deployment has HTTPS/WSS, an explicit ICE/TURN/firewall design, auth evidence,
and receiver validation.

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

In public plain-HTTP/IP bench demos, dashboard Auto stream mode selects
WebSocket JPEG and labels that choice instead of trying WebRTC by constructor
detection alone. WebRTC media needs a reviewed ICE path, and production remote
WebRTC should be validated through TLS/WSS plus TURN/firewall evidence rather
than broad public UDP exposure.

### `production_remote`

Use this when PixEagle will sit behind a separately secured HTTPS/WSS reverse
proxy or equivalent reviewed trust boundary:

```bash
install -d -m 0700 "$HOME/.config/pixeagle/secrets"
make production-remote-profile \
  PUBLIC_HOST=pixeagle.example \
  SESSION_USER_FILE="$HOME/.config/pixeagle/secrets/browser-users.json" \
  CREDENTIAL_HANDOFF_FILE="$HOME/.config/pixeagle/secrets/initial-credentials.json"
```

Optional custom public origin:

```bash
make production-remote-profile \
  PUBLIC_HOST=pixeagle.example \
  PUBLIC_ORIGIN=https://pixeagle.example:8443 \
  SESSION_USER_FILE="$HOME/.config/pixeagle/secrets/browser-users.json" \
  CREDENTIAL_HANDOFF_FILE="$HOME/.config/pixeagle/secrets/initial-credentials.json"
```

`PUBLIC_HOST` is the browser-visible TLS endpoint host, without scheme, path, or
port. If a non-standard HTTPS port is needed, put it in `PUBLIC_ORIGIN`.
`SESSION_USER_FILE` is required and must be a deployment-managed path; the
profile refuses to reuse the demo credential path. The tool generates an
external PBKDF2-SHA256 browser-session user file and sets
`API_SESSION_COOKIE_SECURE: true`. Interactive use can show the generated
password once. Non-interactive use must provide `CREDENTIAL_HANDOFF_FILE` or
explicitly acknowledge captured stdout with `SHOW_GENERATED_PASSWORD=1`.
Delete the owner-only handoff file after secure transfer.

Production credential generation currently runs on the Linux deployment host
because POSIX owner-only mode is enforced; Windows ACL automation is not yet
evidence-backed. The setup utility rejects output-path collisions and applies
credential/config writes atomically with rollback if the later config commit
fails.

The profile intentionally keeps the PixEagle backend loopback-only. It prepares
PixEagle for a reverse proxy; it does not install nginx/Caddy, open firewall
ports, register services, run SITL/HIL, or prove the deployment:

```yaml
Streaming:
  API_EXPOSURE_MODE: trusted_lan_legacy
  HTTP_STREAM_HOST: 127.0.0.1
  HTTP_STREAM_PORT: 5077
  API_CORS_ALLOWED_ORIGINS:
    - https://pixeagle.example
  API_ALLOWED_HOSTS:
    - pixeagle.example:443
  API_AUTH_MODE: browser_session
  API_SESSION_USER_FILE: /home/operator/.config/pixeagle/secrets/browser-users.json
  API_SESSION_COOKIE_SECURE: true
  API_SECURITY_AUDIT_ENABLED: true
```

The recommended same-origin production shape is:

- serve the dashboard under `/pixeagle`;
- proxy `/pixeagle-api` to `http://127.0.0.1:5077`;
- validate the external `Host` at the proxy and preserve the reviewed public
  hostname when forwarding; public authority ports such as `:8443` are
  accepted for exact allowed hosts while direct loopback requests remain pinned
  to backend port `5077`;
- preserve and validate `Origin`;
- keep direct backend port `5077` closed to untrusted networks;
- use HTTPS/WSS with a browser-trusted public certificate, internal PKI, or
  another reviewed trust anchor.

Follow the maintained
[production remote reverse-proxy runbook](production-remote-reverse-proxy.md)
for Linux ownership, nginx path rewriting, WebSocket upgrade handling,
firewall boundaries, the opt-in local HTTPS/browser evidence harness, target
evidence collection, and rollback.

The dashboard already supports this shape: when served under `/pixeagle`, it
routes API and media calls through `/pixeagle-api`. If an operator chooses a
different path or direct API origin, document the reverse-proxy rules and CORS
origin explicitly before handoff.

When `make run` sees this loopback backend/browser-session profile, it keeps
the static dashboard server on loopback by default. The LAN auto-bind behavior
is reserved for `demo_lan_browser`, where the backend bind is intentionally
non-loopback. To expose the production dashboard, terminate HTTPS/WSS at the
reviewed proxy or tunnel instead of relying on the raw development server.

Production readiness still requires operator review, proxy/firewall evidence,
credential handoff evidence, adversarial browser/session/media tests, and the
normal PixEagle safety evidence gates. Do not claim production remote-browser
success from the setup-profile output alone.

## Unsupported Or Not Automated

These profiles are part of the product contract, but the setup utility refuses
to apply them until their remaining security and evidence gates are completed.

| Profile | Intent | Current status |
| --- | --- | --- |
| `unsafe_demo_lan_media_only` | Explicit anonymous media-only lab exception, never a dashboard/control profile and never default | Not supported |

Do not create a no-password remote control panel. If a beginner needs remote
video quickly, use `field_qgc_video`; it is the simplest QGC path and does not
open the PixEagle backend. Use `qgc_direct_media` only when HTTPS/WSS and the
required QGC build are available. If a beginner needs the full browser
dashboard from another device, use `demo_lan_browser` so setup generates
credentials rather than exposing anonymous backend control.

## Tooling

List profiles:

```bash
python scripts/setup/apply-setup-profile.py --list-profiles
```

Preview changes:

```bash
python scripts/setup/apply-setup-profile.py --profile field_qgc_video --gcs-host 192.168.10.20 --dry-run
python scripts/setup/apply-setup-profile.py --profile qgc_direct_media --public-host pixeagle.example --dry-run
python scripts/setup/apply-setup-profile.py --profile demo_lan_browser --lan-host 192.168.10.42 --dry-run
python scripts/setup/apply-setup-profile.py --profile production_remote --public-host pixeagle.example --session-user-file "$HOME/.config/pixeagle/secrets/browser-users.json" --credential-handoff-file "$HOME/.config/pixeagle/secrets/initial-credentials.json" --dry-run
```

Apply changes:

```bash
python scripts/setup/apply-setup-profile.py --profile field_qgc_video --gcs-host 192.168.10.20
python scripts/setup/apply-setup-profile.py --profile demo_lan_browser --lan-host 192.168.10.42
python scripts/setup/apply-setup-profile.py --profile production_remote --public-host pixeagle.example --session-user-file "$HOME/.config/pixeagle/secrets/browser-users.json" --credential-handoff-file "$HOME/.config/pixeagle/secrets/initial-credentials.json"
```

When the destination `configs/config.yaml` already exists, the tool creates a
timestamped backup before writing unless `--no-backup` is explicitly supplied.

## QGC Direct HTTP/WebSocket Media

The simplest field QGC path remains GStreamer UDP/RTP. The guarded
`qgc_direct_media` profile supports direct remote QGC HTTP/WebSocket media for a
draft/test QGC build containing the repaired generic Authorization, optional
WebSocket Origin, strict TLS/custom CA, and credential-redaction
implementation. It requires:

- `Streaming.API_EXPOSURE_MODE: trusted_lan_legacy`;
- exact `Streaming.API_ALLOWED_HOSTS`;
- `Streaming.API_AUTH_MODE: machine_bearer` or a reviewed mixed session/bearer
  deployment;
- a bearer token with `media:read` only for video-only QGC use;
- no query-string credentials;
- HTTPS/WSS with deployment-managed trust for production.

The profile keeps PixEagle loopback behind an external proxy and does not prove
QGC playback. Do not present it as deployment-ready until PR #13594 leaves
draft and QGC CI, target receiver, TLS, proxy, and firewall evidence are
recorded.

See [Remote Media Security](../video/04-streaming/remote-media-security.md) and
[QGC HTTP/WebSocket Source Plan](../video/04-streaming/qgc-http-websocket-source-plan.md).

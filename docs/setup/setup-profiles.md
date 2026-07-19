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

## Source Checkout Provenance

Setup profiles configure a host; they do not establish which PixEagle source
revision is trusted. The mutable `main` one-liner is a beginner lab/development
lane. Production and Raspberry Pi acceptance use the exact-commit bootstrap in
the [Installation Guide](../INSTALLATION.md) with a reviewed 40-hex
`PIXEAGLE_COMMIT`. The bootstrap verifies a detached checkout `HEAD` before
publishing the install directory. Record that commit alongside the selected
profile and test evidence.

Rerunning `install.sh` on an existing branch checkout delegates to
`scripts/update.sh`. That update is clean-worktree and fast-forward-only, but it
is still branch-based; it is not a substitute for an exact production source
pin.

MAVSDK Server and MAVLink2REST downloads are governed separately by the
[Binary Download Policy](binary-download-policy.md). Setup profiles change local
PixEagle configuration; they do not change pinned external binary versions or
checksum policy.

When a profile asks for `LAN_HOST` or `PUBLIC_HOST`, provide the PixEagle
address or DNS name that the browser, QGC, reverse proxy, or test client will
put in the URL. These values become `Streaming.API_ALLOWED_HOSTS` request
authority entries and matching browser origins where needed. They are not GCS
client/source-IP allowlists. Restrict selected GCS devices with firewall,
VPN/overlay, or reverse-proxy source-IP rules, and keep PixEagle auth enabled
unless the explicitly named `unsafe_demo_lan_media_only` profile is being used
for media-only lab viewing.

`make init` reports setup state separately from profile state. Its final
summary distinguishes `ready`, `skipped`, `degraded`, and `manual follow-up`
items for dashboard dependencies, dashboard `.env`, and MAVSDK/MAVLink2REST
binaries; resolve non-ready items before using the related profile in a demo or
deployment.

## Supported Automated Profiles

### `beginner_lab`

This is the profile applied by the concise same-host beginner command:

```bash
make demo
```

It combines loopback-only dashboard/API access with the included looping video,
`COMMAND_PREVIEW`, an active circuit breaker, and safety bypasses disabled. The
launcher starts the dashboard and main application without MAVSDK Server or
MAVLink2REST. Once a target is selected, **Start Follower Test** is available;
an explicitly enabled diagnostic bypass only adds a warning and never changes
the no-PX4 boundary. It is a tracker/follower calculation test, not PX4, SITL,
or vehicle-response evidence.

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
  API_SYSTEM_RESTART_POLICY: local_only
  ALLOW_UNAUTHENTICATED_MEDIA_STREAMING: false

SmartTracker:
  SMART_TRACKER_MODEL_TRUST_POLICY: operator_ack_or_digest

GStreamer:
  ENABLE_GSTREAMER_STREAM: false
  GSTREAMER_HOST: 127.0.0.1
  GSTREAMER_PORT: 5600
```

### `follower_command_preview`

Use this explicit lab profile when a recorded video should exercise follower
math and produce inspectable command intents without a PX4 connection:

```bash
make setup-profile PROFILE=follower_command_preview
```

It selects the canonical looping `VIDEO_FILE` source, sets
`Follower.FOLLOWER_EXECUTION_MODE` to `COMMAND_PREVIEW`, keeps the circuit
breaker active, and keeps both safety-bypass flags false. It preserves the
configured video-file path. It does not install a simulator, start MAVSDK, or
expose a new network service. Follow [Local Follower Test](../drone-interface/06-development/follower-command-preview.md)
for the run and evidence boundary. `COMMAND_PREVIEW` is the safe default of
the explicit beginner/lab `make demo` path. The checked-in runtime default
remains `PX4`; it requires a live source and continues to reject video-file
replay for autonomous Following.

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
.venv\Scripts\python.exe scripts\setup\apply-setup-profile.py --profile field_qgc_video --gcs-host 192.168.10.20
```

This enables PixEagle GStreamer H.264/RTP/UDP output to the GCS host and keeps
the PixEagle backend loopback-only. In QGroundControl, select UDP h.264 video
and use the same port, normally `5600`.

Before relying on this profile, run:

```bash
make check-gstreamer-runtime
```

The check requires both an OpenCV build that reports `GStreamer: YES` and the
exact effective encoder/RTP/UDP plugin path. `x264enc` is always required as
the bounded software fallback; when hardware probing selects NVENC or VA-API,
`h264parse` is required too. A successful capability check does not prove
end-to-end QGC reception; confirm moving video on the target GCS.

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

`PUBLIC_HOST` is the TLS/proxy authority QGC will use in the URL, not the GCS
computer's client IP. To allow only a particular GCS laptop or tablet, scope
the external firewall or reverse proxy to that source address in addition to
the generated `media:read` bearer token.

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

This network profile does not alter the selected video, tracker, follower mode,
or circuit-breaker state. To expose the included-video Follower Test on a
trusted browser device, apply `beginner_lab` first and then apply or run the
browser-demo profile. Cleanup removes the browser exposure while preserving
those separately selected non-network runtime choices.

The generated quick-demo user is an `admin` by default so a maintainer can open
Settings and runtime Logs immediately during the first bench check. The account
is still protected by browser-session login, the hashed credential file,
HttpOnly cookie, CSRF checks, and exact Host/Origin policy. If the first demo
account should be less privileged, run the wrapper with
`SESSION_ROLE=operator` or `SESSION_ROLE=viewer`; those roles intentionally do
not expose raw runtime logs.

This profile also sets `API_SYSTEM_RESTART_POLICY: lab_admin_browser`. Its
authenticated admin may use the dashboard's pending-restart banner after a
saved system-tier setting changes. The backend still refuses restart while
following or Offboard is active, and requires a config backup plus durable
audit event. Browser sessions are process-local, so the dashboard returns to
sign-in after the replacement backend is reachable; use the same configured
account to continue. The supervised launcher and the bounded shutdown watchdog
preserve the same restart exit request, so a slow graceful shutdown cannot turn
an accepted restart into a stopped backend. Other setup profiles keep restart
authority loopback-only.

Before it changes anything, the wrapper prints the selected mode, host scope,
dashboard/backend URLs, hashed credential-store path, one-time handoff path,
minimal-service scope, browser video transport expectation, and cleanup command.
`DRY_RUN=1 START_DEMO=0` is a no-touch preview: it does not create credential
directories, write files, open firewall ports, or start tmux services.

After a bench demo, preview cleanup first:

```bash
DRY_RUN=1 make quick-browser-demo-cleanup LAN_HOST=192.168.10.42
```

Then stop the demo, delete the generated handoff/user credential files, and
restore the local-only config profile:

```bash
CONFIRM=1 make quick-browser-demo-cleanup LAN_HOST=192.168.10.42
```

Set `RESTORE_LOCAL_PROFILE=0` only when you are immediately applying another
reviewed profile such as `production_remote` or `field_qgc_video`. Otherwise,
leaving `configs/config.yaml` in the demo/browser-session profile can expose
the dashboard/backend on the next `make run`.

Add `CLOSE_FIREWALL=1` only when the quick wrapper opened local UFW rules that
should be removed. LAN/private-overlay firewall cleanup requires the same
trusted CIDR that was opened; pass `TRUSTED_CIDR=<cidr>` when auto-detection is
not possible. Add `REMOVE_DEMO_BACKUPS=1` only when deleting timestamped
credential backups is intentional; backups are preserved by default so an
operator can recover from accidental cleanup.

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

After login, select the account chip in the dashboard header to change the
current password. The default admin demo account also receives a **Users** tab;
its changes are written atomically to the same `API_SESSION_USER_FILE`, take
effect immediately, and revoke affected users' active sessions.

For break-glass recovery or stopped-runtime administration, use the offline
management CLI. It edits the same file format and creates owner-only backups by
default:

```bash
python3 scripts/setup/manage-browser-users.py --file configs/secrets/demo-browser-users.json list
python3 scripts/setup/manage-browser-users.py --file configs/secrets/demo-browser-users.json set-password --username pixeagle-demo --generate-password
python3 scripts/setup/manage-browser-users.py --file configs/secrets/demo-browser-users.json add --username viewer --role viewer --generate-password
python3 scripts/setup/manage-browser-users.py --file configs/secrets/demo-browser-users.json disable --username viewer
```

Restart PixEagle after offline changes when immediate enforcement matters.

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
short bench demo where the operator accepts the risk. If UFW rules were opened,
end the test with:

```bash
CONFIRM=1 CLOSE_FIREWALL=1 make quick-browser-demo-cleanup LAN_HOST=<public-ip>
```

Production remote browser access must use the guarded TLS/reverse-proxy profile
or an equivalent reviewed deployment boundary.

Public HTTP/IP browser demos also intentionally use WebSocket JPEG in dashboard
Auto mode rather than WebRTC. Earlier local/LAN WebRTC checks only proved that a
browser could negotiate a permissive path; they did not prove a reviewed public
ICE/TURN/TLS path. WebRTC can be re-enabled for serious remote testing after the
deployment has HTTPS/WSS, an explicit ICE/TURN/firewall design, auth evidence,
and receiver validation.

An operator may select WebRTC manually in a plain-HTTP lab demo. That selection
is an explicit best-effort connectivity test, not a supported-production claim;
Auto remains on WebSocket, signaling still follows the configured API auth and
Host/Origin policy, and a missing ICE path produces a visible failure. Server
STUN/TURN settings do not provision TURN or distribute browser relay secrets.

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

### `unsafe_demo_lan_media_only`

Use this only when a lab or bench test needs anonymous MJPEG/WebSocket video
from PixEagle and does not need a remote dashboard or control panel:

```bash
make unsafe-demo-lan-media-profile LAN_HOST=192.168.10.42
```

Temporary public-IP benches require an explicit override:

```bash
make unsafe-demo-lan-media-profile \
  LAN_HOST=<public-ip> \
  SETUP_PROFILE_ARGS=--allow-public-http-demo
```

This profile enables only the raw media endpoints:

- `GET /video_feed`
- `WS /ws/video_feed`

It does not make dashboard, control, config, logs, typed status/telemetry,
`/api/v1/streams/media-health`, or `/ws/webrtc_signaling` anonymous. It keeps
`API_AUTH_MODE: local_compat`, so non-loopback API callers remain unauthorized
unless a separate reviewed session or bearer-token profile is configured. For a
remote browser dashboard, use `demo_lan_browser`; for production or serious
remote native media, use `qgc_direct_media` behind HTTPS/WSS.

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
  API_AUTH_MODE: local_compat
  API_BEARER_TOKEN_FILE: ""
  API_SESSION_USER_FILE: ""
  ALLOW_UNAUTHENTICATED_MEDIA_STREAMING: true
  API_SECURITY_AUDIT_ENABLED: true
```

Native clients such as QGC may omit `Origin` on `ws://.../ws/video_feed` in
this unsafe profile. Browser WebSocket requests that include an `Origin` still
must match `API_CORS_ALLOWED_ORIGINS`, and HTTP requests still must pass exact
Host/CORS/browser-origin checks. Query-string credentials remain rejected.

The anonymous exception is controlled only by
`ALLOW_UNAUTHENTICATED_MEDIA_STREAMING`. Do not try to create an anonymous
"selected GCS IP" mode with `API_ALLOWED_HOSTS`; that key is the request Host
authority check. If the bench must be limited to one laptop, add a firewall or
reverse-proxy source-IP rule for that laptop and remove the unsafe profile when
testing is complete.

This mode is intentionally loud and non-default because anyone who can reach the
URL can view the live video. Use it only on isolated lab networks, private
overlays, or short operator-approved public benches, then restore a safer
profile with `make setup-profile PROFILE=local_dev` or the normal cleanup path.

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

Unless overridden with `SESSION_USERNAME`, the generated initial account is
named `pixeagle-operator` and has the `admin` role. The username is a stable
deployment default, not a reduced-privilege role label; use the account dialog
or user-management CLI to create separate operator/viewer accounts and remove
or rename deployment defaults according to local policy.

Production credential generation currently runs on the Linux deployment host
because POSIX owner-only mode is enforced; Windows ACL automation is not yet
evidence-backed. The setup utility rejects output-path collisions and applies
credential/config writes atomically with rollback if the later config commit
fails.

For ordinary administration, an authenticated admin can use the dashboard
account chip. The deployment directory containing `SESSION_USER_FILE` must be
owned by the PixEagle process user and must not be group/other writable, so the
running process can perform safe atomic account updates.

For break-glass production password reset, run the same offline user-management
CLI against the deployment-managed `SESSION_USER_FILE` and transfer any
generated password through a one-time owner-only handoff file:

```bash
python3 scripts/setup/manage-browser-users.py \
  --file "$HOME/.config/pixeagle/secrets/browser-users.json" \
  set-password --username pixeagle-operator --generate-password \
  --credential-handoff-file "$HOME/.config/pixeagle/secrets/reset-handoff.json"
```

Delete the handoff file after secure transfer and restart PixEagle so the
offline snapshot is enforced.

The profile intentionally keeps the PixEagle backend loopback-only. It prepares
PixEagle for a reverse proxy; it does not install nginx/Caddy, open firewall
ports, register services, run SITL/HIL, or prove the deployment:

```yaml
Streaming:
  API_EXPOSURE_MODE: trusted_lan_legacy
  HTTP_STREAM_HOST: 127.0.0.1
  HTTP_STREAM_PORT: 5077
  API_SYSTEM_RESTART_POLICY: local_only
  API_CORS_ALLOWED_ORIGINS:
    - https://pixeagle.example
  API_ALLOWED_HOSTS:
    - pixeagle.example:443
  API_AUTH_MODE: browser_session
  API_SESSION_USER_FILE: /home/operator/.config/pixeagle/secrets/browser-users.json
  API_SESSION_COOKIE_SECURE: true
  API_SECURITY_AUDIT_ENABLED: true

SmartTracker:
  SMART_TRACKER_MODEL_TRUST_POLICY: digest_required
```

Production model registration and dashboard upload therefore require the
publisher's expected SHA-256 in addition to explicit operator trust. See
[`docs/MODEL_SETUP.md`](../MODEL_SETUP.md).

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

Do not create a no-password remote control panel. If a beginner needs remote
video quickly, use `field_qgc_video`; it is the simplest QGC path and does not
open the PixEagle backend. Use `unsafe_demo_lan_media_only` only when anonymous
raw media is explicitly acceptable for a lab/bench. Use `qgc_direct_media` only
when HTTPS/WSS and the required QGC build are available. If a beginner needs the
full browser dashboard from another device, use `demo_lan_browser` so setup
generates credentials rather than exposing anonymous backend control.

## Tooling

List profiles:

```bash
python3 scripts/setup/apply-setup-profile.py --list-profiles
```

Preview changes:

```bash
python3 scripts/setup/apply-setup-profile.py --profile field_qgc_video --gcs-host 192.168.10.20 --dry-run
python3 scripts/setup/apply-setup-profile.py --profile follower_command_preview --dry-run
python3 scripts/setup/apply-setup-profile.py --profile qgc_direct_media --public-host pixeagle.example --dry-run
python3 scripts/setup/apply-setup-profile.py --profile demo_lan_browser --lan-host 192.168.10.42 --dry-run
python3 scripts/setup/apply-setup-profile.py --profile unsafe_demo_lan_media_only --lan-host 192.168.10.42 --dry-run
python3 scripts/setup/apply-setup-profile.py --profile production_remote --public-host pixeagle.example --session-user-file "$HOME/.config/pixeagle/secrets/browser-users.json" --credential-handoff-file "$HOME/.config/pixeagle/secrets/initial-credentials.json" --dry-run
```

Apply changes:

```bash
python3 scripts/setup/apply-setup-profile.py --profile field_qgc_video --gcs-host 192.168.10.20
python3 scripts/setup/apply-setup-profile.py --profile follower_command_preview
python3 scripts/setup/apply-setup-profile.py --profile demo_lan_browser --lan-host 192.168.10.42
python3 scripts/setup/apply-setup-profile.py --profile unsafe_demo_lan_media_only --lan-host 192.168.10.42
python3 scripts/setup/apply-setup-profile.py --profile production_remote --public-host pixeagle.example --session-user-file "$HOME/.config/pixeagle/secrets/browser-users.json" --credential-handoff-file "$HOME/.config/pixeagle/secrets/initial-credentials.json"
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
- exact `Streaming.API_ALLOWED_HOSTS` matching the URL/proxy Host authority,
  not the GCS source IP;
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

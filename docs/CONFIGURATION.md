# Configuration Guide

> Complete reference for PixEagle configuration options

## Configuration Files

| File | Purpose |
|------|---------|
| `configs/config_default.yaml` | Checked-in runtime value authority and schema-generation source |
| `configs/config.yaml` | Optional local runtime overrides created manually or by setup profiles |
| `configs/config_schema.yaml` | Generated validation, display, reload, and sensitivity metadata; it does not override default values |
| `configs/config_retirements.yaml` | Versioned exact paths authorized for removal during config migration |
| `configs/config_sync_meta.json` | Local owner-only defaults baseline, provenance, and applied retirement IDs |
| `configs/audit_log.json` | Local owner-only redacted config mutation audit |
| `dashboard/.env` | Dashboard environment variables |

Unknown local paths are preserved as extensions. They are never inferred to be
obsolete from absence in defaults/schema. See [Config Sync](CONFIG_SYNC.md) for
the preview, confirmation, owner-only backup, and rollback workflow.

Runtime consumers reject ambiguous flattened names. Boundary policy is grouped
under `TrackerSafety`; detector appearance validation is owned once by
`Detector.APPEARANCE_CONFIDENCE_THRESHOLD`. Older local aliases are ignored at
runtime only when their exact paths are registered for retirement, then remain
visible in Config Sync until the operator removes them.

## Main Configuration (config.yaml)

### Video Input

```yaml
VIDEO_SOURCE: 0  # Webcam index, file path, or RTSP URL
# Examples:
# VIDEO_SOURCE: "/dev/video0"
# VIDEO_SOURCE: "rtsp://192.168.1.100:8554/stream"
# VIDEO_SOURCE: "test_video.mp4"
```

### SmartTracker

```yaml
SmartTracker:
  SMART_TRACKER_ENABLED: true
  SMART_TRACKER_USE_GPU: true
  SMART_TRACKER_GPU_MODEL_PATH: "models/yolo26n.pt"
  SMART_TRACKER_CPU_MODEL_PATH: "models/yolo26n_ncnn_model"
  TRACKER_TYPE: "botsort"  # bytetrack, botsort, custom_reid
  DETECTION_CONFIDENCE: 0.5
  IOU_THRESHOLD: 0.45
```

### OSD (On-Screen Display)

```yaml
OSD:
  OSD_ENABLED: true
  OSD_PRESET: "professional"          # minimal | professional | full_telemetry
  OSD_PERFORMANCE_MODE: "balanced"    # fast | balanced | quality
  OSD_PIPELINE_MODE: "layered_realtime"     # layered_realtime | legacy
  OSD_TARGET_LAYER_RESOLUTION: "stream"     # stream | capture
  OSD_DYNAMIC_FPS: 10
  OSD_DATETIME_FPS: 1
  OSD_MAX_RENDER_BUDGET_MS: 25.0
  OSD_AUTO_DEGRADE: true
  OSD_AUTO_DEGRADE_MIN_MODE: "fast"         # fast keeps low-power boards responsive
  OSD_COMPOSITOR: "cv2_alpha"               # cv2_alpha | legacy_pil_composite
```

### Follower Modes

Available modes:
- `mc_velocity_position` - Position hold with altitude control
- `mc_velocity_chase` - Body velocity chase
- `mc_velocity_distance` - Compatibility centering profile; no range hold
- `gm_velocity_chase` - Gimbal velocity chase
- `gm_velocity_vector` - Gimbal vector pursuit
- `fw_attitude_rate` - Fixed-wing tracking

### PID Tuning

```yaml
PID:
  KP_X: 1.0
  KI_X: 0.0
  KD_X: 0.1
  KP_Y: 1.0
  KI_Y: 0.0
  KD_Y: 0.1
```

### Safety Limits

```yaml
Safety:
  MAX_VELOCITY: 5.0
  MIN_ALTITUDE: 2.0
  MAX_ALTITUDE: 120.0
  GEOFENCE_ENABLED: true
```

## Dashboard Environment (.env)

```bash
# Dashboard HTTP port (default: 3040)
PORT=3040

# Dashboard HTTP bind (default: loopback only)
HOST=127.0.0.1

# API port (default: 5077)
REACT_APP_API_PORT=5077

# Optional: Override API host for a reviewed proxy/tunnel deployment
REACT_APP_API_HOST_OVERRIDE=

# Polling rate in milliseconds
REACT_APP_POLLING_RATE=500

# Maximum velocity for visualization
REACT_APP_MAX_SPEED=1

# Click-only ROI width/height as a fraction of the visible video.
# Dragging always uses the operator-drawn ROI instead.
REACT_APP_DEFAULT_BOUNDING_BOX_SIZE=0.08
REACT_APP_CONTINUOUS_TARGET_SELECTION=true
```

### Auto Host Detection (v4.1.0+)

The dashboard automatically detects the API host from `window.location.hostname`. No manual configuration needed for:
- Local development (localhost)
- SSH-tunneled local access

Use `REACT_APP_API_HOST_OVERRIDE` only for reviewed proxy/tunnel setups. A
non-loopback reverse-proxy browser origin is not permitted in `local_only`;
`trusted_lan_legacy` only opens the backend bind/CORS boundary. Backend
browser-session auth exists. For HTTPS/WSS reverse-proxy browser deployments,
use `make production-remote-profile PUBLIC_HOST=<tls-host>
SESSION_USER_FILE=<path>` or an equivalent reviewed config; production handoff
still requires proxy/firewall evidence, credential handoff evidence,
adversarial auth/media tests, and the normal safety gates.

The checked-in backend policy is `local_only` on `127.0.0.1:5077` with an
explicit loopback CORS allowlist. Startup fails when local-only configuration
contains a non-loopback bind, browser origin, or Host allowlist entry. The
temporary `trusted_lan_legacy` mode still requires exact
`Streaming.API_ALLOWED_HOSTS` entries plus scoped backend API authorization for
non-loopback clients. Do not use auto-detection or network reachability as
authorization. See the [API exposure boundary](apis/api-exposure-boundary.md).

Existing local configs from older releases that still set
`HTTP_STREAM_HOST: 0.0.0.0` without `API_EXPOSURE_MODE` are coerced to loopback
at runtime. Add `trusted_lan_legacy` explicitly only for temporary isolated-LAN
compatibility. For the supported quick browser path on another device, prefer
`make demo-lan-browser-profile LAN_HOST=<this-pixeagle-lan-ip-or-overlay-ip>`;
it asks for browser-session credentials (Enter keeps admin/admin) and generates
exact Host/CORS allowlists for HTTP lab/private-overlay testing. The dashboard uses `3040` and direct
browser API/media calls use backend port `5077`; allow both only from the
trusted demo device/CIDR.

TLS is not limited to public domain names, but HTTP over a private LAN or
private overlay/VPN is only a lab/operator-approved test posture. Production
remote browser access should use the guarded `production_remote` profile or an
equivalent reviewed config with TLS or an equivalent trust boundary, durable
credentials, audit, adversarial auth/media tests, and evidence.

Backend Host and browser-origin controls live under `Streaming`:

```yaml
Streaming:
  API_EXPOSURE_MODE: local_only
  HTTP_STREAM_HOST: 127.0.0.1
  API_ALLOWED_HOSTS: []
  API_CORS_ALLOWED_ORIGINS:
    - http://127.0.0.1:3040
    - http://localhost:3040
```

`API_ALLOWED_HOSTS` is the backend HTTP `Host` allowlist for reviewed
non-loopback profiles. `API_CORS_ALLOWED_ORIGINS` is the browser Origin
allowlist. Keep both exact; wildcards are rejected. A reviewed non-loopback
Host can arrive with the external reverse-proxy port, while loopback Host
authorities remain pinned to `HTTP_STREAM_PORT`.

Do not read `API_ALLOWED_HOSTS` as a selected GCS/client-IP list. It matches
the host authority in the URL or proxy request, not the remote socket address.
If a lab or deployment must limit which GCS laptops can reach a media port,
apply that source-IP/CIDR policy in UFW, nftables, the VPN, or the reverse
proxy, and still keep PixEagle authentication enabled unless the explicit
unsafe media-only lab flag below is acceptable for that bench.

Backend API authorization controls live under `Streaming`:

```yaml
Streaming:
  API_AUTH_MODE: local_compat
  API_SYSTEM_RESTART_POLICY: local_only
  ALLOW_UNAUTHENTICATED_MEDIA_STREAMING: false
  API_BEARER_TOKEN_FILE: ""
  API_SESSION_USER_FILE: ""
```

`local_compat` is the checked-in same-host default. It allows loopback clients
without credentials only when the immediate socket peer is loopback and no
proxy-forwarded client identity headers are present. It does not trust HTTP
`Host`, and it must not be exposed through a reverse proxy. Non-loopback API
clients require scoped bearer tokens. `machine_bearer` requires bearer tokens
for every API client and is for machine/API clients. `browser_session` loads
browser/operator users from `API_SESSION_USER_FILE`, creates HttpOnly cookie
sessions through `/api/v1/auth/login`, and requires the returned CSRF token for
browser mutations. The token and user files are external JSON with hashed
records; do not put plaintext tokens or passwords in `config.yaml`. On POSIX,
runtime loading requires a regular file owned by the PixEagle process user,
exactly one hard link, owner-read permission, and no group/other permissions
(`0600` or stricter). Symbolic links and auth-record files over 1 MiB are
rejected before JSON parsing.

`API_SYSTEM_RESTART_POLICY` is read once when the PixEagle process starts. The
checked-in `local_only` value permits the guarded restart action only from a
verified loopback transport with `system:admin`. The `demo_lan_browser` setup
profile sets `lab_admin_browser`, which additionally permits its authenticated
remote admin session to restart the backend on the lab host. Production,
machine-bearer, anonymous-media, and local profiles keep `local_only`. Changing
this policy does not authorize the running process; the new value takes effect
only after an externally initiated restart.

`ALLOW_UNAUTHENTICATED_MEDIA_STREAMING` is a lab-only exception and defaults to
`false`. When explicitly set to `true`, anonymous clients may read only
`GET /video_feed` and `WS /ws/video_feed` after the normal Host/CORS/browser
origin checks pass. It does not open dashboard, control, config, logs,
status/telemetry, media-health, recordings, model, WebRTC signaling, or action
APIs. Prefer `make unsafe-demo-lan-media-profile LAN_HOST=<host>` instead of
editing the flag manually so the Host/CORS allowlists stay aligned.

The official quick-start default is a same-host beginner demo: run PixEagle and
open the dashboard locally without creating credentials. When the dashboard or
backend is reachable from another phone, tablet, or GCS machine, use an explicit
profile instead of broadening the default. Full remote browser demos should
generate `browser_session` users; production remote browser deployments should
use `production_remote` behind HTTPS/WSS; QGC field video should normally use
GStreamer H.264/RTP/UDP. Guarded direct QGC HTTP/WS video uses
`make qgc-direct-media-profile PUBLIC_HOST=<tls-host>` to generate a
`machine_bearer` token with only `media:read`, exact Host/Origin policy, and a
loopback backend for an external HTTPS/WSS proxy. QGC CI and target receiver
evidence remain required. See
[Setup Profiles](setup/setup-profiles.md),
[Remote Media Security](video/04-streaming/remote-media-security.md) and
[QGC HTTP/WebSocket Source Plan](video/04-streaming/qgc-http-websocket-source-plan.md).

Generate browser-session user records with a local password prompt:

```bash
PYTHONPATH=src python - <<'PY'
import getpass
import json

from classes.api_auth_runtime import make_user_record

username = input("Username: ")
role = input("Role [operator]: ").strip() or "operator"
password = getpass.getpass("Password: ")
print(json.dumps({"users": [make_user_record(
    username=username,
    plaintext_password=password,
    role=role,
)]}, indent=2))
PY
```

Store the generated JSON outside the repository, set mode `0600`, ensure the
PixEagle process user owns it, and point `Streaming.API_SESSION_USER_FILE` at
that path.

API security-audit controls also live under `Streaming`:

```yaml
Streaming:
  API_SECURITY_AUDIT_ENABLED: true
  API_SECURITY_AUDIT_LOG_PATH: logs/security_audit.jsonl
  API_SECURITY_AUDIT_MAX_BYTES: 5000000
  API_SECURITY_AUDIT_BACKUP_COUNT: 5
```

Keep `API_SECURITY_AUDIT_ENABLED` enabled for any operator or remote-access
profile. Allowed mutation and security-critical requests fail closed when their
required audit event cannot be recorded. `API_SECURITY_AUDIT_LOG_PATH` is
resolved relative to the repository when it is not absolute, and root
`logs/` output is intentionally gitignored. Rotation is local and bounded by
`API_SECURITY_AUDIT_MAX_BYTES` and `API_SECURITY_AUDIT_BACKUP_COUNT`; archive or
ship these logs through a deployment-owned process when retention beyond local
rotation is required. Changing these settings requires a backend restart.

## Configuration via API

The Settings page in the dashboard allows runtime configuration changes:
- `/api/config/current` - Get current configuration
- `/api/config/update` - Update configuration
- `GET /api/v1/config/runtime-status` - Read redacted persisted changes that require a PixEagle process restart
- `POST /api/v1/actions/system-restart` - Confirm and schedule the guarded process restart action; requires pending system-restart changes, an eligible admin policy, inactive following/Offboard state, an idempotency key, a config backup, and durable audit logging

The action exits the Python backend with the fixed restart code `42` after a
bounded shutdown. The maintained Linux launcher,
`scripts/components/main.sh`, supervises that code and starts a fresh backend;
the dashboard waits for a different process-start timestamp before reporting
success. A backend started directly with `python src/main.py` is not supervised
and will exit instead of relaunching. The action never restarts the host, PX4,
MAVLink2REST, MAVSDK Server, or the dashboard.

These legacy routes remain compatibility surfaces and are not approved remote
automation APIs. Keep them inside the trusted local/tunneled boundary or use
scoped bearer tokens only where explicitly reviewed. Typed guarded actions and
the browser-session dashboard client/media and durable security-audit
foundations exist, and Offboard start/stop/operator abort are typed-action-only
over HTTP. Tracking start/stop, segmentation toggle, redetect, smart-mode
toggle, and smart-click are also typed-action-only over HTTP; their former
`/commands/*` aliases are retired. Operator deployment hardening and
adversarial auth/media tests remain tracked under PXE-0064.

## Next Steps

- [Installation Guide](INSTALLATION.md)
- [SmartTracker Guide](trackers/02-reference/smart-tracker.md)
- [OSD Guide](OSD_GUIDE.md)

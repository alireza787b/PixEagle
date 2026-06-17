# Configuration Guide

> Complete reference for PixEagle configuration options

## Configuration Files

| File | Purpose |
|------|---------|
| `configs/config.yaml` | Main application settings |
| `configs/config_schema.yaml` | Schema definitions |
| `dashboard/.env` | Dashboard environment variables |

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
  TRACKER_TYPE: "botsort_reid"  # bytetrack, botsort, botsort_reid, custom_reid
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
- `mc_velocity_distance` - Fixed distance tracking
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

# Default bounding box size
REACT_APP_DEFAULT_BOUNDING_BOX_SIZE=0.1
```

### Auto Host Detection (v4.1.0+)

The dashboard automatically detects the API host from `window.location.hostname`. No manual configuration needed for:
- Local development (localhost)
- SSH-tunneled local access

Use `REACT_APP_API_HOST_OVERRIDE` only for reviewed proxy/tunnel setups. A
non-loopback reverse-proxy browser origin is not permitted in `local_only`;
`trusted_lan_legacy` only opens the backend bind/CORS boundary. Backend
browser-session auth exists, but production remote-browser operation still
requires TLS/operator hardening, retirement of remaining legacy
tracking/control aliases, adversarial auth/media tests, and evidence gates.

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
compatibility.

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
allowlist. Keep both exact; wildcards are rejected.

Backend API authorization controls live under `Streaming`:

```yaml
Streaming:
  API_AUTH_MODE: local_compat
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
records; do not put plaintext tokens or passwords in `config.yaml`.

The official quick-start default is a same-host beginner demo: run PixEagle and
open the dashboard locally without creating credentials. When the dashboard or
backend is reachable from another phone, tablet, or GCS machine, use an explicit
profile instead of broadening the default. Full remote browser demos should
generate `browser_session` users; QGC field video should normally use
GStreamer H.264/RTP/UDP; future direct remote QGC HTTP/WS video should use a
`machine_bearer` token with only `media:read` plus explicit
`API_ALLOWED_HOSTS`. See
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

Store the generated JSON outside the repository, restrict file permissions, and
point `Streaming.API_SESSION_USER_FILE` at that path.

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
- `/api/system/restart` - Restart system

These legacy routes remain compatibility surfaces and are not approved remote
automation APIs. Keep them inside the trusted local/tunneled boundary or use
scoped bearer tokens only where explicitly reviewed. Typed guarded actions and
the browser-session dashboard client/media and durable security-audit
foundations exist, and Offboard start/stop/operator abort are typed-action-only
over HTTP; tracking start/stop also have typed action replacements while their
local-only compatibility aliases await retirement. Segmentation toggle,
redetect, smart-mode toggle, and smart-click also have typed action
replacements; their legacy command routes remain local-only compatibility
aliases until the alias-retirement gate. Operator deployment hardening,
adversarial auth/media tests, and alias retirement remain tracked under
PXE-0064.

## Next Steps

- [Installation Guide](INSTALLATION.md)
- [SmartTracker Guide](trackers/02-reference/smart-tracker.md)
- [OSD Guide](OSD_GUIDE.md)

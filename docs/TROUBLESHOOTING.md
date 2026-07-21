# Troubleshooting Guide

> Common issues and solutions for PixEagle

## Installation Issues

### Python Version Error

**Problem**: setup reports that the selected Python is incompatible with Core
or the resolved Full AI hardware profile.

**Solution**:
```bash
# Check version
python3 --version

# See interpreters already supplied by this host
command -v python3
python3 --version
```

Do not install an arbitrary PPA or replace the operating system's Python to
silence this check. Compatibility comes from
`scripts/setup/pytorch_matrix.json`: Core has a runtime policy, and each CPU,
CUDA, macOS, or Jetson AI profile has its own Python range and exclusions. The
current Linux CPU profile supports Python 3.10-3.14 except 3.14.1.

In guided setup, accept the offered Core fallback when the selected Full AI
profile is unavailable. Core is a complete tracker/dashboard runtime and AI can
be added later. If the host already has another reviewed Python 3 interpreter,
use it explicitly on a fresh setup:

```bash
PIXEAGLE_PYTHON=/usr/bin/python3.12 make init
```

An existing valid PixEagle venv remains authoritative on repair. To change its
interpreter, create a separate clean installation or virtual environment and
validate it before cutover; do not overwrite the active venv in place.

### npm/Node.js Not Found

**Problem**: Dashboard fails to start, npm command not found

**Solution**:
```bash
cd ~/PixEagle
make init
```

The initializer verifies the pinned nvm installer and exact nvm commit, then
resumes Node.js and lockfile-based dashboard setup. It prints the final nvm or
Node error instead of publishing a partial `~/.nvm`. A verified Python
environment from the earlier attempt is reused. If PixEagle reports that an
existing `~/.nvm` has different provenance, either provide Node.js 24.x on
`PATH` through your reviewed host mechanism or move that existing checkout
aside deliberately before rerunning; the installer will not overwrite it.

### Installer Reports No Controlling Terminal

**Problem**: A web console, CI job, remote command, or interrupted SSH session
cannot answer setup prompts.

**Solution**: The one-line bootstrap treats the bootstrap command as install
consent, explicitly selects Core, and skips optional host mutations. A direct
`make init` invocation without a controlling terminal instead requires an
explicit profile so a background task cannot silently approve package changes:

```bash
PIXEAGLE_NONINTERACTIVE=1 \
PIXEAGLE_INSTALL_PROFILE=full \
PIXEAGLE_OPTIONAL_COMPONENTS=shell-shortcut \
make init
```

Use a normal interactive SSH terminal when you want the guided menu. PixEagle
tests opening the controlling terminal once, prints `Interactive terminal
detected`, and explicitly gives that same terminal to the initializer/updater;
the installer pipe is never reused for answers. The mere presence of the
`/dev/tty` device node is not treated as interactive input. If that confirmation
appears but a later prompt still reports no terminal, preserve the transcript
and report it as an installer defect rather than forcing setup with ad hoc
redirection.

### SSH Disconnected During Setup

**Problem**: The SSH connection closes during `apt`, Python/AI dependency
setup, `npm ci`, or an optional OpenCV/GStreamer build.

Do not start multiple installers and do not remove PixEagle lock files. The
setup supervisor forwards termination to its owned descendants and releases
its lease only after they are reaped. An uncommitted venv mutation restores its
exact backup; verified nvm and downloaded binaries publish only after their
staging/checksum gates. Dashboard dependency success is recorded only after
`npm ci` completes and its manifests can be fingerprinted.

An interrupted optional dlib or OpenCV/GStreamer source build is deliberately
not resumed from an untrusted compiler work tree. Select that optional
component again after reconnecting; it restarts from private staging while the
last verified Python/OpenCV environment remains protected by its transaction
or replacement rollback. After a successful optional build, leave it
unselected on routine repairs. Core reconciliation preserves and verifies an
existing supported provider rather than replacing it implicitly.

If the terminal closes while setup is waiting for a guided answer, setup stops
instead of applying the displayed default. Reconnect and rerun the one-line
installer or `make init`; verified components are reused and the summary shows
any remaining work.

For an unreliable SSH link, finish Core setup first and leave long optional
builds unselected. Core installs `tmux`; run the optional build in a protected
session afterward:

```bash
tmux new -s pixeagle-build
cd ~/PixEagle
bash scripts/setup/build-opencv.sh  # or: bash scripts/setup/install-dlib.sh
```

Detach with `Ctrl+B`, then `D`; reconnect with
`tmux attach -t pixeagle-build`. Do not launch a second copy while that session
is active.

After reconnecting, first confirm that the previous setup command is no longer
running. Then use one recovery path:

```bash
cd ~/PixEagle
make repair  # Keep current source; verify and resume missing setup
```

Or rerun the documented one-line installer when you also want the clean branch
checkout fast-forwarded. It detects the existing checkout and asks to
**update and repair in place**. Both paths preserve config, credentials,
models, recordings, logs, and evidence. Already valid dashboard dependencies
are checked offline and reused; an incomplete or stale tree receives one clean
`npm ci`.

If a package-manager interruption reports that `dpkg` needs repair, follow the
exact host error before rerunning setup; do not hide it by deleting package
locks. If another PixEagle setup/runtime still owns the resource, wait for it
or stop it through its documented lifecycle command.

For a genuinely clean comparison, install into a new directory instead of
deleting the current one:

```bash
curl -fsSL https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.sh \
  | PIXEAGLE_HOME="$HOME/PixEagle-clean" bash
```

Use a reviewed exact commit for production/Raspberry Pi acceptance. Validate
the new directory before any operator-controlled cutover.

### Permission Denied on Scripts

**Solution**:
```bash
chmod +x scripts/*.sh scripts/**/*.sh
```

### Optional Setup Script Uses Wrong Python Environment

**Problem**: An optional helper such as `check-ai-runtime.sh`,
`setup-pytorch.sh`, `install-ai-deps.sh`, `build-opencv.sh`, or
`install-dlib.sh` reports missing packages even though the dashboard/runtime
uses a different venv.

**Solution**:
```bash
# Optional: pin the intended environment for this shell
export PIXEAGLE_VENV_DIR="$PWD/.venv"   # or "$PWD/venv"

bash scripts/setup/check-ai-runtime.sh
```

The helpers prefer `PIXEAGLE_VENV_DIR`, then `.venv/`, then `venv/`, and print
the Python path they actually inspected.

### YAML Parse Error in config.yaml

**Problem**: `yaml.scanner.ScannerError: could not find expected ':'` when starting PixEagle

**Why it happens**: The `configs/config.yaml` file has invalid YAML syntax,
usually after an incomplete manual edit or invalid external import. Config Sync
uses an atomic YAML writer and removes empty sections rather than emitting bare
section markers.

**Solution**:
```bash
make reset-config                  # Backs up current config and resets to defaults
# or on embedded Linux:
pixeagle-service reset-config      # Same thing via the service CLI
```

This creates a timestamped backup of your existing config before resetting.

## Video Feed Issues

### Camera Not Detected

**Check available cameras**:
```bash
ls /dev/video*
v4l2-ctl --list-devices
```

**Update config.yaml**:
```yaml
VIDEO_SOURCE: 0  # or /dev/video0
```

### RTSP Stream Not Working

**Test stream**:
```bash
ffplay rtsp://your-stream-url
```

**Check network connectivity** and firewall settings.

### GStreamer Pipeline Errors

**Rebuild OpenCV with GStreamer**:
```bash
bash scripts/setup/build-opencv.sh
```

`make init` preserves one validated source/GStreamer provider and verifies its
fingerprint after Core setup. It refuses multiple wheel owners, unmanaged
non-GStreamer imports, and in-place source-to-wheel overlays. Use a fresh venv
when changing provider class, then rerun `make check-gstreamer-runtime`.

## Dashboard Issues

### Dashboard Not Accessible

1. **Check if running**: `make status`, then use `make attach` for a manual runtime or `pixeagle-service attach` for a managed runtime
2. **Check port**: `lsof -i :3040`
3. **Local tunnel**: use `ssh -L 3040:127.0.0.1:3040 -L 5077:127.0.0.1:5077 <host>`
4. **Dashboard-only trusted/VPN firewall exception**: use the restricted CIDR rules in
   [Port Configuration](drone-interface/04-infrastructure/port-configuration.md);
   do not open the backend broadly.

### API Connection Failed

1. **Check backend**: `lsof -i :5077`
2. **Verify config**: Dashboard auto-detects host from browser URL
3. **Check logs**: use `make attach` for a manual runtime or `pixeagle-service attach` for a managed runtime, then inspect the Python app pane

### Dashboard Restart Returns To Sign-In

This is expected in `browser_session` mode. Dashboard sessions live only in the
current backend process, so a successful process restart invalidates the old
cookie session. Wait until the replacement backend is reachable, then sign in
again with the same account. If an allowed dashboard Origin remains on a failed
reconnect screen instead of returning to sign-in, confirm the running code is
current and that its exact dashboard Origin is listed in
`Streaming.API_CORS_ALLOWED_ORIGINS`.

### Browser Demo Admin Password Forgotten

If the browser-session password is lost but you still have shell access to the
PixEagle host, reset the password in the external `API_SESSION_USER_FILE`:

```bash
# Demo profile default path
python3 scripts/setup/manage-browser-users.py \
  --file configs/secrets/demo-browser-users.json \
  set-password --username pixeagle-demo --generate-password

# Production profile example
python3 scripts/setup/manage-browser-users.py \
  --file "$HOME/.config/pixeagle/secrets/browser-users.json" \
  set-password --username pixeagle-operator --generate-password \
  --credential-handoff-file "$HOME/.config/pixeagle/secrets/reset-handoff.json"
```

The runtime user file stores only PBKDF2-SHA256 hashes. Delete any one-time
handoff file after secure transfer, then restart PixEagle so the offline file
change is published to the running auth snapshot.

When an admin can still sign in, use the account chip in the dashboard header
instead: **My password** changes the current password, while **Users** manages
other accounts. Dashboard role, enablement, reset, and delete changes revoke the
affected user's active sessions immediately. The shell command above is the
recovery path when no admin session is available; restart after that offline
file edit.

### LAN Access Not Working

The dashboard can auto-detect the browser host, but the checked-in backend
profile is local-only. Prefer local access or an SSH tunnel. For a separately
secured trusted/VPN deployment, non-loopback machine API clients need scoped
bearer tokens, and browser operation needs explicit `API_AUTH_MODE=browser_session`
with an external hashed user file, exact Host/CORS allowlists, and the remaining
production hardening gates. Keep backend port `5077` closed to untrusted
networks.

## PX4/MAVLink Issues

### MAVSDK Connection Failed

1. **Check binary exists**: `ls bin/mavsdk_server_bin`
2. **Re-download**: `bash scripts/setup/download-binaries.sh --mavsdk`
3. **Check port**: MAVLink should be on 14540

### MAVLink2REST Not Responding

1. **Check binary**: `ls bin/mavlink2rest`
2. **Re-download**: `bash scripts/setup/download-binaries.sh --mavlink2rest`
3. **Check port 14569**

### No Telemetry Data

1. **Verify MAVLink routing**: `mavlink-routerd` running?
2. **Check endpoints**: 127.0.0.1:14540, 14550, 14569
3. **Verify connection**: QGroundControl can connect?

## SmartTracker Issues

### SmartTracker Says ultralytics/lap Not Installed After Full Init

**Problem**: You selected `Full` in `make init`, but SmartTracker still reports missing AI packages.

**Why it happens**:
- Core dependencies may install successfully while AI verification fails
- AI setup leaves the dedicated virtual environment intact for diagnosis; fix
  the reported dependency/model/device issue and rerun the canonical installer
- Network/wheel availability can cause transient AI install failures

**Solution**:
```bash
bash scripts/setup/setup-pytorch.sh --mode auto
bash scripts/setup/install-ai-deps.sh
bash scripts/setup/check-ai-runtime.sh
```

If the runtime check reports healthy `torch/ultralytics/lap`, restart PixEagle and re-enable SmartTracker.
If an explicitly requested NCNN export fails, verify `pnnx` is installed in the
same venv. Upload and download never export NCNN by default.
The same diagnostic also reports dlib, OpenCV version, OpenCV contrib tracker
APIs, and OpenCV GStreamer support so you can distinguish "AI not installed"
from "OpenCV lacks GStreamer" or "tracker APIs are missing".

### Detection Model Not Loading

**Check model exists**:
```bash
ls models/*.pt
```

**Register a trusted local model**:
```bash
sha256sum models/target.pt
.venv/bin/python add_model.py \
  --model-name target.pt \
  --sha256 <publisher-sha256> \
  --trust-model
```

If the file was copied into `models/` without registration, PixEagle correctly
refuses to load it. See [Model Setup](MODEL_SETUP.md) for the bounded HTTPS
download path and provenance details.

### GPU Not Detected

1. **Check driver/runtime**: `nvidia-smi` (or `tegrastats` on Jetson)
2. **Run diagnostic**: `bash scripts/setup/check-ai-runtime.sh`
3. **Reinstall via matrix installer**: `bash scripts/setup/setup-pytorch.sh --mode auto`
4. **Strict GPU validation** (optional): `bash scripts/setup/setup-pytorch.sh --mode gpu`

### Low FPS

1. **Use smaller model**: yolo26n vs yolo26s
2. **Enable GPU**: Set `SMART_TRACKER_USE_GPU: true`
3. **Lower resolution** in config

### OSD Causes Choppy/Stretchy Video

**Symptom**: Video is smooth with OSD OFF, but choppy with OSD ON (common on Jetson Nano / low-power ARM).

**Check live OSD pipeline timings**:
```bash
curl -s http://127.0.0.1:5077/stats | jq '.osd_pipeline'
```

If `dynamic_render_ms_avg` is high (for example >80ms), tune OSD runtime:

```yaml
OSD:
  OSD_PERFORMANCE_MODE: "balanced"      # keeps quality by default
  OSD_AUTO_DEGRADE: true
  OSD_AUTO_DEGRADE_MIN_MODE: "fast"     # allows emergency fallback on weak hardware
  OSD_MAX_RENDER_BUDGET_MS: 25.0
  OSD_DYNAMIC_FPS: 6                     # lower dynamic redraw cadence on weak CPUs
  OSD_TARGET_LAYER_RESOLUTION: "stream"  # avoid rendering overlays at capture resolution
```

Then restart and recheck:
```bash
pixeagle-service restart
curl -s http://127.0.0.1:5077/stats | jq '.osd_pipeline'
```

## Service Issues

### Service Won't Start

```bash
# Check status
pixeagle-service status

# Check logs
pixeagle-service logs -n 200

# Reinstall command wrapper
sudo bash scripts/service/install.sh

# (Re)enable boot auto-start
sudo pixeagle-service enable
```

### Tmux Session Lost

```bash
# Inspect the ownership-aware runtime
make status
pixeagle-service status

# Reattach
make attach                  # manual runtime
pixeagle-service attach      # managed runtime

# If no session, restart the intended owner
make run                       # manual runtime
pixeagle-service start         # managed runtime
```

### Media Health In Service Status

`pixeagle-service status` includes a best-effort `Media health` block from the
typed process-local route:

```bash
pixeagle-service status
```

- `Backend media: auth required (HTTP 401/403; requires media:read)` means the
  service CLI was not authorized to read `/api/v1/streams/media-health`; it does
  not mean video is down.
- `Frame publisher: stale` means PixEagle has a published frame, but it is older
  than the configured media-health freshness window.
- `Frame publisher: none` means no local frame is currently available to the
  backend media transports.
- `Remote receipt: not proven by this process-local check` is expected. Use QGC,
  browser, WebRTC, SITL, HIL, or field-side evidence when claiming remote media
  receipt.

For `machine_bearer` or `browser_session` deployments, use an explicit
`media:read` bearer token file for this local probe:

```bash
PIXEAGLE_MEDIA_HEALTH_BEARER_TOKEN_FILE=/run/pixeagle/media-health-token \
  pixeagle-service status
```

Do not pass media credentials as query-string tokens.

## Firewall & Network Issues

### Check Port Status

```bash
# Check which ports are in use
sudo lsof -i :3040   # Dashboard
sudo lsof -i :5077   # Backend
sudo lsof -i :5551   # Legacy telemetry WebSocket
sudo lsof -i :8088   # MAVLink2REST
sudo lsof -i :14540  # MAVSDK
sudo lsof -i :14569  # MAVLink input
```

### Separately Secured Trusted/VPN Access

```bash
# Expose only the reviewed HTTPS reverse proxy, not the raw dashboard.
sudo ufw allow from <trusted-cidr> to any port 443 proto tcp

# Optional field GCS access only
sudo ufw allow 14550/udp  # QGC (optional)

# Verify rules
sudo ufw status
```

Keep `5077`, `5551`, `8088`, `14540`, and `14569` local by default. For a quick
browser demo from a phone/tablet/GCS on an isolated LAN or private overlay/VPN,
use `make demo-lan-browser-profile
LAN_HOST=<this-pixeagle-lan-ip-or-overlay-ip>` instead of hand-opening backend
ports; the profile generates browser-session credentials, exact Host/CORS
allowlists, and a backend bind for the browser API/media client on `5077`.
Allow both `3040` and `5077` only from the trusted demo CIDR/device. Use a
separately secured deployment only when production remote access is explicitly
required. For production remote browser access, keep `3040` local and follow
the [reverse-proxy runbook](setup/production-remote-reverse-proxy.md).

### Port Reference

| Port | Service | Protocol | Required |
|------|---------|----------|----------|
| 3040 | Dashboard | TCP | Yes |
| 5077 | Backend API | TCP | Yes |
| 5551 | Legacy telemetry WebSocket | TCP | Local/optional |
| 8088 | MAVLink2REST API | TCP | For telemetry |
| 14540 | MAVSDK | UDP | For PX4 |
| 14569 | MAVLink2REST input | UDP | For PX4 |
| 14550 | QGC | UDP | Optional |

## Windows-Specific Issues

### Python Not Found

**Problem**: `'python' is not recognized as an internal or external command`

**Solution**:
1. Install Python from [python.org](https://www.python.org/downloads/)
2. During installation, check **"Add Python to PATH"**
3. Restart Command Prompt

### Node.js Not Found

**Problem**: `'node' is not recognized...`

**Solution**:
1. Install Node.js from [nodejs.org](https://nodejs.org/en/download)
2. Restart Command Prompt

### Port Already In Use (Windows)

```cmd
# Find process using the port
netstat -ano | findstr :3040

# Kill the process (replace PID with actual number)
taskkill /PID 12345 /F
```

### Colors Not Displaying

**Problem**: ANSI color codes showing as text

**Solution**:
- Use Windows Terminal (recommended)
- Ensure Windows 10 version 1809 or later
- Colors are enabled automatically by the scripts

### Virtual Environment Issues (Windows)

**Problem**: venv activation fails

**Solution**:
```cmd
# Remove corrupted venv
rmdir /s /q venv

# Re-run init
scripts\init.bat
```

### npm Install Fails (Windows)

```cmd
cd dashboard
rmdir /s /q node_modules
del package-lock.json
npm ci
```

### Port Status Check (Windows)

```cmd
netstat -ano | findstr "3040 5077 8088 5551"
```

> **Full Windows Guide**: [Windows Setup Documentation](WINDOWS_SETUP.md)

## Getting Help

- [GitHub Issues](https://github.com/alireza787b/PixEagle/issues)
- [Documentation Index](README.md)
- [Windows Setup Guide](WINDOWS_SETUP.md)
- [YouTube Tutorials](https://www.youtube.com/playlist?list=PLVZvZdBQdm_4oain9--ClKioiZrq64-Ky)

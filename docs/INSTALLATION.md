# Installation Guide

> Detailed installation instructions for PixEagle

## Quick Installation

### Beginner Lab/Development One-Liner

**Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.sh | bash
```

This deliberately follows the mutable `main` branch. The installer prints the
resolved source commit, but this lane is only for a quick lab/development
checkout. Do not use it as production, Raspberry Pi acceptance, or release
provenance.

### Production/Raspberry Pi Exact-Commit Bootstrap

Obtain the reviewed 40-hex commit from the release or tester handoff. A branch,
tag name, or abbreviated commit is not accepted:

```bash
export PIXEAGLE_COMMIT='<reviewed-40-hex-commit>'
installer="$(mktemp)"
curl --proto '=https' --tlsv1.2 --fail --show-error --location \
  "https://raw.githubusercontent.com/alireza787b/PixEagle/${PIXEAGLE_COMMIT}/install.sh" \
  --output "$installer"
PIXEAGLE_COMMIT="$PIXEAGLE_COMMIT" bash "$installer"
rm -f "$installer"
git -C "$HOME/PixEagle" rev-parse HEAD
```

The installer fetches that exact commit into a private sibling directory,
verifies both `FETCH_HEAD` and detached checkout `HEAD`, and only then publishes
`~/PixEagle`. A mismatch, malformed pin, ambiguous branch-plus-commit request,
or destination race fails closed. The exact commit fixes source identity; it
does not by itself prove who approved the commit or replace dependency, host,
SITL/HIL, or field evidence.

### Manual Lab/Development Checkout

**Linux:**
```bash
git clone --depth 1 --branch main https://github.com/alireza787b/PixEagle.git
cd PixEagle
make init
```

This manual branch checkout has the same lab/development boundary as the
one-liner. Use the exact-commit bootstrap above for a production/RPi handoff.

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Debian-family Linux | Current 64-bit Ubuntu/Raspberry Pi OS |
| Python | 3.9 | 3.11+ |
| RAM | 4GB | 8GB+ |
| Disk | 2GB Core | 8GB+ Full; 10GB+ for optional OpenCV build |

### Supported Platforms

- **x86_64** - maintained Debian-family Linux bootstrap architecture
- **ARM64** - maintained bootstrap architecture; Raspberry Pi 5 is the first
  target-board handoff lane and still requires board-specific evidence
- **macOS/native Windows/ARMv7** - not maintained guided-bootstrap targets

Use WSL 2 or Debian-family Linux instead of the experimental native Windows
scripts. See [Native Windows Status](WINDOWS_SETUP.md).

## Prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip make tmux lsof curl git
```

## Init Script Steps

The `scripts/init.sh` (or `make init`) performs a 9-step setup:

1. **System Requirements** - Validates Python version, disk space
2. **System Packages** - Installs missing dependencies
3. **Python Virtual Environment** - Creates isolated venv
4. **Python Dependencies** - Installs role-based Core/AI requirements
5. **Node.js via nvm** - Verifies a commit-pinned nvm installer SHA-256, stages
   the exact nvm commit privately, then installs Node.js for the dashboard
6. **Dashboard Dependencies** - Runs lockfile-enforced `npm ci`
7. **Configuration Defaults** - Uses checked-in runtime defaults and creates
   dashboard `.env` when missing
8. **MAVSDK Server** - Downloads manifest-pinned platform binary with SHA-256 verification
9. **MAVLink2REST** - Downloads manifest-pinned REST API bridge with SHA-256 verification

At the end, init prints a component readiness summary. `ready` means the step
was completed or verified in this run, `skipped` means an optional/operator
choice was intentionally not performed, `degraded` means PixEagle continued but
that component needs attention, and `manual follow-up` means the guide gives the
next command to run before using that capability. Do not treat `make run` as
ready for a workflow until the relevant summary entries are ready.

### OpenCV + GStreamer Safety During Init

If the selected virtual environment already has one valid source/GStreamer
OpenCV provider, `make init` fingerprints and preserves it exactly. The managed
`opencv-contrib-python-headless` wheel is the normal companion-computer
non-GStreamer provider; one GUI contrib wheel is also accepted in an
intentionally customized desktop environment. Multiple owners, base-only
wheels, an unmanaged non-GStreamer import, or an in-place source-to-wheel
replacement request fail closed; create a fresh venv when changing provider
class.

### Full Profile AI Install Strategy

When you select **Full** profile, init uses a guarded Python dependency flow:

1. Install **core** packages first from `requirements-core.txt` (stable base)
2. Resolve/install PyTorch through `scripts/setup/setup-pytorch.sh --mode auto`
3. Install curated AI dependencies and the pinned, hash-verified Ultralytics
   wheel through `scripts/setup/install-ai-deps.sh`

NCNN/pnnx are explicit opt-ins with `install-ai-deps.sh --with-ncnn`. Full may
complete without a model; SmartTracker is ready only after the bounded runtime
checker loads a trusted local detect/OBB model. Setup takes an exact private
copy of an existing PixEagle venv and restores it if Core, PyTorch, AI, or final
verification fails. A successful transaction removes that copy. Host package
changes made through `apt` are outside the venv rollback boundary. See
[SmartTracker Model Setup](MODEL_SETUP.md).

When `--report-json` is requested, the destination is owner/type/write checked
before package mutation. Use an owner-controlled state path such as
`${XDG_STATE_HOME:-$HOME/.local/state}/pixeagle/setup-evidence/`; group/world-
writable path components are rejected. A rare publication failure after commit
is reported as `installed_evidence_failed`; the verified venv remains installed
and the terminal output explicitly says that rollback did not occur.

Manual AI recovery commands:

```bash
bash scripts/setup/setup-pytorch.sh --mode auto
bash scripts/setup/install-ai-deps.sh
bash scripts/setup/check-ai-runtime.sh
```

### Virtual Environment Selection

Fresh `make init` creates `.venv/`. Older checkouts may already use `venv/`.
PixEagle setup helpers use one resolver so optional commands do not silently
inspect the wrong Python environment:

1. `PIXEAGLE_VENV_DIR` when explicitly set, for example
   `export PIXEAGLE_VENV_DIR="$PWD/.venv"`
2. `.venv/` when it contains `bin/python`
3. `venv/` when it contains `bin/python`
4. `.venv/` as the canonical fresh-install path

`scripts/setup/check-ai-runtime.sh` prints the exact Python path it inspected
and reports PyTorch/YOLO/dlib modules, OpenCV version, OpenCV contrib tracker
APIs, and OpenCV GStreamer support.

## Manual Installation

If you prefer manual setup:

```bash
# Create virtual environment
python3 -m venv .venv
export PIXEAGLE_VENV_DIR="$PWD/.venv"
source "$PIXEAGLE_VENV_DIR/bin/activate"

# Install core Python dependencies first, matching scripts/init.sh.
# Full AI packages are installed later with the guarded AI setup scripts.
pip install -r requirements-core.txt

# Optional AI/YOLO support
bash scripts/setup/setup-pytorch.sh --mode auto
bash scripts/setup/install-ai-deps.sh

# Optional developer/test tooling
pip install -r requirements-dev.txt

# Install Node.js 22 through an operator-reviewed host mechanism, then dashboard deps.
# The maintained initializer instead downloads nvm to a temporary file, verifies its
# pinned SHA-256, stages the exact nvm Git commit, and publishes it only after verification.
node --version
npm --version
cd dashboard && npm ci
cd ..

# Optional: create dashboard env if init was skipped
"$PIXEAGLE_VENV_DIR/bin/python" - <<'PY'
import yaml
from pathlib import Path

source = Path("dashboard/env_default.yaml")
target = Path("dashboard/.env")
config = yaml.safe_load(source.read_text(encoding="utf-8"))
target.write_text(
    "".join(f"{key}={value}\n" for key, value in config.items()),
    encoding="utf-8",
)
PY
```

PixEagle can read checked-in defaults from `configs/config_default.yaml` when
`configs/config.yaml` is absent. Create `configs/config.yaml` only when the host
needs local overrides or an explicit setup profile. See
[Setup Profiles](setup/setup-profiles.md).

For field QGroundControl video on another device, keep the backend local and
apply the QGC video profile:

```bash
make qgc-video-profile GCS_HOST=<ground-station-ip>
```

For guarded direct QGC HTTPS/WSS media with a draft/test compatible QGC build:

```bash
make qgc-direct-media-profile PUBLIC_HOST=<tls-host>
```

This keeps PixEagle loopback, generates a hashed `media:read`-only bearer token
record, and writes an owner-only one-time QGC handoff. It still requires a
separately configured TLS reverse proxy and target receiver validation.

## Setup Choice Matrix

| Choice | Default Path | When To Select | Follow-up |
|--------|--------------|----------------|-----------|
| Core profile | Recommended default on every architecture | Demo, OpenCV tracking, dashboard, MAVSDK/MAVLink runtime without AI/YOLO | Add only required optional capabilities later |
| Full profile | Explicit opt-in | AI/YOLO dependencies and model tooling | Add a trusted detect/OBB model and run `check-ai-runtime.sh --require-smart-tracker` |
| Custom OpenCV + GStreamer | Optional, never forced | GStreamer input or QGC H.264/RTP/UDP output | Build and verify with the canonical scripts; init preserves it by default |
| dlib tracker | Optional manual step | Fast correlation-filter tracker experiments | `bash scripts/setup/install-dlib.sh` |
| Browser quick demo | Explicit admin demo command | Fast phone/tablet/PC demo on isolated LAN or private overlay; temporary public HTTP lab demos require explicit override and are not production remote access | `make quick-browser-demo LAN_HOST=<host>`; use `SESSION_ROLE=operator`/`viewer` to downgrade; cleanup with `CONFIRM=1 make quick-browser-demo-cleanup LAN_HOST=<host>`, which restores local-only config by default; add `CLOSE_FIREWALL=1` only when demo UFW rules were opened |
| Services | Opt-in only | Standalone deployment requiring boot auto-start | `PIXEAGLE_ENABLE_SERVICE_SETUP=1 make init` |
| MAVSDK/MAVLink2REST binaries | Guided by init | PX4/SITL/HIL/field integration | Review final summary and binary provenance before claiming readiness |

Browser-session users are managed offline through:

```bash
python3 scripts/setup/manage-browser-users.py --file <API_SESSION_USER_FILE> list
```

Use it for admin password resets, role changes, disabling old users, or adding
viewer/operator/admin users. It writes owner-only JSON and never stores
plaintext passwords in the runtime user file.

## Optional Components

### dlib Tracker

```bash
bash scripts/setup/install-dlib.sh
```

### GPU Support (PyTorch)

Use the deterministic installer:
```bash
bash scripts/setup/setup-pytorch.sh --mode auto
bash scripts/setup/check-ai-runtime.sh
```

Useful options:
- `--mode auto` - Resolve best profile automatically (recommended)
- `--mode gpu` - Require accelerated backend (fail if unavailable)
- `--mode cpu` - Force CPU-only profile
- `--dry-run` - Preview selected profile without installing

`check-ai-runtime.sh` does not install packages. It reports the selected venv,
OpenCV/dlib/PyTorch/Ultralytics/optional NCNN capabilities and performs a
bounded model-load probe when a local candidate exists. Use
`--require-smart-tracker` when readiness must be a hard gate.

### GStreamer Support

```bash
bash scripts/setup/build-opencv.sh
make check-gstreamer-runtime
```

The first command builds the optional OpenCV backend; the second verifies the
active venv plus required QGC UDP plugins. For the canonical contract, see
[OpenCV GStreamer Guide](OPENCV_GSTREAMER.md).

The automated builder defaults to a headless companion configuration and keeps
the current OpenCV usable until compilation and a complete staged install
succeed. It records and backs up every existing install-manifest destination
plus the previous native OpenCV include/library/CMake/pkg-config/share/tool
layout before changing the venv, then commits only after tracker, FFmpeg, and
observed GStreamer sink verification. Symlinked destination ancestors that
resolve outside the canonical selected venv fail before replacement. Use
`OPENCV_GUI=1 bash scripts/setup/build-opencv.sh` only for a host that needs
OpenCV GTK/OpenGL windows.

## Network Requirements

### Required Ports

Keep application ports local by default. PixEagle's checked-in backend policy
binds `127.0.0.1:5077` and fails startup when `local_only` configuration
requests non-loopback exposure. The current backend supports loopback local
compatibility, scoped machine bearer tokens, and explicit browser-session auth
from an external hashed user file. See the
[API exposure boundary](apis/api-exposure-boundary.md) before configuring any
remote operator path.

If upgrading from an older local `configs/config.yaml`, a missing exposure mode
with `HTTP_STREAM_HOST: 0.0.0.0` is coerced to loopback at runtime. For a quick
browser demo on another device, use `make demo-lan-browser-profile
LAN_HOST=<this-pixeagle-lan-ip-or-overlay-ip>` so setup generates credentials
and exact Host/CORS allowlists. Explicitly set `API_EXPOSURE_MODE:
trusted_lan_legacy` by hand only for reviewed temporary isolated-LAN or private
overlay/VPN compatibility.

| Port | Service | Required |
|------|---------|----------|
| 3040 | Dashboard | Loopback by default |
| 5077 | Backend API | Loopback by default |
| 5551 | Legacy telemetry WebSocket | Local/optional |
| 8088 | MAVLink2REST API | Local-only by default |
| 14540 | MAVSDK | Local endpoint for PX4 integration |
| 14569 | MAVLink2REST input | Local endpoint for PX4 integration |
| 14550 | QGC | Optional |
| 22 | SSH | For remote access |

### Separately Secured Remote Operator Path

```bash
# Example only after the guarded HTTPS reverse proxy is configured
sudo ufw allow from <trusted-cidr> to any port 443 proto tcp

# Optional field GCS access only from the trusted GCS device/CIDR
sudo ufw allow from <trusted-gcs-ip-or-cidr> to any port 14550 proto udp
```

Firewall source-IP/CIDR rules are the place to restrict which GCS devices can
reach a port. PixEagle's `Streaming.API_ALLOWED_HOSTS` validates the HTTP Host
authority used in the URL or reverse-proxy request; it is not a selected-GCS-IP
allowlist and does not disable PixEagle authentication.

For the `demo_lan_browser` profile only, add equivalently scoped TCP rules for
dashboard port `3040` and backend/API media port `5077`, limited to the trusted
demo device or CIDR. Do not add a broad backend rule.

Do not open backend port `5077` directly. `trusted_lan_legacy` only permits a
non-loopback bind/CORS boundary; backend requests still require scoped API
authorization or explicit browser-session auth. The `demo_lan_browser` profile
is the supported beginner exception: it intentionally makes `3040` and `5077`
reachable on the isolated LAN/private overlay so the browser dashboard can load
static assets and call the backend API/media endpoints. HTTP over a private LAN
or private overlay/VPN is acceptable only for that explicit lab/demo posture.
TLS is not domain-only. Production remote-browser setup should use
`make production-remote-profile PUBLIC_HOST=<tls-host>
SESSION_USER_FILE=<path>` or an equivalent reviewed config so PixEagle stays
loopback behind HTTPS/WSS; production handoff still requires proxy/firewall
evidence, credential handoff evidence, adversarial auth/media tests, and safety
evidence gates.
Do not open raw dashboard port `3040` for this profile. Follow the
[production remote reverse-proxy runbook](setup/production-remote-reverse-proxy.md)
and expose only its reviewed TLS listener.

Do not expose PixEagle backend `5077`, MAVLink2REST `8088`, local MAVLink
endpoints `14540`/`14569`, or MavlinkAnywhere dashboard `9070` beyond
localhost or an SSH tunnel unless an explicit network-security plan exists.
A reverse proxy does not make `local_compat` remote-safe; non-loopback backend
API clients need scoped bearer tokens or explicit browser-session auth.

## OpenCV Diagnostic

```bash
python src/test_Ver.py
```

This is a quick OpenCV version/build diagnostic, not a release or vehicle
readiness test.

### Maintainer Clean-Handoff Walkthrough

Before tagging a release or handing setup instructions to testers, run the
clean-checkout walkthrough from a clean worktree:

```bash
python3 tools/run_setup_handoff_walkthrough.py
```

The harness clones PixEagle to a temporary checkout, verifies required public
setup docs/files, runs documented setup profile dry-runs, previews the binary
download plan without downloading, checks the stopped-runtime updater preflight,
and runs the schema plus minimum backend/API tests. It writes an evidence manifest
under `docs/reporting/agent-ops/codex-modernization/evidence/`.

Optional heavier dashboard evidence can be added with:

```bash
python3 tools/run_setup_handoff_walkthrough.py --include-dashboard
```

The dashboard option runs `npm ci` in the temporary checkout and may fetch npm
package artifacts from the configured npm registry. This remains setup/update
evidence only: it does not install services, open firewall rules, download
MAVSDK/MAVLink2REST binaries, start PX4/SITL/HIL, prove QGC playback, or claim
field or real-aircraft readiness.

## Running PixEagle

**Linux (using Makefile):**
```bash
make run           # Run all services
make dev           # Development mode with hot-reload
make stop          # Stop all services
make update        # Stopped-runtime source + environment reconciliation
make reset-config  # Reset config files to defaults
make setup-profile # Apply an explicit setup profile
make qgc-video-profile GCS_HOST=<ip>  # Configure QGC field video
make qgc-direct-media-profile PUBLIC_HOST=<tls-host>  # Guarded QGC HTTPS/WSS media
make status        # Show service status
make help          # Show all commands
```

`make update` is the only maintained existing-checkout update command. It owns
the lifecycle, source, and selected virtual environment; refuses active
services, tmux runtimes, marked processes, and known runtime listeners; then
publishes only an exact fast-forward candidate and runs the selected Core/Full
reconciler. It does not stop or restart PixEagle. Before changing source it
privately stages the old checked-in defaults. Registered retirements still
require explicit admin preview/apply. See [Config Sync](CONFIG_SYNC.md).

For an existing branch checkout, rerunning `install.sh` delegates source and
environment reconciliation to `scripts/update.sh`; the bootstrap does not
implement a second merge path. The updater requires a stopped runtime, a clean
worktree, matching branch, and fast-forward-only source history. It refuses an
automatic update if it cannot obtain trustworthy runtime or Git state. If
reconciliation fails, it restores the prior source commit only when HEAD and
all tracked files still exactly match the updater's published candidate. It
never deletes ignored config, credentials, models, or evidence. Candidate
publication and rollback both refuse when a target commit would overwrite an
existing ignored or untracked path.

That existing-checkout updater remains branch-based and therefore mutable. Use
it for reviewed lab/development updates. A production/RPi update must start from
the exact commit supplied in its release/test handoff; install that commit into
a fresh path, validate it with the deployment's local configuration and
evidence, then perform an operator-controlled cutover. `PIXEAGLE_COMMIT` is
intentionally rejected for an existing checkout so it cannot be silently mixed
with branch update semantics.

**Linux (using scripts directly):**
```bash
bash scripts/run.sh          # Run all services
bash scripts/run.sh --dev    # Development mode
bash scripts/stop.sh         # Stop all services
```

## Native Windows

Native Windows scripts are retained only for contributor experiments and fail
closed unless `PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS=1` is set. They do not have
Linux lifecycle, dependency, media, or release-gate parity. Use WSL 2 or a
maintained Debian-family Linux host. See [Native Windows Status](WINDOWS_SETUP.md).

## Downloading Binaries

If you need to download MAVSDK and MAVLink2REST binaries separately:

**Linux:**
```bash
bash scripts/setup/download-binaries.sh --all --dry-run
bash scripts/setup/download-binaries.sh --all
bash scripts/setup/download-binaries.sh --mavsdk
bash scripts/setup/download-binaries.sh --mavlink2rest
```

Binaries are downloaded to the `bin/` directory only after SHA-256 verification
against `scripts/setup/binary-manifest.env`. Successful verified downloads
append provenance to `bin/binary-provenance.jsonl`; keep that file with SITL,
HIL, field, and tester handoff evidence. See the
[Binary Download Policy](setup/binary-download-policy.md) for pinned release
URLs, override variables, manual/offline placement, and unverified-lab limits.

## Service Management

### Standalone Installations

For standalone Linux deployments, normal `make init` skips service setup. Opt
into deployment prompts with:

```bash
PIXEAGLE_ENABLE_SERVICE_SETUP=1 make init
```

Those prompts default to **No** for:
- installing `pixeagle-service` CLI
- enabling boot auto-start
- enabling system-wide SSH login hints
- optional immediate service start and optional reboot validation

```bash
# Install command wrapper
sudo bash scripts/service/install.sh

# Manage runtime
pixeagle-service start
pixeagle-service stop
pixeagle-service status
pixeagle-service attach

# Manage boot auto-start
sudo pixeagle-service enable
sudo pixeagle-service disable

# Inspect logs
pixeagle-service logs -f
```

### Platform-Managed Installations (ARK-OS, etc.)

When installed through a platform like ARK-OS, service management is handled by the
platform. `make init` automatically skips standalone service setup in this case.

Use the platform's web UI or:

```bash
systemctl --user start pixeagle
systemctl --user stop pixeagle
systemctl --user status pixeagle
journalctl --user -u pixeagle -f
```

> **Note**: Standalone and platform-managed modes are mutually exclusive.
> PixEagle auto-detects and prevents conflicts between the two.

See [Service Management Runbook](SERVICE_MANAGEMENT.md) for full operational guidance.

## Next Steps

- [Configuration Guide](CONFIGURATION.md)
- [SmartTracker Model Setup](MODEL_SETUP.md)
- [SmartTracker Reference](trackers/02-reference/smart-tracker.md)
- [Native Windows Status](WINDOWS_SETUP.md)
- [Main README](../README.md)

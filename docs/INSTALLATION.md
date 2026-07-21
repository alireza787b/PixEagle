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

In an interactive terminal, select **Core** for the complete product runtime
without local AI packages or **Full AI** for Core plus PyTorch and Ultralytics.
Although the installer program arrives through a pipe, it detects the active
SSH or local terminal once and explicitly uses that terminal for every guided
choice. It prints `Interactive terminal detected` before cloning and then waits
at each prompt. Required setup does not start PixEagle; the final, separate
browser-lab choice starts the bundled-video runtime only when accepted.

Every prompt displays its Enter default. Pressing Enter throughout chooses
Core, installs the current-user `pixeagle` directory shortcut and standalone
service controls, and leaves dlib, OpenCV/GStreamer compilation, boot
auto-start, and SSH login hints disabled.

For a configured live camera/PX4 runtime:

```bash
cd ~/PixEagle
make run
```

For a bounded local verification with no drone:

```bash
cd ~/PixEagle
make demo
```

Open `http://127.0.0.1:3040`. This is the complete same-host verification path: it
uses the included looping video, classic tracking, and a local follower test.
It does not start MAVSDK Server or MAVLink2REST and cannot publish PX4 commands.

The installer asks before installing missing host packages and selecting Core
or Full AI dependencies. After required setup is ready, separate yes/no prompts
offer dlib, GStreamer-enabled OpenCV, the Bash `pixeagle` directory shortcut,
standalone service controls, boot auto-start, and SSH login hints. Every prompt
shows its Enter default. Resource-heavy builds, auto-start, and login hints are
never selected silently, and the summary lists the commands for adding them
later.

For a beginner, the interactive one-liner is the complete installation and
first lab run. Its final address choice starts the bundled-video demo: Enter
uses the listed default interface, while `l` keeps it on loopback. This does
not enable PX4 command dispatch or boot auto-start. Unattended installation
leaves the runtime stopped unless browser-lab startup is explicitly requested.
Full AI, a trusted model, GStreamer/OpenCV replacement, dlib, QGC networking,
and boot auto-start remain separate choices; they are not hidden Core
prerequisites.

If the optional Bash helper is installed, `pixeagle` is a directory helper, not
a lifecycle command. Use `pixeagle help`, then choose `make demo`/`make run` for
manual operation or `pixeagle-service start` for an installed standalone
service. `pixeagle-service enable` affects the next boot and intentionally does
not start the runtime in the current shell.

When no controlling terminal is available, prompts cannot be answered safely.
The installer uses Core, installs required/default components, skips optional
host mutations, and reports the override syntax. An unattended Full AI example
is:

```bash
curl -fsSL https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.sh \
  | PIXEAGLE_NONINTERACTIVE=1 PIXEAGLE_INSTALL_PROFILE=full bash
```

Optional unattended values are a comma-separated subset of `dlib`,
`gstreamer`, and `shell-shortcut` in `PIXEAGLE_OPTIONAL_COMPONENTS`. Standalone
service installation remains an explicit guided administrator action;
unattended setup never enables a service lifecycle implicitly.

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
| Python (Core) | 3.9 | A Python 3 series recorded in `pytorch_matrix.json`; the exact host is resolved and verified during setup |
| Python (Full AI) | Profile-specific | Current Linux CPU: 3.10-3.14 except 3.14.1; accelerator and target-board profiles define their own ranges |
| Node.js | 24.x | Installer-managed Node.js 24 LTS from `.nvmrc` |
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

The `scripts/init.sh` (or `make init`) performs a 10-step setup:

1. **System Requirements** - Validates Python version, disk space
2. **System Packages** - Installs missing dependencies
3. **Python Virtual Environment** - Creates isolated venv
4. **Python Dependencies** - Installs role-based Core/AI requirements
5. **Node.js via nvm** - Verifies a commit-pinned nvm installer SHA-256, stages
   the exact nvm commit privately, then installs Node.js for the dashboard
6. **Dashboard Dependencies** - Reuses a matching, fully validated dependency
   tree or runs lockfile-enforced `npm ci`
7. **Configuration Defaults** - Uses checked-in runtime defaults and creates
   dashboard `.env` when missing
8. **MAVSDK Server** - Downloads manifest-pinned platform binary with SHA-256 verification
9. **MAVLink2REST** - Downloads manifest-pinned REST API bridge with SHA-256 verification
10. **Optional Components** - Asks separate yes/no questions for dlib,
    OpenCV/GStreamer, a Bash directory shortcut, standalone service controls,
    boot auto-start, and SSH login hints. Each question displays its default.

The verified Python environment is committed before Node/dashboard setup. A
later Node, npm, configuration, or network failure therefore remains visible
and returns a non-zero status without discarding the already-valid Python
installation; rerunning `make init` resumes the missing work.

Setup does not trust a single stale "installed" marker. On every run it checks
the real venv, dependency manifests/tree, Node runtime, configuration, and
binary state. A matching dashboard cache is accepted only when `package.json`
and `package-lock.json` hashes match and an offline `npm ls --all` validates the
complete installed tree. Otherwise setup runs `npm ci`; npm intentionally
replaces `node_modules` during that clean reconciliation. An interrupted
`npm ci` never publishes the success fingerprint, so the next run repairs it.

Required Debian packages are installed with noninteractive `apt-get` only
after the guided or explicitly unattended profile choice. Package-list update
or install failures stop the initializer and preserve their real exit status;
setup does not continue against stale package metadata. If the installer is
run as root, it prints that the resulting checkout, venv, nvm tree, and runtime
are root-owned. A dedicated non-root account is recommended on companion
computers.

At the end, init prints a component readiness summary. `ready` means the step
was completed or verified in this run, `skipped` means an optional/operator
choice was intentionally not performed, `degraded` means PixEagle continued but
that component needs attention, and `manual follow-up` means the guide gives the
next command to run before using that capability. Do not treat `make demo` or `make run` as
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

### Optional Dependency Mutation Lifecycle

PyTorch, AI, dlib, and OpenCV/GStreamer installers need exclusive ownership of
the selected virtual environment. Use only the row matching the runtime owner;
do not delete lock files or run several stop commands speculatively.

| Runtime owner | Stop before mutation | Start after readiness checks |
|---------------|----------------------|------------------------------|
| Manual/quick lab runtime | `make stop` | Reuse the same reviewed `make run`, `scripts/run.sh`, or demo-profile launch command |
| Standalone system service | `pixeagle-service stop` | `pixeagle-service start` |
| Platform-managed user service | Platform control, or `systemctl --user stop pixeagle` | Platform control, or `systemctl --user start pixeagle` |

The normal beginner Core/Raspberry Pi path does not install a service, so its
manual Full upgrade uses `make stop`. Verify the matching runtime is stopped
before mutation and start it only after the relevant readiness command passes.
See [Service Management](SERVICE_MANAGEMENT.md) for deployment modes.

### Full Profile AI Install Strategy

When you select **Full** profile, init uses a guarded Python dependency flow:

1. Install **core** packages first from `requirements-core.txt` (stable base)
2. Resolve/install PyTorch through `scripts/setup/setup-pytorch.sh --mode auto`
3. Install curated AI dependencies and the pinned, hash-verified Ultralytics
   wheel through `scripts/setup/install-ai-deps.sh`

The same `scripts/setup/pytorch_matrix.json` policy is enforced by both
`make init` and the standalone PyTorch setup script. Python compatibility is
owned by each hardware profile instead of one global hard-coded range. The
current Linux CPU profile uses PyTorch 2.12.1 and torchvision 0.27.1 on CPython
3.10-3.14, excluding CPython 3.14.1. Compatibility CUDA profiles and Jetson
wheel contracts have narrower ranges recorded in that same file.

Automatic mode may select the reviewed CPU profile when the detected
accelerator profile does not support the active interpreter. If no supported
Full AI profile is compatible, interactive init offers to finish as Core before
unsupported AI package mutation; unattended Full setup fails closed and prints
the corrective environment variables. Experts who already maintain another
Python 3 interpreter can select it explicitly before a fresh venv is created:

```bash
PIXEAGLE_PYTHON=/usr/bin/python3.12 make init
```

Reruns prefer an already valid PixEagle virtual environment so interrupted
setup repairs do not silently replace its interpreter. Update compatibility by
reviewing the matrix and its policy tests, not by adding interpreter-specific
branches to the installer.

NCNN/pnnx are explicit opt-ins with `install-ai-deps.sh --with-ncnn`. Full may
complete without a model; SmartTracker is ready only after the bounded runtime
checker loads a trusted local detect/OBB model. Setup takes an exact private
copy of an existing PixEagle venv and restores it if Core, PyTorch, AI, or final
verification fails. A successful transaction removes that copy. Host package
changes made through `apt` are outside the venv rollback boundary. See
[SmartTracker Model Setup](MODEL_SETUP.md).

When `--report-json` is requested, the destination is owner/type/write checked
before package mutation. Use a dedicated owner-controlled path such as
`$HOME/pixeagle-setup-evidence/` and keep every ancestor non-writable by other
users. A shared or group-writable XDG state tree is intentionally rejected even
when its final child is mode `0700`. A rare publication failure after commit is
reported as `installed_evidence_failed`; the verified venv remains installed
and the terminal output explicitly says that rollback did not occur.

Manual AI recovery commands:

```bash
# Default no-service path; use the lifecycle table above for managed services.
make stop
bash scripts/setup/setup-pytorch.sh --mode auto
bash scripts/setup/install-ai-deps.sh
bash scripts/setup/check-ai-runtime.sh
```

The maintained PyTorch and AI installers do not retain pip download caches.
This reduces persistent disk use during the transactional Full install;
rerunning a failed network download may therefore fetch the package again.

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

# Install Node.js 24 through an operator-reviewed host mechanism, then dashboard deps.
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
| Core profile | Recommended default on every architecture | OpenCV tracking, dashboard, streaming, and optional PX4/MAVLink use without local AI/YOLO packages | Run the configured product with `make run`, or verify locally with `make demo` |
| Full profile | Explicit opt-in | AI/YOLO dependencies and model tooling | Add a trusted detect/OBB model and run `check-ai-runtime.sh --require-smart-tracker` |
| Custom OpenCV + GStreamer | Optional, never forced | GStreamer input or QGC H.264/RTP/UDP output | Build and verify with the canonical scripts; init preserves it by default |
| dlib tracker | Optional manual step | Fast correlation-filter tracker experiments | `bash scripts/setup/install-dlib.sh` |
| Bash `pixeagle` shortcut | Guided default Yes; current-user profile only | Quickly change to the installed project directory; `pixeagle help` shows explicit start commands | Accept its prompt, or run `bash scripts/setup/install-shell-shortcut.sh`; remove with `--remove` |
| Browser quick demo | Final one-line-installer choice, or explicit command | Select a listed interface address, press Enter for the primary route and `admin/admin`, enter `l` for loopback, or `c` for a custom address; a public IP is labeled temporary plain HTTP | Accept the final bootstrap prompt, or run `make quick-browser-demo LAN_HOST=<host>`; use `DEMO_CREDENTIAL_MODE=generated` for a one-time password; use the printed cleanup command, including `CLOSE_FIREWALL=1`, to remove demo UFW rules |
| Service controls | Guided default Yes; runtime remains stopped | Install `pixeagle-service` without silently enabling boot or SSH-login behavior | Accept the service-controls prompt, or run `sudo bash scripts/service/install.sh` later; auto-start and login hints remain separate default-No prompts |
| MAVSDK/MAVLink2REST binaries | Guided by init | PX4/SITL/HIL/field integration | Review final summary and binary provenance before claiming readiness |

Fresh setup retains the checked-in local-only policy until the operator accepts
the final browser-lab prompt. That explicit path requests dashboard credentials,
uses `admin/admin` when Enter is pressed, opens host UFW rules for `3040` and
`5077` when UFW is active, and starts the bundled-video runtime. Existing local
configuration and credentials are preserved by update/repair; rerunning a demo
profile remains an explicit credential-rotation action.

Signed-in users can select their account chip in the dashboard header to change
their own password. An admin also receives a **Users** tab for creating,
disabling, re-enabling, re-roling, resetting, and deleting browser accounts.
Those dashboard changes are persisted atomically and take effect in the running
process; role, enablement, password-reset, and delete changes revoke the target
user's active sessions.

Shell access remains the break-glass path through:

```bash
python3 scripts/setup/manage-browser-users.py --file <API_SESSION_USER_FILE> list
```

Use it when the dashboard is unavailable or no admin can sign in. It writes
owner-only JSON and never stores plaintext passwords in the runtime user file.
Restart PixEagle after an offline edit when immediate runtime enforcement is
required.

## Optional Components

Before any installer below mutates the selected venv, stop and later restart
only the matching runtime from the optional dependency lifecycle table. The
default no-service path uses `make stop`; run the component's readiness check
before restarting.

### dlib Tracker

```bash
bash scripts/setup/install-dlib.sh
```

### Bash Directory Shortcut

```bash
bash scripts/setup/install-shell-shortcut.sh
```

This adds one marked, idempotent alias block to the current user's `.bashrc`.
Running `pixeagle` changes the current shell to this checkout; it does not start
the runtime or install a service. Remove only that managed block with:

```bash
bash scripts/setup/install-shell-shortcut.sh --remove
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

Stop the matching runtime using the optional dependency lifecycle table above.
For the default no-service path:

```bash
make stop
bash scripts/setup/build-opencv.sh
make check-gstreamer-runtime
```

After verification, restart only through the same runtime owner used before the
build. The canonical build contract is in
[OpenCV GStreamer Guide](OPENCV_GSTREAMER.md).

The first command builds the optional OpenCV backend; the second verifies the
active venv plus required QGC UDP plugins.

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

### Connect PX4 After Installation

The installer downloads and verifies PixEagle's MAVSDK Server and MAVLink2REST
binaries. It does not select the flight-controller UART, radio, Ethernet, or
SITL source and does not install a MAVLink router.

For the default runtime, route the same PX4 MAVLink stream to both local UDP
consumers:

```text
127.0.0.1:14540  PixEagle MAVSDK vehicle link
127.0.0.1:14569  PixEagle MAVLink2REST vehicle link
```

Use MavlinkAnywhere for the guided Raspberry Pi/Jetson/Linux path, or configure
`mavlink-router` directly as an advanced operator. Follow the
[PX4 and MAVLink connectivity guide](drone-interface/04-infrastructure/port-configuration.md)
for source selection, commands, port ownership, and verification. Do not send
vehicle MAVLink to `50051` or `8088`; those are local gRPC/HTTP service ports.

### Required Ports

Keep browser/API and telemetry-bridge ports local outside an explicit browser
lab or reviewed production boundary. PixEagle's checked-in backend policy binds
`127.0.0.1:5077` and fails startup when `local_only` configuration
requests non-loopback exposure. The current backend supports loopback local
compatibility, scoped machine bearer tokens, and explicit browser-session auth
from an external hashed user file. See the
[API exposure boundary](apis/api-exposure-boundary.md) before configuring any
remote operator path.

If upgrading from an older local `configs/config.yaml`, a missing exposure mode
with `HTTP_STREAM_HOST: 0.0.0.0` is coerced to loopback at runtime. For a quick
browser demo on another device, use `make demo-lan-browser-profile
LAN_HOST=<this-pixeagle-lan-ip-or-overlay-ip>` so setup asks for credentials
(Enter keeps admin/admin) and creates exact Host/CORS allowlists. Explicitly set `API_EXPOSURE_MODE:
trusted_lan_legacy` by hand only for reviewed temporary isolated-LAN or private
overlay/VPN compatibility.

In the one-line guided installer, pressing Enter at the dashboard-address prompt
selects a requested host when one was supplied; otherwise it selects the
primary-route device address. The generated browser-lab profile binds internally
to `0.0.0.0`, while the final handoff prints the real device IP or hostname to
open. `0.0.0.0` is a bind wildcard, not a browser URL. Select `l` when local-only
`127.0.0.1` access is preferred.

The browser-lab helper opens only dashboard `3040/tcp` and backend
`5077/tcp`. It does not open vehicle ingress, MAVLink2REST, or MAVSDK gRPC
ports. The pinned upstream MAVSDK Server nevertheless listens on
`0.0.0.0:50051`; block `50051/tcp` on untrusted interfaces. The canonical
[PX4 and MAVLink connectivity guide](drone-interface/04-infrastructure/port-configuration.md)
owns the complete port inventory and firewall guidance.

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

For the `demo_lan_browser` profile, add equivalently scoped TCP rules for
dashboard port `3040` and backend/API media port `5077`, limited to the trusted
demo device or CIDR whenever possible. The explicit temporary public-IP
override may open both ports broadly; it prints that credentials cross plain
HTTP and must be removed after the bench test.

Outside the explicit temporary browser-lab profile, do not open backend port
`5077` directly. `trusted_lan_legacy` only permits a non-loopback bind/CORS
boundary; backend requests still require scoped API
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

Do not expose PixEagle backend `5077`, MAVSDK gRPC `50051`, MAVLink2REST
`8088`, local MAVLink endpoints `14540`/`14569`, or MavlinkAnywhere dashboard
`9070` beyond the documented boundary unless an explicit network-security plan
exists.
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
.venv/bin/python tools/run_setup_handoff_walkthrough.py
```

The harness clones PixEagle to a temporary checkout, verifies required public
setup docs/files, runs documented setup profile dry-runs, previews the binary
download plan without downloading, checks the stopped-runtime updater preflight,
and runs the schema plus minimum backend/API tests. It writes an evidence manifest
under `docs/reporting/agent-ops/codex-modernization/evidence/`.

Optional heavier dashboard evidence can be added with:

```bash
.venv/bin/python tools/run_setup_handoff_walkthrough.py --include-dashboard
```

The dashboard option runs `npm ci` in the temporary checkout and may fetch npm
package artifacts from the configured npm registry. This remains setup/update
evidence only: it does not install services, open firewall rules, download
MAVSDK/MAVLink2REST binaries, start PX4/SITL/HIL, prove QGC playback, or claim
field or real-aircraft readiness. If `.venv` is absent, complete the Core
installer first. The walkthrough runs import-dependent checks with the project
environment even though its source checkout is temporary and clean.

## Running PixEagle

**Linux (using Makefile):**
```bash
make run           # Start the manual runtime
make dev           # Development mode with hot-reload
make stop          # Stop the manual runtime
make repair        # Verify/repair current source; preserve operator data
make update        # Stopped-runtime source + environment reconciliation
make reset-config  # Reset config files to defaults
make setup-profile # Apply an explicit setup profile
make qgc-video-profile GCS_HOST=<ip>  # Configure QGC field video
make qgc-direct-media-profile PUBLIC_HOST=<tls-host>  # Guarded QGC HTTPS/WSS media
make status        # Show manual runtime status
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

`make repair` runs the same profile reconciler against the current source
without fetching Git. It is the direct recovery command after an interrupted
dependency/setup run. The one-line installer uses `make update` semantics for
an existing branch checkout, so it updates and repairs in one guarded action.
Both paths preserve ignored operator data and reuse verified components.

These maintenance commands have deliberately narrow meanings:

| Intent | Command | Data behavior |
|--------|---------|---------------|
| Resume or repair current source | `make repair` | Preserves operator data and source revision |
| Update and repair | `make update` | Fast-forward only; preserves operator data |
| Remove generated build/cache output | `make clean` | Preserves venv, `node_modules`, config, credentials, models, recordings, logs, evidence |
| Reset runtime config | `make reset-config` | Creates a timestamped config backup; does not reinstall |
| Isolated clean install | Set a new `PIXEAGLE_HOME` | Leaves the existing installation untouched for validation/cutover |

The beginner installer intentionally has no destructive full-reset choice. A
production clean replacement belongs in a new exact-commit directory followed
by explicit validation and operator-controlled cutover.

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
bash scripts/stop.sh         # Stop the manual runtime
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

Interactive `make init` offers standalone service onboarding only after the
source/environment transaction and its locks have been released. Installing
the `pixeagle-service` CLI defaults to **Yes**; enabling boot auto-start and
system-wide SSH login hints are separate prompts that default to **No**.

Onboarding does not start PixEagle or reboot the host. The one-line installer
offers the separate browser lab next; configured deployments start explicitly
with `pixeagle-service start` after reviewing their source/PX4 settings.

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

# Remove the managed unit (also stops it)
sudo pixeagle-service uninstall

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

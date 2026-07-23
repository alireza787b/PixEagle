# Service Management Runbook

Operations guide for the maintained Debian-family Linux/systemd runtime on
x86_64 or ARM64. A target board still requires its own setup and runtime
evidence before deployment.

## Service Modes

PixEagle supports two mutually exclusive service modes:

| Mode | Service Level | Managed By | When Used |
|------|--------------|------------|-----------|
| **Standalone** | System (`/etc/systemd/system/`) | `pixeagle-service` CLI | Reviewed Debian-family systemd host |
| **Platform-managed** | User (`~/.config/systemd/user/`) | Platform (e.g., ARK-OS) | Installed through a platform |

PixEagle auto-detects the active mode:
- interactive `make init` offers standalone service setup after the setup lock
  is released; controls default to Yes, while boot and SSH hints default to No
- `make init` skips standalone service setup when running non-interactively (platform install)
- `make init` skips standalone service setup when a user-level service already exists
- standalone service installation refuses a conflicting platform-owned user service
- Platform installers automatically disable any pre-existing standalone service

**If you're using ARK-OS or another platform**, skip this guide and use the platform's
web UI or `systemctl --user {start|stop|status} pixeagle` instead.

## Architecture (Standalone Mode)

- `systemd` controls lifecycle and restart policy (`pixeagle.service`)
- `scripts/service/run.sh` is the systemd supervisor
- `scripts/run.sh --no-attach` launches PixEagle components in tmux
- canonical tmux session name: `pixeagle`
- `pixeagle-service` is the management CLI

Manual (`make demo`, `make run`, or the one-line browser lab) and managed
(`pixeagle-service start`) runtimes are separate ownership modes and cannot use
the same configured ports concurrently. The CLI identifies the other PixEagle
mode before starting; it never stops or replaces it implicitly.

## Install

Install the command and a disabled managed unit:

```bash
sudo bash scripts/service/install.sh
```

This installs `/usr/local/bin/pixeagle-service`, creates and validates
`/etc/systemd/system/pixeagle.service`, and leaves both the current runtime and
boot policy unchanged. On a fresh host, boot auto-start remains disabled.

The wrapper is bound to this checkout. After a source update, refresh and
validate the unit without changing runtime or boot state:

```bash
sudo pixeagle-service install
```

The interactive post-setup deployment prompts cover:
- installing `pixeagle-service`
- enabling boot auto-start
- enabling SSH login hint
- displaying the explicit start/status/log commands

Service onboarding never starts a runtime or reboots the host. Start explicitly
after the setup summary completes:

```bash
pixeagle-service start
```

This start works with boot auto-start disabled. The one-line installer may then
start its separate manual browser lab; its final summary says so. Keep that
runtime, or stop it with `make stop` before starting managed mode.

## Daily Operations

Start/stop/restart:

```bash
pixeagle-service start
pixeagle-service stop
pixeagle-service restart
```

`pixeagle-service start`/`stop` control the current managed runtime.
`pixeagle-service enable`/`disable` control only boot auto-start and retain the
current runtime. Use
`pixeagle-service uninstall` only to stop and remove the managed unit. Use
`sudo pixeagle-service install` to install or refresh the unit without changing
either state.
An explicit `start` or `restart` clears the prior systemd failure budget before
making that new operator request; automatic `Restart=on-failure` attempts remain
bounded by the generated unit's start-limit policy.
The CLI queues the systemd job and prints readiness progress every five seconds
for up to five minutes, including the current systemd state. `Ctrl+C` stops only
the CLI wait; it does not pretend the queued systemd job was cancelled. Check
`pixeagle-service status` and `pixeagle-service logs -f` after an interrupted
wait.
Without the managed service, run an attached
manual runtime with `cd ~/PixEagle && make run`, or a background manual runtime
with `cd ~/PixEagle && bash scripts/run.sh --no-attach`.

To switch from a browser lab/manual runtime to managed mode:

```bash
cd ~/PixEagle && make stop
pixeagle-service start
```

Startup readiness covers the dashboard, backend, and MAVLink2REST listeners,
plus the exact supervised tmux component contract. MAVSDK Server is supervised
as a live process, but its gRPC listener may remain unavailable while it waits
for a PX4 vehicle on the configured MAVLink endpoint. That is a normal
no-PX4/lab state; vehicle discovery and telemetry readiness remain separate
fail-closed application checks and are not implied by service startup.

Inspect status:

```bash
pixeagle-service status
```

Status output includes service/tmux/port checks and a best-effort `Media
health` block from `GET /api/v1/streams/media-health`. With the default
same-host `local_compat` profile this probe uses loopback without credentials.
The legacy telemetry WebSocket on port `5551` is optional and is reported as
such when absent; dashboard video and current backend WebSocket routes use the
backend listener instead.
For `machine_bearer` or `browser_session` deployments, provide an explicit
`media:read` bearer token file for the status probe:

```bash
PIXEAGLE_MEDIA_HEALTH_BEARER_TOKEN_FILE=/run/pixeagle/media-health-token \
  pixeagle-service status
```

The probe never uses query-string tokens, browser cookies, or CLI login. `401`
or `403` means media-health auth is required, not that video is down. The block
is process-local backend observability only; it does not prove a remote browser,
QGC, WebRTC peer, GCS, PX4, SITL, HIL, or field video path received usable
media.

Inspect logs (journald):

```bash
pixeagle-service logs -f
pixeagle-service logs -n 200
```

Attach to tmux:

```bash
pixeagle-service attach
```

Detach without stopping: `Ctrl+B`, then `D`.

## Boot Auto-Start

Enable at boot:

```bash
sudo pixeagle-service enable
```

Disable boot auto-start:

```bash
sudo pixeagle-service disable
```

The systemd unit is generated at:

```bash
/etc/systemd/system/pixeagle.service
```

Recommended first-time validation after enabling auto-start:

```bash
sudo reboot
# after reconnect:
pixeagle-service status
```

## Optional SSH Login Hint

Two scopes are supported:

- `--user` (default): only current/default service user
- `--system`: all users on the board (recommended for shared embedded devices)

Enable for all users:

```bash
sudo pixeagle-service login-hint enable --system
```

Open a new SSH session after changing hint scope to verify output.

System-scope hint output includes:
- PixEagle ASCII banner
- host + service + boot state
- loopback dashboard/backend URLs and an SSH tunnel example
- git metadata (repo path, branch, commit, commit date, origin)
- quick service command references

If output still shows an older short hint format after code update, regenerate:

```bash
sudo pixeagle-service login-hint disable --system
sudo pixeagle-service login-hint enable --system
```

Disable for all users:

```bash
sudo pixeagle-service login-hint disable --system
```

Enable only for current/default user:

```bash
pixeagle-service login-hint enable --user
```

Check status by scope:

```bash
pixeagle-service login-hint status --user
pixeagle-service login-hint status --system
```

## Updates and Maintenance

With PixEagle already stopped, update source and reconcile the selected setup
profile:

```bash
pixeagle-service update
pixeagle-service update --remote upstream --branch develop
```

`pixeagle-service update` and `make update` use the same updater. It does not
stop or restart PixEagle, stash local work, delete ignored operator data, or
create merge commits. If the checkout has local edits or the remote branch has
diverged, the update stops with recovery guidance. Commit or stash local edits
yourself, resolve divergence deliberately, then rerun the update. A candidate
or rollback that would replace ignored/untracked operator data is also refused.
If source was already changed with an external `git pull`, keep PixEagle
stopped and run `make repair` from the checkout instead; then start the desired
manual or managed runtime explicitly.

Before a handoff or release after updating, run the relevant validation gates:

```bash
bash scripts/check_schema.sh
PYTHONPATH=src python -m pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -q
cd dashboard && npm test -- --runInBand --watchAll=false && CI=true npm run build
```

Reset config files to defaults (creates timestamped backups):

```bash
pixeagle-service reset-config
```

The maintenance commands are also available via Makefile:

```bash
make update
make reset-config
```

## Recovery Patterns

Service inactive after boot:

```bash
pixeagle-service status
pixeagle-service logs -n 200
sudo systemctl restart pixeagle.service
```

For the pre-beta.15 ownership-marker failure, do not delete the virtual
environment or operator data. Update the checkout, regenerate the unit, and
start it explicitly:

```bash
cd /path/to/PixEagle
pixeagle-service update
sudo pixeagle-service install
pixeagle-service start
pixeagle-service status
```

tmux session missing while service is active:

```bash
pixeagle-service logs -n 200
sudo systemctl restart pixeagle.service
```

Need full reinstall of management layer:

```bash
sudo bash scripts/service/install.sh uninstall
sudo bash scripts/service/install.sh
# Optional next-boot policy:
sudo pixeagle-service enable
```

## Uninstall

Remove wrapper and systemd unit:

```bash
sudo bash scripts/service/install.sh uninstall
```

Uninstall queries and verifies the unit's load, active, and enabled states
before deleting the unit or wrapper. If systemd state cannot be determined, it
fails closed and leaves both paths in place for inspection.

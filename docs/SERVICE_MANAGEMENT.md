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
- `make init` skips standalone service setup by default; use
  `PIXEAGLE_ENABLE_SERVICE_SETUP=1 make init` for deployment prompts
- `make init` skips standalone service setup when running non-interactively (platform install)
- `make init` skips standalone service setup when a user-level service already exists
- `pixeagle-service enable` refuses to create a system-level service if a user-level one exists
- Platform installers automatically disable any pre-existing standalone service

**If you're using ARK-OS or another platform**, skip this guide and use the platform's
web UI or `systemctl --user {start|stop|status} pixeagle` instead.

## Architecture (Standalone Mode)

- `systemd` controls lifecycle and restart policy (`pixeagle.service`)
- `scripts/service/run.sh` is the systemd supervisor
- `scripts/run.sh --no-attach` launches PixEagle components in tmux
- canonical tmux session name: `pixeagle`
- `pixeagle-service` is the management CLI

## Install

Install the command wrapper:

```bash
sudo bash scripts/service/install.sh
```

This installs `/usr/local/bin/pixeagle-service` and points it to this repo.

The wrapper is bound to this checkout. After a source update, run the wrapper's
`enable` command once to regenerate and validate the unit before starting it;
the runtime launcher still performs the ownership and readiness checks.

Normal `make init` skips standalone service setup. For a deployment host, run
the installer directly or opt into guided service prompts:

```bash
PIXEAGLE_ENABLE_SERVICE_SETUP=1 make init
```

The deployment prompts cover:
- installing `pixeagle-service`
- enabling boot auto-start
- enabling SSH login hint
- optional immediate start and optional reboot validation

During `pixeagle-service update` reconciliation, the setup transaction may
install or enable the service command but deliberately defers starting the
runtime and rebooting. The updater owns the source, environment, and
configuration transaction until it has verified the result. Start explicitly
after the update summary completes:

```bash
pixeagle-service start
```

For first-time deployment setup, choose only the service actions you intend to
enable, then reconnect once after init to confirm the SSH startup guide output
if login hints were enabled.

## Daily Operations

Start/stop/restart:

```bash
pixeagle-service start
pixeagle-service stop
pixeagle-service restart
```

`pixeagle-service enable` controls boot auto-start; it intentionally does not
start the process immediately. `pixeagle-service disable` retains the unit and
any currently running process while disabling the next boot. Use
`pixeagle-service uninstall` only to stop and remove the managed unit. Use
`pixeagle-service start` after enabling when the runtime should start now.
An explicit `start` or `restart` clears the prior systemd failure budget before
making that new operator request; automatic `Restart=on-failure` attempts remain
bounded by the generated unit's start-limit policy.
Without the managed service, run an attached
manual runtime with `cd ~/PixEagle && make run`, or a background manual runtime
with `cd ~/PixEagle && bash scripts/run.sh --no-attach`.

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
sudo pixeagle-service enable
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

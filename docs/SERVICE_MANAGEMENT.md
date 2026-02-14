# Service Management Runbook

Production operations guide for running PixEagle on Linux/systemd platforms
(Raspberry Pi, Jetson, and similar embedded Linux systems).

## Service Modes

PixEagle supports two mutually exclusive service modes:

| Mode | Service Level | Managed By | When Used |
|------|--------------|------------|-----------|
| **Standalone** | System (`/etc/systemd/system/`) | `pixeagle-service` CLI | Direct installs on any Linux |
| **Platform-managed** | User (`~/.config/systemd/user/`) | Platform (e.g., ARK-OS) | Installed through a platform |

PixEagle auto-detects the active mode:
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

If you run `make init`, PixEagle will also walk you through:
- installing `pixeagle-service`
- enabling boot auto-start
- enabling SSH login hint
- optional immediate start and optional reboot validation

For first-time setup, accept the guided defaults, then reconnect once after init
to confirm the SSH startup guide output.

## Daily Operations

Start/stop/restart:

```bash
pixeagle-service start
pixeagle-service stop
pixeagle-service restart
```

Inspect status:

```bash
pixeagle-service status
```

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
- dashboard/backend URLs for each detected IPv4 interface
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

Pull latest upstream changes (auto-stashes local edits, quiet output):

```bash
pixeagle-service sync
pixeagle-service sync --remote upstream --branch develop
```

Reset config files to defaults (creates timestamped backups):

```bash
pixeagle-service reset-config
```

Both commands are also available via Makefile:

```bash
make sync
make reset-config
```

## Recovery Patterns

Service inactive after boot:

```bash
pixeagle-service status
pixeagle-service logs -n 200
sudo systemctl restart pixeagle.service
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

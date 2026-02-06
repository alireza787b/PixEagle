# Service Management Runbook

Production operations guide for running PixEagle on Linux/systemd platforms
(Raspberry Pi, Jetson, and similar embedded Linux systems).

## Architecture

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

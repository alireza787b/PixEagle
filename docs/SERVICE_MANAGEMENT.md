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

## Optional SSH Login Hint

Enable compact status/help on interactive SSH login:

```bash
pixeagle-service login-hint enable
```

Disable:

```bash
pixeagle-service login-hint disable
```

Check status:

```bash
pixeagle-service login-hint status
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


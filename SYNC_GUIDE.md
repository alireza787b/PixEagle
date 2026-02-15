# PixEagle Sync & Restart Guide

Quick reference for updating PixEagle in different installation scenarios.

---

## TL;DR - One Command for Everything

```bash
make sync-restart
```

This command:
- ✅ Pulls latest code from GitHub
- ✅ Auto-detects installation type (native vs ARK-OS)
- ✅ Restarts services appropriately
- ✅ Works on local dev machine and remote Jetson/Pi

---

## Installation Scenarios

### Scenario 1: Native/Standalone Installation

**On your local dev machine:**

```bash
# Pull latest code + restart
make sync-restart

# OR manually:
make sync          # Pull latest code
make stop          # Stop services
make run           # Start services
```

**If installed as systemd service:**

```bash
make sync-restart

# OR manually:
make sync
sudo systemctl restart pixeagle
```

---

### Scenario 2: ARK-OS Managed Installation (Jetson/Pi)

**Quick sync + restart:**

```bash
# SSH to Jetson
ssh jetson@192.168.1.112

# One command to sync and restart
cd ~/PixEagle
make sync-restart
```

**Manual method (if you prefer step-by-step):**

```bash
ssh jetson@192.168.1.112

# Pull latest code
cd ~/PixEagle
make sync

# Restart service
systemctl --user restart pixeagle

# Check status
systemctl --user status pixeagle
journalctl --user -u pixeagle -f
```

**Full reinstall (safest, rebuilds everything):**

```bash
ssh jetson@192.168.1.112

# Reinstall via ARK-OS install script
cd ~/ARK-OS
export INSTALL_PIXEAGLE="y"
bash tools/service_control.sh install pixeagle

# This does:
# - git pull origin main
# - Creates .env.production.local for proxy
# - Runs full init.sh (rebuilds dashboard, downloads models, etc.)
# - Restarts service
```

---

## What Each Command Does

| Command | What It Does | When to Use |
|---------|--------------|-------------|
| `make sync` | Pulls latest code from GitHub (auto-stashes local changes) | Just update code, don't restart yet |
| `make sync-restart` | Pulls code + auto-detects installation type + restarts services | **Recommended** - safest one-liner |
| `systemctl --user restart pixeagle` | Restart ARK-OS managed service | Quick restart without pulling code |
| `service_control.sh install pixeagle` | Full reinstall (git pull + rebuild + restart) | Major updates or troubleshooting |

---

## Troubleshooting

### Service won't start after sync

```bash
# Check logs
journalctl --user -u pixeagle -n 50

# Full reinstall
cd ~/ARK-OS
export INSTALL_PIXEAGLE="y"
bash tools/service_control.sh install pixeagle
```

### Local changes conflict with sync

```bash
# make sync auto-stashes changes, but if you want to manually handle:
git stash           # Save local changes
make sync           # Pull updates
git stash pop       # Restore local changes
```

### Permission issues on Jetson

```bash
# Fix script permissions
chmod +x ~/PixEagle/scripts/**/*.sh
```

---

## Testing Without Breaking Production

### On Jetson (test before committing)

```bash
# Make local changes
cd ~/PixEagle
# ... edit files ...

# Test without pushing to GitHub
systemctl --user restart pixeagle
journalctl --user -u pixeagle -f

# If it works, commit + push
git add .
git commit -m "your changes"
git push origin main
```

### On dev machine (safe testing)

```bash
# Make changes
cd c:/Users/Alireza/PixEagle
# ... edit files ...

# Test locally
make stop
make run

# If it works, commit + push
git add .
git commit -m "your changes"
git push origin main

# Then sync on Jetson
ssh jetson@192.168.1.112
cd ~/PixEagle && make sync-restart
```

---

## Summary

**For most updates:**
```bash
make sync-restart
```

**For major changes or troubleshooting:**
```bash
cd ~/ARK-OS
export INSTALL_PIXEAGLE="y"
bash tools/service_control.sh install pixeagle
```

**Both methods work for native and ARK-OS installations without breaking anything.**

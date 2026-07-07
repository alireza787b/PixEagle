#!/bin/bash
# ============================================================================
# PixEagle Sync & Restart - Works for both Native and ARK-OS installations
# ============================================================================
# Fast-forwards the current checkout when clean, then restarts services
# appropriately.
#
# Usage:
#   bash scripts/service/sync_and_restart.sh
#   make sync-restart  (if added to Makefile)
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PixEagle Sync & Restart"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Step 1: Sync code
echo "→ Syncing code (clean worktree, fetch, fast-forward only)..."
make sync || { echo "ERROR: Sync failed"; exit 1; }
echo "→ Recommended validation before handoff:"
echo "  bash scripts/check_schema.sh"
echo "  PYTHONPATH=src python -m pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -q"

# Step 2: Detect installation type and restart
if systemctl --user is-active pixeagle.service >/dev/null 2>&1; then
    # ARK-OS managed service (or native systemd service)
    echo ""
    echo "→ Detected systemd service - restarting..."
    systemctl --user restart pixeagle
    sleep 2

    if systemctl --user is-active pixeagle.service >/dev/null 2>&1; then
        echo "✓ Service restarted successfully"
        echo ""
        echo "  Status:  systemctl --user status pixeagle"
        echo "  Logs:    journalctl --user -u pixeagle -f"
    else
        echo "✗ Service failed to start - check logs:"
        echo "  journalctl --user -u pixeagle -n 50"
        exit 1
    fi

elif tmux has-session -t pixeagle 2>/dev/null; then
    # Native tmux-based installation
    echo ""
    echo "→ Detected tmux session - restarting..."
    make stop
    sleep 1
    make run

    if tmux has-session -t pixeagle 2>/dev/null; then
        echo "✓ Services restarted successfully"
        echo ""
        echo "  Attach:  make attach"
        echo "  Logs:    make logs"
    else
        echo "✗ Services failed to start"
        exit 1
    fi

else
    # Not currently running
    echo ""
    echo "⚠ PixEagle is not currently running"
    echo ""
    echo "To start:"
    echo "  Native:  make run"
    echo "  Service: systemctl --user start pixeagle"
    echo ""
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

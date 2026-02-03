#!/bin/bash

# ============================================================================
# scripts/stop.sh - Stop All PixEagle Services
# ============================================================================
# Gracefully stops all PixEagle services.
#
# Usage:
#   make stop                    (recommended)
#   bash scripts/stop.sh         (direct)
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# ============================================================================

# Get directories
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"

# Source shared functions
source "$SCRIPTS_DIR/lib/common.sh"

# Configuration
SESSION_NAME="pixeagle"
PORTS=(3000 5077 5551 8088)

# ============================================================================
# Banner
# ============================================================================
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
echo -e "                    ${BOLD}Stopping PixEagle Services${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
echo ""

# ============================================================================
# Stop Tmux Session
# ============================================================================
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo -e "   ${CYAN}→${NC} Stopping tmux session '$SESSION_NAME'..."

    # Send Ctrl+C to all panes first (graceful)
    tmux list-panes -t "$SESSION_NAME" -F "#{session_name}:#{window_index}.#{pane_index}" 2>/dev/null | \
    while read -r pane; do
        tmux send-keys -t "$pane" C-c 2>/dev/null || true
    done
    sleep 2

    # Kill the session
    tmux kill-session -t "$SESSION_NAME" 2>/dev/null
    echo -e "   ${GREEN}${CHECK}${NC} Tmux session stopped"
else
    echo -e "   ${DIM}No tmux session '$SESSION_NAME' running${NC}"
fi

# ============================================================================
# Kill Processes on Ports
# ============================================================================
echo ""
echo -e "   ${CYAN}→${NC} Cleaning up ports..."

for port in "${PORTS[@]}"; do
    pid=$(lsof -t -i :"$port" 2>/dev/null)
    if [[ -n "$pid" ]]; then
        process_name=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
        kill -TERM "$pid" 2>/dev/null
        sleep 0.5
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null
        fi
        echo -e "   ${GREEN}${CHECK}${NC} Killed $process_name on port $port"
    fi
done

# ============================================================================
# Summary
# ============================================================================
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
echo -e "                    ${GREEN}${CHECK}${NC} ${BOLD}All Services Stopped${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "   To start again: ${BOLD}make run${NC}"
echo ""

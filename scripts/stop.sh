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

# Fix CRLF line endings before sourcing
fix_crlf() {
    local f="$1"
    [[ -f "$f" ]] && grep -q $'\r' "$f" 2>/dev/null && sed -i.bak 's/\r$//' "$f" 2>/dev/null && rm -f "${f}.bak"
}
fix_crlf "$SCRIPTS_DIR/lib/common.sh"
fix_crlf "$SCRIPTS_DIR/lib/ports.sh"

# Source shared functions
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    # Fallback colors
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
fi

# Source shared port helpers (optional fallback below).
source "$SCRIPTS_DIR/lib/ports.sh" 2>/dev/null || true

# Configuration
SESSION_NAME="pixeagle"
DASHBOARD_PORT="${PIXEAGLE_DEFAULT_DASHBOARD_PORT:-3040}"
BACKEND_PORT="${PIXEAGLE_DEFAULT_BACKEND_PORT:-5077}"
WEBSOCKET_PORT="${PIXEAGLE_DEFAULT_WEBSOCKET_PORT:-5551}"
MAVLINK2REST_PORT="${PIXEAGLE_DEFAULT_MAVLINK2REST_PORT:-8088}"

if declare -f resolve_dashboard_port >/dev/null 2>&1; then
    DASHBOARD_PORT="$(resolve_dashboard_port "$PIXEAGLE_DIR/dashboard" 2>/dev/null || echo "$DASHBOARD_PORT")"
fi
if declare -f resolve_backend_port >/dev/null 2>&1; then
    BACKEND_PORT="$(resolve_backend_port "$PIXEAGLE_DIR/configs/config.yaml" 2>/dev/null || echo "$BACKEND_PORT")"
fi

PORTS=("$DASHBOARD_PORT" "$BACKEND_PORT" "$WEBSOCKET_PORT" "$MAVLINK2REST_PORT")

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

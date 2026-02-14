#!/bin/bash

# ============================================================================
# scripts/service/run.sh - PixEagle systemd supervisor
# ============================================================================
# Starts PixEagle in detached tmux mode and monitors the session. If the tmux
# session dies unexpectedly, the script exits non-zero so systemd can restart.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUN_SCRIPT="$PROJECT_ROOT/scripts/run.sh"
STOP_SCRIPT="$PROJECT_ROOT/scripts/stop.sh"
TMUX_SESSION_NAME="pixeagle"

# Optional file logging; journald is always primary.
LOG_FILE="${PIXEAGLE_SERVICE_LOG_FILE:-}"
STOP_REQUESTED=false

log_message() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"

    echo "[$timestamp] [$level] $message"

    if [ -n "$LOG_FILE" ]; then
        echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    fi
}

check_prerequisites() {
    local missing=()
    local cmd

    for cmd in tmux bash; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing+=("$cmd")
        fi
    done

    if [ "${#missing[@]}" -gt 0 ]; then
        log_message "ERROR" "Missing dependencies: ${missing[*]}"
        return 1
    fi

    if [ ! -f "$RUN_SCRIPT" ]; then
        log_message "ERROR" "Missing launcher: $RUN_SCRIPT"
        return 1
    fi

    if [ ! -f "$STOP_SCRIPT" ]; then
        log_message "ERROR" "Missing stop script: $STOP_SCRIPT"
        return 1
    fi

    return 0
}

start_stack() {
    if tmux has-session -t "$TMUX_SESSION_NAME" >/dev/null 2>&1; then
        log_message "WARN" "tmux session '$TMUX_SESSION_NAME' already exists; monitoring existing stack"
        return 0
    fi

    log_message "INFO" "Launching PixEagle stack with --no-attach"
    bash "$RUN_SCRIPT" --no-attach
    sleep 2

    if ! tmux has-session -t "$TMUX_SESSION_NAME" >/dev/null 2>&1; then
        log_message "ERROR" "tmux session '$TMUX_SESSION_NAME' did not start"
        return 1
    fi

    log_message "INFO" "tmux session '$TMUX_SESSION_NAME' started"
    return 0
}

stop_stack() {
    if tmux has-session -t "$TMUX_SESSION_NAME" >/dev/null 2>&1; then
        log_message "INFO" "Stopping PixEagle stack"
        bash "$STOP_SCRIPT" || true
    else
        log_message "INFO" "No tmux session to stop"
    fi
}

handle_shutdown() {
    STOP_REQUESTED=true
    log_message "INFO" "Shutdown signal received"
    stop_stack
    log_message "INFO" "Shutdown complete"
    exit 0
}

monitor_tmux_session() {
    log_message "INFO" "Monitoring tmux session '$TMUX_SESSION_NAME'"

    while true; do
        if ! tmux has-session -t "$TMUX_SESSION_NAME" >/dev/null 2>&1; then
            if [ "$STOP_REQUESTED" = "true" ]; then
                log_message "INFO" "tmux session exited after requested stop"
                return 0
            fi

            log_message "ERROR" "tmux session '$TMUX_SESSION_NAME' exited unexpectedly"
            return 1
        fi

        sleep 5
    done
}

log_startup_info() {
    local ip
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    local hostname_local
    hostname_local="$(hostname 2>/dev/null).local"
    local dashboard_port="${PIXEAGLE_DEFAULT_DASHBOARD_PORT:-3040}"
    local api_port="${PIXEAGLE_DEFAULT_BACKEND_PORT:-5077}"
    local branch
    branch="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
    local commit
    commit="$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'unknown')"

    log_message "INFO" "──────────────────────────────────────────"
    log_message "INFO" "PixEagle Vision Tracking Service"
    log_message "INFO" "  Install:   $PROJECT_ROOT"
    log_message "INFO" "  Version:   $branch @ $commit"

    if [ -n "$ip" ]; then
        log_message "INFO" "  Dashboard: http://$ip:$dashboard_port"
        log_message "INFO" "  API:       http://$ip:$api_port"
    fi

    # Detect if running behind a platform proxy (e.g., ARK-OS nginx)
    if [ -f "$PROJECT_ROOT/dashboard/.env.production.local" ]; then
        log_message "INFO" "  Proxy:     http://$hostname_local/pixeagle/"
        log_message "INFO" "  Proxy API: http://$hostname_local/pixeagle-api/"
    fi

    log_message "INFO" "  tmux:      tmux attach -t $TMUX_SESSION_NAME"
    log_message "INFO" "  Logs:      journalctl --user -u pixeagle -f"
    log_message "INFO" "──────────────────────────────────────────"
}

main() {
    cd "$PROJECT_ROOT"
    log_message "INFO" "PixEagle service supervisor starting"

    check_prerequisites
    start_stack
    log_startup_info
    monitor_tmux_session
}

trap 'handle_shutdown' TERM INT

main "$@"

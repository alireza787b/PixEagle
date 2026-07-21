#!/bin/bash

# ============================================================================
# scripts/service/run.sh - PixEagle systemd supervisor
# ============================================================================
# Starts PixEagle on a dedicated service tmux socket and monitors the exact
# run/component contract. Manual runtimes use a separate socket and identity.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUN_SCRIPT="$PROJECT_ROOT/scripts/run.sh"
STOP_SCRIPT="$PROJECT_ROOT/scripts/stop.sh"
TMUX_SESSION_NAME="pixeagle"
OWNERSHIP_HELPER="$PROJECT_ROOT/scripts/lib/runtime_ownership.sh"

# shellcheck source=scripts/lib/runtime_ownership.sh
if ! source "$OWNERSHIP_HELPER"; then
    echo "Missing runtime ownership helper: $OWNERSHIP_HELPER" >&2
    exit 1
fi

SERVICE_RUNTIME_MODE="service"
SERVICE_RUN_ID="$(pixeagle_generate_run_id pixeagle_service)" || {
    echo "Could not generate a collision-resistant PixEagle service run ID" >&2
    exit 1
}
if ! pixeagle_run_id_is_valid "$SERVICE_RUN_ID"; then
    echo "Invalid PixEagle service run ID" >&2
    exit 2
fi
SERVICE_TMUX_SOCKET_NAME="$(pixeagle_tmux_socket_name "$PROJECT_ROOT" "$SERVICE_RUNTIME_MODE")"

# The long-lived systemd supervisor is not a PixEagle component process. Keep
# exact runtime ownership markers off it and inject them only into the launcher
# child; otherwise startup orphan detection can classify the supervisor itself.
unset PIXEAGLE_RUNTIME_MODE PIXEAGLE_PROJECT_ROOT PIXEAGLE_RUN_ID
unset PIXEAGLE_SESSION_NAME PIXEAGLE_TMUX_SOCKET_NAME

tmux_runtime() {
    pixeagle_tmux "$SERVICE_TMUX_SOCKET_NAME" "$@"
}

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

    if [ ! -f "$OWNERSHIP_HELPER" ]; then
        log_message "ERROR" "Missing ownership helper: $OWNERSHIP_HELPER"
        return 1
    fi

    return 0
}

notify_service_ready() {
    # Direct contributor invocation remains possible for diagnostics. A
    # generated Type=notify unit always supplies NOTIFY_SOCKET and must receive
    # application readiness before `systemctl start` can succeed.
    if [ -z "${NOTIFY_SOCKET:-}" ]; then
        log_message "WARN" "NOTIFY_SOCKET is absent; running outside a Type=notify service"
        return 0
    fi
    if ! command -v systemd-notify >/dev/null 2>&1; then
        log_message "ERROR" "systemd-notify is required by the generated service unit"
        return 1
    fi
    systemd-notify --ready --status="PixEagle runtime $SERVICE_RUN_ID is ready"
}

start_stack() {
    if pixeagle_tmux_session_exists "$SERVICE_TMUX_SOCKET_NAME" "$TMUX_SESSION_NAME"; then
        if ! pixeagle_tmux_session_is_owned \
            "$SERVICE_TMUX_SOCKET_NAME" "$TMUX_SESSION_NAME" "$PROJECT_ROOT" \
            "$SERVICE_RUNTIME_MODE"; then
            log_message "ERROR" "tmux session '$TMUX_SESSION_NAME' is not owned by this checkout"
            return 1
        fi
        log_message "WARN" "A stale owned service runtime exists; the launcher will replace it under the lifecycle lock"
    fi

    log_message "INFO" "Launching PixEagle stack with --no-attach"
    # The supervisor is the only process allowed to access systemd's notify and
    # watchdog channels. Components receive an explicitly sanitized environment.
    pixeagle_without_systemd_runtime_channels \
        env \
            PIXEAGLE_LAUNCH_RUNTIME_MODE="$SERVICE_RUNTIME_MODE" \
            PIXEAGLE_LAUNCH_RUN_ID="$SERVICE_RUN_ID" \
            bash "$RUN_SCRIPT" --no-attach

    if ! pixeagle_tmux_runtime_is_healthy \
        "$SERVICE_TMUX_SOCKET_NAME" "$TMUX_SESSION_NAME" "$PROJECT_ROOT" \
        "$SERVICE_RUNTIME_MODE" "$SERVICE_RUN_ID"; then
        log_message "ERROR" "service runtime did not publish a healthy exact component contract"
        return 1
    fi

    log_message "INFO" "service runtime '$SERVICE_RUN_ID' is ready"
    return 0
}

stop_stack() {
    log_message "INFO" "Stopping marked service-mode runtime"
    bash "$STOP_SCRIPT" --mode service
}

handle_shutdown() {
    local result=0
    STOP_REQUESTED=true
    log_message "INFO" "Shutdown signal received"
    if pixeagle_tmux_session_exists \
        "$SERVICE_TMUX_SOCKET_NAME" "$TMUX_SESSION_NAME"; then
        if ! stop_stack; then
            log_message "ERROR" "Owned stack shutdown was incomplete"
            result=1
        fi
    fi
    if [[ "$result" == 0 ]]; then
        log_message "INFO" "Shutdown complete"
    fi
    exit "$result"
}

monitor_tmux_session() {
    local expected_components
    expected_components="$(pixeagle_tmux_environment_value \
        "$SERVICE_TMUX_SOCKET_NAME" "$TMUX_SESSION_NAME" \
        PIXEAGLE_EXPECTED_COMPONENTS 2>/dev/null || true)"
    if [ -z "$expected_components" ]; then
        log_message "ERROR" "runtime did not publish expected component identities"
        return 1
    fi
    log_message "INFO" "Monitoring run '$SERVICE_RUN_ID' components: $expected_components"

    while true; do
        if ! pixeagle_tmux_session_exists \
            "$SERVICE_TMUX_SOCKET_NAME" "$TMUX_SESSION_NAME"; then
            if [ "$STOP_REQUESTED" = "true" ]; then
                log_message "INFO" "tmux session exited after requested stop"
                return 0
            fi

            log_message "ERROR" "tmux session '$TMUX_SESSION_NAME' exited unexpectedly"
            return 1
        fi

        if ! pixeagle_tmux_session_is_owned \
            "$SERVICE_TMUX_SOCKET_NAME" "$TMUX_SESSION_NAME" "$PROJECT_ROOT" \
            "$SERVICE_RUNTIME_MODE" "$SERVICE_RUN_ID"; then
            log_message "ERROR" "runtime identity marker changed or disappeared"
            return 1
        fi

        local pane_records dead_panes actual_components
        pane_records="$(tmux_runtime list-panes -t "=$TMUX_SESSION_NAME" -s \
            -F '#{pane_dead}|#{@pixeagle_component}|#{pane_dead_status}' 2>/dev/null || true)"
        dead_panes="$(awk -F'|' '$1 == "1" {print ($2 == "" ? "unknown" : $2) " (exit " $3 ")"}' <<< "$pane_records")"
        if [ -n "$dead_panes" ]; then
            log_message "ERROR" "PixEagle component exited: $dead_panes"
            return 1
        fi
        actual_components="$(awk -F'|' '$1 == "0" && $2 != "" {print $2}' \
            <<< "$pane_records" | LC_ALL=C sort | paste -sd, -)"
        if [ "$actual_components" != "$expected_components" ]; then
            log_message "ERROR" "component set changed: expected '$expected_components', observed '${actual_components:-none}'"
            return 1
        fi

        sleep 5
    done
}

log_startup_info() {
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
    log_message "INFO" "  Dashboard: http://127.0.0.1:$dashboard_port"
    log_message "INFO" "  API:       http://127.0.0.1:$api_port"
    log_message "INFO" "  Exposure:  local-only by default; use SSH tunnels for browser access"

    # Detect if running behind a platform proxy (e.g., ARK-OS nginx)
    if [ -f "$PROJECT_ROOT/dashboard/.env.production.local" ]; then
        log_message "INFO" "  Proxy:     http://$hostname_local/pixeagle/"
        log_message "INFO" "  Proxy API: http://$hostname_local/pixeagle-api/"
    fi

    log_message "INFO" "  tmux:      pixeagle-service attach"
    log_message "INFO" "  Logs:      pixeagle-service logs -f"
    log_message "INFO" "──────────────────────────────────────────"
}

main() {
    cd "$PROJECT_ROOT"
    log_message "INFO" "PixEagle service supervisor starting"

    check_prerequisites || return 1

    local result=0
    if ! start_stack; then
        result=1
    elif ! notify_service_ready; then
        log_message "ERROR" "Readiness notification failed; cleaning the owned stack"
        stop_stack || log_message "ERROR" "Owned stack cleanup after readiness failure was incomplete"
        result=1
    else
        log_startup_info
    fi

    if [[ "$result" == 0 ]] && ! monitor_tmux_session; then
        log_message "ERROR" "Supervisor detected runtime failure; cleaning the owned stack before restart"
        stop_stack || log_message "ERROR" "Owned stack cleanup after failure was incomplete"
        result=1
    fi

    return "$result"
}

trap 'handle_shutdown' TERM INT

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi

#!/bin/bash

# ============================================================================
# scripts/service/cli.sh - PixEagle Service Manager (Canonical CLI)
# ============================================================================
# Linux/systemd-only management interface for PixEagle.
# ============================================================================

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UTILS_SCRIPT="$SCRIPT_DIR/utils.sh"

if [ ! -f "$UTILS_SCRIPT" ]; then
    echo "[ERROR] Missing utility script: $UTILS_SCRIPT"
    exit 1
fi

# shellcheck source=scripts/service/utils.sh
source "$UTILS_SCRIPT"

run_systemctl() {
    if [ "$EUID" -eq 0 ]; then
        systemctl "$@"
    else
        sudo systemctl "$@"
    fi
}

require_root() {
    if [ "$EUID" -ne 0 ]; then
        print_status "error" "This command requires root privileges"
        print_status "note" "Re-run with sudo"
        return 1
    fi
    return 0
}

show_help() {
    cat <<'EOF'
PixEagle Service Manager
========================

Usage:
  pixeagle-service <command> [options]

Commands:
  start                 Start PixEagle (systemd if installed, unmanaged otherwise)
  stop                  Stop PixEagle
  restart               Restart PixEagle
  status                Show service, tmux, and port status
  enable                Install + enable auto-start on boot (requires sudo)
  disable               Disable + remove auto-start service (requires sudo)
  logs [-f] [-n LINES]  View service logs (journald)
  attach                Attach to tmux session
  update [options]      Fast-forward source + reconcile dependencies/config
                         Options: --dry-run, --remote <name>, --branch <name>
                         Runtime must already be stopped; it is not restarted
  reset-config          Reset config files to defaults (creates backups)
  login-hint <action>   Manage SSH login hint (enable|disable|status)
                         Options: --system (all users), --user (current/default user)
  help                  Show this message

Examples:
  pixeagle-service start
  pixeagle-service status
  pixeagle-service logs -f
  pixeagle-service update
  pixeagle-service update --remote upstream --branch develop
  pixeagle-service reset-config
  sudo pixeagle-service enable
  pixeagle-service login-hint enable
  sudo pixeagle-service login-hint enable --system
EOF
}

start_command() {
    local active_state=""
    if ! check_prerequisites; then
        return 1
    fi

    if is_service_installed; then
        local previous_run_id=""
        local was_active=false
        if ! active_state="$(service_active_state)"; then
            print_status "error" "Could not determine ${SERVICE_NAME}.service state"
            print_status "note" "Refusing an unmanaged fallback while a service unit is installed"
            return 1
        fi
        [[ "$active_state" == active ]] && was_active=true
        previous_run_id="$(runtime_run_id_for_mode service 2>/dev/null || true)"
        print_status "process" "Starting ${SERVICE_NAME}.service via systemd"
        if ! run_systemctl start "${SERVICE_NAME}.service"; then
            print_status "error" "systemd failed to start ${SERVICE_NAME}.service"
            return 1
        fi
        if [ "$was_active" = "true" ]; then
            previous_run_id=""
        fi
        if ! wait_for_runtime_ready_for_mode service 300 "$previous_run_id"; then
            print_status "error" "systemd returned but the exact PixEagle runtime did not become ready"
            print_status "note" "Inspect: sudo journalctl -u ${SERVICE_NAME}.service -n 100"
            return 1
        fi
        print_status "success" "Service runtime is ready"
        return 0
    fi

    print_status "warning" "A managed service is not installed"
    print_status "note" "Starting unmanaged tmux session instead"
    print_status "note" "Install managed startup with: sudo bash scripts/service/install.sh"
    start_unmanaged_stack
}

stop_command() {
    local did_stop=false
    local stop_failed=false
    local active_state=""

    if is_service_installed; then
        if ! active_state="$(service_active_state)"; then
            print_status "error" "Could not determine ${SERVICE_NAME}.service state"
            return 1
        fi
        if [ "$active_state" != "inactive" ]; then
            print_status "process" "Stopping ${SERVICE_NAME}.service"
            if ! run_systemctl stop "${SERVICE_NAME}.service"; then
                print_status "error" "systemd failed to stop ${SERVICE_NAME}.service"
                stop_failed=true
            fi
            did_stop=true
        fi
    fi

    if is_tmux_session_active_for_mode manual; then
        if ! stop_unmanaged_stack; then
            print_status "error" "Unmanaged PixEagle runtime stop was incomplete"
            stop_failed=true
        fi
        did_stop=true
    fi

    if [ "$did_stop" = "false" ]; then
        print_status "info" "PixEagle is not running"
    elif [ "$stop_failed" = "false" ]; then
        print_status "success" "Stop sequence completed"
    fi
    [ "$stop_failed" = "false" ]
}

restart_command() {
    if is_service_installed; then
        if ! service_active_state >/dev/null; then
            print_status "error" "Could not determine ${SERVICE_NAME}.service state"
            print_status "note" "Refusing an unmanaged fallback while a service unit is installed"
            return 1
        fi
        local previous_run_id=""
        previous_run_id="$(runtime_run_id_for_mode service 2>/dev/null || true)"
        print_status "process" "Restarting ${SERVICE_NAME}.service"
        if ! run_systemctl restart "${SERVICE_NAME}.service"; then
            print_status "error" "systemd failed to restart ${SERVICE_NAME}.service"
            return 1
        fi
        if ! wait_for_runtime_ready_for_mode service 300 "$previous_run_id"; then
            print_status "error" "systemd returned but a new exact PixEagle runtime did not become ready"
            print_status "note" "Inspect: sudo journalctl -u ${SERVICE_NAME}.service -n 100"
            return 1
        fi
        print_status "success" "Replacement service runtime is ready"
        return 0
    fi

    stop_unmanaged_stack || return 1
    sleep 1
    start_unmanaged_stack
}

enable_command() {
    require_root || return 1

    if ! check_prerequisites; then
        return 1
    fi

    # Detect externally-managed user-level service (e.g., ARK-OS).
    # A system-level service would conflict with it.
    if sudo -u "${SUDO_USER:-$USER}" systemctl --user cat "${SERVICE_NAME}.service" &>/dev/null 2>&1; then
        print_status "error" "User-level ${SERVICE_NAME}.service already exists (managed by external system, e.g., ARK-OS)"
        print_status "note" "Cannot create system-level service — it would conflict"
        print_status "note" "Manage via: systemctl --user {start|stop|enable|disable} ${SERVICE_NAME}"
        return 1
    fi

    create_service_file || return 1
    systemctl daemon-reload || return 1
    systemctl enable "${SERVICE_NAME}.service" || return 1
    print_status "success" "Auto-start enabled"
    print_status "note" "Start now with: sudo systemctl start ${SERVICE_NAME}.service"
}

disable_command() {
    require_root || return 1
    remove_service || return 1
    print_status "success" "Auto-start disabled"
}

logs_command() {
    local lines=100
    local follow=false

    while [ $# -gt 0 ]; do
        case "$1" in
            -f|--follow)
                follow=true
                ;;
            -n|--lines)
                shift
                if [ -z "${1:-}" ] || ! [[ "$1" =~ ^[0-9]+$ ]]; then
                    print_status "error" "Invalid line count for logs"
                    return 1
                fi
                lines="$1"
                ;;
            *)
                print_status "error" "Unknown logs option: $1"
                return 1
                ;;
        esac
        shift
    done

    show_service_logs "$lines" "$follow"
}

update_command() {
    if ! detect_service_user; then
        return 1
    fi

    local update_script="$PROJECT_ROOT/scripts/update.sh"
    if [ ! -f "$update_script" ]; then
        print_status "error" "Update script not found: $update_script"
        return 1
    fi

    cd "$PROJECT_ROOT" || return 1
    if [ "$(id -un)" = "$SERVICE_USER" ]; then
        bash "$update_script" "$@"
    else
        run_as_service_user env \
            SYNC_REMOTE="${SYNC_REMOTE:-}" \
            SYNC_BRANCH="${SYNC_BRANCH:-}" \
            bash "$update_script" "$@"
    fi
}

reset_config_command() {
    if ! detect_service_user; then
        return 1
    fi

    local reset_script="$PROJECT_ROOT/scripts/lib/reset-config.sh"
    if [ ! -f "$reset_script" ]; then
        print_status "error" "Reset-config script not found: $reset_script"
        return 1
    fi

    cd "$PROJECT_ROOT" || return 1
    PIXEAGLE_ROOT="$PROJECT_ROOT" bash "$reset_script"
}

login_hint_command() {
    local action="${1:-status}"
    local scope="user"
    if [ $# -gt 0 ]; then
        shift
    fi

    while [ $# -gt 0 ]; do
        case "$1" in
            --system)
                scope="system"
                ;;
            --user)
                scope="user"
                ;;
            *)
                print_status "error" "Unknown login-hint option: $1"
                print_status "note" "Use: pixeagle-service login-hint <enable|disable|status> [--system|--user]"
                return 1
                ;;
        esac
        shift
    done

    case "$action" in
        enable)
            login_hint_enable "$scope"
            ;;
        disable)
            login_hint_disable "$scope"
            ;;
        status)
            login_hint_status "$scope"
            ;;
        *)
            print_status "error" "Unknown login-hint action: $action"
            print_status "note" "Use: pixeagle-service login-hint <enable|disable|status> [--system|--user]"
            return 1
            ;;
    esac
}

main() {
    local command="${1:-help}"
    shift || true

    case "$command" in
        start)
            start_command "$@"
            ;;
        stop)
            stop_command "$@"
            ;;
        restart)
            restart_command "$@"
            ;;
        status)
            get_service_status
            ;;
        enable)
            enable_command "$@"
            ;;
        disable)
            disable_command "$@"
            ;;
        logs)
            logs_command "$@"
            ;;
        attach)
            attach_to_session
            ;;
        update)
            update_command "$@"
            ;;
        reset-config)
            reset_config_command "$@"
            ;;
        login-hint)
            login_hint_command "$@"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_status "error" "Unknown command: $command"
            show_help
            return 1
            ;;
    esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi

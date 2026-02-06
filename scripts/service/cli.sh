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
  start                 Start PixEagle (systemd if enabled, unmanaged otherwise)
  stop                  Stop PixEagle
  restart               Restart PixEagle
  status                Show service, tmux, and port status
  enable                Install + enable auto-start on boot (requires sudo)
  disable               Disable + remove auto-start service (requires sudo)
  logs [-f] [-n LINES]  View service logs (journald)
  attach                Attach to tmux session
  login-hint <action>   Manage SSH login hint (enable|disable|status)
                         Options: --system (all users), --user (current/default user)
  help                  Show this message

Examples:
  pixeagle-service start
  pixeagle-service status
  pixeagle-service logs -f
  sudo pixeagle-service enable
  pixeagle-service login-hint enable
  sudo pixeagle-service login-hint enable --system
EOF
}

start_command() {
    if ! check_prerequisites; then
        return 1
    fi

    if is_service_installed && is_service_enabled; then
        print_status "process" "Starting ${SERVICE_NAME}.service via systemd"
        run_systemctl start "${SERVICE_NAME}.service"
        print_status "success" "Service start requested"
        return 0
    fi

    print_status "warning" "Auto-start service is not enabled"
    print_status "note" "Starting unmanaged tmux session instead"
    print_status "note" "Enable boot startup with: sudo pixeagle-service enable"
    start_unmanaged_stack
}

stop_command() {
    local did_stop=false

    if is_service_active; then
        print_status "process" "Stopping ${SERVICE_NAME}.service"
        run_systemctl stop "${SERVICE_NAME}.service"
        did_stop=true
    fi

    if is_tmux_session_active; then
        stop_unmanaged_stack
        did_stop=true
    fi

    if [ "$did_stop" = "false" ]; then
        print_status "info" "PixEagle is not running"
    else
        print_status "success" "Stop sequence completed"
    fi
}

restart_command() {
    if is_service_installed && is_service_enabled; then
        print_status "process" "Restarting ${SERVICE_NAME}.service"
        run_systemctl restart "${SERVICE_NAME}.service"
        print_status "success" "Service restart requested"
        return 0
    fi

    stop_unmanaged_stack
    sleep 1
    start_unmanaged_stack
}

enable_command() {
    require_root || return 1

    if ! check_prerequisites; then
        return 1
    fi

    create_service_file
    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}.service"
    print_status "success" "Auto-start enabled"
    print_status "note" "Start now with: sudo systemctl start ${SERVICE_NAME}.service"
}

disable_command() {
    require_root || return 1
    remove_service
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

main "$@"

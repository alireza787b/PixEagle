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

reset_explicit_start_budget() {
    # Automatic Restart=on-failure remains bounded by the unit's StartLimit.
    # An explicit operator start/restart is a new recovery decision and should
    # not be blocked by earlier, already-observed attempts in that window.
    if ! run_systemctl reset-failed "${SERVICE_NAME}.service"; then
        print_status "note" "Could not reset the previous systemd failure budget; continuing with the explicit request"
    fi
}

service_wait_sleep() {
    sleep "$1"
}

restore_interrupt_trap() {
    local previous_trap="$1"
    if [ -n "$previous_trap" ]; then
        eval "$previous_trap"
    else
        trap - INT
    fi
}

wait_for_managed_runtime_ready() {
    local operation="$1"
    local previous_run_id="${2:-}"
    local timeout_seconds="${PIXEAGLE_SERVICE_READY_TIMEOUT_SECONDS:-300}"
    local progress_interval="${PIXEAGLE_SERVICE_PROGRESS_INTERVAL_SECONDS:-5}"
    local elapsed=0
    local terminal_observations=0
    local active_state=""
    local interrupted=false
    local previous_int_trap=""

    [[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]] || timeout_seconds=300
    [[ "$progress_interval" =~ ^[1-9][0-9]*$ ]] || progress_interval=5
    previous_int_trap="$(trap -p INT)"
    trap 'interrupted=true' INT

    while [ "$elapsed" -lt "$timeout_seconds" ]; do
        if [ "$interrupted" = "true" ]; then
            restore_interrupt_trap "$previous_int_trap"
            print_status "warning" "Service wait interrupted; the systemd job may still be running"
            print_status "note" "Check: pixeagle-service status"
            print_status "note" "Logs: pixeagle-service logs -f"
            return 130
        fi
        if runtime_is_ready_for_mode service "$previous_run_id"; then
            restore_interrupt_trap "$previous_int_trap"
            return 0
        fi
        if ! active_state="$(service_active_state)"; then
            restore_interrupt_trap "$previous_int_trap"
            print_status "error" "Could not determine ${SERVICE_NAME}.service state while waiting"
            return 2
        fi

        if (( elapsed % progress_interval == 0 )); then
            print_status "process" "Waiting for $operation: ${elapsed}s (systemd: $active_state)"
        fi

        case "$active_state" in
            failed|inactive)
                terminal_observations=$((terminal_observations + 1))
                if [ "$terminal_observations" -ge 2 ]; then
                    restore_interrupt_trap "$previous_int_trap"
                    return 1
                fi
                ;;
            *)
                terminal_observations=0
                ;;
        esac
        service_wait_sleep 1
        elapsed=$((elapsed + 1))
    done

    restore_interrupt_trap "$previous_int_trap"
    print_status "error" "Timed out after ${timeout_seconds}s waiting for $operation"
    return 1
}

print_service_start_diagnostics() {
    print_status "note" "Inspect: systemctl status ${SERVICE_NAME}.service --no-pager -l"
    print_status "note" "Journal: journalctl -u ${SERVICE_NAME}.service -b --no-pager -n 200"
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
  install               Install/refresh unit; preserve runtime and boot policy (sudo)
  start                 Start the installed managed service
  stop                  Stop the installed managed service
  restart               Restart the installed managed service
  status                Show service, tmux, and port status
  enable                Enable boot; install unit if missing; runtime unchanged (sudo)
  disable               Disable boot auto-start; current runtime unchanged (sudo)
  uninstall             Stop and remove the managed unit (requires sudo)
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
  sudo pixeagle-service install
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

install_command() {
    require_root || return 1
    check_prerequisites || return 1
    refuse_external_user_service_conflict "$SERVICE_USER" || return 1
    install_service_unit || return 1
    print_status "note" "Start now: pixeagle-service start"
    print_status "note" "Boot policy: pixeagle-service enable | disable"
}

ensure_manual_runtime_is_stopped() {
    local manual_pids=""
    local quoted_project_root=""
    printf -v quoted_project_root '%q' "$PROJECT_ROOT"

    if runtime_is_ready_for_mode manual; then
        print_status "error" "PixEagle is already running in manual/browser-lab mode"
        print_status "note" "Keep that runtime, or switch modes:"
        print_status "note" "  make -C $quoted_project_root stop"
        print_status "note" "  pixeagle-service start"
        return 1
    fi
    if is_tmux_session_present_for_mode manual; then
        print_status "error" "A manual PixEagle session exists but is not healthy"
        print_status "note" "Inspect it with: make -C $quoted_project_root status"
        print_status "note" "Stop it before starting the managed service: make -C $quoted_project_root stop"
        return 1
    fi
    if ! manual_pids="$(runtime_owned_pids_for_mode manual)"; then
        print_status "error" "Could not verify whether manual PixEagle processes are stopped"
        return 1
    fi
    if [[ -n "$manual_pids" ]]; then
        manual_pids="${manual_pids//$'\n'/,}"
        print_status "error" "Manual PixEagle processes exist without a healthy session: $manual_pids"
        print_status "note" "Inspect and stop the manual runtime before starting the managed service"
        return 1
    fi
    return 0
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
        ensure_manual_runtime_is_stopped || return 1
        if [[ "$was_active" != true ]]; then
            reset_explicit_start_budget
        fi
        print_status "process" "Queueing ${SERVICE_NAME}.service start via systemd"
        if ! run_systemctl --no-block start "${SERVICE_NAME}.service"; then
            print_status "error" "systemd refused to queue ${SERVICE_NAME}.service start"
            print_service_start_diagnostics
            return 1
        fi
        if [ "$was_active" = "true" ]; then
            previous_run_id=""
        fi
        local wait_status=0
        if wait_for_managed_runtime_ready "the exact PixEagle runtime" "$previous_run_id"; then
            wait_status=0
        else
            wait_status=$?
        fi
        if [ "$wait_status" -eq 130 ]; then
            return 130
        fi
        if [ "$wait_status" -ne 0 ]; then
            print_status "error" "The exact PixEagle runtime did not become ready"
            print_service_start_diagnostics
            return 1
        fi
        print_status "success" "Service runtime is ready"
        return 0
    fi

    local quoted_project_root
    printf -v quoted_project_root '%q' "$PROJECT_ROOT"
    print_status "error" "The managed ${SERVICE_NAME}.service unit is not installed"
    print_status "note" "Install it with: sudo pixeagle-service install"
    print_status "note" "For a manual runtime instead: cd $quoted_project_root && make run"
    return 1
}

stop_command() {
    local did_stop=false
    local stop_failed=false
    local active_state=""

    if ! is_service_installed; then
        local quoted_project_root
        printf -v quoted_project_root '%q' "$PROJECT_ROOT"
        print_status "error" "The managed ${SERVICE_NAME}.service unit is not installed"
        print_status "note" "Stop a manual runtime with: cd $quoted_project_root && make stop"
        return 1
    fi
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

    if [ "$did_stop" = "false" ]; then
        print_status "info" "PixEagle is not running"
    elif [ "$stop_failed" = "false" ]; then
        print_status "success" "Stop sequence completed"
    fi
    [ "$stop_failed" = "false" ]
}

restart_command() {
    if is_service_installed; then
        local active_state=""
        if ! active_state="$(service_active_state)"; then
            print_status "error" "Could not determine ${SERVICE_NAME}.service state"
            print_status "note" "Refusing an unmanaged fallback while a service unit is installed"
            return 1
        fi
        ensure_manual_runtime_is_stopped || return 1
        local previous_run_id=""
        previous_run_id="$(runtime_run_id_for_mode service 2>/dev/null || true)"
        reset_explicit_start_budget
        print_status "process" "Queueing ${SERVICE_NAME}.service restart"
        if ! run_systemctl --no-block restart "${SERVICE_NAME}.service"; then
            print_status "error" "systemd refused to queue ${SERVICE_NAME}.service restart"
            print_service_start_diagnostics
            return 1
        fi
        local wait_status=0
        if wait_for_managed_runtime_ready "a replacement PixEagle runtime" "$previous_run_id"; then
            wait_status=0
        else
            wait_status=$?
        fi
        if [ "$wait_status" -eq 130 ]; then
            return 130
        fi
        if [ "$wait_status" -ne 0 ]; then
            print_status "error" "A replacement PixEagle runtime did not become ready"
            print_service_start_diagnostics
            return 1
        fi
        print_status "success" "Replacement service runtime is ready"
        return 0
    fi

    print_status "error" "The managed ${SERVICE_NAME}.service unit is not installed"
    print_status "note" "Install it with: sudo pixeagle-service install"
    return 1
}

enable_command() {
    require_root || return 1

    if ! check_prerequisites; then
        return 1
    fi

    refuse_external_user_service_conflict "$SERVICE_USER" || return 1

    if ! is_service_installed; then
        install_service_unit || return 1
    fi
    systemctl enable "${SERVICE_NAME}.service" || return 1
    print_status "success" "Auto-start enabled; current runtime unchanged"
    print_status "note" "Start now: pixeagle-service start"
}

disable_command() {
    require_root || return 1
    disable_service_autostart
}

uninstall_command() {
    require_root || return 1
    remove_service || return 1
    print_status "success" "Managed service unit uninstalled"
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
        install)
            install_command "$@"
            ;;
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
        uninstall)
            uninstall_command "$@"
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

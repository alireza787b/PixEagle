#!/bin/bash

# ============================================================================
# scripts/service/utils.sh - PixEagle Service Utilities
# ============================================================================
# Shared helpers for the PixEagle service CLI and installer.
# Linux/systemd only.
# ============================================================================

set -o pipefail

SERVICE_NAME="pixeagle"
TMUX_SESSION_NAME="pixeagle"
SERVICE_DESCRIPTION="PixEagle UAV Tracking and Control System"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_ROOT="${PIXEAGLE_INSTALL_DIR:-$DEFAULT_PROJECT_ROOT}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m'

LOGIN_HINT_BLOCK_BEGIN="# >>> pixeagle login hint >>>"
LOGIN_HINT_BLOCK_END="# <<< pixeagle login hint <<<"
SYSTEM_LOGIN_HINT_FILE="/etc/profile.d/pixeagle-login-hint.sh"

print_status() {
    local status="$1"
    local message="$2"

    case "$status" in
        "info")    echo -e "${BLUE}[*] $message${NC}" ;;
        "success") echo -e "${GREEN}[OK] $message${NC}" ;;
        "warning") echo -e "${YELLOW}[WARN] $message${NC}" ;;
        "error")   echo -e "${RED}[ERROR] $message${NC}" ;;
        "process") echo -e "${CYAN}[*] $message${NC}" ;;
        "note")    echo -e "${PURPLE}[NOTE] $message${NC}" ;;
        *)         echo -e "${WHITE}$message${NC}" ;;
    esac
}

have_systemd() {
    command -v systemctl >/dev/null 2>&1
}

get_user_home() {
    local user_name="$1"
    local home_dir=""

    if command -v getent >/dev/null 2>&1; then
        home_dir="$(getent passwd "$user_name" | cut -d: -f6)"
    fi

    if [ -z "$home_dir" ]; then
        home_dir="$(eval echo "~$user_name")"
    fi

    echo "$home_dir"
}

detect_service_user() {
    if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
        SERVICE_USER="$SUDO_USER"
    else
        SERVICE_USER="$(id -un)"
    fi

    if ! id "$SERVICE_USER" >/dev/null 2>&1; then
        print_status "error" "User '$SERVICE_USER' does not exist"
        return 1
    fi

    SERVICE_HOME="$(get_user_home "$SERVICE_USER")"

    local candidates=()
    [ -n "${PIXEAGLE_INSTALL_DIR:-}" ] && candidates+=("$PIXEAGLE_INSTALL_DIR")
    candidates+=("$PROJECT_ROOT")
    candidates+=("$SERVICE_HOME/PixEagle")

    USER_PIXEAGLE_DIR=""
    local candidate
    for candidate in "${candidates[@]}"; do
        if [ -n "$candidate" ] && [ -f "$candidate/scripts/run.sh" ]; then
            USER_PIXEAGLE_DIR="$(cd "$candidate" && pwd)"
            break
        fi
    done

    if [ -z "$USER_PIXEAGLE_DIR" ]; then
        print_status "error" "PixEagle root not found (scripts/run.sh missing)"
        print_status "note" "Looked in: ${candidates[*]}"
        return 1
    fi

    PROJECT_ROOT="$USER_PIXEAGLE_DIR"
    RUN_SCRIPT="$PROJECT_ROOT/scripts/run.sh"
    STOP_SCRIPT="$PROJECT_ROOT/scripts/stop.sh"
    SERVICE_RUN_SCRIPT="$PROJECT_ROOT/scripts/service/run.sh"
    LOGIN_HINT_DIR="$SERVICE_HOME/.config/pixeagle"
    LOGIN_HINT_SCRIPT="$LOGIN_HINT_DIR/login_hint.sh"
    BASHRC_PATH="$SERVICE_HOME/.bashrc"

    export SERVICE_USER SERVICE_HOME USER_PIXEAGLE_DIR PROJECT_ROOT
    export RUN_SCRIPT STOP_SCRIPT SERVICE_RUN_SCRIPT
    export LOGIN_HINT_DIR LOGIN_HINT_SCRIPT BASHRC_PATH
    return 0
}

run_as_service_user() {
    if [ -z "${SERVICE_USER:-}" ]; then
        if ! detect_service_user >/dev/null 2>&1; then
            return 1
        fi
    fi

    if [ "$(id -un)" = "$SERVICE_USER" ]; then
        "$@"
        return $?
    fi

    if command -v sudo >/dev/null 2>&1; then
        sudo -u "$SERVICE_USER" "$@"
        return $?
    fi

    if command -v runuser >/dev/null 2>&1; then
        runuser -u "$SERVICE_USER" -- "$@"
        return $?
    fi

    print_status "error" "Neither sudo nor runuser is available"
    return 1
}

is_service_installed() {
    [ -f "$SERVICE_FILE" ]
}

is_service_enabled() {
    have_systemd && systemctl is-enabled --quiet "${SERVICE_NAME}.service"
}

is_service_active() {
    have_systemd && systemctl is-active --quiet "${SERVICE_NAME}.service"
}

is_tmux_session_active() {
    command -v tmux >/dev/null 2>&1 || return 1
    if [ -z "${SERVICE_USER:-}" ]; then
        detect_service_user >/dev/null 2>&1 || return 1
    fi
    run_as_service_user tmux has-session -t "$TMUX_SESSION_NAME" >/dev/null 2>&1
}

get_tmux_session_status() {
    if ! is_tmux_session_active; then
        echo "Not running"
        return 0
    fi

    local windows
    windows="$(run_as_service_user tmux display-message -t "$TMUX_SESSION_NAME" -p "#{session_windows}" 2>/dev/null || true)"
    windows="${windows:-unknown}"
    echo "Active (${windows} windows)"
}

check_component_health() {
    local component="$1"
    local port="$2"

    if ! command -v lsof >/dev/null 2>&1; then
        echo -e "${YELLOW}*${NC} $component (port $port) - cannot check (lsof missing)"
        return 0
    fi

    if lsof -i ":$port" >/dev/null 2>&1; then
        echo -e "${GREEN}*${NC} $component (port $port)"
    else
        echo -e "${RED}*${NC} $component (port $port) - not responding"
    fi
}

check_prerequisites() {
    if ! detect_service_user; then
        return 1
    fi

    local missing=()
    local cmd
    for cmd in tmux systemctl bash; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing+=("$cmd")
        fi
    done

    if [ "${#missing[@]}" -gt 0 ]; then
        print_status "error" "Missing dependencies: ${missing[*]}"
        return 1
    fi

    local required_files=("$RUN_SCRIPT" "$STOP_SCRIPT" "$SERVICE_RUN_SCRIPT")
    local file
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            print_status "error" "Required file missing: $file"
            return 1
        fi
    done

    return 0
}

create_service_file() {
    if ! detect_service_user; then
        return 1
    fi

    print_status "process" "Writing $SERVICE_FILE"

    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=$SERVICE_DESCRIPTION
Documentation=https://github.com/alireza787b/PixEagle
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$USER_PIXEAGLE_DIR
Environment=HOME=$SERVICE_HOME
Environment=USER=$SERVICE_USER
Environment=PIXEAGLE_SERVICE_MODE=1
ExecStart=$SERVICE_RUN_SCRIPT
ExecStop=$STOP_SCRIPT
Restart=on-failure
RestartSec=5
KillMode=control-group
TimeoutStartSec=90
TimeoutStopSec=45
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    print_status "success" "Service unit created"
}

remove_service() {
    print_status "process" "Removing ${SERVICE_NAME}.service"

    if have_systemd && is_service_active; then
        systemctl stop "${SERVICE_NAME}.service"
    fi

    if have_systemd && is_service_enabled; then
        systemctl disable "${SERVICE_NAME}.service"
    fi

    if [ -f "$SERVICE_FILE" ]; then
        rm -f "$SERVICE_FILE"
        have_systemd && systemctl daemon-reload
        print_status "success" "Service removed"
    else
        print_status "warning" "Service file not found at $SERVICE_FILE"
    fi
}

show_service_logs() {
    local lines="${1:-100}"
    local follow="${2:-false}"

    if ! is_service_installed; then
        print_status "warning" "Service is not installed"
        return 1
    fi

    if [ "$follow" = "true" ]; then
        journalctl -u "${SERVICE_NAME}.service" -f
    else
        journalctl -u "${SERVICE_NAME}.service" -n "$lines" --no-pager
    fi
}

start_unmanaged_stack() {
    if ! detect_service_user; then
        return 1
    fi

    if is_tmux_session_active; then
        print_status "warning" "tmux session '$TMUX_SESSION_NAME' is already running"
        return 0
    fi

    print_status "process" "Starting unmanaged PixEagle stack (no systemd)"
    run_as_service_user bash "$RUN_SCRIPT" --no-attach
}

stop_unmanaged_stack() {
    if ! detect_service_user; then
        return 1
    fi

    if ! is_tmux_session_active; then
        print_status "info" "No tmux session '$TMUX_SESSION_NAME' is running"
        return 0
    fi

    print_status "process" "Stopping unmanaged PixEagle stack"
    run_as_service_user bash "$STOP_SCRIPT"
}

attach_to_session() {
    if ! detect_service_user; then
        return 1
    fi

    if ! is_tmux_session_active; then
        print_status "warning" "tmux session '$TMUX_SESSION_NAME' is not running"
        print_status "note" "Start with: pixeagle-service start"
        return 1
    fi

    print_status "info" "Attaching to tmux session '$TMUX_SESSION_NAME'"
    print_status "note" "Detach without stopping: Ctrl+B then D"
    echo
    run_as_service_user tmux attach -t "$TMUX_SESSION_NAME"
}

get_service_status() {
    if ! detect_service_user; then
        return 1
    fi

    echo "PixEagle Service Status"
    echo "======================="
    echo
    echo "Context:"
    echo "  User: $SERVICE_USER"
    echo "  Home: $SERVICE_HOME"
    echo "  Project: $USER_PIXEAGLE_DIR"
    echo

    echo "systemd:"
    if is_service_installed; then
        print_status "success" "Service installed: $SERVICE_FILE"
        if is_service_enabled; then
            print_status "success" "Auto-start: enabled"
        else
            print_status "warning" "Auto-start: disabled"
        fi
        if is_service_active; then
            print_status "success" "Runtime: active"
        else
            print_status "warning" "Runtime: inactive"
        fi
    else
        print_status "warning" "Service not installed"
        print_status "note" "Install command first: sudo bash scripts/service/install.sh"
    fi
    echo

    echo "tmux:"
    local tmux_status
    tmux_status="$(get_tmux_session_status)"
    if [ "$tmux_status" = "Not running" ]; then
        print_status "warning" "Session '$TMUX_SESSION_NAME': not running"
    else
        print_status "success" "Session '$TMUX_SESSION_NAME': $tmux_status"
    fi
    echo

    echo "Ports:"
    check_component_health "Dashboard" "3000"
    check_component_health "Backend API" "5077"
    check_component_health "MAVLink2REST" "8088"
    check_component_health "WebSocket" "5551"
    echo

    echo "Commands:"
    echo "  pixeagle-service start"
    echo "  pixeagle-service stop"
    echo "  pixeagle-service attach"
    echo "  pixeagle-service logs -f"
    echo "  sudo pixeagle-service enable"
    echo "  sudo pixeagle-service disable"
}

require_root_for_system_scope() {
    if [ "$EUID" -ne 0 ]; then
        print_status "error" "System-wide login hint management requires root"
        print_status "note" "Re-run with sudo"
        return 1
    fi
    return 0
}

create_user_login_hint_script() {
    cat > "$LOGIN_HINT_SCRIPT" <<'EOF'
#!/bin/bash
# Managed by pixeagle-service login-hint

case "$-" in
    *i*) ;;
    *) return 0 ;;
esac

[ -n "${SSH_CONNECTION:-}" ] || return 0
[ -n "${PIXEAGLE_LOGIN_HINT_SHOWN:-}" ] && return 0
export PIXEAGLE_LOGIN_HINT_SHOWN=1

if ! command -v pixeagle-service >/dev/null 2>&1; then
    return 0
fi

service_state="$(systemctl is-active pixeagle.service 2>/dev/null || echo "inactive")"
enabled_state="$(systemctl is-enabled pixeagle.service 2>/dev/null || echo "disabled")"

tmux_state="stopped"
if command -v tmux >/dev/null 2>&1 && tmux has-session -t pixeagle 2>/dev/null; then
    tmux_state="running"
fi

printf '\n[PixEagle] service=%s enabled=%s tmux=%s\n' "$service_state" "$enabled_state" "$tmux_state"
printf '[PixEagle] Commands: pixeagle-service status | pixeagle-service attach | pixeagle-service logs -f\n'
printf '[PixEagle] Boot: sudo pixeagle-service enable | sudo pixeagle-service disable\n\n'
EOF
}

create_system_login_hint_script() {
    cat > "$SYSTEM_LOGIN_HINT_FILE" <<'EOF'
#!/bin/bash
# Managed by pixeagle-service login-hint --system

case "$-" in
    *i*) ;;
    *) return 0 ;;
esac

[ -n "${SSH_CONNECTION:-}" ] || return 0
[ -t 1 ] || return 0
[ -n "${PIXEAGLE_LOGIN_HINT_SHOWN:-}" ] && return 0
export PIXEAGLE_LOGIN_HINT_SHOWN=1

if ! command -v systemctl >/dev/null 2>&1; then
    return 0
fi

service_state="$(systemctl is-active pixeagle.service 2>/dev/null || echo "inactive")"
enabled_state="$(systemctl is-enabled pixeagle.service 2>/dev/null || echo "disabled")"

printf '\n[PixEagle] service=%s enabled=%s\n' "$service_state" "$enabled_state"
printf '[PixEagle] Commands: pixeagle-service status | pixeagle-service attach | pixeagle-service logs -f\n'
printf '[PixEagle] Boot: sudo pixeagle-service enable | sudo pixeagle-service disable\n\n'
EOF
}

remove_login_hint_block() {
    local bashrc_file="$1"
    [ -f "$bashrc_file" ] || return 0

    local tmp_file
    tmp_file="$(mktemp)"

    awk -v begin="$LOGIN_HINT_BLOCK_BEGIN" -v end="$LOGIN_HINT_BLOCK_END" '
        $0 == begin {skip=1; next}
        $0 == end {skip=0; next}
        !skip {print}
    ' "$bashrc_file" > "$tmp_file"

    cat "$tmp_file" > "$bashrc_file"
    rm -f "$tmp_file"
}

login_hint_enable_user() {
    if ! detect_service_user; then
        return 1
    fi

    mkdir -p "$LOGIN_HINT_DIR"
    create_user_login_hint_script
    chmod 0644 "$LOGIN_HINT_SCRIPT"

    [ -f "$BASHRC_PATH" ] || touch "$BASHRC_PATH"
    remove_login_hint_block "$BASHRC_PATH"

    cat >> "$BASHRC_PATH" <<EOF
$LOGIN_HINT_BLOCK_BEGIN
if [ -f "$LOGIN_HINT_SCRIPT" ]; then
    . "$LOGIN_HINT_SCRIPT"
fi
$LOGIN_HINT_BLOCK_END
EOF

    if [ "$(id -un)" = "root" ] && [ "$SERVICE_USER" != "root" ]; then
        chown "$SERVICE_USER:$SERVICE_USER" "$LOGIN_HINT_SCRIPT" "$BASHRC_PATH" >/dev/null 2>&1 || true
    fi

    print_status "success" "SSH login hint enabled for user '$SERVICE_USER' (per-user scope)"
}

login_hint_disable_user() {
    if ! detect_service_user; then
        return 1
    fi

    if [ -f "$LOGIN_HINT_SCRIPT" ]; then
        rm -f "$LOGIN_HINT_SCRIPT"
    fi

    remove_login_hint_block "$BASHRC_PATH"

    if [ "$(id -un)" = "root" ] && [ "$SERVICE_USER" != "root" ] && [ -f "$BASHRC_PATH" ]; then
        chown "$SERVICE_USER:$SERVICE_USER" "$BASHRC_PATH" >/dev/null 2>&1 || true
    fi

    print_status "success" "SSH login hint disabled for user '$SERVICE_USER' (per-user scope)"
}

login_hint_status_user() {
    if ! detect_service_user; then
        return 1
    fi

    local script_present="no"
    local block_present="no"

    [ -f "$LOGIN_HINT_SCRIPT" ] && script_present="yes"
    if [ -f "$BASHRC_PATH" ] && grep -Fq "$LOGIN_HINT_BLOCK_BEGIN" "$BASHRC_PATH"; then
        block_present="yes"
    fi

    echo "Login Hint Status (per-user)"
    echo "============================"
    echo "  User: $SERVICE_USER"
    echo "  Script: $LOGIN_HINT_SCRIPT ($script_present)"
    echo "  Bashrc block: $block_present"

    if [ "$script_present" = "yes" ] && [ "$block_present" = "yes" ]; then
        print_status "success" "Login hint is enabled"
    else
        print_status "warning" "Login hint is disabled"
    fi
}

login_hint_enable_system() {
    require_root_for_system_scope || return 1

    create_system_login_hint_script
    chmod 0644 "$SYSTEM_LOGIN_HINT_FILE"
    print_status "success" "SSH login hint enabled for all users (system scope)"
}

login_hint_disable_system() {
    require_root_for_system_scope || return 1

    if [ -f "$SYSTEM_LOGIN_HINT_FILE" ]; then
        rm -f "$SYSTEM_LOGIN_HINT_FILE"
        print_status "success" "SSH login hint disabled for all users (system scope)"
    else
        print_status "warning" "System login hint file not found: $SYSTEM_LOGIN_HINT_FILE"
    fi
}

login_hint_status_system() {
    local system_present="no"
    [ -f "$SYSTEM_LOGIN_HINT_FILE" ] && system_present="yes"

    echo "Login Hint Status (system)"
    echo "=========================="
    echo "  File: $SYSTEM_LOGIN_HINT_FILE ($system_present)"

    if [ "$system_present" = "yes" ]; then
        print_status "success" "System-wide login hint is enabled"
    else
        print_status "warning" "System-wide login hint is disabled"
    fi
}

login_hint_enable() {
    local scope="${1:-user}"
    case "$scope" in
        user)
            login_hint_enable_user
            ;;
        system)
            login_hint_enable_system
            ;;
        *)
            print_status "error" "Unknown login-hint scope: $scope"
            return 1
            ;;
    esac
}

login_hint_disable() {
    local scope="${1:-user}"
    case "$scope" in
        user)
            login_hint_disable_user
            ;;
        system)
            login_hint_disable_system
            ;;
        *)
            print_status "error" "Unknown login-hint scope: $scope"
            return 1
            ;;
    esac
}

login_hint_status() {
    local scope="${1:-user}"
    case "$scope" in
        user)
            login_hint_status_user
            ;;
        system)
            login_hint_status_system
            ;;
        *)
            print_status "error" "Unknown login-hint scope: $scope"
            return 1
            ;;
    esac
}

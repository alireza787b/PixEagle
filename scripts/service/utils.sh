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
PORTS_HELPER="$PROJECT_ROOT/scripts/lib/ports.sh"
OWNERSHIP_HELPER="$PROJECT_ROOT/scripts/lib/runtime_ownership.sh"

# Shared port helpers are optional; fallback defaults are still used below.
source "$PORTS_HELPER" 2>/dev/null || true
if ! source "$OWNERSHIP_HELPER" 2>/dev/null; then
    echo "[ERROR] Missing runtime ownership helper: $OWNERSHIP_HELPER" >&2
    return 1 2>/dev/null || exit 1
fi

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
    SERVICE_GROUP="$(id -gn "$SERVICE_USER")" || {
        print_status "error" "Could not resolve the primary group for '$SERVICE_USER'"
        return 1
    }

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

    export SERVICE_USER SERVICE_GROUP SERVICE_HOME USER_PIXEAGLE_DIR PROJECT_ROOT
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

service_active_state() {
    local state=""
    have_systemd || return 2
    state="$(systemctl show --property=ActiveState --value \
        "${SERVICE_NAME}.service" 2>/dev/null)" || return 2
    case "$state" in
        active|inactive|activating|deactivating|failed|reloading|maintenance)
            printf '%s\n' "$state"
            ;;
        *) return 2 ;;
    esac
}

service_load_state() {
    local state=""
    have_systemd || return 2
    state="$(systemctl show --property=LoadState --value \
        "${SERVICE_NAME}.service" 2>/dev/null)" || return 2
    case "$state" in
        loaded|not-found) printf '%s\n' "$state" ;;
        *) return 2 ;;
    esac
}

service_enabled_state() {
    local state=""
    have_systemd || return 2
    state="$(systemctl show --property=UnitFileState --value \
        "${SERVICE_NAME}.service" 2>/dev/null)" || return 2
    [[ -n "$state" ]] || return 2
    printf '%s\n' "$state"
}

is_service_enabled() {
    local state
    state="$(service_enabled_state)" || return $?
    [[ "$state" == enabled || "$state" == enabled-runtime ]]
}

is_service_active() {
    local state
    state="$(service_active_state)" || return $?
    [[ "$state" == active ]]
}

tmux_socket_for_mode() {
    local runtime_mode="$1"
    if [ -z "${SERVICE_USER:-}" ]; then
        detect_service_user >/dev/null 2>&1 || return 1
    fi
    pixeagle_tmux_socket_name \
        "$PROJECT_ROOT" "$runtime_mode" "$(id -u "$SERVICE_USER")"
}

is_tmux_session_present_for_mode() {
    local runtime_mode="$1"
    command -v tmux >/dev/null 2>&1 || return 1
    if [ -z "${SERVICE_USER:-}" ]; then
        detect_service_user >/dev/null 2>&1 || return 1
    fi
    local socket_name
    socket_name="$(tmux_socket_for_mode "$runtime_mode")" || return 1
    run_as_service_user bash -c \
        'source "$1" && pixeagle_tmux_session_exists "$2" "$3"' \
        _ "$OWNERSHIP_HELPER" "$socket_name" "$TMUX_SESSION_NAME"
}

is_tmux_session_active_for_mode() {
    local runtime_mode="$1"
    is_tmux_session_present_for_mode "$runtime_mode" || return 1
    local socket_name
    socket_name="$(tmux_socket_for_mode "$runtime_mode")" || return 1
    run_as_service_user bash -c \
        'source "$1" || exit 1
         run_id="$(pixeagle_tmux_environment_value "$2" "$3" PIXEAGLE_RUN_ID 2>/dev/null || true)"
         pixeagle_run_id_is_valid "$run_id" || exit 1
         pixeagle_tmux_session_is_owned "$2" "$3" "$4" "$5" "$run_id"' \
        _ "$OWNERSHIP_HELPER" "$socket_name" "$TMUX_SESSION_NAME" \
        "$PROJECT_ROOT" "$runtime_mode"
}

is_tmux_session_active() {
    is_tmux_session_active_for_mode service
}

is_tmux_session_present() {
    is_tmux_session_present_for_mode service
}

runtime_run_id_for_mode() {
    local runtime_mode="$1"
    if [ -z "${SERVICE_USER:-}" ]; then
        detect_service_user >/dev/null 2>&1 || return 1
    fi
    local socket_name
    socket_name="$(tmux_socket_for_mode "$runtime_mode")" || return 1
    run_as_service_user bash -c '
        source "$1" || exit 1
        pixeagle_tmux_environment_value "$2" "$3" PIXEAGLE_RUN_ID
    ' _ "$OWNERSHIP_HELPER" "$socket_name" "$TMUX_SESSION_NAME"
}

runtime_is_ready_for_mode() {
    local runtime_mode="$1"
    local expected_run_id="${2:-}"
    if [ -z "${SERVICE_USER:-}" ]; then
        detect_service_user >/dev/null 2>&1 || return 1
    fi
    local socket_name
    socket_name="$(tmux_socket_for_mode "$runtime_mode")" || return 1
    run_as_service_user bash -c '
        source "$1" || exit 1
        run_id="$(pixeagle_tmux_environment_value "$2" "$3" PIXEAGLE_RUN_ID 2>/dev/null || true)"
        pixeagle_run_id_is_valid "$run_id" || exit 1
        [[ -z "$6" || "$run_id" != "$6" ]] || exit 1
        pixeagle_tmux_runtime_is_healthy "$2" "$3" "$4" "$5" "$run_id"
    ' _ "$OWNERSHIP_HELPER" "$socket_name" "$TMUX_SESSION_NAME" \
        "$PROJECT_ROOT" "$runtime_mode" "$expected_run_id"
}

wait_for_runtime_ready_for_mode() {
    local runtime_mode="$1"
    local timeout_seconds="${2:-300}"
    local previous_run_id="${3:-}"
    local attempt

    [[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]] || return 1
    for ((attempt=0; attempt<timeout_seconds; attempt++)); do
        if runtime_is_ready_for_mode "$runtime_mode" "$previous_run_id"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

get_tmux_session_status() {
    local runtime_mode="${1:-service}"
    if ! is_tmux_session_present_for_mode "$runtime_mode"; then
        echo "Not running"
        return 0
    fi

    if ! is_tmux_session_active_for_mode "$runtime_mode"; then
        echo "Conflict (session is not owned by this checkout)"
        return 0
    fi

    local windows socket_name
    socket_name="$(tmux_socket_for_mode "$runtime_mode")" || return 1
    windows="$(run_as_service_user tmux -L "$socket_name" display-message \
        -t "=$TMUX_SESSION_NAME" -p "#{session_windows}" 2>/dev/null || true)"
    windows="${windows:-unknown}"
    echo "Active (${windows} windows)"
}

check_component_health() {
    local component="$1"
    local port="$2"
    local runtime_mode="${3:-service}"
    local expected_run_id="${4:-}"

    if ! command -v lsof >/dev/null 2>&1; then
        echo -e "${YELLOW}*${NC} $component (port $port) - cannot check (lsof missing)"
        return 0
    fi

    local pids pid found=false
    pids="$(lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u)"
    if [ -z "$pids" ]; then
        echo -e "${RED}*${NC} $component (port $port) - not responding"
        return 0
    fi
    for pid in $pids; do
        if ! pixeagle_pid_is_owned "$pid" "$PROJECT_ROOT" \
            "$(id -u "$SERVICE_USER")" "$runtime_mode" "$expected_run_id"; then
            echo -e "${RED}*${NC} $component (port $port) - foreign listener, not PixEagle (pid $pid)"
            return 0
        fi
        found=true
    done
    if [ "$found" = "true" ]; then
        echo -e "${GREEN}*${NC} $component (port $port, ownership verified)"
    fi
}

probe_media_health() {
    local backend_port="${1:-5077}"
    local media_health_url="${PIXEAGLE_MEDIA_HEALTH_URL:-http://127.0.0.1:${backend_port}/api/v1/streams/media-health}"

    echo "Media health:"

    if ! command -v "${PYTHON:-python3}" >/dev/null 2>&1; then
        echo "  Backend media: unavailable (python3 missing)"
        echo "  Remote receipt: not proven by this process-local check"
        return 0
    fi

    PIXEAGLE_MEDIA_HEALTH_URL="$media_health_url" "${PYTHON:-python3}" - <<'PY'
import json
import os
import socket
import sys
import urllib.error
import urllib.request

url = os.environ.get("PIXEAGLE_MEDIA_HEALTH_URL", "").strip()
token = os.environ.get("PIXEAGLE_MEDIA_HEALTH_BEARER_TOKEN", "").strip()
token_file = os.environ.get("PIXEAGLE_MEDIA_HEALTH_BEARER_TOKEN_FILE", "").strip()
timeout_raw = os.environ.get("PIXEAGLE_MEDIA_HEALTH_TIMEOUT_S", "2").strip()

try:
    timeout_s = max(0.1, float(timeout_raw))
except ValueError:
    timeout_s = 2.0

if token_file:
    try:
        with open(os.path.expanduser(token_file), "r", encoding="utf-8") as handle:
            token = handle.read().strip()
    except OSError as exc:
        print(f"  Backend media: auth token file unreadable ({exc.__class__.__name__})")
        print("  Remote receipt: not proven by this process-local check")
        sys.exit(0)

headers = {"Accept": "application/json"}
if token:
    headers["Authorization"] = f"Bearer {token}"

request = urllib.request.Request(url, headers=headers, method="GET")

try:
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        status_code = response.status
        raw_body = response.read(262144)
except urllib.error.HTTPError as exc:
    status_code = exc.code
    if status_code in (401, 403):
        print(f"  Backend media: auth required (HTTP {status_code}; requires media:read)")
        print("  Token: set PIXEAGLE_MEDIA_HEALTH_BEARER_TOKEN_FILE for machine_bearer/browser_session probes")
    elif status_code == 404:
        print("  Backend media: typed media-health route missing (HTTP 404)")
    else:
        print(f"  Backend media: probe failed (HTTP {status_code})")
    print("  Remote receipt: not proven by this process-local check")
    sys.exit(0)
except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
    reason = getattr(exc, "reason", exc)
    print(f"  Backend media: unavailable ({reason.__class__.__name__})")
    print("  Remote receipt: not proven by this process-local check")
    sys.exit(0)

if status_code < 200 or status_code >= 300:
    print(f"  Backend media: probe failed (HTTP {status_code})")
    print("  Remote receipt: not proven by this process-local check")
    sys.exit(0)

try:
    payload = json.loads(raw_body.decode("utf-8"))
except (UnicodeDecodeError, json.JSONDecodeError):
    print("  Backend media: invalid response (expected JSON)")
    print("  Remote receipt: not proven by this process-local check")
    sys.exit(0)

status = payload.get("status", "unknown")
guidance = payload.get("consumer_guidance", "unknown")
frames = payload.get("frames") or {}
if not frames.get("source_available"):
    frame_state = "none"
elif frames.get("latest_frame_stale"):
    age = frames.get("latest_frame_age_s")
    frame_state = f"stale ({age}s)" if age is not None else "stale"
else:
    age = frames.get("latest_frame_age_s")
    frame_state = f"fresh ({age}s)" if age is not None else "fresh"

transport_parts = []
for transport in payload.get("transports") or []:
    name = str(transport.get("name") or "unknown")
    transport_status = str(transport.get("status") or "unknown")
    max_connections = transport.get("max_connections")
    active_connections = transport.get("active_connections")
    if max_connections is None:
        transport_parts.append(f"{name}={transport_status}")
    else:
        transport_parts.append(f"{name}={transport_status}/{active_connections or 0}")

issues = payload.get("health_issues") or []
issue_text = ", ".join(str(item) for item in issues) if issues else "none"

print(f"  Backend media: {status} ({guidance})")
print(f"  Frame publisher: {frame_state}")
print(f"  Transports: {' '.join(transport_parts) if transport_parts else 'none'}")
print(f"  Issues: {issue_text}")
print("  Remote receipt: not proven by this process-local check")
PY
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

    local required_files=(
        "$RUN_SCRIPT"
        "$STOP_SCRIPT"
        "$SERVICE_RUN_SCRIPT"
        "$OWNERSHIP_HELPER"
    )
    local file
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            print_status "error" "Required file missing: $file"
            return 1
        fi
    done

    return 0
}

validate_service_generation_values() {
    local identifier value
    for identifier in "$SERVICE_USER" "$SERVICE_GROUP"; do
        [[ "$identifier" =~ ^[A-Za-z_][A-Za-z0-9_.-]*$ ]] || {
            print_status "error" "Unsupported service user/group identifier: $identifier"
            return 1
        }
    done
    for value in "$SERVICE_HOME" "$USER_PIXEAGLE_DIR" "$SERVICE_RUN_SCRIPT"; do
        [[ "$value" == /* ]] || {
            print_status "error" "Service paths must be absolute: $value"
            return 1
        }
        case "$value" in
            *[[:space:]%\"\\]*|*$'\n'*|*$'\r'*)
                print_status "error" "Service paths cannot contain whitespace, quotes, backslashes, or percent specifiers: $value"
                return 1
                ;;
        esac
    done
}

create_service_file() {
    local service_tmp

    if ! detect_service_user; then
        return 1
    fi
    validate_service_generation_values || return 1

    service_tmp=$(umask 077 && mktemp --suffix=.service \
        "${SERVICE_FILE%/*}/.${SERVICE_NAME}.tmp.XXXXXX") || {
        print_status "error" "Unable to create a private temporary service unit"
        return 1
    }

    print_status "process" "Generating and validating $SERVICE_FILE"

    if ! cat > "$service_tmp" <<EOF
[Unit]
Description=$SERVICE_DESCRIPTION
Documentation=https://github.com/alireza787b/PixEagle
Wants=network-online.target
After=network-online.target
# Bound repeated startup failures so a bad configuration cannot create an
# unbounded systemd restart storm while the operator is recovering it.
StartLimitIntervalSec=300
StartLimitBurst=3

[Service]
Type=notify
NotifyAccess=all
Delegate=yes
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$USER_PIXEAGLE_DIR
Environment=HOME=$SERVICE_HOME
Environment=USER=$SERVICE_USER
Environment=PIXEAGLE_SERVICE_MODE=1
# Canonical runtime markers are injected only into the supervised launcher and
# component processes. Never seed them on the long-lived systemd supervisor.
UnsetEnvironment=PIXEAGLE_PROJECT_ROOT PIXEAGLE_RUN_ID PIXEAGLE_RUNTIME_MODE PIXEAGLE_SESSION_NAME PIXEAGLE_TMUX_SOCKET_NAME
Environment=PIXEAGLE_INSTALL_DIR=$USER_PIXEAGLE_DIR
ExecStart=$SERVICE_RUN_SCRIPT
Restart=on-failure
RestartSec=5
KillMode=mixed
TimeoutStartSec=300
TimeoutStopSec=45
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    then
        rm -f -- "$service_tmp"
        print_status "error" "Unable to write the temporary service unit"
        return 1
    fi

    if command -v systemd-analyze >/dev/null 2>&1; then
        if ! systemd-analyze verify "$service_tmp" >/dev/null 2>&1; then
            rm -f -- "$service_tmp"
            print_status "error" "Generated service unit failed systemd-analyze verify"
            return 1
        fi
    else
        rm -f -- "$service_tmp"
        print_status "error" "systemd-analyze is required to verify the generated service unit"
        return 1
    fi

    if ! chmod 0644 "$service_tmp" || ! mv -f -- "$service_tmp" "$SERVICE_FILE"; then
        rm -f -- "$service_tmp"
        print_status "error" "Unable to publish the validated service unit"
        return 1
    fi

    print_status "success" "Service unit created"
}

disable_service_autostart() {
    local load_state=""
    local enabled_state=""

    if ! have_systemd; then
        print_status "error" "Cannot verify systemd state; auto-start change refused"
        return 1
    fi
    if ! load_state="$(service_load_state)"; then
        print_status "error" "Could not determine ${SERVICE_NAME}.service load state"
        return 1
    fi
    if [[ "$load_state" == not-found ]]; then
        print_status "warning" "Service unit is not installed"
        return 0
    fi
    if ! enabled_state="$(service_enabled_state)"; then
        print_status "error" "Could not determine ${SERVICE_NAME}.service enabled state"
        return 1
    fi
    case "$enabled_state" in
        enabled|enabled-runtime|linked|linked-runtime)
            systemctl disable "${SERVICE_NAME}.service" || {
                print_status "error" "Could not disable ${SERVICE_NAME}.service auto-start"
                return 1
            }
            if ! enabled_state="$(service_enabled_state)"; then
                print_status "error" "Could not verify ${SERVICE_NAME}.service disabled state"
                return 1
            fi
            case "$enabled_state" in
                enabled|enabled-runtime|linked|linked-runtime)
                    print_status "error" "${SERVICE_NAME}.service remained enabled"
                    return 1
                    ;;
            esac
            ;;
        disabled|static|indirect|masked|generated|transient|alias) ;;
        *)
            print_status "error" "Unsupported ${SERVICE_NAME}.service enabled state: $enabled_state"
            return 1
            ;;
    esac

    print_status "success" "Auto-start disabled; service unit and current runtime retained"
}

remove_service() {
    local load_state=""
    local active_state=""
    local enabled_state=""

    print_status "process" "Removing ${SERVICE_NAME}.service"

    if ! have_systemd; then
        print_status "error" "Cannot verify systemd state; service removal refused"
        return 1
    fi
    if ! load_state="$(service_load_state)"; then
        print_status "error" "Could not determine ${SERVICE_NAME}.service load state"
        return 1
    fi
    if [[ "$load_state" == not-found ]]; then
        if [[ -e "$SERVICE_FILE" || -L "$SERVICE_FILE" ]]; then
            if [[ ! -f "$SERVICE_FILE" || -L "$SERVICE_FILE" ]]; then
                print_status "error" "Refusing unsafe service unit path: $SERVICE_FILE"
                return 1
            fi
            if ! rm -f -- "$SERVICE_FILE" || ! systemctl daemon-reload; then
                print_status "error" "Could not remove and reload the unloaded service unit"
                return 1
            fi
            print_status "success" "Removed unloaded service unit"
        else
            print_status "warning" "Service unit is not installed"
        fi
        return 0
    fi
    if ! active_state="$(service_active_state)"; then
        print_status "error" "Could not determine ${SERVICE_NAME}.service active state"
        return 1
    fi
    case "$active_state" in
        active|activating|deactivating|reloading|maintenance)
            if ! systemctl stop "${SERVICE_NAME}.service"; then
                print_status "error" "Could not stop ${SERVICE_NAME}.service"
                return 1
            fi
            if ! active_state="$(service_active_state)" \
                || [[ "$active_state" != inactive && "$active_state" != failed ]]; then
                print_status "error" "Could not verify ${SERVICE_NAME}.service stopped state"
                return 1
            fi
            ;;
        inactive|failed) ;;
        *)
            print_status "error" "Unsupported ${SERVICE_NAME}.service active state: $active_state"
            return 1
            ;;
    esac

    if ! enabled_state="$(service_enabled_state)"; then
        print_status "error" "Could not determine ${SERVICE_NAME}.service enabled state"
        return 1
    fi
    case "$enabled_state" in
        enabled|enabled-runtime|linked|linked-runtime)
            if ! systemctl disable "${SERVICE_NAME}.service"; then
                print_status "error" "Could not disable ${SERVICE_NAME}.service"
                return 1
            fi
            if ! enabled_state="$(service_enabled_state)"; then
                print_status "error" "Could not verify ${SERVICE_NAME}.service disabled state"
                return 1
            fi
            case "$enabled_state" in
                enabled|enabled-runtime|linked|linked-runtime)
                    print_status "error" "${SERVICE_NAME}.service remained enabled"
                    return 1
                    ;;
            esac
            ;;
        disabled|static|indirect|masked|generated|transient|alias) ;;
        *)
            print_status "error" "Unsupported ${SERVICE_NAME}.service enabled state: $enabled_state"
            return 1
            ;;
    esac

    if [[ -e "$SERVICE_FILE" || -L "$SERVICE_FILE" ]]; then
        if [[ ! -f "$SERVICE_FILE" || -L "$SERVICE_FILE" ]]; then
            print_status "error" "Refusing unsafe service unit path: $SERVICE_FILE"
            return 1
        fi
        if ! rm -f -- "$SERVICE_FILE" || ! systemctl daemon-reload; then
            print_status "error" "Could not remove and reload the service unit"
            return 1
        fi
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

attach_to_session() {
    if ! detect_service_user; then
        return 1
    fi

    local runtime_mode="" service_present=false manual_present=false
    is_tmux_session_present_for_mode service && service_present=true
    is_tmux_session_present_for_mode manual && manual_present=true

    if [[ "$service_present" == "true" && "$manual_present" == "true" ]]; then
        print_status "error" "Both service and manual tmux runtimes exist; refusing an ambiguous attach"
        return 1
    elif [[ "$service_present" == "true" ]]; then
        runtime_mode=service
    elif [[ "$manual_present" == "true" ]]; then
        runtime_mode=manual
    else
        print_status "warning" "tmux session '$TMUX_SESSION_NAME' is not running"
        print_status "note" "Start with: pixeagle-service start"
        return 1
    fi
    if ! is_tmux_session_active_for_mode "$runtime_mode"; then
        print_status "error" "Refusing $runtime_mode session without an exact owned run identity"
        return 1
    fi

    print_status "info" "Attaching to tmux session '$TMUX_SESSION_NAME'"
    print_status "note" "Detach without stopping: Ctrl+B then D"
    echo
    local socket_name
    socket_name="$(tmux_socket_for_mode "$runtime_mode")" || return 1
    run_as_service_user tmux -L "$socket_name" attach -t "=$TMUX_SESSION_NAME"
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
    local tmux_status runtime_mode active_runtime_mode="" active_run_id=""
    for runtime_mode in service manual; do
        tmux_status="$(get_tmux_session_status "$runtime_mode")"
        if [ "$tmux_status" = "Not running" ]; then
            print_status "warning" "${runtime_mode} session: not running"
        elif [[ "$tmux_status" == Conflict* ]]; then
            print_status "error" "${runtime_mode} session: $tmux_status"
        else
            print_status "success" "${runtime_mode} session: $tmux_status"
            active_runtime_mode="$runtime_mode"
            active_run_id="$(runtime_run_id_for_mode "$runtime_mode" 2>/dev/null || true)"
        fi
    done
    echo

    echo "Ports:"
    local runtime_ports_helper="$USER_PIXEAGLE_DIR/scripts/lib/ports.sh"
    source "$runtime_ports_helper" 2>/dev/null || true

    local dashboard_port="${PIXEAGLE_DEFAULT_DASHBOARD_PORT:-3040}"
    local backend_port="${PIXEAGLE_DEFAULT_BACKEND_PORT:-5077}"
    local mavlink2rest_port="${PIXEAGLE_DEFAULT_MAVLINK2REST_PORT:-8088}"
    local websocket_port="${PIXEAGLE_DEFAULT_WEBSOCKET_PORT:-5551}"

    if declare -f resolve_dashboard_port >/dev/null 2>&1; then
        dashboard_port="$(resolve_dashboard_port "$USER_PIXEAGLE_DIR/dashboard" 2>/dev/null || echo "$dashboard_port")"
    fi
    if declare -f resolve_backend_port >/dev/null 2>&1; then
        backend_port="$(resolve_backend_port "$USER_PIXEAGLE_DIR/configs/config.yaml" 2>/dev/null || echo "$backend_port")"
    fi

    if [ -n "$active_runtime_mode" ]; then
        check_component_health "Dashboard" "$dashboard_port" "$active_runtime_mode" "$active_run_id"
        check_component_health "Backend API" "$backend_port" "$active_runtime_mode" "$active_run_id"
        check_component_health "MAVLink2REST" "$mavlink2rest_port" "$active_runtime_mode" "$active_run_id"
        check_component_health "Legacy telemetry WebSocket" "$websocket_port" "$active_runtime_mode" "$active_run_id"
    else
        print_status "warning" "No owned runtime contract is active; port ownership not attributed"
    fi
    echo

    probe_media_health "$backend_port"
    echo

    echo "Commands:"
    echo "  pixeagle-service start"
    echo "  pixeagle-service stop"
    echo "  pixeagle-service attach"
    echo "  pixeagle-service logs -f"
    echo "  sudo pixeagle-service enable"
    echo "  sudo pixeagle-service disable"
    echo "  sudo pixeagle-service uninstall"
}

require_root_for_system_scope() {
    if [ "$EUID" -ne 0 ]; then
        print_status "error" "System-wide login hint management requires root"
        print_status "note" "Re-run with sudo"
        return 1
    fi
    return 0
}

write_login_hint_script() {
    local target_file="$1"
    local scope_label="$2"

    cat > "$target_file" <<'EOF'
#!/bin/bash
# Managed by pixeagle-service login-hint (__SCOPE__)

case "$-" in
    *i*) ;;
    *) return 0 ;;
esac

[ -n "${SSH_CONNECTION:-}" ] || return 0
[ -t 1 ] || return 0
[ -n "${PIXEAGLE_LOGIN_HINT_SHOWN:-}" ] && return 0
export PIXEAGLE_LOGIN_HINT_SHOWN=1

if command -v tput >/dev/null 2>&1 && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
    C_CYAN="$(printf '\033[1;36m')"
    C_BOLD="$(printf '\033[1m')"
    C_DIM="$(printf '\033[2m')"
    C_NC="$(printf '\033[0m')"
else
    C_CYAN=""
    C_BOLD=""
    C_DIM=""
    C_NC=""
fi

get_service_workdir() {
    local wd=""

    if command -v systemctl >/dev/null 2>&1; then
        wd="$(systemctl show -p WorkingDirectory --value pixeagle.service 2>/dev/null)"
        if [ -n "$wd" ] && [ -d "$wd" ]; then
            printf '%s\n' "$wd"
            return 0
        fi
    fi

    if [ -d "$HOME/PixEagle" ]; then
        printf '%s\n' "$HOME/PixEagle"
        return 0
    fi

    return 1
}

get_yaml_int_value() {
    local file_path="$1"
    local key_name="$2"

    [ -f "$file_path" ] || return 1

    awk -F: -v key="$key_name" '
        $1 ~ "^[[:space:]]*" key "[[:space:]]*$" {
            val=$2
            sub(/#.*/, "", val)
            gsub(/[[:space:]]/, "", val)
            if (val ~ /^[0-9]+$/) {
                print val
                exit 0
            }
        }
    ' "$file_path"
}

get_env_int_value() {
    local file_path="$1"
    local key_name="$2"

    [ -f "$file_path" ] || return 1

    grep -E "^${key_name}=[0-9]+$" "$file_path" 2>/dev/null | head -n 1 | cut -d= -f2
}

print_pixeagle_ascii_banner() {
    local banner_file=""

    if [ -n "$repo_dir" ] && [ -f "$repo_dir/scripts/banner.txt" ]; then
        banner_file="$repo_dir/scripts/banner.txt"
    fi

    if [ -n "$banner_file" ]; then
        while IFS= read -r line; do
            printf '%s\n' "${C_CYAN}${line}${C_NC}"
        done < "$banner_file"
        return 0
    fi

    # Fallback keeps output stable even if scripts/banner.txt is missing.
    printf '%s\n' "${C_CYAN} _____ _      ______            _${C_NC}"
    printf '%s\n' "${C_CYAN}|  __ (_)    |  ____|          | |${C_NC}"
    printf '%s\n' "${C_CYAN}| |__) |__  _| |__   __ _  __ _| | ___${C_NC}"
    printf '%s\n' "${C_CYAN}|  ___/ \\ \\/ /  __| / _\` |/ _\` | |/ _ \\${C_NC}"
    printf '%s\n' "${C_CYAN}| |   | |>  <| |___| (_| | (_| | |  __/${C_NC}"
    printf '%s\n' "${C_CYAN}|_|   |_/_/\\_\\______\\__,_|\\__, |_|\\___|${C_NC}"
    printf '%s\n' "${C_CYAN}                           __/ |${C_NC}"
    printf '%s\n' "${C_CYAN}                          |___/${C_NC}"
}

service_state="unknown"
enabled_state="unknown"
if command -v systemctl >/dev/null 2>&1; then
    service_state="$(systemctl is-active pixeagle.service 2>/dev/null || true)"
    enabled_state="$(systemctl is-enabled pixeagle.service 2>/dev/null || true)"
    [ -n "$service_state" ] || service_state="inactive"
    [ -n "$enabled_state" ] || enabled_state="disabled"
fi

repo_dir="$(get_service_workdir 2>/dev/null || true)"

backend_port="5077"
dashboard_port="3040"
if [ -n "$repo_dir" ] && [ -f "$repo_dir/configs/config.yaml" ]; then
    cfg_backend_port="$(get_yaml_int_value "$repo_dir/configs/config.yaml" "HTTP_STREAM_PORT" 2>/dev/null || true)"
    [ -n "$cfg_backend_port" ] && backend_port="$cfg_backend_port"
fi
if [ -n "$repo_dir" ] && [ -f "$repo_dir/dashboard/env_default.yaml" ]; then
    cfg_dashboard_default_port="$(get_yaml_int_value "$repo_dir/dashboard/env_default.yaml" "PORT" 2>/dev/null || true)"
    [ -n "$cfg_dashboard_default_port" ] && dashboard_port="$cfg_dashboard_default_port"
fi
if [ -n "$repo_dir" ] && [ -f "$repo_dir/dashboard/.env" ]; then
    cfg_dashboard_port="$(get_env_int_value "$repo_dir/dashboard/.env" "PORT" 2>/dev/null || true)"
    [ -n "$cfg_dashboard_port" ] && dashboard_port="$cfg_dashboard_port"
fi

branch_name="unknown"
commit_id="unknown"
commit_date="unknown"
origin_url="unknown"
if [ -n "$repo_dir" ] && [ -d "$repo_dir/.git" ] && command -v git >/dev/null 2>&1; then
    branch_name="$(git -C "$repo_dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"
    commit_id="$(git -C "$repo_dir" rev-parse --short HEAD 2>/dev/null || echo "unknown")"
    commit_date="$(git -C "$repo_dir" show -s --date=format:'%Y-%m-%d %H:%M:%S %z' --format=%cd HEAD 2>/dev/null || echo "unknown")"
    origin_url="$(git -C "$repo_dir" remote get-url origin 2>/dev/null || echo "unknown")"
fi

host_name="$(hostname 2>/dev/null || echo "unknown")"

printf '\n'
print_pixeagle_ascii_banner
printf '%s\n' " ${C_BOLD}[PixEagle]${C_NC} host=${host_name} service=${service_state} enabled=${enabled_state}"

if [ -n "$repo_dir" ]; then
    printf '%s\n' " ${C_DIM}[Version] repo=${repo_dir}${C_NC}"
fi
printf '%s\n' " ${C_DIM}[Version] branch=${branch_name} commit=${commit_id} date=${commit_date}${C_NC}"
printf '%s\n' " ${C_DIM}[Version] origin=${origin_url}${C_NC}"

printf '%s\n' " [PixEagle] Access URLs:"
printf '   - local dashboard: http://127.0.0.1:%s\n' "$dashboard_port"
printf '   - local backend:   http://127.0.0.1:%s\n' "$backend_port"
printf '   - SSH tunnel:      ssh -L %s:127.0.0.1:%s -L %s:127.0.0.1:%s <host>\n' "$dashboard_port" "$dashboard_port" "$backend_port" "$backend_port"
printf '%s\n' " [PixEagle] Exposure: backend/dashboard are local-only by default; do not expose backend 5077 directly."

printf '%s\n' " [PixEagle] Commands: pixeagle-service start | pixeagle-service stop | pixeagle-service status"
printf '%s\n' " [PixEagle] Inspect: pixeagle-service attach | pixeagle-service logs -f"
printf '%s\n' " [PixEagle] Boot: sudo pixeagle-service enable | sudo pixeagle-service disable"
printf '%s\n\n' " [PixEagle] Remove managed unit: sudo pixeagle-service uninstall"
EOF

    sed -i "s/__SCOPE__/${scope_label}/g" "$target_file"
}

create_user_login_hint_script() {
    write_login_hint_script "$LOGIN_HINT_SCRIPT" "user"
}

create_system_login_hint_script() {
    write_login_hint_script "$SYSTEM_LOGIN_HINT_FILE" "system"
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

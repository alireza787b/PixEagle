#!/usr/bin/env bash
# Stop one explicitly identified PixEagle runtime without signalling unrelated
# processes. Manual and service runtimes use separate tmux sockets and modes.

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd -P)"
SESSION_NAME="pixeagle"
LEGACY_DEFAULT_SESSION=false
ASSUME_YES=false
STOP_FAILED=false
LEGACY_PROCESS_RECORDS=()

# shellcheck source=scripts/lib/common.sh
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; DIM=''; NC=''
    CHECK='OK'; CROSS='ERROR'; WARN='WARN'
fi
# shellcheck source=scripts/lib/ports.sh
source "$SCRIPTS_DIR/lib/ports.sh" 2>/dev/null || true
# shellcheck source=scripts/lib/runtime_ownership.sh
if ! source "$SCRIPTS_DIR/lib/runtime_ownership.sh" 2>/dev/null; then
    echo "Refusing to stop processes: runtime ownership helper is unavailable" >&2
    exit 1
fi
# shellcheck source=scripts/lib/setup_lock.sh
if ! source "$SCRIPTS_DIR/lib/setup_lock.sh" 2>/dev/null; then
    echo "Refusing to stop processes: resource lock helper is unavailable" >&2
    exit 1
fi
LIFECYCLE_RESOURCE="$(pixeagle_lifecycle_resource "$PIXEAGLE_DIR")" || {
    echo "Refusing to stop processes: lifecycle resource is unavailable" >&2
    exit 1
}

INTERNAL_LIFECYCLE_STOP=false
if [[ "${1:-}" == "--internal-lifecycle-stop" ]]; then
    INTERNAL_LIFECYCLE_STOP=true
    shift
fi
ORIGINAL_ARGS=("$@")

show_help() {
    cat <<'EOF'
Usage: bash scripts/stop.sh [OPTIONS]

Options:
  --mode manual|service       Stop that supervised runtime mode (default: env/manual)
  --legacy-default-session    One-time migration: inspect and stop the pre-ownership
                              'pixeagle' session on the user's default tmux server
  --yes                       Confirm a verified legacy migration non-interactively
  -h, --help                  Show this help

Normal users should run `make stop`. The legacy option is only for a runtime
created by PixEagle before dedicated ownership-aware tmux sockets were added.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)
            shift
            PIXEAGLE_RUNTIME_MODE="${1:-}"
            ;;
        --legacy-default-session)
            LEGACY_DEFAULT_SESSION=true
            ;;
        --yes)
            ASSUME_YES=true
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            show_help >&2
            exit 2
            ;;
    esac
    shift
done

PIXEAGLE_RUNTIME_MODE="${PIXEAGLE_RUNTIME_MODE:-manual}"
if ! pixeagle_runtime_mode_is_valid "$PIXEAGLE_RUNTIME_MODE"; then
    echo "PIXEAGLE_RUNTIME_MODE must be manual or service" >&2
    exit 2
fi
TMUX_SOCKET_NAME="$(pixeagle_tmux_socket_name "$PIXEAGLE_DIR" "$PIXEAGLE_RUNTIME_MODE")"

tmux_runtime() {
    pixeagle_tmux "$TMUX_SOCKET_NAME" "$@"
}

default_tmux_session_exists_exact() {
    local listed_name
    command -v tmux >/dev/null 2>&1 || return 1
    while IFS= read -r listed_name; do
        [[ "$listed_name" == "$SESSION_NAME" ]] && return 0
    done < <(pixeagle_default_tmux list-sessions -F '#{session_name}' 2>/dev/null || true)
    return 1
}

legacy_session_matches_checkout() {
    local path pane_pid pane_uid canonical_path found=false
    default_tmux_session_exists_exact || return 1

    while IFS='|' read -r path pane_pid; do
        [[ -n "$path" && "$pane_pid" =~ ^[1-9][0-9]*$ ]] || return 1
        pane_uid="$(ps -o uid= -p "$pane_pid" 2>/dev/null | tr -d '[:space:]')"
        [[ "$pane_uid" == "$(id -u)" ]] || return 1
        canonical_path="$(realpath -m -- "$path" 2>/dev/null || true)"
        case "$canonical_path" in
            "$PIXEAGLE_DIR"|"$PIXEAGLE_DIR"/*) ;;
            *) return 1 ;;
        esac
        found=true
    done < <(pixeagle_default_tmux list-panes -t "=$SESSION_NAME" -s \
        -F '#{pane_current_path}|#{pane_pid}' 2>/dev/null || true)
    [[ "$found" == "true" ]]
}

legacy_pid_matches_checkout_identity() {
    local pid="$1"
    local expected_start_token="$2"
    local process_uid canonical_path

    [[ "$(pixeagle_pid_start_token "$pid" 2>/dev/null || true)" == "$expected_start_token" ]] || return 1
    process_uid="$(pixeagle_proc_uid "/proc/$pid" 2>/dev/null || true)"
    [[ "$process_uid" == "$(id -u)" ]] || return 1
    canonical_path="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    case "$canonical_path" in
        "$PIXEAGLE_DIR"|"$PIXEAGLE_DIR"/*) return 0 ;;
        *) return 1 ;;
    esac
}

capture_legacy_process_tree() {
    local pane_pid pid ppid start_token changed
    local -a process_rows=()
    local -A selected=()

    while IFS= read -r pane_pid; do
        [[ "$pane_pid" =~ ^[1-9][0-9]*$ ]] || return 1
        selected["$pane_pid"]=1
    done < <(pixeagle_default_tmux list-panes -t "=$SESSION_NAME" -s \
        -F '#{pane_pid}' 2>/dev/null || true)
    (( ${#selected[@]} > 0 )) || return 1

    mapfile -t process_rows < <(ps -e -o pid=,ppid= 2>/dev/null)
    changed=true
    while [[ "$changed" == "true" ]]; do
        changed=false
        for row in "${process_rows[@]}"; do
            read -r pid ppid <<< "$row"
            [[ "$pid" =~ ^[1-9][0-9]*$ && "$ppid" =~ ^[0-9]+$ ]] || continue
            if [[ -n "${selected[$ppid]:-}" && -z "${selected[$pid]:-}" ]]; then
                selected["$pid"]=1
                changed=true
            fi
        done
    done

    LEGACY_PROCESS_RECORDS=()
    for pid in "${!selected[@]}"; do
        start_token="$(pixeagle_pid_start_token "$pid" 2>/dev/null || true)"
        [[ -n "$start_token" ]] || return 1
        legacy_pid_matches_checkout_identity "$pid" "$start_token" || return 1
        LEGACY_PROCESS_RECORDS+=("$pid|$start_token")
    done
}

terminate_legacy_record() {
    local record="$1"
    local pid="${record%%|*}"
    local start_token="${record##*|}"

    legacy_pid_matches_checkout_identity "$pid" "$start_token" || {
        [[ "$(pixeagle_pid_start_token "$pid" 2>/dev/null || true)" != "$start_token" ]]
        return $?
    }
    kill -TERM "$pid" 2>/dev/null || true
    pixeagle_wait_for_pid_exit "$pid" "$start_token" 30 0.1 && return 0
    legacy_pid_matches_checkout_identity "$pid" "$start_token" || return 1
    kill -KILL "$pid" 2>/dev/null || true
    pixeagle_wait_for_pid_exit "$pid" "$start_token" 30 0.1
}

stop_legacy_session() {
    if ! default_tmux_session_exists_exact; then
        echo "No legacy default tmux session '$SESSION_NAME' is running"
        return 0
    fi
    if ! legacy_session_matches_checkout; then
        echo "Refusing legacy session: not every pane belongs to this user and checkout" >&2
        return 1
    fi
    echo "Verified legacy PixEagle panes under: $PIXEAGLE_DIR"
    pixeagle_default_tmux list-panes -t "=$SESSION_NAME" -s \
        -F '  #{session_name}:#{window_index}.#{pane_index} #{pane_current_path} pid=#{pane_pid}'
    if [[ "$ASSUME_YES" != "true" ]]; then
        [[ -t 0 ]] || {
            echo "Interactive confirmation is unavailable; rerun with --yes after reviewing the panes" >&2
            return 1
        }
        read -r -p "Stop this verified legacy session? [y/N]: " reply
        [[ "$reply" =~ ^[Yy]$ ]] || return 1
    fi
    if ! capture_legacy_process_tree; then
        echo "Refusing legacy migration: could not prove every pane descendant belongs to this checkout" >&2
        return 1
    fi

    while IFS= read -r target; do
        pixeagle_default_tmux send-keys -t "$target" C-c 2>/dev/null || true
    done < <(pixeagle_default_tmux list-panes -t "=$SESSION_NAME" -s \
        -F '#{session_name}:#{window_index}.#{pane_index}' 2>/dev/null || true)
    sleep 2
    if default_tmux_session_exists_exact; then
        pixeagle_default_tmux kill-session -t "=$SESSION_NAME" || return 1
    fi
    local record failed=false
    for record in "${LEGACY_PROCESS_RECORDS[@]}"; do
        terminate_legacy_record "$record" || failed=true
    done
    if default_tmux_session_exists_exact; then
        echo "Legacy default tmux session is still present after stop" >&2
        failed=true
    fi
    if [[ "$failed" == "true" ]]; then
        echo "Legacy migration is incomplete; retained descendants were not adopted or ignored" >&2
        return 1
    fi
    echo "Legacy PixEagle session stopped. Future runs use the dedicated supervised socket."
}

terminate_owned_pid() {
    local pid="$1"
    local expected_run_id="${2:-}"
    local start_token
    start_token="$(pixeagle_pid_start_token "$pid" 2>/dev/null || true)"
    if [[ -z "$start_token" ]]; then
        kill -0 "$pid" 2>/dev/null && return 1
        return 0
    fi
    if ! pixeagle_pid_is_owned "$pid" "$PIXEAGLE_DIR" "$(id -u)" \
        "$PIXEAGLE_RUNTIME_MODE" "$expected_run_id"; then
        kill -0 "$pid" 2>/dev/null && return 1
        return 0
    fi

    pixeagle_terminate_owned_pid \
        "$pid" "$start_token" "$PIXEAGLE_DIR" "$(id -u)" \
        "$PIXEAGLE_RUNTIME_MODE" "$expected_run_id"
}

stop_marked_processes() {
    local expected_run_id="${1:-}"
    local pid failed=false
    while IFS= read -r pid; do
        [[ -n "$pid" && "$pid" != "$$" && "$pid" != "$PPID" ]] || continue
        if terminate_owned_pid "$pid" "$expected_run_id"; then
            echo -e "   ${GREEN}${CHECK}${NC} Stopped marked process $pid"
        else
            echo -e "   ${RED}${CROSS}${NC} Could not safely stop marked process $pid"
            failed=true
        fi
    done < <(pixeagle_owned_pids "$PIXEAGLE_DIR" "$(id -u)" \
        "$PIXEAGLE_RUNTIME_MODE" "$expected_run_id")
    [[ "$failed" != "true" ]]
}

report_retained_listeners() {
    command -v lsof >/dev/null 2>&1 || return 0
    local dashboard_port backend_port websocket_port mavlink2rest_port mavsdk_port
    dashboard_port="${PIXEAGLE_DEFAULT_DASHBOARD_PORT:-3040}"
    backend_port="${PIXEAGLE_DEFAULT_BACKEND_PORT:-5077}"
    websocket_port="${PIXEAGLE_DEFAULT_WEBSOCKET_PORT:-5551}"
    mavlink2rest_port="${PIXEAGLE_DEFAULT_MAVLINK2REST_PORT:-8088}"
    mavsdk_port=50051
    if declare -f resolve_dashboard_port >/dev/null 2>&1; then
        dashboard_port="$(resolve_dashboard_port "$PIXEAGLE_DIR/dashboard")"
    fi
    if declare -f resolve_backend_port >/dev/null 2>&1; then
        backend_port="$(resolve_backend_port "$PIXEAGLE_DIR/configs/config.yaml")"
    fi
    if declare -f get_yaml_int_value >/dev/null 2>&1; then
        local config_file="$PIXEAGLE_DIR/configs/config.yaml" candidate
        [[ -f "$config_file" ]] || config_file="$PIXEAGLE_DIR/configs/config_default.yaml"
        candidate="$(get_yaml_int_value "$config_file" MAVSDK_SERVER_PORT 2>/dev/null || true)"
        is_valid_port "$candidate" && mavsdk_port="$candidate"
    fi

    local port pids
    for port in "$dashboard_port" "$backend_port" "$websocket_port" \
        "$mavlink2rest_port" "$mavsdk_port"; do
        pids="$(lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u || true)"
        [[ -z "$pids" ]] || echo -e "   ${DIM}Retained nonmatching listener(s) on port $port: ${pids//$'\n'/,}${NC}"
    done
}

stop_runtime() {
if [[ "$LEGACY_DEFAULT_SESSION" == "true" ]]; then
    stop_legacy_session
    return $?
fi

echo ""
echo -e "${CYAN}Stopping PixEagle ${PIXEAGLE_RUNTIME_MODE} runtime${NC}"
echo ""

RUN_ID=""
SESSION_PRESENT=false
SESSION_IDENTITY_VALID=false
if pixeagle_tmux_session_exists "$TMUX_SOCKET_NAME" "$SESSION_NAME"; then
    SESSION_PRESENT=true
    if ! pixeagle_tmux_session_is_owned "$TMUX_SOCKET_NAME" "$SESSION_NAME" \
        "$PIXEAGLE_DIR" "$PIXEAGLE_RUNTIME_MODE"; then
        echo -e "   ${RED}${CROSS}${NC} Refusing session with invalid ownership markers"
        STOP_FAILED=true
    else
        RUN_ID="$(pixeagle_tmux_environment_value \
            "$TMUX_SOCKET_NAME" "$SESSION_NAME" PIXEAGLE_RUN_ID 2>/dev/null || true)"
        if [[ -z "$RUN_ID" ]] || \
           ! pixeagle_tmux_session_is_owned "$TMUX_SOCKET_NAME" "$SESSION_NAME" \
                "$PIXEAGLE_DIR" "$PIXEAGLE_RUNTIME_MODE" "$RUN_ID"; then
            echo -e "   ${RED}${CROSS}${NC} Refusing session without an exact run identity"
            STOP_FAILED=true
        else
            SESSION_IDENTITY_VALID=true
            while IFS= read -r target; do
                tmux_runtime send-keys -t "$target" C-c 2>/dev/null || true
            done < <(tmux_runtime list-panes -t "=$SESSION_NAME" -s \
                -F '#{session_name}:#{window_index}.#{pane_index}' 2>/dev/null || true)
            sleep 2
            if ! pixeagle_tmux_session_exists "$TMUX_SOCKET_NAME" "$SESSION_NAME" || \
               tmux_runtime kill-session -t "=$SESSION_NAME" 2>/dev/null; then
                echo -e "   ${GREEN}${CHECK}${NC} Supervised tmux session stopped"
            else
                echo -e "   ${RED}${CROSS}${NC} Could not stop supervised tmux session"
                STOP_FAILED=true
            fi
        fi
    fi
else
    echo -e "   ${DIM}No supervised ${PIXEAGLE_RUNTIME_MODE} session is running${NC}"
fi

# A valid live session supplies an exact run ID. When no session exists, the
# lifecycle lock makes a mode-wide orphan sweep race-free. An invalid live
# session is never widened into a mode-wide signal operation.
if [[ "$SESSION_PRESENT" == "false" || "$SESSION_IDENTITY_VALID" == "true" ]]; then
    if ! stop_marked_processes "$RUN_ID"; then
        STOP_FAILED=true
    fi
fi

if default_tmux_session_exists_exact; then
    echo -e "   ${YELLOW}${WARN}${NC} A pre-ownership default tmux session still exists"
    echo -e "   ${DIM}Review it with: make stop-legacy${NC}"
    STOP_FAILED=true
fi
report_retained_listeners

echo ""
if [[ "$STOP_FAILED" == "true" ]]; then
    echo -e "${YELLOW}${WARN}${NC} Stop incomplete"
    return 1
fi
echo -e "${GREEN}${CHECK}${NC} Marked ${PIXEAGLE_RUNTIME_MODE} runtime stopped"
}

if [[ "$INTERNAL_LIFECYCLE_STOP" == "true" ]]; then
    if ! pixeagle_validate_resource_lock_context exclusive "$LIFECYCLE_RESOURCE"; then
        echo "Stop is outside the supervised lifecycle transaction" >&2
        exit 73
    fi
    stop_runtime
else
    pixeagle_run_with_resource_lock \
        exclusive "$LIFECYCLE_RESOURCE" \
        "stop ${PIXEAGLE_RUNTIME_MODE} runtime" 30 \
        bash "$SCRIPTS_DIR/stop.sh" --internal-lifecycle-stop "${ORIGINAL_ARGS[@]}"
fi

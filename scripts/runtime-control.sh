#!/usr/bin/env bash
# Ownership-aware tmux status and attachment for a PixEagle checkout.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
SESSION_NAME="pixeagle"
COMMAND="${1:-status}"
[[ $# -eq 0 ]] || shift
RUNTIME_MODE="${PIXEAGLE_RUNTIME_MODE:-manual}"

# shellcheck source=scripts/lib/runtime_ownership.sh
source "$SCRIPT_DIR/lib/runtime_ownership.sh"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)
            shift
            RUNTIME_MODE="${1:-}"
            ;;
        -h|--help)
            echo "Usage: bash scripts/runtime-control.sh status|attach [--mode manual|service]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
    shift
done

pixeagle_runtime_mode_is_valid "$RUNTIME_MODE" || {
    echo "Runtime mode must be manual or service" >&2
    exit 2
}
SOCKET_NAME="$(pixeagle_tmux_socket_name "$PROJECT_ROOT" "$RUNTIME_MODE")"

require_owned_session() {
    if ! pixeagle_tmux_session_exists "$SOCKET_NAME" "$SESSION_NAME"; then
        echo "No $RUNTIME_MODE PixEagle session is running"
        return 1
    fi
    if ! pixeagle_tmux_session_is_owned \
        "$SOCKET_NAME" "$SESSION_NAME" "$PROJECT_ROOT" "$RUNTIME_MODE"; then
        echo "Refusing $RUNTIME_MODE session with invalid ownership markers" >&2
        return 1
    fi
    local run_id
    run_id="$(pixeagle_tmux_environment_value \
        "$SOCKET_NAME" "$SESSION_NAME" PIXEAGLE_RUN_ID 2>/dev/null)" || {
        echo "Refusing $RUNTIME_MODE session without a run ID" >&2
        return 1
    }
    pixeagle_run_id_is_valid "$run_id" || {
        echo "Refusing $RUNTIME_MODE session with an invalid run ID" >&2
        return 1
    }
}

case "$COMMAND" in
    status)
        echo ""
        echo "  PixEagle Runtime Status"
        echo "  ========================"
        echo "  Checkout: $PROJECT_ROOT"
        echo "  Mode:     $RUNTIME_MODE"
        if ! require_owned_session; then
            exit 1
        fi
        run_id="$(pixeagle_tmux_environment_value "$SOCKET_NAME" "$SESSION_NAME" PIXEAGLE_RUN_ID)"
        ready="$(pixeagle_tmux_environment_value "$SOCKET_NAME" "$SESSION_NAME" PIXEAGLE_READY 2>/dev/null || echo 0)"
        expected="$(pixeagle_tmux_environment_value "$SOCKET_NAME" "$SESSION_NAME" PIXEAGLE_EXPECTED_COMPONENTS 2>/dev/null || echo unknown)"
        echo "  Run ID:   $run_id"
        echo "  Ready:    $ready"
        echo "  Expected: $expected"
        if pixeagle_tmux_runtime_is_healthy \
            "$SOCKET_NAME" "$SESSION_NAME" "$PROJECT_ROOT" "$RUNTIME_MODE" "$run_id"; then
            echo "  Healthy:  yes"
            status_result=0
        else
            echo "  Healthy:  no"
            status_result=1
        fi
        echo "  Components:"
        pixeagle_tmux "$SOCKET_NAME" list-panes -t "=$SESSION_NAME" -s \
            -F '    #{@pixeagle_component}: dead=#{pane_dead} pid=#{pane_pid}'
        echo ""
        exit "$status_result"
        ;;
    attach)
        require_owned_session
        exec tmux -L "$SOCKET_NAME" attach -t "=$SESSION_NAME"
        ;;
    *)
        echo "Usage: bash scripts/runtime-control.sh status|attach [--mode manual|service]" >&2
        exit 2
        ;;
esac

#!/usr/bin/env bash
# Secure cross-process serialization for PixEagle deployment resources.

if [[ -n "${PIXEAGLE_SETUP_LOCK_SH_LOADED:-}" ]]; then
    if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
        return 0
    fi
    exit 0
fi
PIXEAGLE_SETUP_LOCK_SH_LOADED=1

PIXEAGLE_SETUP_LOCK_HELPER_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P
)" || {
    printf 'Cannot resolve the PixEagle resource lock helper directory\n' >&2
    if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
        return 1
    fi
    exit 1
}
PIXEAGLE_SETUP_LOCK_SUPERVISOR="$PIXEAGLE_SETUP_LOCK_HELPER_DIR/setup_lock_supervisor.py"

_pixeagle_require_lock_supervisor() {
    command -v python3 >/dev/null 2>&1 || {
        printf 'python3 is required for supervised PixEagle resource access\n' >&2
        return 1
    }
    [[ -f "$PIXEAGLE_SETUP_LOCK_SUPERVISOR" \
        && ! -L "$PIXEAGLE_SETUP_LOCK_SUPERVISOR" ]] || {
        printf 'PixEagle resource lock supervisor is unavailable\n' >&2
        return 1
    }
}

pixeagle_setup_lock_directory() {
    local identity="${1:-}"

    _pixeagle_require_lock_supervisor || return 1
    if [[ -z "$identity" ]]; then
        python3 "$PIXEAGLE_SETUP_LOCK_SUPERVISOR" directory --caller
    elif [[ "$identity" =~ ^[0-9]+$ ]]; then
        python3 "$PIXEAGLE_SETUP_LOCK_SUPERVISOR" directory --owner-uid "$identity"
    else
        python3 "$PIXEAGLE_SETUP_LOCK_SUPERVISOR" directory --resource-path "$identity"
    fi
}

pixeagle_prepare_setup_lock_directory() {
    local directory="${1:-}"

    [[ -n "$directory" && $# -eq 1 ]] || return 2
    _pixeagle_require_lock_supervisor || return 1
    python3 "$PIXEAGLE_SETUP_LOCK_SUPERVISOR" prepare-directory \
        --directory "$directory" >/dev/null
}

pixeagle_resource_lock_identity() {
    local resource_path="${1:-}"

    [[ -n "$resource_path" && $# -eq 1 ]] || return 2
    _pixeagle_require_lock_supervisor || return 1
    python3 "$PIXEAGLE_SETUP_LOCK_SUPERVISOR" identity \
        --resource-path "$resource_path"
}

pixeagle_setup_environment_identity() {
    pixeagle_resource_lock_identity "$@"
}

pixeagle_resource_lock_path() {
    local resource_path="${1:-}"

    [[ -n "$resource_path" && $# -eq 1 ]] || return 2
    _pixeagle_require_lock_supervisor || return 1
    python3 "$PIXEAGLE_SETUP_LOCK_SUPERVISOR" path \
        --resource-path "$resource_path"
}

pixeagle_setup_lock_path() {
    pixeagle_resource_lock_path "$@"
}

pixeagle_setup_lock_status() {
    local resource_path="${1:-}"
    shift || return 2

    [[ -n "$resource_path" ]] || return 2
    [[ $# -eq 0 || ( $# -eq 1 && "$1" == "--json" ) ]] || return 2
    _pixeagle_require_lock_supervisor || return 1
    python3 "$PIXEAGLE_SETUP_LOCK_SUPERVISOR" status \
        --resource-path "$resource_path" "$@"
}

pixeagle_prepare_setup_lock_file() {
    local lock_path="${1:-}"

    [[ -n "$lock_path" && $# -eq 1 ]] || return 2
    _pixeagle_require_lock_supervisor || return 1
    python3 "$PIXEAGLE_SETUP_LOCK_SUPERVISOR" prepare \
        --lock-path "$lock_path" >/dev/null
}

pixeagle_resource_lock_context_present() {
    [[ -n "${PIXEAGLE_RESOURCE_LOCK_MODE:-}" \
        || -n "${PIXEAGLE_RESOURCE_LOCK_SET:-}" \
        || -n "${PIXEAGLE_RESOURCE_LOCK_STATE_PATH:-}" \
        || -n "${PIXEAGLE_RESOURCE_LOCK_TOKEN:-}" \
        || -n "${PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_PID:-}" \
        || -n "${PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_START_TOKEN:-}" \
        || -n "${PIXEAGLE_RESOURCE_LOCK_SESSION_ID:-}" \
        || -n "${PIXEAGLE_ENVIRONMENT_LOCK_MODE:-}" \
        || -n "${PIXEAGLE_ENVIRONMENT_LOCK_PATH:-}" \
        || -n "${PIXEAGLE_ENVIRONMENT_LOCK_PATHS:-}" \
        || -n "${PIXEAGLE_ENVIRONMENT_LOCK_SUPERVISOR_PID:-}" \
        || -n "${PIXEAGLE_ENVIRONMENT_LOCK_SUPERVISOR_START_TOKEN:-}" \
        || -n "${PIXEAGLE_ENVIRONMENT_LOCK_SESSION_ID:-}" \
        || -n "${PIXEAGLE_SETUP_LOCK_PATH:-}" \
        || -n "${PIXEAGLE_SETUP_LOCK_STATE_PATH:-}" \
        || -n "${PIXEAGLE_SETUP_LOCK_TOKEN:-}" \
        || -n "${PIXEAGLE_SETUP_LOCK_SUPERVISOR_PID:-}" \
        || -n "${PIXEAGLE_SETUP_LOCK_SUPERVISOR_START_TOKEN:-}" \
        || -n "${PIXEAGLE_SETUP_LOCK_SESSION_ID:-}" ]]
}

pixeagle_setup_lock_context_present() {
    [[ "${PIXEAGLE_RESOURCE_LOCK_MODE:-}" == "exclusive" \
        || -n "${PIXEAGLE_SETUP_LOCK_PATH:-}" \
        || -n "${PIXEAGLE_SETUP_LOCK_STATE_PATH:-}" \
        || -n "${PIXEAGLE_SETUP_LOCK_TOKEN:-}" \
        || -n "${PIXEAGLE_SETUP_LOCK_SUPERVISOR_PID:-}" \
        || -n "${PIXEAGLE_SETUP_LOCK_SUPERVISOR_START_TOKEN:-}" \
        || -n "${PIXEAGLE_SETUP_LOCK_SESSION_ID:-}" ]]
}

pixeagle_shared_setup_lock_context_present() {
    [[ "${PIXEAGLE_RESOURCE_LOCK_MODE:-${PIXEAGLE_ENVIRONMENT_LOCK_MODE:-}}" \
        == "shared" ]]
}

pixeagle_validate_resource_lock_context() {
    local mode="${1:-}"
    shift || return 2
    local resource_path
    local -a supervisor_args

    [[ "$mode" == "exclusive" || "$mode" == "shared" ]] || return 2
    [[ $# -gt 0 ]] || return 2
    _pixeagle_require_lock_supervisor || return 1
    supervisor_args=(validate --mode "$mode")
    for resource_path in "$@"; do
        [[ -n "$resource_path" ]] || return 2
        supervisor_args+=(--resource-path "$resource_path")
    done
    python3 "$PIXEAGLE_SETUP_LOCK_SUPERVISOR" "${supervisor_args[@]}"
}

pixeagle_validate_resource_locks_context() {
    pixeagle_validate_resource_lock_context "$@"
}

pixeagle_validate_setup_lock_context() {
    local environment_path="${1:-}"

    [[ -n "$environment_path" && $# -eq 1 ]] || return 2
    pixeagle_validate_resource_lock_context exclusive "$environment_path"
}

pixeagle_validate_shared_setup_lock_context() {
    local environment_path="${1:-}"

    [[ -n "$environment_path" && $# -eq 1 ]] || return 2
    pixeagle_validate_resource_lock_context shared "$environment_path"
}

pixeagle_acquire_setup_lock() {
    local environment_path="${1:-}"
    local operation="${2:-environment setup}"
    local _timeout_seconds="${3:-30}"

    if ! pixeagle_setup_lock_context_present; then
        printf 'PixEagle %s must run through the non-leaking resource lock supervisor\n' \
            "$operation" >&2
        return 1
    fi
    pixeagle_validate_setup_lock_context "$environment_path"
}

pixeagle_release_setup_lock() {
    # The external supervisor owns every descriptor and releases only after all
    # command descendants have been terminated and reaped.
    return 0
}

# Internal contract: DESCENDANT_POLICY MODE OPERATION TIMEOUT RESOURCE... -- COMMAND...
_pixeagle_run_with_resource_locks() {
    local descendant_policy="${1:-}"
    local mode="${2:-}"
    local operation="${3:-}"
    local timeout_seconds="${4:-}"
    shift 4 || return 2
    local resource_path
    local -a resources=()
    local -a supervisor_args=()

    [[ "$descendant_policy" == "terminate" \
        || "$descendant_policy" == "preserve-on-success" ]] || return 2
    [[ "$mode" == "exclusive" || "$mode" == "shared" ]] || return 2
    [[ "$timeout_seconds" =~ ^[0-9]+$ ]] || return 2
    while [[ $# -gt 0 && "$1" != "--" ]]; do
        [[ -n "$1" ]] || return 2
        resources+=("$1")
        shift
    done
    [[ ${#resources[@]} -gt 0 && "${1:-}" == "--" ]] || return 2
    shift
    [[ $# -gt 0 ]] || return 2
    _pixeagle_require_lock_supervisor || return 1

    if pixeagle_resource_lock_context_present; then
        pixeagle_validate_resource_lock_context "$mode" "${resources[@]}" || return 1
        "$@"
        return
    fi

    supervisor_args=(
        run
        --mode "$mode"
        --operation "$operation"
        --timeout "$timeout_seconds"
        --descendant-policy "$descendant_policy"
    )
    for resource_path in "${resources[@]}"; do
        supervisor_args+=(--resource-path "$resource_path")
    done
    python3 "$PIXEAGLE_SETUP_LOCK_SUPERVISOR" "${supervisor_args[@]}" -- "$@"
}

# Usage: pixeagle_run_with_resource_locks MODE OPERATION TIMEOUT RESOURCE... -- COMMAND...
pixeagle_run_with_resource_locks() {
    _pixeagle_run_with_resource_locks terminate "$@"
}

# Lifecycle launchers use this only when a successful command intentionally
# hands detached runtime descendants to tmux/systemd. Failures are still reaped.
pixeagle_run_with_resource_locks_preserving_descendants() {
    _pixeagle_run_with_resource_locks preserve-on-success "$@"
}

pixeagle_run_with_resource_set_lock() {
    pixeagle_run_with_resource_locks "$@"
}

pixeagle_run_with_resource_lock() {
    local mode="${1:-}"
    local resource_path="${2:-}"
    local operation="${3:-}"
    local timeout_seconds="${4:-}"
    shift 4 || return 2

    pixeagle_run_with_resource_locks \
        "$mode" "$operation" "$timeout_seconds" "$resource_path" -- "$@"
}

pixeagle_run_with_resource_lock_preserving_descendants() {
    local mode="${1:-}"
    local resource_path="${2:-}"
    local operation="${3:-}"
    local timeout_seconds="${4:-}"
    shift 4 || return 2

    pixeagle_run_with_resource_locks_preserving_descendants \
        "$mode" "$operation" "$timeout_seconds" "$resource_path" -- "$@"
}

pixeagle_run_with_environment_lock() {
    local mode="${1:-}"
    local environment_path="${2:-}"
    local operation="${3:-}"
    local timeout_seconds="${4:-}"
    shift 4 || return 2

    pixeagle_run_with_resource_lock \
        "$mode" "$environment_path" "$operation" "$timeout_seconds" "$@"
}

pixeagle_run_with_setup_lock() {
    local environment_path="${1:-}"
    local operation="${2:-environment setup}"
    local timeout_seconds="${3:-30}"
    shift 3 || return 2

    pixeagle_run_with_environment_lock \
        exclusive "$environment_path" "$operation" "$timeout_seconds" "$@"
}

pixeagle_run_with_shared_setup_lock() {
    local environment_path="${1:-}"
    local operation="${2:-runtime access}"
    local timeout_seconds="${3:-30}"
    shift 3 || return 2

    pixeagle_run_with_environment_lock \
        shared "$environment_path" "$operation" "$timeout_seconds" "$@"
}

#!/usr/bin/env bash
# Internal Dashboard worker. Web requests cannot select shell commands.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/update.sh"
# The worker executes this retained driver from an immutable pre-update copy.
# Resolve runtime ownership and the live initializer against the original checkout.
DRIVER_ROOT="$PROJECT_ROOT"
PROJECT_ROOT="$(pwd -P)"
STOP_SCRIPT="$PROJECT_ROOT/scripts/stop.sh"
SERVICE_CLI="$PROJECT_ROOT/scripts/service/cli.sh"
INIT_SCRIPT="$PROJECT_ROOT/scripts/init.sh"
require_contract_files
if [[ "${1:-}" == rollback-source ]]; then
    pixeagle_validate_resource_lock_context exclusive "$LIFECYCLE_RESOURCE" "$PROJECT_ROOT" "$VENV_DIR"
    source "$SYNC_SCRIPT"
    PIXEAGLE_SYNC_CHANGED=true
    PIXEAGLE_SYNC_OLD_HEAD="$2"
    PIXEAGLE_SYNC_NEW_HEAD="$3"
    rollback_source_if_safe "Runtime verification failed"
    exit
fi
[[ "$1" == apply || "$1" == restore ]] || exit 2
if [[ -n "${PIXEAGLE_UPDATE_EXPECTED_RUN:-}" ]]; then
    other_mode=manual
    [[ "$PIXEAGLE_UPDATE_EXPECTED_MODE" != manual ]] || other_mode=service
    if runtime_mode_has_owned_state "$other_mode"; then
        echo 'A second runtime is active; both runtimes were preserved.' >&2
        exit 1
    fi
    expected_active=false
    runtime_mode_has_owned_state "$PIXEAGLE_UPDATE_EXPECTED_MODE" && expected_active=true
    if [[ "$1" == apply || "$expected_active" == true ]]; then
        socket="$(pixeagle_tmux_socket_name "$PROJECT_ROOT" "$PIXEAGLE_UPDATE_EXPECTED_MODE")"
        pixeagle_tmux_session_is_owned "$socket" pixeagle "$PROJECT_ROOT" \
            "$PIXEAGLE_UPDATE_EXPECTED_MODE" "$PIXEAGLE_UPDATE_EXPECTED_RUN" || {
                echo 'The reviewed runtime changed before shutdown.' >&2
                exit 1
            }
    elif ! assert_runtime_stopped quiet; then
        echo 'A different runtime is active; recovery was not attempted.' >&2
        exit 1
    fi
fi
# Only enter runtime recovery once a shutdown was actually attempted.
if [[ "$1" == apply ]]; then
    touch "$2/shutdown-started"
fi
ensure_runtime_stopped_before_update
pixeagle_run_with_resource_locks exclusive "Dashboard software update" 30 \
    "$LIFECYCLE_RESOURCE" "$PROJECT_ROOT" "$VENV_DIR" -- \
    "$3" "$DRIVER_ROOT/src/classes/software_update.py" "$1" "$2"

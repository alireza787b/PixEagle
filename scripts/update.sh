#!/usr/bin/env bash
# Perform one stopped-runtime source and environment reconciliation transaction.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
COMMON_HELPER="$PROJECT_ROOT/scripts/lib/common.sh"
SYNC_SCRIPT="$PROJECT_ROOT/scripts/lib/sync.sh"
OWNERSHIP_HELPER="$PROJECT_ROOT/scripts/lib/runtime_ownership.sh"
SETUP_LOCK_HELPER="$PROJECT_ROOT/scripts/lib/setup_lock.sh"
PORTS_HELPER="$PROJECT_ROOT/scripts/lib/ports.sh"
INIT_SCRIPT="$PROJECT_ROOT/scripts/init.sh"
DASHBOARD_DEPENDENCIES_HELPER="$PROJECT_ROOT/scripts/lib/dashboard_dependencies.sh"
STOP_SCRIPT="$PROJECT_ROOT/scripts/stop.sh"
SERVICE_CLI="$PROJECT_ROOT/scripts/service/cli.sh"

DRY_RUN=false
INTERNAL_UPDATE=false
VENV_DIR=""
LIFECYCLE_RESOURCE=""

if [[ -f "$COMMON_HELPER" ]]; then
    # shellcheck source=scripts/lib/common.sh
    source "$COMMON_HELPER"
else
    log_info() { printf '  [INFO] %s\n' "$1"; }
    log_success() { printf '  [OK] %s\n' "$1"; }
    log_error() { printf '  [ERROR] %s\n' "$1" >&2; }
    log_warn() { printf '  [WARN] %s\n' "$1"; }
    log_detail() { printf '         %s\n' "$1"; }
fi

show_help() {
    cat <<'USAGE'
Usage: bash scripts/update.sh [--dry-run] [--remote NAME] [--branch NAME]

Safely update and reconcile an existing PixEagle checkout:
  1. acquire exclusive lifecycle, source, and virtual-environment ownership;
  2. require a stopped runtime, offering to stop an owned runtime interactively;
  3. fetch one exact branch and apply only a verified fast-forward candidate;
  4. run the guided Core/Full dependency and config reconciler;
  5. restore the previous source commit if reconciliation fails and the tracked
     checkout is still unchanged by any other actor.

An interactive update asks before stopping a runtime owned by this checkout.
The updater never restarts PixEagle and never deletes untracked or ignored
configuration, credentials, models, or evidence. Conflicting or unverified
runtime ownership remains a hard stop.

In non-interactive automation, stop PixEagle first or explicitly set:
  PIXEAGLE_UPDATE_STOP_RUNTIME=1
Also set PIXEAGLE_NONINTERACTIVE=1 and PIXEAGLE_INSTALL_PROFILE=core|full.

Manual stop commands:
  manual runtime:  make stop
  managed runtime: pixeagle-service stop

If source was already changed with an external `git pull`, do not run another
fetch transaction. Stop PixEagle and run `make repair` from the checkout to
reconcile the current source, then start the selected runtime explicitly.

Optional policy:
  PIXEAGLE_UPDATE_REQUIRE_SIGNED_COMMIT=1  Require `git verify-commit` success.
USAGE
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run)
                DRY_RUN=true
                ;;
            --remote)
                shift
                [[ -n "${1:-}" ]] || {
                    log_error "--remote requires a Git remote name"
                    return 2
                }
                SYNC_REMOTE="$1"
                ;;
            --branch)
                shift
                [[ -n "${1:-}" ]] || {
                    log_error "--branch requires a branch name"
                    return 2
                }
                SYNC_BRANCH="$1"
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help >&2
                return 2
                ;;
        esac
        shift
    done
    export SYNC_REMOTE="${SYNC_REMOTE:-}" SYNC_BRANCH="${SYNC_BRANCH:-}"
}

require_contract_files() {
    local required
    for required in \
        "$SYNC_SCRIPT" \
        "$OWNERSHIP_HELPER" \
        "$SETUP_LOCK_HELPER" \
        "$PORTS_HELPER" \
        "$INIT_SCRIPT" \
        "$DASHBOARD_DEPENDENCIES_HELPER" \
        "$STOP_SCRIPT" \
        "$SERVICE_CLI"; do
        if [[ ! -f "$required" || -L "$required" ]]; then
            log_error "Missing or unsafe update contract file: $required"
            return 1
        fi
    done

    # shellcheck source=scripts/lib/runtime_ownership.sh
    source "$OWNERSHIP_HELPER"
    # shellcheck source=scripts/lib/setup_lock.sh
    source "$SETUP_LOCK_HELPER"
    # shellcheck source=scripts/lib/ports.sh
    source "$PORTS_HELPER"

    VENV_DIR="$(resolve_pixeagle_venv_dir "$PROJECT_ROOT")" || {
        log_error "Could not resolve the PixEagle virtual environment"
        return 1
    }
    LIFECYCLE_RESOURCE="$(pixeagle_lifecycle_resource "$PROJECT_ROOT")" || {
        log_error "Could not resolve the PixEagle lifecycle resource"
        return 1
    }
}

validate_automation_profile() {
    case "${PIXEAGLE_UPDATE_STOP_RUNTIME:-}" in
        ""|0|1) ;;
        *)
            log_error "PIXEAGLE_UPDATE_STOP_RUNTIME must be 0 or 1"
            return 2
            ;;
    esac
    if [[ "${PIXEAGLE_NONINTERACTIVE:-0}" != "1" ]]; then
        return 0
    fi
    case "${PIXEAGLE_INSTALL_PROFILE:-}" in
        core|CORE|full|FULL|1|2)
            return 0
            ;;
        *)
            log_error "Non-interactive update requires PIXEAGLE_INSTALL_PROFILE=core|full"
            log_detail "No source update was attempted."
            return 1
            ;;
    esac
}

systemd_unit_file_exists() {
    local scope="$1"
    local candidate
    local -a candidates=()

    if [[ "$scope" == system ]]; then
        candidates=(
            /etc/systemd/system/pixeagle.service
            /run/systemd/system/pixeagle.service
            /usr/local/lib/systemd/system/pixeagle.service
            /usr/lib/systemd/system/pixeagle.service
            /lib/systemd/system/pixeagle.service
        )
    else
        candidates=(
            "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/pixeagle.service"
            /etc/systemd/user/pixeagle.service
            /usr/local/lib/systemd/user/pixeagle.service
            /usr/lib/systemd/user/pixeagle.service
            /lib/systemd/user/pixeagle.service
        )
    fi
    for candidate in "${candidates[@]}"; do
        [[ -e "$candidate" || -L "$candidate" ]] && return 0
    done
    return 1
}

systemd_scope_is_expected() {
    local scope="$1"
    if systemd_unit_file_exists "$scope"; then
        return 0
    fi
    if [[ "$scope" == system ]]; then
        [[ -d /run/systemd/system ]]
    else
        [[ -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/systemd/private" ]]
    fi
}

systemd_scope_blockers() {
    local scope="$1"
    local output load_state="" active_state="" job_state="" line
    local -a command=(systemctl)
    [[ "$scope" == user ]] && command+=(--user)

    if ! command -v systemctl >/dev/null 2>&1; then
        if systemd_unit_file_exists "$scope"; then
            printf '%s\n' "$scope pixeagle.service state unknown (systemctl unavailable)"
        fi
        return 0
    fi

    if ! output="$("${command[@]}" show \
        --property=LoadState --property=ActiveState --property=Job \
        pixeagle.service 2>/dev/null)"; then
        if systemd_scope_is_expected "$scope"; then
            printf '%s\n' "$scope pixeagle.service state query failed"
        fi
        return 0
    fi
    while IFS= read -r line; do
        case "$line" in
            LoadState=*) load_state="${line#*=}" ;;
            ActiveState=*) active_state="${line#*=}" ;;
            Job=*) job_state="${line#*=}" ;;
        esac
    done <<< "$output"

    if [[ "$load_state" == not-found ]]; then
        return 0
    fi
    if [[ -z "$load_state" || -z "$active_state" ]]; then
        printf '%s\n' "$scope pixeagle.service returned an incomplete state"
        return 0
    fi
    if [[ -n "$job_state" ]]; then
        printf '%s\n' "$scope pixeagle.service has a queued systemd job"
        return 0
    fi
    case "$active_state" in
        inactive|failed)
            return 0
            ;;
        active|activating|deactivating|reloading|maintenance)
            printf '%s\n' "$scope pixeagle.service ($active_state)"
            ;;
        *)
            printf '%s\n' "$scope pixeagle.service returned unknown state: $active_state"
            ;;
    esac
}

active_service_labels() {
    systemd_scope_blockers system
    systemd_scope_blockers user
}

runtime_mode_has_owned_state() {
    local runtime_mode="$1"
    local socket_name=""
    local owned_pid=""

    socket_name="$(pixeagle_tmux_socket_name "$PROJECT_ROOT" "$runtime_mode")"
    if command -v tmux >/dev/null 2>&1 \
        && pixeagle_tmux_session_exists "$socket_name" pixeagle \
        && pixeagle_tmux_session_is_owned \
            "$socket_name" pixeagle "$PROJECT_ROOT" "$runtime_mode"; then
        return 0
    fi
    IFS= read -r owned_pid < <(
        pixeagle_owned_pids \
            "$PROJECT_ROOT" "$(id -u)" "$runtime_mode"
    ) || true
    [[ -n "$owned_pid" ]]
}

system_service_unit_value() {
    local unit_path="$1"
    local key="$2"
    awk -F= -v expected_key="$key" '
        $1 == expected_key {
            value=$0
            sub(/^[^=]*=/, "", value)
            count++
        }
        END {
            if (count == 1 && value != "") print value
            else exit 1
        }
    ' "$unit_path"
}

system_service_matches_checkout() {
    local fragment_path="" working_directory="" exec_start="" service_user=""
    local canonical_working_directory="" drop_in_paths=""

    command -v systemctl >/dev/null 2>&1 || return 1
    fragment_path="$(
        systemctl show --property=FragmentPath --value \
            pixeagle.service 2>/dev/null
    )" || return 1
    drop_in_paths="$(
        systemctl show --property=DropInPaths --value \
            pixeagle.service 2>/dev/null
    )" || return 1
    [[ -z "$drop_in_paths" ]] || return 1
    [[ -f "$fragment_path" && ! -L "$fragment_path" ]] || return 1
    working_directory="$(
        system_service_unit_value "$fragment_path" WorkingDirectory
    )" || return 1
    exec_start="$(
        system_service_unit_value "$fragment_path" ExecStart
    )" || return 1
    service_user="$(
        system_service_unit_value "$fragment_path" User
    )" || return 1
    canonical_working_directory="$(
        realpath -m -- "$working_directory" 2>/dev/null
    )" || return 1

    [[ "$canonical_working_directory" == "$PROJECT_ROOT" ]] || return 1
    [[ "$exec_start" == "$PROJECT_ROOT/scripts/service/run.sh" ]] || return 1
    if [[ "$EUID" -ne 0 ]]; then
        [[ "$service_user" == "$(id -un)" ]] || return 1
    fi
}

system_service_for_checkout_is_stoppable() {
    local output="" load_state="" active_state="" job_state="" line=""

    system_service_matches_checkout || return 1
    output="$(
        systemctl show \
            --property=LoadState --property=ActiveState --property=Job \
            pixeagle.service 2>/dev/null
    )" || return 1
    while IFS= read -r line; do
        case "$line" in
            LoadState=*) load_state="${line#*=}" ;;
            ActiveState=*) active_state="${line#*=}" ;;
            Job=*) job_state="${line#*=}" ;;
        esac
    done <<< "$output"
    [[ "$load_state" == loaded && -z "$job_state" ]] || return 1
    case "$active_state" in
        active|activating|deactivating|reloading|maintenance) return 0 ;;
        *) return 1 ;;
    esac
}

owned_runtime_can_be_stopped() {
    runtime_mode_has_owned_state manual \
        || runtime_mode_has_owned_state service \
        || system_service_for_checkout_is_stoppable
}

stop_owned_runtime_for_update() {
    local stop_manual=false
    local stop_managed=false

    runtime_mode_has_owned_state manual && stop_manual=true
    if runtime_mode_has_owned_state service \
        || system_service_for_checkout_is_stoppable; then
        stop_managed=true
    fi

    if [[ "$stop_manual" == true ]]; then
        log_info "Stopping the owned manual runtime"
        bash "$STOP_SCRIPT" --mode manual || return 1
    fi
    if [[ "$stop_managed" == true ]] \
        && system_service_for_checkout_is_stoppable; then
        if [[ "$EUID" -ne 0 ]] && ! pixeagle_sudo_validate; then
            log_error "$(pixeagle_sudo_failure_message)"
            return 1
        fi
        log_info "Stopping the managed PixEagle service"
        bash "$SERVICE_CLI" stop || return 1
    fi
    if [[ "$stop_managed" == true ]] \
        && runtime_mode_has_owned_state service; then
        log_info "Stopping the owned service-mode runtime"
        bash "$STOP_SCRIPT" --mode service || return 1
    fi
}

runtime_listener_labels() {
    command -v lsof >/dev/null 2>&1 || {
        printf '%s\n' "listener ownership unknown (lsof is unavailable)"
        return 0
    }

    local dashboard_port backend_port websocket_port mavlink2rest_port mavsdk_port
    local config_file candidate port pids raw_pids lsof_status line
    local lsof_error_file lsof_error previous_umask
    dashboard_port="${PIXEAGLE_DEFAULT_DASHBOARD_PORT:-3040}"
    backend_port="${PIXEAGLE_DEFAULT_BACKEND_PORT:-5077}"
    websocket_port="${PIXEAGLE_DEFAULT_WEBSOCKET_PORT:-5551}"
    mavlink2rest_port="${PIXEAGLE_DEFAULT_MAVLINK2REST_PORT:-8088}"
    mavsdk_port=50051
    dashboard_port="$(resolve_dashboard_port "$PROJECT_ROOT/dashboard")"
    backend_port="$(resolve_backend_port "$PROJECT_ROOT/configs/config.yaml")"
    config_file="$PROJECT_ROOT/configs/config.yaml"
    [[ -f "$config_file" ]] || config_file="$PROJECT_ROOT/configs/config_default.yaml"
    candidate="$(get_yaml_int_value "$config_file" MAVSDK_SERVER_PORT 2>/dev/null || true)"
    is_valid_port "$candidate" && mavsdk_port="$candidate"

    previous_umask="$(umask)"
    umask 077
    lsof_error_file="$(mktemp "${TMPDIR:-/tmp}/pixeagle-lsof.XXXXXX")" || {
        umask "$previous_umask"
        printf '%s\n' "listener ownership unknown (cannot create private lsof diagnostics)"
        return 0
    }
    umask "$previous_umask"

    for port in "$dashboard_port" "$backend_port" "$websocket_port" \
        "$mavlink2rest_port" "$mavsdk_port"; do
        if ! : > "$lsof_error_file"; then
            printf '%s\n' "listener ownership unknown (cannot reset private lsof diagnostics)"
            break
        fi
        lsof_status=0
        if raw_pids="$(lsof -w -nP -t -iTCP:"$port" -sTCP:LISTEN 2>"$lsof_error_file")"; then
            :
        else
            lsof_status=$?
        fi
        lsof_error="$(<"$lsof_error_file")"
        if (( lsof_status == 1 )) && [[ -z "$raw_pids" && -z "$lsof_error" ]]; then
            continue
        fi
        if (( lsof_status != 0 )) || [[ -n "$lsof_error" ]]; then
            printf 'listener ownership query failed on PixEagle port %s (lsof status %s)\n' \
                "$port" "$lsof_status"
            continue
        fi
        while IFS= read -r line; do
            if [[ -n "$line" && ! "$line" =~ ^[0-9]+$ ]]; then
                printf 'listener ownership query returned malformed output on PixEagle port %s\n' \
                    "$port"
                raw_pids=""
                break
            fi
        done <<< "$raw_pids"
        [[ -n "$raw_pids" ]] || continue
        pids="$(printf '%s\n' "$raw_pids" | sort -u)"
        [[ -z "$pids" ]] || printf 'listener(s) on PixEagle port %s: %s\n' \
            "$port" "${pids//$'\n'/,}"
    done
    if ! rm -f -- "$lsof_error_file"; then
        printf '%s\n' "listener ownership query diagnostics could not be removed"
    fi
}

assert_runtime_stopped() {
    local report_mode="${1:-report}"
    local blockers=()
    local label owned_pids runtime_mode socket_name

    while IFS= read -r label; do
        [[ -n "$label" ]] && blockers+=("$label")
    done < <(active_service_labels)

    if command -v tmux >/dev/null 2>&1; then
        for runtime_mode in manual service; do
            socket_name="$(pixeagle_tmux_socket_name "$PROJECT_ROOT" "$runtime_mode")"
            if pixeagle_tmux_session_exists "$socket_name" pixeagle; then
                if pixeagle_tmux_session_is_owned \
                    "$socket_name" pixeagle "$PROJECT_ROOT" "$runtime_mode"; then
                    blockers+=("owned $runtime_mode tmux runtime")
                else
                    blockers+=("conflicting $runtime_mode tmux runtime")
                fi
            fi
        done
        if pixeagle_default_tmux list-sessions -F '#{session_name}' 2>/dev/null |
            grep -Fxq pixeagle; then
            blockers+=("legacy/default tmux session pixeagle")
        fi
    fi

    owned_pids="$(pixeagle_owned_pids "$PROJECT_ROOT" | paste -sd, -)"
    if [[ -n "$owned_pids" ]]; then
        blockers+=("marked PixEagle process(es): $owned_pids")
    fi
    while IFS= read -r label; do
        [[ -n "$label" ]] && blockers+=("$label")
    done < <(runtime_listener_labels)

    if (( ${#blockers[@]} > 0 )); then
        if [[ "$report_mode" != quiet ]]; then
            log_error "PixEagle must be stopped before source or dependencies are changed"
            for label in "${blockers[@]}"; do
                log_detail "$label"
            done
            log_detail "Manual runtime: cd \"$PROJECT_ROOT\" && make stop"
            log_detail "Managed runtime: pixeagle-service stop (or sudo systemctl stop pixeagle.service)"
            log_detail "After it reports inactive and no owned listeners, rerun the same update command."
        fi
        return 1
    fi
    [[ "$report_mode" == quiet ]] || log_success "No active PixEagle runtime detected"
}

ensure_runtime_stopped_before_update() {
    local reply=""
    local stop_policy="${PIXEAGLE_UPDATE_STOP_RUNTIME:-}"

    if assert_runtime_stopped quiet; then
        log_success "No active PixEagle runtime detected"
        return 0
    fi
    if [[ "$DRY_RUN" == true ]]; then
        assert_runtime_stopped
        log_detail "Dry-run never stops a running runtime."
        return 1
    fi
    if ! owned_runtime_can_be_stopped; then
        assert_runtime_stopped
        log_error "Only a verified runtime owned by this checkout can be stopped automatically."
        return 1
    fi
    case "$stop_policy" in
        1) ;;
        0)
            log_error "Update requires a stopped runtime; automatic stop was disabled."
            return 1
            ;;
        "")
            if ! pixeagle_has_interactive_input; then
                log_error "PixEagle is running and interactive confirmation is unavailable."
                log_detail "Stop it first, or set PIXEAGLE_UPDATE_STOP_RUNTIME=1."
                return 1
            fi
            log_warn "PixEagle is running; update requires a brief shutdown."
            log_detail "The runtime will remain stopped after the update."
            printf '   Stop PixEagle and continue? [Y/n]: '
            if ! pixeagle_read_user_input reply; then
                log_error "Could not read runtime-stop confirmation."
                return 1
            fi
            case "$reply" in
                ""|[Yy]|[Yy][Ee][Ss]) ;;
                [Nn]|[Nn][Oo])
                    log_info "Update cancelled; the active runtime was not changed."
                    return 1
                    ;;
                *)
                    log_error "Please answer y or n, then rerun the update."
                    return 1
                    ;;
            esac
            ;;
        *)
            log_error "PIXEAGLE_UPDATE_STOP_RUNTIME must be 0 or 1."
            return 2
            ;;
    esac

    if ! stop_owned_runtime_for_update; then
        log_error "PixEagle could not be stopped through its ownership-aware controls."
        return 1
    fi
    if ! assert_runtime_stopped; then
        log_error "Update was not started because runtime shutdown is incomplete."
        return 1
    fi
}

print_plan() {
    echo ""
    echo "  PixEagle Update Plan"
    echo "  ---------------------"
    echo "  1. Own lifecycle, source, and virtual-environment resources"
    echo "  2. Verify every known PixEagle runtime path is stopped"
    echo "  3. Publish one exact fast-forward source candidate"
    echo "  4. Reconcile the selected Core/Full setup profile"
    echo "  5. Verify config metadata and tracked-checkout integrity"
    echo ""
}

tracked_checkout_is_clean() {
    git diff --quiet --ignore-submodules -- \
        && git diff --cached --quiet --ignore-submodules --
}

rollback_source_if_safe() {
    local reason="$1"
    local current_head=""
    local old_head="${PIXEAGLE_SYNC_OLD_HEAD:-}"
    local new_head="${PIXEAGLE_SYNC_NEW_HEAD:-}"

    [[ "${PIXEAGLE_SYNC_CHANGED:-false}" == true ]] || return 2
    if [[ ! "$old_head" =~ ^[0-9a-fA-F]{40}$ \
        || ! "$new_head" =~ ^[0-9a-fA-F]{40}$ ]]; then
        log_error "Automatic source rollback lacks exact old/new commit evidence"
        return 1
    fi
    current_head="$(git rev-parse --verify 'HEAD^{commit}' 2>/dev/null || true)"
    if [[ "$current_head" != "$new_head" ]]; then
        log_error "Automatic source rollback refused: HEAD changed after publication"
        log_detail "Expected $new_head but found ${current_head:-unavailable}."
        return 1
    fi
    if ! tracked_checkout_is_clean; then
        log_error "Automatic source rollback refused: tracked files changed during reconciliation"
        log_detail "Local tracked changes were preserved for inspection."
        return 1
    fi
    if ! declare -F _target_tree_preserves_untracked_paths >/dev/null 2>&1; then
        log_error "Automatic source rollback lacks the untracked-data collision guard"
        return 1
    fi
    if ! _target_tree_preserves_untracked_paths "$new_head" "$old_head"; then
        log_error "Automatic source rollback refused: previous source would overwrite operator data"
        log_detail "Move the colliding untracked/ignored path explicitly before manual recovery."
        return 1
    fi

    log_warn "$reason; restoring the previous source commit"
    if ! git reset --hard "$old_head" >/dev/null; then
        log_error "Could not restore the previous source commit"
        return 1
    fi
    current_head="$(git rev-parse --verify 'HEAD^{commit}' 2>/dev/null || true)"
    if [[ "$current_head" != "$old_head" ]]; then
        log_error "Source rollback did not restore the exact previous commit"
        return 1
    fi
    log_success "Previous source commit restored: $old_head"
    log_detail "Ignored config, credentials, models, and evidence were not deleted."
    return 0
}

report_update_failure() {
    local reason="$1"
    local rollback_status=0

    if [[ "${PIXEAGLE_SYNC_CHANGED:-false}" == true ]]; then
        rollback_source_if_safe "$reason" || rollback_status=$?
        if (( rollback_status != 0 )); then
            log_error "Update recovery is incomplete; do not start PixEagle yet"
            log_detail "Inspect git status, the initializer output, and configs/.config_default_preupdate.yaml."
            log_detail "No untracked or ignored operator data was automatically removed."
        fi
    else
        log_error "$reason; source HEAD was not changed"
    fi
    return 0
}

verify_reconciliation() {
    local current_head expected_head config_python staged_defaults status_script
    expected_head="${PIXEAGLE_SYNC_NEW_HEAD:-}"
    current_head="$(git rev-parse --verify 'HEAD^{commit}' 2>/dev/null || true)"
    if [[ ! "$expected_head" =~ ^[0-9a-fA-F]{40}$ || "$current_head" != "$expected_head" ]]; then
        log_error "Reconciliation ended on an unexpected source commit"
        return 1
    fi
    if ! tracked_checkout_is_clean; then
        log_error "Reconciliation changed tracked checkout files"
        git status --short
        return 1
    fi

    staged_defaults="$PROJECT_ROOT/configs/.config_default_preupdate.yaml"
    if [[ -e "$staged_defaults" || -L "$staged_defaults" ]]; then
        log_error "Pre-update config defaults remain unconsumed"
        return 1
    fi
    config_python="$(resolve_pixeagle_venv_python "$PROJECT_ROOT")"
    status_script="$PROJECT_ROOT/scripts/setup/config-sync-status.py"
    if [[ ! -x "$config_python" || ! -f "$status_script" || -L "$status_script" ]]; then
        log_error "Config lifecycle postcondition tools are unavailable"
        return 1
    fi
    if ! "$config_python" "$status_script" --project-root "$PROJECT_ROOT" --json \
        >/dev/null; then
        log_error "Config lifecycle metadata did not pass its read-only postcondition"
        return 1
    fi
    log_success "Source, environment, and config lifecycle postconditions passed"
}

run_update_transaction() {
    local sync_status=0 init_status=0

    if ! pixeagle_validate_resource_lock_context exclusive \
        "$LIFECYCLE_RESOURCE" "$PROJECT_ROOT" "$VENV_DIR"; then
        log_error "Update is outside the supervised lifecycle/source/venv transaction"
        return 73
    fi
    assert_runtime_stopped || return 1

    if [[ "$DRY_RUN" == true ]]; then
        log_success "Dry-run complete; source and environment were not changed"
        return 0
    fi

    # shellcheck source=scripts/lib/sync.sh
    source "$SYNC_SCRIPT"
    if do_sync; then
        :
    else
        sync_status=$?
        report_update_failure "Source candidate publication failed"
        return "$sync_status"
    fi

    log_info "Reconciling the selected installation profile"
    if PIXEAGLE_SETUP_ACTION=update-repair bash "$INIT_SCRIPT"; then
        :
    else
        init_status=$?
        report_update_failure "Setup reconciliation failed"
        return "$init_status"
    fi
    if ! verify_reconciliation; then
        report_update_failure "Update postcondition failed"
        return 1
    fi

    log_success "Update reconciliation complete"
    log_detail "Old HEAD: ${PIXEAGLE_SYNC_OLD_HEAD}"
    log_detail "New HEAD: ${PIXEAGLE_SYNC_NEW_HEAD}"
    log_detail "Source: ${PIXEAGLE_SYNC_REMOTE} ${PIXEAGLE_SYNC_BRANCH} (${PIXEAGLE_SYNC_REMOTE_URL})"
    log_detail "Start explicitly with make run after reviewing this summary."
}

main() {
    local -a original_args=("$@")

    if [[ "${1:-}" == --internal-update ]]; then
        INTERNAL_UPDATE=true
        shift
    fi
    parse_args "$@"
    cd "$PROJECT_ROOT"
    require_contract_files
    validate_automation_profile

    if [[ "$INTERNAL_UPDATE" == true ]]; then
        print_plan
        run_update_transaction
        return
    fi

    # Stop only a verified owned runtime after explicit operator consent. The
    # transaction repeats the check under lock to close the race window.
    if ! ensure_runtime_stopped_before_update; then
        log_error "Update was not started; no source, dependency, or config changes were made."
        return 1
    fi

    pixeagle_run_with_resource_locks \
        exclusive "update checkout" 30 \
        "$LIFECYCLE_RESOURCE" "$PROJECT_ROOT" "$VENV_DIR" -- \
        bash "$SCRIPT_DIR/update.sh" --internal-update "${original_args[@]}"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi

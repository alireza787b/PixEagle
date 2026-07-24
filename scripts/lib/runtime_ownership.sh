#!/usr/bin/env bash
# Shared, fail-closed ownership checks for PixEagle runtime processes/sessions.

pixeagle_canonical_root() {
    local root="$1"
    [[ -d "$root" ]] || return 1
    (cd "$root" 2>/dev/null && pwd -P)
}

pixeagle_runtime_mode_is_valid() {
    case "$1" in
        manual|service) return 0 ;;
        *) return 1 ;;
    esac
}

pixeagle_run_id_is_valid() {
    local run_id="$1"

    [[ "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]]
}

pixeagle_generate_run_id() {
    local prefix="${1:-pixeagle}"
    local identifier=""

    case "$prefix" in
        ""|*[!A-Za-z0-9_.-]*) return 1 ;;
    esac

    if [[ -r /proc/sys/kernel/random/uuid ]]; then
        IFS= read -r identifier < /proc/sys/kernel/random/uuid || return 1
    elif command -v od >/dev/null 2>&1 && [[ -r /dev/urandom ]]; then
        identifier="$(od -An -N16 -tx1 /dev/urandom 2>/dev/null | tr -d '[:space:]')" || return 1
    else
        printf 'A collision-resistant run ID source is unavailable\n' >&2
        return 1
    fi

    [[ "$identifier" =~ ^[A-Fa-f0-9-]{32,36}$ ]] || return 1
    identifier="${prefix}_${identifier}"
    pixeagle_run_id_is_valid "$identifier" || return 1
    printf '%s\n' "$identifier"
}

pixeagle_tmux_socket_name() {
    local project_root="$1"
    local runtime_mode="$2"
    local owner_uid="${3:-$(id -u)}"
    local canonical_root checksum

    pixeagle_runtime_mode_is_valid "$runtime_mode" || return 1
    [[ "$owner_uid" =~ ^[0-9]+$ ]] || return 1
    canonical_root="$(pixeagle_canonical_root "$project_root")" || return 1
    checksum="$(printf '%s\n' "$canonical_root" | cksum | awk '{print $1}')"
    [[ "$checksum" =~ ^[0-9]+$ ]] || return 1
    printf 'pixeagle-%s-%s-%s\n' "$owner_uid" "$runtime_mode" "$checksum"
}

pixeagle_without_systemd_runtime_channels() {
    local name
    local -a env_args=(-u NOTIFY_SOCKET)

    while IFS='=' read -r name _value; do
        case "$name" in
            WATCHDOG_*) env_args+=(-u "$name") ;;
        esac
    done < <(env)

    command env "${env_args[@]}" "$@"
}

pixeagle_without_resource_lock_context() {
    local -a env_args=(
        -u PIXEAGLE_RESOURCE_LOCK_MODE
        -u PIXEAGLE_RESOURCE_LOCK_SET
        -u PIXEAGLE_RESOURCE_LOCK_STATE_PATH
        -u PIXEAGLE_RESOURCE_LOCK_TOKEN
        -u PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_PID
        -u PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_START_TOKEN
        -u PIXEAGLE_RESOURCE_LOCK_SESSION_ID
        -u PIXEAGLE_ENVIRONMENT_LOCK_MODE
        -u PIXEAGLE_ENVIRONMENT_LOCK_PATH
        -u PIXEAGLE_ENVIRONMENT_LOCK_PATHS
        -u PIXEAGLE_ENVIRONMENT_LOCK_SUPERVISOR_PID
        -u PIXEAGLE_ENVIRONMENT_LOCK_SUPERVISOR_START_TOKEN
        -u PIXEAGLE_ENVIRONMENT_LOCK_SESSION_ID
        -u PIXEAGLE_SETUP_LOCK_PATH
        -u PIXEAGLE_SETUP_LOCK_STATE_PATH
        -u PIXEAGLE_SETUP_LOCK_TOKEN
        -u PIXEAGLE_SETUP_LOCK_SUPERVISOR_PID
        -u PIXEAGLE_SETUP_LOCK_SUPERVISOR_START_TOKEN
        -u PIXEAGLE_SETUP_LOCK_SESSION_ID
    )

    command env "${env_args[@]}" "$@"
}

pixeagle_tmux() {
    local socket_name="$1"
    local name
    local -a systemd_env_args=(-u NOTIFY_SOCKET)
    shift
    [[ "$socket_name" =~ ^[A-Za-z0-9_.-]+$ ]] || return 1

    while IFS='=' read -r name _value; do
        case "$name" in
            WATCHDOG_*) systemd_env_args+=(-u "$name") ;;
        esac
    done < <(env)

    pixeagle_without_resource_lock_context \
        env "${systemd_env_args[@]}" tmux -L "$socket_name" "$@"
}

# Address the user's real default tmux server even when this command is run
# from inside another tmux server. An inherited TMUX value otherwise redirects
# bare tmux commands to the caller's server and can hide a legacy session.
pixeagle_default_tmux() {
    env -u TMUX tmux "$@"
}

pixeagle_lifecycle_resource() {
    local project_root="$1"
    local canonical_root resource

    canonical_root="$(pixeagle_canonical_root "$project_root")" || return 1
    resource="$canonical_root/scripts/lib/runtime_ownership.sh"
    [[ -f "$resource" && ! -L "$resource" ]] || return 1
    printf '%s\n' "$resource"
}

pixeagle_tmux_session_exists() {
    local socket_name="$1"
    local session_name="$2"
    local listed_name

    command -v tmux >/dev/null 2>&1 || return 1
    while IFS= read -r listed_name; do
        [[ "$listed_name" == "$session_name" ]] && return 0
    done < <(pixeagle_tmux "$socket_name" list-sessions -F '#{session_name}' 2>/dev/null || true)
    return 1
}

pixeagle_tmux_environment_value() {
    local socket_name="$1"
    local session_name="$2"
    local key="$3"
    local marker

    pixeagle_tmux_session_exists "$socket_name" "$session_name" || return 1
    marker="$(pixeagle_tmux "$socket_name" show-environment -t "=$session_name" "$key" 2>/dev/null || true)"
    case "$marker" in
        "$key="*) printf '%s\n' "${marker#*=}" ;;
        *) return 1 ;;
    esac
}

pixeagle_tmux_session_is_owned() {
    local socket_name="$1"
    local session_name="$2"
    local project_root="$3"
    local expected_mode="${4:-}"
    local expected_run_id="${5:-}"
    local expected_root actual_root actual_mode actual_run_id

    expected_root="$(pixeagle_canonical_root "$project_root")" || return 1
    actual_root="$(pixeagle_tmux_environment_value "$socket_name" "$session_name" PIXEAGLE_PROJECT_ROOT)" || return 1
    [[ "$actual_root" == "$expected_root" ]] || return 1

    if [[ -n "$expected_mode" ]]; then
        pixeagle_runtime_mode_is_valid "$expected_mode" || return 1
        actual_mode="$(pixeagle_tmux_environment_value "$socket_name" "$session_name" PIXEAGLE_RUNTIME_MODE)" || return 1
        [[ "$actual_mode" == "$expected_mode" ]] || return 1
    fi
    if [[ -n "$expected_run_id" ]]; then
        pixeagle_run_id_is_valid "$expected_run_id" || return 1
        actual_run_id="$(pixeagle_tmux_environment_value "$socket_name" "$session_name" PIXEAGLE_RUN_ID)" || return 1
        [[ "$actual_run_id" == "$expected_run_id" ]] || return 1
    fi
}

pixeagle_pid_environment_value() {
    local pid="$1"
    local key="$2"
    local proc_root="${PIXEAGLE_PROC_ROOT:-/proc}"
    local environment_file="$proc_root/$pid/environ"

    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
    [[ -r "$environment_file" ]] || return 1
    local entry
    while IFS= read -r -d '' entry; do
        case "$entry" in
            "$key="*) printf '%s\n' "${entry#*=}"; return 0 ;;
        esac
    done 2>/dev/null < "$environment_file"
    return 1
}

pixeagle_proc_uid() {
    local process_path="$1"
    local process_uid=""

    if process_uid="$(stat -c '%u' "$process_path" 2>/dev/null)"; then
        printf '%s\n' "$process_uid"
        return 0
    fi
    if process_uid="$(stat -f '%u' "$process_path" 2>/dev/null)"; then
        printf '%s\n' "$process_uid"
        return 0
    fi
    return 1
}

pixeagle_pid_is_owned() {
    local pid="$1"
    local project_root="$2"
    local expected_uid="${3:-$(id -u)}"
    local expected_mode="${4:-}"
    local expected_run_id="${5:-}"
    local proc_root="${PIXEAGLE_PROC_ROOT:-/proc}"
    local expected_root actual_root process_uid actual_mode actual_run_id

    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
    [[ -d "$proc_root/$pid" ]] || return 1
    expected_root="$(pixeagle_canonical_root "$project_root")" || return 1
    process_uid="$(pixeagle_proc_uid "$proc_root/$pid")" || return 1
    [[ "$process_uid" == "$expected_uid" ]] || return 1

    actual_root="$(pixeagle_pid_environment_value "$pid" PIXEAGLE_PROJECT_ROOT)" || return 1
    [[ "$actual_root" == "$expected_root" ]] || return 1
    if [[ -n "$expected_mode" ]]; then
        pixeagle_runtime_mode_is_valid "$expected_mode" || return 1
        actual_mode="$(pixeagle_pid_environment_value "$pid" PIXEAGLE_RUNTIME_MODE)" || return 1
        [[ "$actual_mode" == "$expected_mode" ]] || return 1
    fi
    if [[ -n "$expected_run_id" ]]; then
        pixeagle_run_id_is_valid "$expected_run_id" || return 1
        actual_run_id="$(pixeagle_pid_environment_value "$pid" PIXEAGLE_RUN_ID)" || return 1
        [[ "$actual_run_id" == "$expected_run_id" ]] || return 1
    fi
}

pixeagle_pid_start_token() {
    local pid="$1"
    local proc_root="${PIXEAGLE_PROC_ROOT:-/proc}"
    local stat_line remainder
    local -a fields=()

    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
    [[ -r "$proc_root/$pid/stat" ]] || return 1
    IFS= read -r stat_line 2>/dev/null < "$proc_root/$pid/stat" || return 1
    remainder="${stat_line##*) }"
    read -r -a fields <<< "$remainder"
    # The remainder begins at proc stat field 3; starttime is field 22.
    [[ "${#fields[@]}" -ge 20 && "${fields[19]}" =~ ^[0-9]+$ ]] || return 1
    printf '%s\n' "${fields[19]}"
}

pixeagle_pid_identity_is_unchanged() {
    local pid="$1"
    local expected_start_token="$2"
    shift 2
    [[ "$(pixeagle_pid_start_token "$pid" 2>/dev/null || true)" == "$expected_start_token" ]] || return 1
    pixeagle_pid_is_owned "$pid" "$@"
}

pixeagle_terminate_owned_pid() {
    local pid="$1"
    local expected_start_token="$2"
    local project_root="$3"
    local expected_uid="$4"
    local runtime_mode="$5"
    local expected_run_id="${6:-}"
    local helper_dir helper

    helper_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)" || return 1
    helper="$helper_dir/terminate_owned_process.py"
    [[ -f "$helper" && ! -L "$helper" ]] || return 1
    python3 "$helper" \
        --pid "$pid" \
        --start-token "$expected_start_token" \
        --expected-uid "$expected_uid" \
        --project-root "$project_root" \
        --runtime-mode "$runtime_mode" \
        --run-id "$expected_run_id"
}

pixeagle_tmux_runtime_is_healthy() {
    local socket_name="$1"
    local session_name="$2"
    local project_root="$3"
    local runtime_mode="$4"
    local expected_run_id="${5:-}"
    local run_id ready expected_components required_components pane_records
    local actual_components required_component required_count
    local -a required_component_list=()

    pixeagle_tmux_session_exists "$socket_name" "$session_name" || return 1
    run_id="$(pixeagle_tmux_environment_value \
        "$socket_name" "$session_name" PIXEAGLE_RUN_ID 2>/dev/null)" || return 1
    pixeagle_run_id_is_valid "$run_id" || return 1
    [[ -z "$expected_run_id" || "$run_id" == "$expected_run_id" ]] || return 1
    pixeagle_tmux_session_is_owned \
        "$socket_name" "$session_name" "$project_root" "$runtime_mode" "$run_id" || return 1
    ready="$(pixeagle_tmux_environment_value \
        "$socket_name" "$session_name" PIXEAGLE_READY 2>/dev/null)" || return 1
    [[ "$ready" == 1 ]] || return 1
    expected_components="$(pixeagle_tmux_environment_value \
        "$socket_name" "$session_name" PIXEAGLE_EXPECTED_COMPONENTS 2>/dev/null)" || return 1
    [[ "$expected_components" =~ ^[A-Za-z0-9_.-]+(,[A-Za-z0-9_.-]+)*$ ]] || return 1
    required_components="$(pixeagle_tmux_environment_value \
        "$socket_name" "$session_name" PIXEAGLE_REQUIRED_COMPONENTS 2>/dev/null || true)"
    # Backward compatibility for runtimes created before required/optional
    # component roles were published.
    [[ -n "$required_components" ]] || required_components="$expected_components"
    [[ "$required_components" =~ ^[A-Za-z0-9_.-]+(,[A-Za-z0-9_.-]+)*$ ]] || return 1
    pane_records="$(pixeagle_tmux "$socket_name" list-panes -t "=$session_name" -s \
        -F '#{pane_dead}|#{@pixeagle_component}' 2>/dev/null)" || return 1
    [[ -n "$pane_records" ]] || return 1
    actual_components="$(awk -F'|' '$2 != "" {print $2}' \
        <<< "$pane_records" | LC_ALL=C sort | paste -sd, -)"
    [[ "$actual_components" == "$expected_components" ]] || return 1

    IFS=',' read -r -a required_component_list <<< "$required_components"
    for required_component in "${required_component_list[@]}"; do
        [[ ",$expected_components," == *",$required_component,"* ]] || return 1
        required_count="$(awk -F'|' -v component="$required_component" \
            '$1 == "0" && $2 == component {count++} END {print count + 0}' \
            <<< "$pane_records")"
        [[ "$required_count" == 1 ]] || return 1
    done
}

pixeagle_owned_pids() {
    local project_root="$1"
    local expected_uid="${2:-$(id -u)}"
    local expected_mode="${3:-}"
    local expected_run_id="${4:-}"
    local proc_root="${PIXEAGLE_PROC_ROOT:-/proc}"
    local process_dir pid
    local -a process_dirs=()

    # Snapshot directory names before ownership checks. Those checks may invoke
    # short-lived utilities; a live glob per iteration could enumerate helpers
    # created by this inventory itself.
    process_dirs=("$proc_root"/[0-9]*)
    for process_dir in "${process_dirs[@]}"; do
        [[ -d "$process_dir" ]] || continue
        pid="${process_dir##*/}"
        [[ "$pid" != "$$" && "$pid" != "$BASHPID" && "$pid" != "$PPID" ]] || continue
        if pixeagle_pid_is_owned "$pid" "$project_root" "$expected_uid" "$expected_mode" "$expected_run_id"; then
            printf '%s\n' "$pid"
        fi
    done
}

pixeagle_wait_for_pid_exit() {
    local pid="$1"
    local expected_start_token="$2"
    local attempts="${3:-20}"
    local delay="${4:-0.1}"
    local attempt current_token

    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
    [[ "$expected_start_token" =~ ^[0-9]+$ ]] || return 1
    [[ "$attempts" =~ ^[1-9][0-9]*$ ]] || return 1
    for ((attempt=0; attempt<attempts; attempt++)); do
        current_token="$(pixeagle_pid_start_token "$pid" 2>/dev/null || true)"
        [[ "$current_token" == "$expected_start_token" ]] || return 0
        sleep "$delay"
    done
    return 1
}

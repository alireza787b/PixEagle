#!/usr/bin/env bash
# Exact-path backup/restore transaction for PixEagle virtual environments.
# shellcheck disable=SC2317  # The helper supports sourcing in policy tests.

if [[ -n "${PIXEAGLE_VENV_TRANSACTION_SH_LOADED:-}" ]]; then
    return 0 2>/dev/null || exit 0
fi
PIXEAGLE_VENV_TRANSACTION_SH_LOADED=1

pixeagle_venv_transaction_process_token() {
    local pid="$1"
    local stat_line remainder
    local -a fields=()

    [[ "$pid" =~ ^[1-9][0-9]*$ && -r "/proc/$pid/stat" ]] || return 1
    IFS= read -r stat_line < "/proc/$pid/stat" || return 1
    remainder="${stat_line##*) }"
    read -r -a fields <<< "$remainder"
    [[ "${#fields[@]}" -ge 20 && "${fields[19]}" =~ ^[0-9]+$ ]] || return 1
    printf '%s\n' "${fields[19]}"
}

pixeagle_venv_transaction_target() {
    local target="$1"
    local parent basename

    [[ "$target" == /* ]] || return 1
    parent="$(dirname "$target")"
    basename="$(basename "$target")"
    [[ "$basename" != "." && "$basename" != ".." && "$basename" != "/" ]] || return 1
    [[ -d "$parent" && ! -L "$parent" ]] || return 1
    parent="$(cd "$parent" 2>/dev/null && pwd -P)" || return 1
    printf '%s/%s\n' "$parent" "$basename"
}

pixeagle_venv_transaction_owner_is_live() {
    local owner_pid="${PIXEAGLE_VENV_TRANSACTION_OWNER_PID:-}"
    local owner_token="${PIXEAGLE_VENV_TRANSACTION_OWNER_START_TOKEN:-}"

    [[ "$owner_pid" =~ ^[1-9][0-9]*$ && "$owner_token" =~ ^[0-9]+$ ]] \
        && [[ "$(pixeagle_venv_transaction_process_token "$owner_pid" 2>/dev/null || true)" == "$owner_token" ]]
}

pixeagle_begin_venv_transaction() {
    local requested_target="$1"
    local operation="${2:-Python environment mutation}"
    local target parent backup_root backup_venv owner_pid owner_token
    local venv_bytes available_bytes reserve_bytes required_bytes

    target="$(pixeagle_venv_transaction_target "$requested_target")" || {
        printf 'Refusing unsafe PixEagle venv transaction target: %s\n' "$requested_target" >&2
        return 1
    }

    if [[ -n "${PIXEAGLE_VENV_TRANSACTION_OWNER_PID:-}" ]]; then
        if [[ "${PIXEAGLE_VENV_TRANSACTION_TARGET:-}" != "$target" ]] \
            || ! pixeagle_venv_transaction_owner_is_live; then
            printf 'Refusing invalid inherited PixEagle venv transaction\n' >&2
            return 1
        fi
        return 0
    fi

    if [[ -e "$target" || -L "$target" ]]; then
        if [[ ! -d "$target" || -L "$target" ]] \
            || [[ "$(stat -Lc '%u' -- "$target" 2>/dev/null || true)" != "$(id -u)" ]]; then
            printf 'PixEagle venv must be an owner-controlled, non-symlink directory: %s\n' "$target" >&2
            return 1
        fi
        PIXEAGLE_VENV_TRANSACTION_TARGET_EXISTED=1
    else
        PIXEAGLE_VENV_TRANSACTION_TARGET_EXISTED=0
    fi

    parent="$(dirname "$target")"
    backup_root=""
    if [[ "$PIXEAGLE_VENV_TRANSACTION_TARGET_EXISTED" == "1" ]]; then
        venv_bytes="$(du -s --block-size=1 -- "$target" 2>/dev/null | awk '{print $1}')"
        available_bytes="$(df -P --block-size=1 -- "$parent" 2>/dev/null | awk 'NR==2 {print $4}')"
        [[ "$venv_bytes" =~ ^[0-9]+$ && "$available_bytes" =~ ^[0-9]+$ ]] || return 1
        reserve_bytes=$((64 * 1024 * 1024))
        required_bytes=$((venv_bytes + reserve_bytes))
        if (( available_bytes < required_bytes )); then
            printf '%s requires %s bytes free for exact venv rollback; only %s available\n' \
                "$operation" "$required_bytes" "$available_bytes" >&2
            return 1
        fi

        backup_root="$(mktemp -d "$parent/.pixeagle-venv-backup.XXXXXX")" || return 1
        chmod 0700 -- "$backup_root" || { rm -rf -- "$backup_root"; return 1; }
        backup_venv="$backup_root/venv"
        if ! cp -a --reflink=auto -- "$target" "$backup_venv"; then
            rm -rf -- "$backup_root"
            printf 'Could not create exact venv rollback copy for %s\n' "$operation" >&2
            return 1
        fi
    fi

    owner_pid="${BASHPID:-$$}"
    owner_token="$(pixeagle_venv_transaction_process_token "$owner_pid" 2>/dev/null || true)"
    if [[ ! "$owner_token" =~ ^[0-9]+$ ]]; then
        [[ -z "$backup_root" ]] || rm -rf -- "$backup_root"
        return 1
    fi

    PIXEAGLE_VENV_TRANSACTION_TARGET="$target"
    PIXEAGLE_VENV_TRANSACTION_BACKUP_ROOT="$backup_root"
    PIXEAGLE_VENV_TRANSACTION_OWNER_PID="$owner_pid"
    PIXEAGLE_VENV_TRANSACTION_OWNER_START_TOKEN="$owner_token"
    PIXEAGLE_VENV_TRANSACTION_COMMITTED=0
    export PIXEAGLE_VENV_TRANSACTION_TARGET PIXEAGLE_VENV_TRANSACTION_BACKUP_ROOT
    export PIXEAGLE_VENV_TRANSACTION_TARGET_EXISTED PIXEAGLE_VENV_TRANSACTION_COMMITTED
    export PIXEAGLE_VENV_TRANSACTION_OWNER_PID PIXEAGLE_VENV_TRANSACTION_OWNER_START_TOKEN
}

pixeagle_rollback_venv_transaction() {
    local target="${PIXEAGLE_VENV_TRANSACTION_TARGET:-}"
    local backup_root="${PIXEAGLE_VENV_TRANSACTION_BACKUP_ROOT:-}"
    local parent displaced

    [[ -n "$target" ]] || return 0
    parent="$(dirname "$target")"
    if [[ "${PIXEAGLE_VENV_TRANSACTION_TARGET_EXISTED:-0}" == "1" ]]; then
        [[ -d "$backup_root/venv" && ! -L "$backup_root/venv" ]] || {
            printf 'PixEagle venv rollback copy is unavailable: %s\n' "$backup_root" >&2
            return 1
        }
        displaced="$(mktemp -d "$parent/.pixeagle-venv-failed.XXXXXX")" || return 1
        rmdir -- "$displaced" || return 1
        if [[ -e "$target" || -L "$target" ]]; then
            mv -- "$target" "$displaced" || return 1
        fi
        if ! mv -- "$backup_root/venv" "$target"; then
            if [[ ! -e "$target" && ! -L "$target" && -e "$displaced" ]]; then
                mv -- "$displaced" "$target" 2>/dev/null || true
            fi
            return 1
        fi
        rm -rf -- "$displaced" "$backup_root"
    else
        if [[ -L "$target" || -f "$target" ]]; then
            rm -f -- "$target"
        elif [[ -d "$target" ]]; then
            rm -rf --one-file-system -- "$target"
        elif [[ -e "$target" ]]; then
            rm -f -- "$target"
        fi
    fi
}

pixeagle_commit_venv_transaction() {
    local current_pid="${BASHPID:-$$}"
    local backup_root="${PIXEAGLE_VENV_TRANSACTION_BACKUP_ROOT:-}"

    if [[ "${PIXEAGLE_VENV_TRANSACTION_OWNER_PID:-}" != "$current_pid" ]]; then
        return 0
    fi
    [[ -z "$backup_root" ]] || rm -rf -- "$backup_root" || return 1
    PIXEAGLE_VENV_TRANSACTION_COMMITTED=1
    export PIXEAGLE_VENV_TRANSACTION_COMMITTED
}

pixeagle_finalize_venv_transaction() {
    local current_pid="${BASHPID:-$$}"
    local result=0

    if [[ "${PIXEAGLE_VENV_TRANSACTION_OWNER_PID:-}" == "$current_pid" ]] \
        && [[ "${PIXEAGLE_VENV_TRANSACTION_COMMITTED:-0}" != "1" ]]; then
        pixeagle_rollback_venv_transaction || result=1
    fi
    unset PIXEAGLE_VENV_TRANSACTION_TARGET PIXEAGLE_VENV_TRANSACTION_BACKUP_ROOT
    unset PIXEAGLE_VENV_TRANSACTION_TARGET_EXISTED PIXEAGLE_VENV_TRANSACTION_COMMITTED
    unset PIXEAGLE_VENV_TRANSACTION_OWNER_PID PIXEAGLE_VENV_TRANSACTION_OWNER_START_TOKEN
    return "$result"
}

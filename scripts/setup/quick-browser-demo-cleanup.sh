#!/usr/bin/env bash
# Stop a quick browser demo and remove generated demo credentials.
#
# Destructive actions require CONFIRM=1. Use DRY_RUN=1 to preview.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$PIXEAGLE_DIR/scripts/lib/common.sh"
# shellcheck source=scripts/lib/webrtc_firewall.sh
source "$PIXEAGLE_DIR/scripts/lib/webrtc_firewall.sh"

resolve_python() {
    if [[ -n "${PIXEAGLE_QUICK_DEMO_PYTHON:-${PYTHON:-}}" ]]; then
        printf '%s\n' "${PIXEAGLE_QUICK_DEMO_PYTHON:-${PYTHON:-}}"
    elif [[ -x "$PIXEAGLE_DIR/.venv/bin/python" ]]; then
        printf '%s\n' "$PIXEAGLE_DIR/.venv/bin/python"
    elif [[ -x "$PIXEAGLE_DIR/venv/bin/python" ]]; then
        printf '%s\n' "$PIXEAGLE_DIR/venv/bin/python"
    else
        printf '%s\n' "python3"
    fi
}

truthy() {
    case "${1:-}" in
        1|true|TRUE|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

run_privileged() {
    if pixeagle_sudo_run "$@"; then
        return 0
    else
        local status=$?
    fi
    if [[ -n "${PIXEAGLE_SUDO_FAILURE_REASON:-}" ]]; then
        echo "ERROR: $(pixeagle_sudo_failure_message)" >&2
    fi
    return "$status"
}

remove_file_if_present() {
    local path="$1"
    local label="$2"
    local dry_run="$3"

    if [[ -z "$path" ]]; then
        return 0
    fi
    if [[ ! -e "$path" && ! -L "$path" ]]; then
        echo "$label: already absent ($path)"
        return 0
    fi
    if [[ -d "$path" && ! -L "$path" ]]; then
        echo "WARNING: refusing to remove directory for $label: $path" >&2
        return 1
    fi
    if truthy "$dry_run"; then
        echo "$label: would remove $path"
    else
        rm -f -- "$path"
        echo "$label: removed $path"
    fi
}

remove_backups_if_requested() {
    local path="$1"
    local label="$2"
    local dry_run="$3"

    if [[ -z "$path" ]]; then
        return 0
    fi
    shopt -s nullglob
    local backups=("${path}".backup.*)
    shopt -u nullglob
    if [[ "${#backups[@]}" -eq 0 ]]; then
        echo "$label backups: none found"
        return 0
    fi
    local backup
    for backup in "${backups[@]}"; do
        if [[ -d "$backup" && ! -L "$backup" ]]; then
            echo "WARNING: refusing to remove directory backup: $backup" >&2
            continue
        fi
        if truthy "$dry_run"; then
            echo "$label backups: would remove $backup"
        else
            rm -f -- "$backup"
            echo "$label backups: removed $backup"
        fi
    done
}

restore_local_profile() {
    local dry_run="$1"
    local python
    python="$(resolve_python)"
    if truthy "$dry_run"; then
        echo "Configuration: would restore local-only profile with $python scripts/setup/apply-setup-profile.py --profile local_dev"
    else
        "$python" scripts/setup/apply-setup-profile.py --profile local_dev >/dev/null
        echo "Configuration: restored local-only profile in configs/config.yaml"
    fi
}

main() {
    cd "$PIXEAGLE_DIR"

    local dashboard_port="${DASHBOARD_PORT:-3040}"
    local backend_port="${HTTP_STREAM_PORT:-5077}"
    local secret_dir="${PIXEAGLE_QUICK_DEMO_SECRET_DIR:-$HOME/.config/pixeagle/secrets}"
    local user_file="${SESSION_USER_FILE:-$secret_dir/demo-browser-users.json}"
    local handoff_file="${CREDENTIAL_HANDOFF_FILE:-$secret_dir/demo-browser-handoff.json}"
    local firewall_receipt="${FIREWALL_RECEIPT_FILE:-${handoff_file}.ufw-rules}"
    local dry_run="${DRY_RUN:-0}"
    local confirm="${CONFIRM:-0}"
    local stop_demo="${STOP_DEMO:-1}"
    local remove_credentials="${REMOVE_DEMO_CREDENTIALS:-1}"
    local remove_backups="${REMOVE_DEMO_BACKUPS:-0}"
    local close_firewall="${CLOSE_FIREWALL:-0}"
    local restore_profile="${RESTORE_LOCAL_PROFILE:-1}"

    echo "PixEagle quick browser demo cleanup"
    echo "Mode: $(truthy "$dry_run" && echo "dry run (no services, files, or firewall rules will be changed)" || echo "cleanup")"
    echo "Stop services: $stop_demo"
    echo "Remove demo credentials: $remove_credentials"
    echo "Remove credential backups: $remove_backups"
    echo "Restore local-only config profile: $restore_profile"
    echo "Close UFW rules: $close_firewall"
    echo "Credential store: $user_file"
    echo "Credential handoff: $handoff_file"
    echo "UFW receipt: $firewall_receipt"
    echo "Dashboard port: $dashboard_port"
    echo "Backend/API port: $backend_port"

    if ! truthy "$dry_run" && ! truthy "$confirm"; then
        echo "ERROR: cleanup changes require CONFIRM=1. Preview with DRY_RUN=1." >&2
        return 2
    fi

    if truthy "$close_firewall"; then
        if [[ -e "$firewall_receipt" || -L "$firewall_receipt" ]]; then
            local firewall_dry_run=0
            if truthy "$dry_run"; then
                firewall_dry_run=1
            fi
            pixeagle_ufw_delete_receipt_rules \
                "$firewall_receipt" "$firewall_dry_run" || {
                echo "ERROR: firewall cleanup failed; services, credentials, and config were not changed." >&2
                return 2
            }
        else
            echo "Firewall: no PixEagle-owned receipt; no UFW rule will be removed."
        fi
    fi

    if truthy "$stop_demo"; then
        if truthy "$dry_run"; then
            echo "Services: would run bash scripts/stop.sh"
        else
            bash scripts/stop.sh >/dev/null 2>&1 || true
            echo "Services: stopped PixEagle tmux demo session if it was running"
        fi
    fi

    if truthy "$remove_credentials"; then
        remove_file_if_present "$handoff_file" "Credential handoff" "$dry_run"
        remove_file_if_present "$user_file" "Credential store" "$dry_run"
        if truthy "$remove_backups"; then
            remove_backups_if_requested "$handoff_file" "Credential handoff" "$dry_run"
            remove_backups_if_requested "$user_file" "Credential store" "$dry_run"
        fi
    fi

    if truthy "$restore_profile"; then
        restore_local_profile "$dry_run"
    fi

    echo "Cleanup complete."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi

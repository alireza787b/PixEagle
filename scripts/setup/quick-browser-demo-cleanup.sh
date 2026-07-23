#!/usr/bin/env bash
# Stop a quick browser demo and remove generated demo credentials.
#
# Destructive actions require CONFIRM=1. Use DRY_RUN=1 to preview.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$PIXEAGLE_DIR/scripts/lib/common.sh"

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

host_scope() {
    local host="$1"
    if [[ -z "$host" ]]; then
        echo "unknown"
        return 0
    fi
    "$(resolve_python)" - "$host" <<'PY'
import ipaddress
import sys

host = sys.argv[1].strip()
try:
    address = ipaddress.ip_address(host.strip("[]"))
except ValueError:
    print("hostname")
    raise SystemExit(0)

demo_networks = [
    ipaddress.ip_network(value)
    for value in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "169.254.0.0/16",
        "fc00::/7",
        "fe80::/10",
    )
]
if any(address in network for network in demo_networks):
    print("private")
elif address.is_loopback or address.is_unspecified or address.is_multicast or address.is_reserved:
    print("invalid")
else:
    print("public")
PY
}

detect_interface_cidr() {
    local host="$1"
    if [[ -z "$host" ]] || ! command -v ip >/dev/null 2>&1; then
        return 1
    fi
    ip -o -f inet addr show scope global 2>/dev/null \
        | awk -v host="$host" '$4 ~ ("^" host "/") {print $4; exit}'
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

delete_ufw_rule() {
    local port="$1"
    local cidr="$2"
    local dry_run="$3"

    if truthy "$dry_run"; then
        if [[ -n "$cidr" ]]; then
            echo "Firewall: would delete allow rule for TCP $port from $cidr"
        else
            echo "Firewall: would delete allow rule for TCP $port from anywhere"
        fi
        return 0
    fi

    if ! command -v ufw >/dev/null 2>&1; then
        echo "Firewall: ufw is not installed; nothing to close here."
        return 0
    fi

    local ufw_status=""
    echo "Firewall: checking UFW status (sudo may request your password)."
    if ! ufw_status="$(run_privileged ufw status)"; then
        echo "Firewall: status check failed; no firewall rule was changed."
        return 0
    fi
    if ! grep -q "Status: active" <<<"$ufw_status"; then
        echo "Firewall: ufw is not active; check cloud/provider firewall manually if used."
        return 0
    fi

    if [[ -n "$cidr" ]]; then
        echo "Firewall: deleting allow rule for TCP $port from $cidr"
        run_privileged ufw --force delete allow from "$cidr" to any port "$port" proto tcp || true
    else
        echo "Firewall: deleting allow rule for TCP $port from anywhere"
        run_privileged ufw --force delete allow "$port/tcp" || true
    fi
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
    local host="${PIXEAGLE_QUICK_DEMO_HOST:-${LAN_HOST:-}}"
    local dry_run="${DRY_RUN:-0}"
    local confirm="${CONFIRM:-0}"
    local stop_demo="${STOP_DEMO:-1}"
    local remove_credentials="${REMOVE_DEMO_CREDENTIALS:-1}"
    local remove_backups="${REMOVE_DEMO_BACKUPS:-0}"
    local close_firewall="${CLOSE_FIREWALL:-0}"
    local restore_profile="${RESTORE_LOCAL_PROFILE:-1}"
    local allow_broad_firewall_cleanup="${ALLOW_BROAD_FIREWALL_CLEANUP:-0}"

    echo "PixEagle quick browser demo cleanup"
    echo "Mode: $(truthy "$dry_run" && echo "dry run (no services, files, or firewall rules will be changed)" || echo "cleanup")"
    echo "Stop services: $stop_demo"
    echo "Remove demo credentials: $remove_credentials"
    echo "Remove credential backups: $remove_backups"
    echo "Restore local-only config profile: $restore_profile"
    echo "Close UFW rules: $close_firewall"
    echo "Credential store: $user_file"
    echo "Credential handoff: $handoff_file"
    echo "Dashboard port: $dashboard_port"
    echo "Backend/API port: $backend_port"

    if ! truthy "$dry_run" && ! truthy "$confirm"; then
        echo "ERROR: cleanup changes require CONFIRM=1. Preview with DRY_RUN=1." >&2
        return 2
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

    if truthy "$close_firewall"; then
        local cidr=""
        local scope
        scope="$(host_scope "$host")"
        if [[ "$scope" == "public" ]]; then
            echo "Firewall: public demo cleanup; deleting broad UFW rules for the demo ports."
            if [[ -n "${TRUSTED_CIDR:-}" ]]; then
                echo "Firewall: ignoring TRUSTED_CIDR because public quick demos open broad UFW rules."
            fi
        elif [[ -n "${TRUSTED_CIDR:-}" ]]; then
            cidr="$TRUSTED_CIDR"
            echo "Firewall: using explicit TRUSTED_CIDR=$cidr for scoped cleanup."
        elif [[ "$scope" == "private" || "$scope" == "hostname" ]]; then
            cidr="$(detect_interface_cidr "$host" || true)"
            if [[ -z "$cidr" ]]; then
                echo "ERROR: cannot infer the trusted CIDR for LAN/private-overlay firewall cleanup." >&2
                echo "Set TRUSTED_CIDR=<cidr> to delete scoped rules, or set ALLOW_BROAD_FIREWALL_CLEANUP=1 only if the demo opened broad rules." >&2
                if truthy "$allow_broad_firewall_cleanup"; then
                    echo "Firewall: ALLOW_BROAD_FIREWALL_CLEANUP=1 accepted; deleting broad UFW rules for demo ports."
                else
                    return 2
                fi
            fi
        elif truthy "$allow_broad_firewall_cleanup"; then
            echo "Firewall: host scope is $scope; ALLOW_BROAD_FIREWALL_CLEANUP=1 accepted."
        else
            echo "ERROR: cannot classify LAN_HOST for firewall cleanup: ${host:-<empty>}." >&2
            echo "Set TRUSTED_CIDR=<cidr> for scoped cleanup or ALLOW_BROAD_FIREWALL_CLEANUP=1 for intentional broad cleanup." >&2
            return 2
        fi
        delete_ufw_rule "$dashboard_port" "$cidr" "$dry_run"
        delete_ufw_rule "$backend_port" "$cidr" "$dry_run"
    fi

    echo "Cleanup complete."
}

main "$@"

#!/usr/bin/env bash
# Configure and optionally start the simplest browser demo profile.
#
# Intended use after `make init` on a companion computer or demo VPS:
#   make quick-browser-demo LAN_HOST=<pixeagle-ip-or-hostname>
#
# Defaults are intentionally beginner-friendly for isolated LAN/private overlay
# demos while keeping public HTTP exposure explicit.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

truthy() {
    case "${1:-}" in
        1|true|TRUE|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

run_privileged() {
    if [[ "$EUID" -eq 0 ]]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        echo "ERROR: firewall changes require root or sudo." >&2
        return 1
    fi
}

shell_quote() {
    printf '%q' "$1"
}

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

detect_host() {
    local detected=""
    if command -v ip >/dev/null 2>&1; then
        detected="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}' || true)"
    fi
    if [[ -z "$detected" ]] && command -v hostname >/dev/null 2>&1; then
        detected="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
    fi
    printf '%s\n' "$detected"
}

host_scope() {
    local host="$1"
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

detect_trusted_cidr() {
    local host="$1"
    if [[ -n "${TRUSTED_CIDR:-}" ]]; then
        printf '%s\n' "$TRUSTED_CIDR"
        return 0
    fi
    if ! command -v ip >/dev/null 2>&1; then
        return 1
    fi
    ip -o -f inet addr show scope global 2>/dev/null \
        | awk -v host="$host" '$4 ~ ("^" host "/") {print $4; exit}'
}

open_ufw_port() {
    local port="$1"
    local comment="$2"
    local cidr="${3:-}"
    if [[ -n "$cidr" ]]; then
        run_privileged ufw allow from "$cidr" to any port "$port" proto tcp comment "$comment"
    else
        run_privileged ufw allow "$port/tcp" comment "$comment"
    fi
}

ensure_parent_dir() {
    local target="$1"
    local parent
    parent="$(dirname "$target")"
    if [[ -d "$parent" ]]; then
        return 0
    fi
    install -d -m 0700 "$parent"
}

maybe_open_firewall() {
    local host="$1"
    local scope="$2"
    local dashboard_port="$3"
    local backend_port="$4"
    local mode="${OPEN_FIREWALL:-${PIXEAGLE_QUICK_DEMO_OPEN_FIREWALL:-auto}}"

    case "$mode" in
        0|false|FALSE|no|NO|off|OFF)
            echo "Firewall: skipped by OPEN_FIREWALL=$mode"
            return 0
            ;;
        auto|1|true|TRUE|yes|YES|on|ON)
            ;;
        *)
            echo "ERROR: OPEN_FIREWALL must be auto, 1, or 0 (got $mode)" >&2
            return 2
            ;;
    esac

    if ! command -v ufw >/dev/null 2>&1; then
        echo "Firewall: ufw is not installed; check any OS/cloud firewall manually."
        return 0
    fi
    if ! run_privileged ufw status 2>/dev/null | grep -q "Status: active"; then
        echo "Firewall: ufw is not active; check any cloud/provider firewall manually."
        return 0
    fi

    if [[ "$scope" == "public" && "$mode" == "auto" ]]; then
        echo "Firewall: public HTTP demo detected; not opening public ports automatically."
        echo "Set OPEN_FIREWALL=1 with ALLOW_PUBLIC_HTTP_DEMO=1 only for a temporary public demo."
        return 0
    fi

    local cidr=""
    if [[ "$scope" != "public" ]]; then
        cidr="$(detect_trusted_cidr "$host" || true)"
        if [[ -z "$cidr" ]]; then
            echo "Firewall: could not infer a trusted CIDR for $host; set TRUSTED_CIDR=<cidr> or OPEN_FIREWALL=1."
            return 0
        fi
    fi

    open_ufw_port "$dashboard_port" "PixEagle quick browser demo dashboard" "$cidr"
    open_ufw_port "$backend_port" "PixEagle quick browser demo API/media" "$cidr"
    if [[ -n "$cidr" ]]; then
        echo "Firewall: allowed ports $dashboard_port and $backend_port from $cidr."
    else
        echo "Firewall: allowed ports $dashboard_port and $backend_port from anywhere for a temporary public demo."
    fi
}

verify_dashboard_http() {
    local port="$1"
    local url="http://127.0.0.1:$port/"

    if ! command -v curl >/dev/null 2>&1; then
        echo "Dashboard HTTP check: skipped (curl is unavailable; launcher port gate passed)."
        return 0
    fi
    for _ in 1 2 3 4 5; do
        if curl --fail --silent --show-error --max-time 5 "$url" >/dev/null 2>&1; then
            echo "Dashboard HTTP check: verified locally at $url"
            return 0
        fi
        sleep 1
    done
    echo "ERROR: dashboard port opened, but an HTTP page was not returned at $url." >&2
    echo "Inspect: make status and logs/runtime/<run-id>/dashboard.log" >&2
    return 1
}

main() {
    cd "$PIXEAGLE_DIR"

    local host="${PIXEAGLE_QUICK_DEMO_HOST:-${LAN_HOST:-}}"
    if [[ -z "$host" ]]; then
        host="$(detect_host)"
    fi
    if [[ -z "$host" ]]; then
        echo "ERROR: could not detect a browser-reachable host address." >&2
        echo "Run: make quick-browser-demo LAN_HOST=<this-pixeagle-ip-or-hostname>" >&2
        return 2
    fi

    local dashboard_port="${DASHBOARD_PORT:-3040}"
    local backend_port="${HTTP_STREAM_PORT:-5077}"
    local secret_dir="${PIXEAGLE_QUICK_DEMO_SECRET_DIR:-$HOME/.config/pixeagle/secrets}"
    local user_file="${SESSION_USER_FILE:-$secret_dir/demo-browser-users.json}"
    local handoff_file="${CREDENTIAL_HANDOFF_FILE:-$secret_dir/demo-browser-handoff.json}"
    local username="${DEMO_USERNAME:-${SESSION_USERNAME:-admin}}"
    local role="${DEMO_ROLE:-${SESSION_ROLE:-admin}}"
    local credential_mode="${DEMO_CREDENTIAL_MODE:-prompt}"
    local allow_public="${ALLOW_PUBLIC_HTTP_DEMO:-${PIXEAGLE_ALLOW_PUBLIC_HTTP_DEMO:-0}}"
    local dry_run="${DRY_RUN:-0}"
    local start_demo="${START_DEMO:-${PIXEAGLE_QUICK_DEMO_START:-1}}"
    local rotate="${ROTATE_DEMO_CREDENTIALS:-1}"
    local scope
    scope="$(host_scope "$host")"

    if [[ "$scope" == "invalid" ]]; then
        echo "ERROR: $host is not a valid quick-demo host address." >&2
        return 2
    fi
    if [[ "$scope" == "public" ]] && ! truthy "$allow_public"; then
        echo "ERROR: $host appears to be public internet address space." >&2
        echo "Use a LAN/private-overlay IP for the default beginner demo." >&2
        echo "For a temporary public HTTP demo only, rerun with ALLOW_PUBLIC_HTTP_DEMO=1." >&2
        return 2
    fi

    local python
    python="$(resolve_python)"
    local profile_cmd=(
        "$python"
        scripts/setup/apply-setup-profile.py
        --profile demo_lan_browser
        --lan-host "$host"
        --http-stream-port "$backend_port"
        --dashboard-port "$dashboard_port"
        --session-user-file "$user_file"
        --credential-handoff-file "$handoff_file"
        --demo-username "$username"
        --demo-role "$role"
        --demo-credential-mode "$credential_mode"
    )
    if truthy "$rotate"; then
        profile_cmd+=(--rotate-demo-credentials)
    fi
    if truthy "$allow_public"; then
        profile_cmd+=(--allow-public-http-demo)
    fi
    if truthy "$dry_run"; then
        profile_cmd+=(--dry-run)
    fi

    echo "PixEagle quick browser demo"
    echo "Mode: $(truthy "$dry_run" && echo "dry run (no files, firewall, or services will be changed)" || echo "apply profile and optionally start demo")"
    echo "Host: $host ($scope)"
    echo "Dashboard URL: http://$host:$dashboard_port"
    echo "Backend/API URL: http://$host:$backend_port"
    echo "Username: $username"
    echo "Role: $role"
    echo "Credential mode: $credential_mode (Enter keeps the beginner admin/admin login)"
    echo "Configuration: configs/config.yaml"
    echo "Credential store: $user_file (hashed passwords only)"
    echo "Credential handoff: $handoff_file (one-time plaintext demo password)"
    echo "Services: dashboard/backend only; MAVSDK Server and MAVLink2REST are skipped for this browser demo"
    echo "Video transport: Auto uses WebSocket on public HTTP; manual WebRTC remains an explicit lab attempt"
    echo "Role override: use SESSION_ROLE=operator or SESSION_ROLE=viewer for a less-privileged demo account"
    echo "Credential override: use DEMO_CREDENTIAL_MODE=generated for a one-time password"
    local cleanup_args
    cleanup_args="LAN_HOST=$(shell_quote "$host") SESSION_USER_FILE=$(shell_quote "$user_file") CREDENTIAL_HANDOFF_FILE=$(shell_quote "$handoff_file") DASHBOARD_PORT=$dashboard_port BACKEND_PORT=$backend_port"
    echo "Cleanup restores local-only config by default; use RESTORE_LOCAL_PROFILE=0 only if applying another reviewed profile immediately."
    echo "Cleanup preview: DRY_RUN=1 make quick-browser-demo-cleanup $cleanup_args"
    echo "Cleanup after test: CONFIRM=1 make quick-browser-demo-cleanup $cleanup_args"
    if [[ "$scope" == "public" ]]; then
        echo "WARNING: temporary public HTTP demo; credentials cross the network without TLS."
        echo "Public firewall cleanup: add CLOSE_FIREWALL=1 to the cleanup command if this script opened UFW rules."
    fi

    if ! truthy "$dry_run"; then
        ensure_parent_dir "$user_file"
        ensure_parent_dir "$handoff_file"
    fi

    "${profile_cmd[@]}"

    if ! truthy "$dry_run"; then
        maybe_open_firewall "$host" "$scope" "$dashboard_port" "$backend_port"
        if truthy "$start_demo"; then
            bash scripts/stop.sh >/dev/null 2>&1 || true
            bash scripts/run.sh --no-attach -m -k
            verify_dashboard_http "$dashboard_port"
            echo "Started minimal browser demo. Open http://$host:$dashboard_port and log in as $username."
            echo "Exposed lab TCP ports: dashboard $dashboard_port and authenticated API/media $backend_port."
            echo "MAVSDK, MAVLink2REST, and MAVLink UDP ports were not exposed by this workflow."
        else
            echo "Start later with: bash scripts/run.sh --no-attach -m -k"
        fi
    fi
}

main "$@"

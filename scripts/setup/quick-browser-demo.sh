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
    "$(resolve_python)" "$PIXEAGLE_DIR/scripts/setup/browser_hosts.py" --format tsv \
        | awk -F '\t' 'NR == 1 {print $1; exit}'
}

host_scope() {
    "$(resolve_python)" "$PIXEAGLE_DIR/scripts/setup/browser_hosts.py" --classify "$1"
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

read_login_metadata() {
    local python="$1"
    local handoff_file="$2"

    "$python" - "$handoff_file" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    handoff = json.load(handle)

username = str(handoff.get("username") or "admin")
password_kind = "default" if handoff.get("password") == "admin" else "custom"
print(f"{username}\t{password_kind}")
PY
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
    local verbose="${PIXEAGLE_QUICK_DEMO_VERBOSE:-${VERBOSE:-0}}"
    local scope
    scope="$(host_scope "$host")"

    if [[ "$scope" == "invalid" || "$scope" == "unsupported" ]]; then
        echo "ERROR: $host is not a valid quick-demo host address." >&2
        return 2
    fi
    if [[ "$scope" == "public" ]] && ! truthy "$allow_public"; then
        echo "ERROR: $host appears to be public internet address space." >&2
        echo "Use a LAN/private or overlay IP for the default beginner demo." >&2
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
    if ! truthy "$verbose"; then
        profile_cmd+=(--quiet)
    fi

    echo "PixEagle browser lab"
    echo "Dashboard: http://$host:$dashboard_port"
    echo "Bind: 0.0.0.0 (open the dashboard URL, not the bind wildcard)"
    if [[ "$credential_mode" == "generated" ]]; then
        echo "Login: a one-time password will be stored in the owner-only handoff file"
    else
        echo "Login: choose below (Enter keeps admin/admin)"
    fi
    echo "Runtime: bundled video; PX4 commands are disabled"
    local cleanup_args
    cleanup_args="LAN_HOST=$(shell_quote "$host") SESSION_USER_FILE=$(shell_quote "$user_file") CREDENTIAL_HANDOFF_FILE=$(shell_quote "$handoff_file") DASHBOARD_PORT=$dashboard_port BACKEND_PORT=$backend_port"
    if [[ "$scope" == "public" ]]; then
        echo "Security: temporary public HTTP test only; production HTTPS guide:"
        echo "https://github.com/alireza787b/PixEagle/blob/main/docs/setup/production-remote-reverse-proxy.md"
    fi
    if truthy "$verbose"; then
        echo "Backend/API: http://$host:$backend_port"
        echo "Credential store: $user_file"
        echo "Credential handoff: $handoff_file"
        echo "Cleanup preview: DRY_RUN=1 CLOSE_FIREWALL=1 make quick-browser-demo-cleanup $cleanup_args"
    fi

    if ! truthy "$dry_run"; then
        ensure_parent_dir "$user_file"
        ensure_parent_dir "$handoff_file"
    fi

    "${profile_cmd[@]}"

    if ! truthy "$dry_run"; then
        local actual_username="$username"
        local password_kind="custom"
        if [[ -f "$handoff_file" ]]; then
            IFS=$'\t' read -r actual_username password_kind < <(
                read_login_metadata "$python" "$handoff_file"
            )
        fi
        if [[ "$password_kind" == "default" ]]; then
            echo "Login: $actual_username / admin"
        elif [[ "$credential_mode" == "generated" ]]; then
            echo "Login: $actual_username / password in $handoff_file"
        else
            echo "Login: $actual_username / the password selected above"
        fi
        maybe_open_firewall "$host" "$scope" "$dashboard_port" "$backend_port"
        if truthy "$start_demo"; then
            bash scripts/stop.sh >/dev/null 2>&1 || true
            bash scripts/run.sh --no-attach -m -k
            verify_dashboard_http "$dashboard_port"
            echo "Ready: http://$host:$dashboard_port"
            echo "Stop: make stop"
            echo "Cleanup: CONFIRM=1 CLOSE_FIREWALL=1 make quick-browser-demo-cleanup $cleanup_args"
        else
            echo "Start later with: bash scripts/run.sh --no-attach -m -k"
        fi
    fi
}

main "$@"

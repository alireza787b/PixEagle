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
# shellcheck source=scripts/lib/common.sh
source "$PIXEAGLE_DIR/scripts/lib/common.sh"
# shellcheck source=scripts/lib/webrtc_firewall.sh
source "$PIXEAGLE_DIR/scripts/lib/webrtc_firewall.sh"

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
    local cidr=""
    if [[ -n "${TRUSTED_CIDR:-}" ]]; then
        cidr="$TRUSTED_CIDR"
    else
        command -v ip >/dev/null 2>&1 || return 1
        cidr="$(
            ip -o -f inet addr show scope global 2>/dev/null \
                | awk -v host="$host" \
                    'split($4, address, "/") == 2 && address[1] == host {print $4; exit}'
        )"
    fi
    [[ -n "$cidr" ]] || return 1

    "$(resolve_python)" - "$cidr" <<'PY'
import ipaddress
import sys

try:
    network = ipaddress.ip_network(sys.argv[1], strict=False)
except ValueError:
    raise SystemExit(1)
print(network.with_prefixlen)
PY
}

open_ufw_rule() {
    local port="$1"
    local protocol="$2"
    local comment="$3"
    local cidr="${4:-}"
    if [[ -n "$cidr" ]]; then
        run_privileged \
            ufw allow from "$cidr" to any port "$port" proto "$protocol" \
            comment "$comment"
    else
        run_privileged ufw allow "$port/$protocol" comment "$comment"
    fi
}

add_owned_ufw_rule() {
    local record="$1"
    local token="" scope="" port="" protocol="" source=""
    IFS=$'\t' read -r token scope port protocol source <<< "$record"

    local added_rules rule_base
    added_rules="$(LC_ALL=C LANG=C run_privileged ufw show added)" || {
        echo "ERROR: could not inspect existing UFW rules." >&2
        return 2
    }
    rule_base="$(pixeagle_ufw_rule_base "$record")" || return 2
    if pixeagle_ufw_show_has_rule_base "$added_rules" "$rule_base"; then
        echo "Firewall: preserving existing operator rule ($rule_base)"
        return 0
    fi

    local cidr=""
    if [[ "$scope" == "scoped" ]]; then
        cidr="$source"
    fi
    open_ufw_rule "$port" "$protocol" "$token" "$cidr"

    added_rules="$(LC_ALL=C LANG=C run_privileged ufw show added)" || {
        echo "ERROR: could not verify the new UFW rule." >&2
        return 2
    }
    if ! pixeagle_ufw_show_has_token "$added_rules" "$token"; then
        echo "ERROR: UFW did not publish the PixEagle ownership marker $token." >&2
        return 2
    fi
    echo "Firewall: added owned rule $token"
}

verify_demo_ufw_rules() {
    local receipt_file="$1"
    local records added_rules record rule_base
    records="$(pixeagle_ufw_receipt_records "$receipt_file")" || {
        echo "ERROR: could not validate the PixEagle UFW ownership receipt." >&2
        return 2
    }
    added_rules="$(LC_ALL=C LANG=C run_privileged ufw show added)" || {
        echo "ERROR: could not verify active PixEagle UFW rules." >&2
        return 2
    }
    while IFS= read -r record; do
        rule_base="$(pixeagle_ufw_rule_base "$record")" || return 2
        if ! pixeagle_ufw_show_has_rule_base "$added_rules" "$rule_base"; then
            echo "ERROR: requested UFW rule was not published ($rule_base)." >&2
            return 2
        fi
    done <<< "$records"
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
    local webrtc_udp_port_range="$5"
    local receipt_file="$6"
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

    if [[ "$scope" == "local" ]]; then
        echo "Firewall: loopback-only browser lab; no host rule is required."
        return 0
    fi

    if ! command -v ufw >/dev/null 2>&1; then
        echo "Firewall: ufw is not installed; check any OS/cloud firewall manually."
        echo "Later UFW: rerun make quick-browser-demo LAN_HOST=$host after enabling it."
        return 0
    fi

    local ufw_status=""
    echo "Firewall: checking UFW status (sudo may request your password)."
    if ! ufw_status="$(LC_ALL=C LANG=C run_privileged ufw status)"; then
        echo "ERROR: UFW status check failed; browser-lab firewall setup was not verified." >&2
        return 2
    fi
    if ! grep -q "Status: active" <<<"$ufw_status"; then
        echo "Firewall: ufw is not active; check any cloud/provider firewall manually."
        echo "Later UFW: rerun make quick-browser-demo LAN_HOST=$host after enabling it."
        return 0
    fi
    if ! pixeagle_webrtc_validate_udp_port_range "$webrtc_udp_port_range"; then
        echo "ERROR: could not determine the host UDP range used by WebRTC ICE." >&2
        echo "No quick-demo firewall rule was changed." >&2
        return 2
    fi

    if [[ "$scope" == "public" && "$mode" == "auto" ]]; then
        echo "Firewall: public lab consent accepted; reconciling temporary owned rules."
    fi

    local cidr=""
    if [[ "$scope" != "public" ]]; then
        cidr="$(detect_trusted_cidr "$host" || true)"
        if [[ -z "$cidr" ]]; then
            echo "ERROR: could not infer a trusted CIDR for $host." >&2
            echo "Set TRUSTED_CIDR=<cidr>, or use OPEN_FIREWALL=0 only when rules are managed separately." >&2
            return 2
        fi
    fi

    if [[ -e "$receipt_file" || -L "$receipt_file" ]]; then
        echo "Firewall: reconciling prior PixEagle-owned demo rules."
        pixeagle_ufw_delete_receipt_rules "$receipt_file" 0 || return 2
    fi

    local nonce
    nonce="$("$(resolve_python)" -c 'import secrets; print(secrets.token_hex(6))')" || {
        echo "ERROR: could not create the UFW ownership identifier." >&2
        return 2
    }
    [[ "$nonce" =~ ^[a-f0-9]{12}$ ]] || return 2

    local rule_scope="broad" source="-"
    if [[ -n "$cidr" ]]; then
        rule_scope="scoped"
        source="$cidr"
    fi
    local records=(
        "pixeagle-demo-${nonce}-dashboard"$'\t'"$rule_scope"$'\t'"$dashboard_port"$'\t'"tcp"$'\t'"$source"
        "pixeagle-demo-${nonce}-backend"$'\t'"$rule_scope"$'\t'"$backend_port"$'\t'"tcp"$'\t'"$source"
        "pixeagle-demo-${nonce}-webrtc"$'\t'"$rule_scope"$'\t'"$webrtc_udp_port_range"$'\t'"udp"$'\t'"$source"
    )
    pixeagle_ufw_write_receipt "$receipt_file" "${records[@]}" || {
        echo "ERROR: could not publish the owner-only UFW receipt: $receipt_file" >&2
        return 2
    }

    local record
    for record in "${records[@]}"; do
        if ! add_owned_ufw_rule "$record"; then
            echo "Firewall: setup failed; rolling back only PixEagle-owned rules." >&2
            if ! pixeagle_ufw_delete_receipt_rules "$receipt_file" 0; then
                echo "ERROR: rollback incomplete; retain this receipt for recovery: $receipt_file" >&2
            fi
            return 2
        fi
    done
    if ! verify_demo_ufw_rules "$receipt_file"; then
        echo "Firewall: verification failed; rolling back only PixEagle-owned rules." >&2
        if ! pixeagle_ufw_delete_receipt_rules "$receipt_file" 0; then
            echo "ERROR: rollback incomplete; retain this receipt for recovery: $receipt_file" >&2
        fi
        return 2
    fi

    if [[ -n "$cidr" ]]; then
        echo "Firewall: allowed TCP $dashboard_port/$backend_port and WebRTC UDP $webrtc_udp_port_range from $cidr."
    else
        echo "Firewall: allowed TCP $dashboard_port/$backend_port and WebRTC UDP $webrtc_udp_port_range from anywhere for this temporary public demo."
    fi
    echo "Firewall receipt: $receipt_file"
    echo "Firewall: host UFW rules verified; provider/NAT reachability is separate."
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
    local user_file="$2"

    PYTHONPATH="$PIXEAGLE_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
        "$python" - "$user_file" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

users = payload.get("users", [])
enabled = [record for record in users if record.get("enabled", True) is True]
admins = [record for record in enabled if record.get("role") == "admin"]
if not admins:
    raise SystemExit("browser-session user file has no enabled administrator")
record = admins[0]
username = str(record.get("username") or "admin")

from classes.browser_user_store import verify_password_pbkdf2_sha256

password_kind = (
    "default"
    if verify_password_pbkdf2_sha256(
        password="admin",
        encoded=str(record.get("password_pbkdf2_sha256") or ""),
    )
    else "custom"
)
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
    local firewall_receipt="${FIREWALL_RECEIPT_FILE:-${handoff_file}.ufw-rules}"
    local username="${DEMO_USERNAME:-${SESSION_USERNAME:-admin}}"
    local role="${DEMO_ROLE:-${SESSION_ROLE:-admin}}"
    local credential_mode="${DEMO_CREDENTIAL_MODE:-prompt}"
    local allow_public="${ALLOW_PUBLIC_HTTP_DEMO:-${PIXEAGLE_ALLOW_PUBLIC_HTTP_DEMO:-0}}"
    local dry_run="${DRY_RUN:-0}"
    local start_demo="${START_DEMO:-${PIXEAGLE_QUICK_DEMO_START:-1}}"
    local rotate="${ROTATE_DEMO_CREDENTIALS:-0}"
    local verbose="${PIXEAGLE_QUICK_DEMO_VERBOSE:-${VERBOSE:-0}}"
    local reuse_existing=0
    local webrtc_udp_port_range=""
    local scope
    scope="$(host_scope "$host")"
    webrtc_udp_port_range="$(pixeagle_webrtc_detect_udp_port_range || true)"

    if [[ "$scope" == "invalid" || "$scope" == "unsupported" ]]; then
        echo "ERROR: $host is not a valid quick-demo host address." >&2
        return 2
    fi
    if [[ "$scope" == "local" ]]; then
        host="127.0.0.1"
    fi
    if [[ "$scope" == "public" ]] && ! truthy "$allow_public"; then
        echo "ERROR: $host appears to be public internet address space." >&2
        echo "Use a LAN/private or overlay IP for the default beginner demo." >&2
        echo "For a temporary public HTTP demo only, rerun with ALLOW_PUBLIC_HTTP_DEMO=1." >&2
        return 2
    fi
    if [[ -f "$user_file" ]] && ! truthy "$rotate"; then
        reuse_existing=1
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
        --demo-username "$username"
        --demo-role "$role"
        --demo-credential-mode "$credential_mode"
    )
    if [[ "$credential_mode" == "generated" ]]; then
        profile_cmd+=(--credential-handoff-file "$handoff_file")
    fi
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
    if [[ "$scope" == "local" ]]; then
        echo "Bind: 127.0.0.1 (this computer only)"
    else
        echo "Bind: 0.0.0.0 (open the dashboard URL, not the bind wildcard)"
    fi
    if truthy "$reuse_existing"; then
        echo "Login: existing dashboard account will be preserved"
    elif [[ "$credential_mode" == "generated" ]]; then
        echo "Login: a one-time password will be stored in the owner-only handoff file"
    else
        echo "Login: choose below (Enter keeps admin/admin)"
    fi
    echo "Runtime: configured video source (fresh installs default to bundled video); PX4 commands are disabled"
    local cleanup_args
    cleanup_args="LAN_HOST=$(shell_quote "$host") SESSION_USER_FILE=$(shell_quote "$user_file") CREDENTIAL_HANDOFF_FILE=$(shell_quote "$handoff_file") FIREWALL_RECEIPT_FILE=$(shell_quote "$firewall_receipt") DASHBOARD_PORT=$dashboard_port BACKEND_PORT=$backend_port"
    if [[ "$scope" == "public" ]]; then
        echo "Security: temporary public HTTP test only; production HTTPS guide:"
        echo "https://github.com/alireza787b/PixEagle/blob/main/docs/setup/production-remote-reverse-proxy.md"
    fi
    if truthy "$verbose"; then
        echo "Backend/API: http://$host:$backend_port"
        echo "Credential store: $user_file"
        if [[ "$credential_mode" == "generated" ]]; then
            echo "Credential handoff: $handoff_file"
        fi
        echo "UFW receipt: $firewall_receipt"
    fi
    if [[ "${PIXEAGLE_BOOTSTRAP_CONTEXT:-0}" != "1" ]]; then
        if [[ "$scope" == "local" ]]; then
            echo "Cleanup after testing: CONFIRM=1 make quick-browser-demo-cleanup $cleanup_args"
        else
            echo "Cleanup after testing: CONFIRM=1 CLOSE_FIREWALL=1 make quick-browser-demo-cleanup $cleanup_args"
        fi
    fi

    if ! truthy "$dry_run"; then
        ensure_parent_dir "$user_file"
        if [[ "$credential_mode" == "generated" ]]; then
            ensure_parent_dir "$handoff_file"
        fi
        ensure_parent_dir "$firewall_receipt"
    fi

    "${profile_cmd[@]}"

    if ! truthy "$dry_run"; then
        local actual_username="$username"
        local password_kind="custom"
        if [[ -f "$user_file" ]]; then
            IFS=$'\t' read -r actual_username password_kind < <(
                read_login_metadata "$python" "$user_file"
            )
        fi
        if [[ "$password_kind" == "default" ]]; then
            echo "Login: $actual_username / admin"
        elif [[ "$credential_mode" == "generated" ]]; then
            echo "Login: $actual_username / password in $handoff_file"
        elif truthy "$reuse_existing"; then
            echo "Login: $actual_username / existing password"
        else
            echo "Login: $actual_username / the password selected above"
        fi
        maybe_open_firewall \
            "$host" "$scope" "$dashboard_port" "$backend_port" \
            "$webrtc_udp_port_range" "$firewall_receipt"
        if truthy "$start_demo"; then
            bash scripts/stop.sh >/dev/null 2>&1 || true
            bash scripts/run.sh --no-attach -m -k
            verify_dashboard_http "$dashboard_port"
            echo "Ready: http://$host:$dashboard_port"
            if [[ "$scope" == "public" && -n "$webrtc_udp_port_range" ]]; then
                echo "Cloud firewall: allow UDP $webrtc_udp_port_range for WebRTC during this temporary lab."
            fi
            echo "Stop: make stop"
            if [[ "${PIXEAGLE_BOOTSTRAP_CONTEXT:-0}" != "1" ]]; then
                if [[ "$scope" == "local" ]]; then
                    echo "Cleanup: CONFIRM=1 make quick-browser-demo-cleanup $cleanup_args"
                else
                    echo "Cleanup: CONFIRM=1 CLOSE_FIREWALL=1 make quick-browser-demo-cleanup $cleanup_args"
                fi
            fi
        else
            echo "Start later with: bash scripts/run.sh --no-attach -m -k"
        fi
    fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi

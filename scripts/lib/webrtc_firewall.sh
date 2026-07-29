#!/usr/bin/env bash
# Shared WebRTC port-range and owned UFW receipt helpers.

PIXEAGLE_UFW_RECEIPT_MAGIC="pixeagle-quick-demo-ufw-v1"

pixeagle_webrtc_validate_udp_port_range() {
    local value="${1:-}"
    local first="${value%%:*}"
    local last="${value##*:}"
    [[ "$value" =~ ^[0-9]+:[0-9]+$ ]] || return 1
    first=$((10#$first))
    last=$((10#$last))
    (( first >= 1024 && first <= last && last <= 65535 ))
}

pixeagle_webrtc_detect_udp_port_range() {
    local range_file="${PIXEAGLE_IP_LOCAL_PORT_RANGE_FILE:-/proc/sys/net/ipv4/ip_local_port_range}"
    local first="" last="" extra=""
    [[ -r "$range_file" ]] || return 1
    read -r first last extra < "$range_file" || return 1
    [[ -z "$extra" ]] || return 1
    local value="${first}:${last}"
    pixeagle_webrtc_validate_udp_port_range "$value" || return 1
    printf '%s\n' "$value"
}

pixeagle_ufw_validate_port_spec() {
    local value="${1:-}"
    local protocol="${2:-}"
    [[ "$protocol" == "tcp" || "$protocol" == "udp" ]] || return 1
    if [[ "$value" =~ ^[0-9]+$ ]]; then
        value=$((10#$value))
        (( value >= 1 && value <= 65535 ))
        return
    fi
    [[ "$protocol" == "udp" ]] || return 1
    pixeagle_webrtc_validate_udp_port_range "$value"
}

pixeagle_ufw_validate_receipt_record() {
    local record="${1:-}"
    local token="" scope="" port="" protocol="" source="" extra=""
    IFS=$'\t' read -r token scope port protocol source extra <<< "$record"
    [[ -z "$extra" ]] || return 1
    [[ "$token" =~ ^pixeagle-demo-[a-f0-9]{12}-(dashboard|backend|webrtc)$ ]] || return 1
    [[ "$scope" == "broad" || "$scope" == "scoped" ]] || return 1
    pixeagle_ufw_validate_port_spec "$port" "$protocol" || return 1
    if [[ "$scope" == "broad" ]]; then
        [[ "$source" == "-" ]]
    else
        [[ "$source" =~ ^[0-9A-Fa-f:./]+$ && "$source" == */* ]]
    fi
}

pixeagle_ufw_write_receipt() {
    local path="${1:-}"
    shift || true
    [[ -n "$path" && ! -L "$path" ]] || return 1
    [[ ! -e "$path" || -f "$path" ]] || return 1
    [[ "$#" -gt 0 ]] || return 1

    local record
    for record in "$@"; do
        pixeagle_ufw_validate_receipt_record "$record" || return 1
    done

    local temporary
    umask 077
    temporary="$(mktemp "${path}.tmp.XXXXXX")" || return 1
    if ! {
        printf '%s\n' "$PIXEAGLE_UFW_RECEIPT_MAGIC"
        printf '%s\n' "$@"
    } > "$temporary"; then
        rm -f -- "$temporary"
        return 1
    fi
    chmod 0600 "$temporary"
    if [[ -L "$path" || ( -e "$path" && ! -f "$path" ) ]]; then
        rm -f -- "$temporary"
        return 1
    fi
    mv -fT -- "$temporary" "$path"
}

pixeagle_ufw_receipt_records() {
    local path="${1:-}"
    [[ -f "$path" && ! -L "$path" ]] || return 1

    local owner mode
    owner="$(stat -c '%u' "$path" 2>/dev/null)" || return 1
    mode="$(stat -c '%a' "$path" 2>/dev/null)" || return 1
    [[ "$owner" == "$(id -u)" && "$mode" =~ ^[0-7]00$ ]] || return 1

    local magic="" record="" count=0
    IFS= read -r magic < "$path" || return 1
    [[ "$magic" == "$PIXEAGLE_UFW_RECEIPT_MAGIC" ]] || return 1
    while IFS= read -r record || [[ -n "$record" ]]; do
        [[ -n "$record" ]] || return 1
        pixeagle_ufw_validate_receipt_record "$record" || return 1
        printf '%s\n' "$record"
        count=$((count + 1))
    done < <(tail -n +2 -- "$path")
    (( count > 0 ))
}

pixeagle_ufw_rule_base() {
    local record="${1:-}"
    pixeagle_ufw_validate_receipt_record "$record" || return 1
    local token="" scope="" port="" protocol="" source=""
    IFS=$'\t' read -r token scope port protocol source <<< "$record"
    if [[ "$scope" == "broad" ]]; then
        printf 'ufw allow %s/%s\n' "$port" "$protocol"
    else
        printf 'ufw allow from %s to any port %s proto %s\n' \
            "$source" "$port" "$protocol"
    fi
}

pixeagle_ufw_show_has_rule_base() {
    local added_rules="${1:-}"
    local expected="${2:-}"
    local line normalized
    while IFS= read -r line; do
        normalized="${line%% comment *}"
        [[ "$normalized" == "$expected" ]] && return 0
    done <<< "$added_rules"
    return 1
}

pixeagle_ufw_show_has_token() {
    local added_rules="${1:-}"
    local token="${2:-}"
    [[ "$token" =~ ^pixeagle-demo-[a-f0-9]{12}-(dashboard|backend|webrtc)$ ]] || return 1
    grep -Fq " comment '$token'" <<< "$added_rules"
}

pixeagle_ufw_delete_receipt_rules() {
    local path="${1:-}"
    local dry_run="${2:-0}"
    local records
    records="$(pixeagle_ufw_receipt_records "$path")" || {
        echo "ERROR: invalid or unsafe PixEagle UFW receipt: $path" >&2
        return 2
    }

    if [[ "$dry_run" != "1" ]] && ! command -v ufw >/dev/null 2>&1; then
        echo "ERROR: UFW receipt exists but ufw is unavailable; no rule was removed." >&2
        return 2
    fi

    local record token scope port protocol source added_rules
    while IFS= read -r record; do
        IFS=$'\t' read -r token scope port protocol source <<< "$record"
        if [[ "$dry_run" == "1" ]]; then
            echo "Firewall: would remove owned rule $token ($(pixeagle_ufw_rule_base "$record"))"
            continue
        fi

        added_rules="$(LC_ALL=C LANG=C run_privileged ufw show added)" || {
            echo "ERROR: could not inspect UFW rules; owned cleanup stopped." >&2
            return 2
        }
        if ! pixeagle_ufw_show_has_token "$added_rules" "$token"; then
            echo "Firewall: owned rule already absent ($token)"
            continue
        fi

        if [[ "$scope" == "broad" ]]; then
            LC_ALL=C LANG=C run_privileged \
                ufw --force delete allow "$port/$protocol" comment "$token" >/dev/null || {
                echo "ERROR: failed to remove owned UFW rule $token." >&2
                return 2
            }
        else
            LC_ALL=C LANG=C run_privileged \
                ufw --force delete allow from "$source" to any port "$port" \
                proto "$protocol" comment "$token" >/dev/null || {
                echo "ERROR: failed to remove owned UFW rule $token." >&2
                return 2
            }
        fi

        added_rules="$(LC_ALL=C LANG=C run_privileged ufw show added)" || {
            echo "ERROR: could not verify UFW cleanup for $token." >&2
            return 2
        }
        if pixeagle_ufw_show_has_token "$added_rules" "$token"; then
            echo "ERROR: owned UFW rule remains after deletion: $token" >&2
            return 2
        fi
        echo "Firewall: removed owned rule $token"
    done <<< "$records"

    if [[ "$dry_run" != "1" ]]; then
        rm -f -- "$path"
        echo "Firewall receipt: removed $path"
    fi
}

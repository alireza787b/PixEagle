#!/bin/bash
# ============================================================================
# ports.sh - Shared port defaults and resolution helpers for PixEagle scripts
# ============================================================================

# Prevent multiple sourcing.
if [[ -n "${_PIXEAGLE_PORTS_SOURCED:-}" ]]; then
    return 0 2>/dev/null || exit 0
fi
_PIXEAGLE_PORTS_SOURCED=1

# Canonical defaults.
PIXEAGLE_DEFAULT_MAVLINK2REST_PORT=8088
PIXEAGLE_DEFAULT_BACKEND_PORT=5077
PIXEAGLE_DEFAULT_DASHBOARD_PORT=3040
PIXEAGLE_DEFAULT_WEBSOCKET_PORT=5551

is_valid_port() {
    local port="$1"
    [[ "$port" =~ ^[0-9]+$ ]] && (( port >= 1 && port <= 65535 ))
}

get_env_int_value() {
    local file_path="$1"
    local key_name="$2"

    [ -f "$file_path" ] || return 1
    grep -E "^${key_name}=[0-9]+$" "$file_path" 2>/dev/null | head -n 1 | cut -d= -f2
}

get_yaml_int_value() {
    local file_path="$1"
    local key_name="$2"

    [ -f "$file_path" ] || return 1

    awk -F: -v key="$key_name" '
        $1 ~ "^[[:space:]]*" key "[[:space:]]*$" {
            val=$2
            sub(/#.*/, "", val)
            gsub(/[[:space:]]/, "", val)
            if (val ~ /^[0-9]+$/) {
                print val
                exit 0
            }
        }
    ' "$file_path"
}

resolve_dashboard_port() {
    local dashboard_dir="$1"
    local resolved_port="$PIXEAGLE_DEFAULT_DASHBOARD_PORT"
    local candidate=""

    candidate="$(get_yaml_int_value "$dashboard_dir/env_default.yaml" "PORT" 2>/dev/null || true)"
    if is_valid_port "$candidate"; then
        resolved_port="$candidate"
    fi

    candidate="$(get_env_int_value "$dashboard_dir/.env" "PORT" 2>/dev/null || true)"
    if is_valid_port "$candidate"; then
        resolved_port="$candidate"
    fi

    printf '%s\n' "$resolved_port"
}

resolve_backend_port() {
    local config_file="$1"
    local resolved_port="$PIXEAGLE_DEFAULT_BACKEND_PORT"
    local candidate=""

    candidate="$(get_yaml_int_value "$config_file" "HTTP_STREAM_PORT" 2>/dev/null || true)"
    if is_valid_port "$candidate"; then
        resolved_port="$candidate"
    fi

    printf '%s\n' "$resolved_port"
}

# Optional CLI mode for scripts (e.g., Makefile).
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    case "${1:-}" in
        --dashboard-port)
            dashboard_dir="${2:-$(pwd)/dashboard}"
            resolve_dashboard_port "$dashboard_dir"
            ;;
        --backend-port)
            config_file="${2:-$(pwd)/configs/config.yaml}"
            resolve_backend_port "$config_file"
            ;;
        --defaults)
            printf 'DASHBOARD=%s\n' "$PIXEAGLE_DEFAULT_DASHBOARD_PORT"
            printf 'BACKEND=%s\n' "$PIXEAGLE_DEFAULT_BACKEND_PORT"
            printf 'MAVLINK2REST=%s\n' "$PIXEAGLE_DEFAULT_MAVLINK2REST_PORT"
            printf 'WEBSOCKET=%s\n' "$PIXEAGLE_DEFAULT_WEBSOCKET_PORT"
            ;;
        *)
            echo "Usage: $0 [--dashboard-port [dashboard_dir] | --backend-port [config_file] | --defaults]" >&2
            exit 1
            ;;
    esac
fi

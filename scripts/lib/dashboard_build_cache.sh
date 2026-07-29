#!/usr/bin/env bash
# Content-addressed dashboard build-cache helpers.

if [[ -z "${PIXEAGLE_DASHBOARD_CONTRACT_CLI:-}" ]]; then
    PIXEAGLE_DASHBOARD_CONTRACT_CLI="$(
        cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P
    )/dashboard_contract.js"
fi

_pixeagle_dashboard_build_contract() {
    command -v node >/dev/null 2>&1 || return 1
    [[ -f "$PIXEAGLE_DASHBOARD_CONTRACT_CLI" ]] || return 1
    node "$PIXEAGLE_DASHBOARD_CONTRACT_CLI" "$@"
}

pixeagle_dashboard_build_fingerprint() {
    local dashboard_dir="${1:-}"
    local node_version_file="${2:-}"
    [[ -d "$dashboard_dir" && -f "$node_version_file" ]] || return 1

    _pixeagle_dashboard_build_contract \
        build-fingerprint \
        "$dashboard_dir" \
        "$node_version_file"
}

pixeagle_dashboard_build_is_complete() {
    local dashboard_dir="${1:-}"
    local build_dir="$dashboard_dir/build"
    [[ -d "$build_dir" ]] || return 1

    _pixeagle_dashboard_build_contract \
        build-complete \
        "$dashboard_dir" \
        >/dev/null
}

pixeagle_dashboard_build_cache_is_valid() {
    local dashboard_dir="${1:-}"
    local node_version_file="${2:-}"
    local cache_file="${3:-}"
    [[ -f "$cache_file" && ! -L "$cache_file" ]] || return 1
    pixeagle_dashboard_build_is_complete "$dashboard_dir" || return 1

    local cached_fingerprint current_fingerprint
    IFS= read -r cached_fingerprint < "$cache_file" || return 1
    [[ "$cached_fingerprint" =~ ^[a-f0-9]{64}$ ]] || return 1
    current_fingerprint="$(
        pixeagle_dashboard_build_fingerprint "$dashboard_dir" "$node_version_file"
    )" || return 1
    [[ "$cached_fingerprint" == "$current_fingerprint" ]]
}

pixeagle_dashboard_publish_build_fingerprint() {
    local dashboard_dir="${1:-}"
    local node_version_file="${2:-}"
    local cache_file="${3:-}"
    pixeagle_dashboard_build_is_complete "$dashboard_dir" || return 1

    local cache_dir fingerprint temporary
    fingerprint="$(
        pixeagle_dashboard_build_fingerprint "$dashboard_dir" "$node_version_file"
    )" || return 1
    [[ "$fingerprint" =~ ^[a-f0-9]{64}$ ]] || return 1

    cache_dir="$(dirname "$cache_file")"
    [[ ! -L "$cache_dir" && ! -L "$cache_file" ]] || return 1
    mkdir -p -- "$cache_dir" || return 1
    [[ "$(stat -Lc '%u' -- "$cache_dir" 2>/dev/null || true)" == "$(id -u)" ]] \
        || return 1
    temporary="$(mktemp "${cache_file}.tmp.XXXXXX")" || return 1
    if ! printf '%s\n' "$fingerprint" > "$temporary"; then
        rm -f -- "$temporary"
        return 1
    fi
    chmod 0600 "$temporary" || {
        rm -f -- "$temporary"
        return 1
    }
    mv -fT -- "$temporary" "$cache_file"
}

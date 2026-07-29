#!/usr/bin/env bash
# Shared lockfile/cache contract for dashboard dependency reconciliation.
# shellcheck disable=SC2317  # This helper is sourced by setup/runtime scripts.

if [[ -n "${PIXEAGLE_DASHBOARD_DEPENDENCIES_SH_LOADED:-}" ]]; then
    return 0 2>/dev/null || exit 0
fi
PIXEAGLE_DASHBOARD_DEPENDENCIES_SH_LOADED=1

if [[ -z "${PIXEAGLE_DASHBOARD_CONTRACT_CLI:-}" ]]; then
    PIXEAGLE_DASHBOARD_CONTRACT_CLI="$(
        cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P
    )/dashboard_contract.js"
fi

_pixeagle_dashboard_dependency_contract() {
    command -v node >/dev/null 2>&1 || return 1
    [[ -f "$PIXEAGLE_DASHBOARD_CONTRACT_CLI" ]] || return 1
    node "$PIXEAGLE_DASHBOARD_CONTRACT_CLI" "$@"
}

pixeagle_dashboard_dependency_fingerprint() {
    local dashboard_dir="${1:-}"
    local node_version_file="${2:-$dashboard_dir/../.nvmrc}"

    [[ -d "$dashboard_dir" && ! -L "$dashboard_dir" \
        && -f "$node_version_file" ]] || return 1
    _pixeagle_dashboard_dependency_contract \
        dependency-fingerprint \
        "$dashboard_dir" \
        "$node_version_file"
}

pixeagle_dashboard_dependencies_ready() {
    local dashboard_dir="${1:-}"
    local node_version_file="${2:-$dashboard_dir/../.nvmrc}"

    _pixeagle_dashboard_dependency_contract \
        dependencies-ready \
        "$dashboard_dir" \
        "$node_version_file" \
        >/dev/null
}

pixeagle_record_dashboard_dependency_fingerprint() {
    local dashboard_dir="${1:-}"
    local node_version_file="${2:-$dashboard_dir/../.nvmrc}"
    local cache_dir cache_file fingerprint temporary

    fingerprint="$(
        pixeagle_dashboard_dependency_fingerprint \
            "$dashboard_dir" "$node_version_file"
    )" || return 1
    cache_dir="$dashboard_dir/.pixeagle_cache"
    cache_file="$cache_dir/deps_hash"
    [[ ! -L "$cache_dir" && ! -L "$cache_file" ]] || return 1
    mkdir -p -- "$cache_dir" || return 1
    [[ "$(stat -Lc '%u' -- "$cache_dir" 2>/dev/null || true)" == "$(id -u)" ]] \
        || return 1
    temporary="$(mktemp "$cache_dir/.deps_hash.XXXXXX")" || return 1
    chmod 0600 -- "$temporary" || {
        rm -f -- "$temporary"
        return 1
    }
    if ! printf '%s\n' "$fingerprint" > "$temporary"; then
        rm -f -- "$temporary"
        return 1
    fi
    mv -- "$temporary" "$cache_file"
}

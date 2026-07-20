#!/usr/bin/env bash
# Shared lockfile/cache contract for dashboard dependency reconciliation.
# shellcheck disable=SC2317  # This helper is sourced by setup/runtime scripts.

if [[ -n "${PIXEAGLE_DASHBOARD_DEPENDENCIES_SH_LOADED:-}" ]]; then
    return 0 2>/dev/null || exit 0
fi
PIXEAGLE_DASHBOARD_DEPENDENCIES_SH_LOADED=1

pixeagle_dashboard_file_hash() {
    local path="${1:-}"

    [[ -f "$path" && ! -L "$path" ]] || return 1
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum -- "$path" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 -- "$path" | awk '{print $1}'
    else
        return 1
    fi
}

pixeagle_dashboard_dependency_fingerprint() {
    local dashboard_dir="${1:-}"
    local package_hash lock_hash

    [[ -d "$dashboard_dir" && ! -L "$dashboard_dir" ]] || return 1
    package_hash="$(
        pixeagle_dashboard_file_hash "$dashboard_dir/package.json"
    )" || return 1
    lock_hash="$(
        pixeagle_dashboard_file_hash "$dashboard_dir/package-lock.json"
    )" || return 1
    printf '%s_%s\n' "$package_hash" "$lock_hash"
}

pixeagle_dashboard_dependencies_ready() {
    local dashboard_dir="${1:-}"
    local cache_file fingerprint cached=""

    command -v npm >/dev/null 2>&1 || return 1
    [[ -d "$dashboard_dir/node_modules" \
        && ! -L "$dashboard_dir/node_modules" ]] || return 1
    cache_file="$dashboard_dir/.pixeagle_cache/deps_hash"
    [[ -f "$cache_file" && ! -L "$cache_file" ]] || return 1
    fingerprint="$(
        pixeagle_dashboard_dependency_fingerprint "$dashboard_dir"
    )" || return 1
    IFS= read -r cached < "$cache_file" || return 1
    [[ "$cached" == "$fingerprint" ]] || return 1

    # A matching cache is only a hint. Validate the complete installed tree
    # offline before skipping the lockfile-enforced clean install.
    (cd "$dashboard_dir" && npm ls --all --silent >/dev/null 2>&1)
}

pixeagle_record_dashboard_dependency_fingerprint() {
    local dashboard_dir="${1:-}"
    local cache_dir cache_file fingerprint temporary

    fingerprint="$(
        pixeagle_dashboard_dependency_fingerprint "$dashboard_dir"
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

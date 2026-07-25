#!/usr/bin/env bash
# Shared policy for explicit component rebuild requests.
# shellcheck disable=SC2317  # The helper is sourced by setup scripts and tests.

if [[ -n "${PIXEAGLE_COMPONENT_REUSE_SH_LOADED:-}" ]]; then
    return 0 2>/dev/null || exit 0
fi
PIXEAGLE_COMPONENT_REUSE_SH_LOADED=1

pixeagle_normalized_rebuild_components() {
    local raw="${PIXEAGLE_REBUILD_COMPONENTS:-}"
    raw="${raw,,}"
    raw="${raw//[[:space:]]/}"
    printf '%s\n' "$raw"
}

pixeagle_validate_rebuild_components() {
    local raw token
    local -a tokens=()
    raw="$(pixeagle_normalized_rebuild_components)"
    [[ -n "$raw" ]] || return 0

    IFS=',' read -r -a tokens <<< "$raw"
    for token in "${tokens[@]}"; do
        case "$token" in
            all|python|ai|dlib|opencv|dashboard) ;;
            "")
                printf 'PIXEAGLE_REBUILD_COMPONENTS contains an empty item\n' >&2
                return 1
                ;;
            *)
                printf 'Unknown PIXEAGLE_REBUILD_COMPONENTS item: %s\n' "$token" >&2
                printf 'Allowed: all,python,ai,dlib,opencv,dashboard\n' >&2
                return 1
                ;;
        esac
    done
}

pixeagle_component_rebuild_requested() {
    local component="${1:-}"
    local raw
    case "$component" in
        python|ai|dlib|opencv|dashboard) ;;
        *) return 2 ;;
    esac
    pixeagle_validate_rebuild_components || return 2
    raw="$(pixeagle_normalized_rebuild_components)"
    [[ ",$raw," == *,all,* || ",$raw," == *",$component,"* ]]
}

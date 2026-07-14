#!/bin/bash
# ============================================================================
# scripts/lib/sync.sh - PixEagle Upstream Sync
# ============================================================================
# Fetches latest changes from the selected remote and fast-forwards only when
# the worktree is clean. It never stashes, hard-resets, or performs a merge
# commit for the operator.
#
# Usage (standalone):
#   bash scripts/lib/sync.sh
#   SYNC_REMOTE=upstream SYNC_BRANCH=develop bash scripts/lib/sync.sh
#
# Usage (sourced):
#   source scripts/lib/sync.sh
#   do_sync            # uses SYNC_REMOTE / SYNC_BRANCH env vars
# ============================================================================

_SYNC_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_CONFIG_PREUPDATE_RELATIVE="configs/.config_default_preupdate.yaml"

# Source common.sh for colored logging
if [[ -f "$_SYNC_SCRIPT_DIR/common.sh" ]]; then
    # shellcheck source=/dev/null
    source "$_SYNC_SCRIPT_DIR/common.sh"
else
    # Minimal fallback if common.sh is missing
    log_info()    { echo "  [INFO] $1"; }
    log_success() { echo "  [OK]   $1"; }
    log_error()   { echo "  [ERR]  $1" >&2; }
    log_warn()    { echo "  [WARN] $1"; }
    log_detail()  { echo "         $1"; }
fi

_validate_staged_defaults_yaml() {
    local project_root="$1"
    local staged_path="$2"
    local status_script="$project_root/scripts/setup/config-sync-status.py"
    local candidate
    local validation_python=""

    if [[ ! -f "$status_script" ]]; then
        log_error "Cannot validate pre-update defaults: config-sync-status.py is missing"
        return 1
    fi
    if declare -F resolve_pixeagle_venv_python >/dev/null 2>&1; then
        candidate="$(resolve_pixeagle_venv_python "$project_root")"
        if [[ -x "$candidate" ]]; then
            validation_python="$candidate"
        fi
    fi
    if [[ -z "$validation_python" ]]; then
        for candidate in python3 python; do
            if command -v "$candidate" >/dev/null 2>&1 &&
               "$candidate" -c "import yaml" >/dev/null 2>&1; then
                validation_python="$(command -v "$candidate")"
                break
            fi
        done
    fi
    if [[ -z "$validation_python" ]]; then
        log_error "Cannot validate pre-update defaults: Python with PyYAML is unavailable"
        log_detail "Run make init before attempting a source update."
        return 1
    fi
    if ! "$validation_python" "$status_script" \
        --project-root "$project_root" \
        --validate-staged-baseline "$staged_path" >/dev/null; then
        log_error "Pending pre-update defaults failed integrity validation"
        return 1
    fi
    return 0
}

_stage_preupdate_defaults() {
    local project_root="$1"
    local source_path="$project_root/configs/config_default.yaml"
    local staged_path="$project_root/$_CONFIG_PREUPDATE_RELATIVE"

    if [[ ! -e "$source_path" && ! -L "$source_path" ]]; then
        log_error "Cannot preserve pre-update defaults: configs/config_default.yaml is missing"
        return 1
    fi
    if [[ ! -f "$source_path" || -L "$source_path" || ! -s "$source_path" ]]; then
        log_error "Cannot preserve pre-update defaults: tracked defaults must be a non-empty regular file"
        return 1
    fi

    # A prior failed update may have left the earliest baseline pending. Never
    # replace it with defaults from a newer checkout.
    if [[ -e "$staged_path" || -L "$staged_path" ]]; then
        if [[ ! -f "$staged_path" || -L "$staged_path" || ! -O "$staged_path" ]]; then
            log_error "Pending pre-update defaults are not an owner-controlled regular file"
            return 1
        fi
        if ! chmod 600 "$staged_path"; then
            log_error "Could not restrict pending pre-update defaults to the current user"
            return 1
        fi
        if ! _validate_staged_defaults_yaml "$project_root" "$staged_path"; then
            return 1
        fi
        log_info "Keeping the pending pre-update defaults baseline"
        return 0
    fi

    local previous_umask
    local temp_path
    previous_umask="$(umask)"
    umask 077
    if ! temp_path="$(mktemp "${staged_path}.tmp.XXXXXX")"; then
        umask "$previous_umask"
        log_error "Could not create the private pre-update defaults staging file"
        return 1
    fi
    umask "$previous_umask"

    if ! cp -- "$source_path" "$temp_path" ||
       ! chmod 600 "$temp_path" ||
       ! cmp -s -- "$source_path" "$temp_path"; then
        rm -f -- "$temp_path"
        log_error "Could not copy and verify the pre-update defaults baseline"
        return 1
    fi
    if ! _validate_staged_defaults_yaml "$project_root" "$temp_path"; then
        rm -f -- "$temp_path"
        return 1
    fi

    # Publishing a hard link in the same directory is atomic and refuses to
    # overwrite a baseline created concurrently.
    if ! ln -- "$temp_path" "$staged_path"; then
        rm -f -- "$temp_path"
        log_error "Could not atomically publish the pre-update defaults baseline"
        return 1
    fi
    rm -f -- "$temp_path"
    log_success "Pre-update config defaults preserved"
    return 0
}

_consume_preupdate_defaults() {
    local project_root="$1"
    local staged_path="$project_root/$_CONFIG_PREUPDATE_RELATIVE"
    local status_script="$project_root/scripts/setup/config-sync-status.py"
    local config_sync_python

    if ! declare -F resolve_pixeagle_venv_python >/dev/null 2>&1; then
        log_error "Config lifecycle helper is unavailable after source update"
        return 1
    fi
    config_sync_python="$(resolve_pixeagle_venv_python "$project_root")"
    if [[ ! -x "$config_sync_python" ]]; then
        log_error "Config lifecycle is pending: PixEagle virtual-environment Python is unavailable"
        log_detail "Run make init; the preserved baseline will remain in place."
        return 1
    fi
    if [[ ! -f "$status_script" ]]; then
        log_error "Config lifecycle is pending: config-sync-status.py is unavailable"
        return 1
    fi
    if [[ ! -f "$staged_path" || -L "$staged_path" ]]; then
        log_error "Config lifecycle is pending: the preserved pre-update baseline is unavailable"
        return 1
    fi

    log_info "Checking config defaults and retirements..."
    if ! "$config_sync_python" "$status_script" \
        --initialize-baseline-from "$staged_path"; then
        log_error "Config lifecycle check failed; the preserved baseline was retained"
        return 1
    fi
    if ! rm -f -- "$staged_path" || [[ -e "$staged_path" || -L "$staged_path" ]]; then
        log_error "Config lifecycle completed, but the consumed staging file could not be removed"
        return 1
    fi
    log_success "Config update baseline and retirement status checked"
    return 0
}

do_sync() {
    local remote="${SYNC_REMOTE:-}"
    local branch="${SYNC_BRANCH:-}"

    echo ""
    echo -e "  ${BOLD:-}PixEagle Sync${NC:-}"
    echo "  ───────────────────────────────────────────"

    # Verify git repo
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        log_error "Not a git repository"
        return 1
    fi

    # Resolve remote and branch
    local cur_branch
    cur_branch="$(git symbolic-ref --short HEAD 2>/dev/null || true)"
    if [[ -z "$remote" ]]; then
        remote="$(git config "branch.${cur_branch}.remote" 2>/dev/null || echo "origin")"
    fi
    if [[ -z "$branch" ]]; then
        branch="$cur_branch"
    fi
    if [[ -z "$branch" ]]; then
        log_error "Detached HEAD detected and SYNC_BRANCH was not provided"
        log_detail "Run with SYNC_BRANCH=<branch> or check out a branch first."
        return 2
    fi

    local remote_url
    remote_url="$(git remote get-url "$remote" 2>/dev/null || echo "unknown")"

    echo -e "  Remote:  ${BOLD:-}${remote}${NC:-} (${remote_url})"
    echo -e "  Branch:  ${BOLD:-}${branch}${NC:-}"
    echo ""

    # Refuse hidden state changes. Operators can commit or stash manually first.
    local untracked
    untracked="$(
        git ls-files --others --exclude-standard 2>/dev/null |
            awk -v staged="$_CONFIG_PREUPDATE_RELATIVE" '$0 != staged { print; exit }'
    )"
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null || [[ -n "$untracked" ]]; then
        log_error "Worktree has local changes; sync requires a clean worktree"
        git status --short
        log_detail "Commit, stash manually, or copy your changes, then rerun sync."
        log_detail "No automatic stash, merge commit, or hard reset was attempted."
        return 2
    fi

    local project_root
    local config_lifecycle_required=false
    project_root="$(git rev-parse --show-toplevel)"
    log_info "Preserving the current config defaults before update..."
    if ! _stage_preupdate_defaults "$project_root"; then
        log_detail "No source update was attempted."
        return 1
    fi
    config_lifecycle_required=true

    # Fetch
    log_info "Fetching updates..."
    local fetch_err
    local remote_ref="${remote}/${branch}"
    local fetch_refspec="+refs/heads/${branch}:refs/remotes/${remote}/${branch}"
    if ! fetch_err="$(git fetch --prune "$remote" "$fetch_refspec" 2>&1)"; then
        log_error "Fetch failed from ${remote}"
        # Detect common clock-related SSL failures (embedded boards without RTC)
        if echo "$fetch_err" | grep -qi "ssl\|certificate\|not yet valid\|expired"; then
            log_warn "This may be a system clock issue (common on Jetson/Pi without RTC)"
            log_detail "Current system time: $(date)"
            log_detail "Fix: sudo date -s \"$(date -u +'%Y-%m-%d %H:%M:%S' 2>/dev/null || echo '2026-01-01 00:00:00')\" or sudo timedatectl set-ntp true"
        fi
        return 1
    fi

    if ! git rev-parse --verify "${remote_ref}^{commit}" >/dev/null 2>&1; then
        log_error "Remote branch not found after fetch: ${remote_ref}"
        return 1
    fi

    local old_head
    old_head="$(git rev-parse HEAD)"
    local remote_head
    remote_head="$(git rev-parse "${remote_ref}^{commit}")"

    if [[ "$old_head" == "$remote_head" ]]; then
        log_success "Already up to date"
    elif git merge --ff-only --quiet "$remote_ref"; then
        local diffstat
        diffstat="$(git diff --stat "$old_head"..HEAD 2>/dev/null | tail -1)"
        if [[ -n "$diffstat" && "$diffstat" != *"0 files"* ]]; then
            log_success "Applied fast-forward updates (${diffstat})"
        else
            log_success "Applied fast-forward updates"
        fi
    else
        log_error "Fast-forward update was not possible; no merge was attempted"
        log_detail "Inspect divergence with: git log --oneline --graph --decorate HEAD ${remote_ref}"
        log_detail "Resolve manually, then rerun sync from a clean worktree."
        return 1
    fi

    if [[ "$config_lifecycle_required" == true ]] &&
       ! _consume_preupdate_defaults "$project_root"; then
        log_error "Source sync finished, but configuration readiness is degraded"
        return 1
    fi

    echo ""
    log_success "Sync complete"
    log_info "Recommended post-update validation before handoff:"
    log_detail "bash scripts/check_schema.sh"
    log_detail "PYTHONPATH=src python -m pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -q"
    log_detail "cd dashboard && npm test -- --runInBand --watchAll=false && CI=true npm run build"
    echo "  ───────────────────────────────────────────"
    echo ""
    return 0
}

# Standalone guard: run do_sync() when executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    do_sync
fi

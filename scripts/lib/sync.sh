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

# Source common.sh for colored logging
if [[ -f "$_SYNC_SCRIPT_DIR/common.sh" ]]; then
    source "$_SYNC_SCRIPT_DIR/common.sh"
else
    # Minimal fallback if common.sh is missing
    log_info()    { echo "  [INFO] $1"; }
    log_success() { echo "  [OK]   $1"; }
    log_error()   { echo "  [ERR]  $1" >&2; }
    log_warn()    { echo "  [WARN] $1"; }
    log_detail()  { echo "         $1"; }
fi

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
    untracked="$(git ls-files --others --exclude-standard 2>/dev/null | head -n 1 || true)"
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null || [[ -n "$untracked" ]]; then
        log_error "Worktree has local changes; sync requires a clean worktree"
        git status --short
        log_detail "Commit, stash manually, or copy your changes, then rerun sync."
        log_detail "No automatic stash, merge commit, or hard reset was attempted."
        return 2
    fi

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

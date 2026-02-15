#!/bin/bash
# ============================================================================
# scripts/lib/sync.sh - PixEagle Upstream Sync
# ============================================================================
# Pulls latest changes from the upstream remote with clean, concise output.
# Auto-stashes local changes, uses --quiet on all git commands.
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
    local stashed=0

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
    cur_branch="$(git symbolic-ref --short HEAD 2>/dev/null)"
    if [[ -z "$remote" ]]; then
        remote="$(git config "branch.${cur_branch}.remote" 2>/dev/null || echo "origin")"
    fi
    if [[ -z "$branch" ]]; then
        branch="$cur_branch"
    fi

    local remote_url
    remote_url="$(git remote get-url "$remote" 2>/dev/null || echo "unknown")"

    echo -e "  Remote:  ${BOLD:-}${remote}${NC:-} (${remote_url})"
    echo -e "  Branch:  ${BOLD:-}${branch}${NC:-}"
    echo ""

    # Auto-stash local changes
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
        log_warn "Local changes detected — auto-stashing..."
        if ! git stash push --quiet -m "pixeagle-sync-$(date +%Y%m%d-%H%M%S)" 2>/dev/null; then
            log_error "Failed to stash local changes"
            return 1
        fi
        stashed=1
    fi

    # Fetch
    log_info "Fetching updates..."
    local fetch_err
    if ! fetch_err="$(git fetch "$remote" 2>&1)"; then
        log_error "Fetch failed from ${remote}"
        # Detect common clock-related SSL failures (embedded boards without RTC)
        if echo "$fetch_err" | grep -qi "ssl\|certificate\|not yet valid\|expired"; then
            log_warn "This may be a system clock issue (common on Jetson/Pi without RTC)"
            log_detail "Current system time: $(date)"
            log_detail "Fix: sudo date -s \"$(date -u +'%Y-%m-%d %H:%M:%S' 2>/dev/null || echo '2026-01-01 00:00:00')\" or sudo timedatectl set-ntp true"
        fi
        if [[ "$stashed" -eq 1 ]]; then
            git stash pop --quiet 2>/dev/null || true
            log_warn "Restored stashed changes"
        fi
        return 1
    fi

    # Merge (prefer fast-forward)
    local merge_method=""
    local merge_output
    if merge_output="$(git merge --ff-only --quiet "$remote/$branch" 2>&1)"; then
        merge_method="fast-forward"
    else
        log_info "Fast-forward not possible, attempting merge..."
        if merge_output="$(git merge --quiet --no-edit "$remote/$branch" 2>&1)"; then
            merge_method="merge"
        else
            log_error "Merge conflict detected — aborting merge"
            git merge --abort 2>/dev/null || true
            log_detail "Resolve manually: git pull ${remote} ${branch}"
            if [[ "$stashed" -eq 1 ]]; then
                log_warn "Your stashed changes are preserved. Run: git stash pop"
            fi
            return 1
        fi
    fi

    # Show diffstat one-liner
    local diffstat
    diffstat="$(git diff --stat HEAD@{1}..HEAD 2>/dev/null | tail -1)"
    if [[ -n "$diffstat" && "$diffstat" != *"0 files"* ]]; then
        log_success "Applied updates: ${merge_method} (${diffstat})"
    else
        log_success "Already up to date"
    fi

    # Restore stash
    if [[ "$stashed" -eq 1 ]]; then
        if git stash pop --quiet 2>/dev/null; then
            log_success "Local changes restored"
        else
            log_warn "Stash pop had conflicts. Run: git stash show -p | git apply"
        fi
    fi

    echo ""
    log_success "Sync complete"
    echo "  ───────────────────────────────────────────"
    echo ""
    return 0
}

# Standalone guard: run do_sync() when executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    do_sync
fi

#!/bin/bash
# ============================================================================
# scripts/lib/sync.sh - PixEagle Upstream Sync
# ============================================================================
# Fetches latest changes from the selected remote and fast-forwards only when
# the worktree is clean. It never stashes, hard-resets, or performs a merge
# commit for the operator.
#
# Internal usage (sourced by scripts/update.sh):
#   source scripts/lib/sync.sh
#   do_sync            # uses SYNC_REMOTE / SYNC_BRANCH env vars
# ============================================================================

_SYNC_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_CONFIG_PREUPDATE_RELATIVE="configs/.config_default_preupdate.yaml"
_SETUP_LOCK_HELPER="$_SYNC_SCRIPT_DIR/setup_lock.sh"

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

# shellcheck source=scripts/lib/setup_lock.sh
if ! source "$_SETUP_LOCK_HELPER" 2>/dev/null; then
    log_error "Secure source-update lock helper is unavailable"
    if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
        return 1
    fi
    exit 1
fi

PIXEAGLE_SYNC_OLD_HEAD=""
PIXEAGLE_SYNC_NEW_HEAD=""
PIXEAGLE_SYNC_CHANGED=false
PIXEAGLE_SYNC_REMOTE=""
PIXEAGLE_SYNC_BRANCH=""
PIXEAGLE_SYNC_REMOTE_URL=""

_validate_update_remote_url() {
    local value="$1"
    [[ -n "$value" && "$value" != -* && "$value" != *$'\n'* \
        && "$value" != *$'\r'* ]] || return 1
    case "$value" in
        https://*|ssh://*|git@*:*|file://*|/*|./*|../*) return 0 ;;
        *) return 1 ;;
    esac
}

_candidate_has_required_contract() {
    local candidate="$1"
    local path entry mode type
    local -a required_paths=(
        Makefile
        install.sh
        configs/config_default.yaml
        configs/config_schema.yaml
        configs/config_retirements.yaml
        scripts/init.sh
        scripts/run.sh
        scripts/stop.sh
        scripts/update.sh
        scripts/lib/common.sh
        scripts/lib/ports.sh
        scripts/lib/runtime_ownership.sh
        scripts/lib/setup_lock.sh
        scripts/lib/setup_lock_supervisor.py
        scripts/lib/sync.sh
        scripts/lib/venv_transaction.sh
        scripts/service/cli.sh
        scripts/service/install.sh
        scripts/service/run.sh
        scripts/service/utils.sh
        scripts/setup/config-sync-status.py
    )
    for path in "${required_paths[@]}"; do
        entry="$(git ls-tree "$candidate" -- "$path")" || return 1
        read -r mode type _object <<< "${entry%%$'\t'*}"
        if [[ "$type" != "blob" || ( "$mode" != "100644" && "$mode" != "100755" ) ]]; then
            log_error "Update candidate has an unsafe or missing required path: $path"
            return 1
        fi
    done
}

_target_tree_preserves_untracked_paths() {
    local from_commit="$1"
    local target_commit="$2"
    local project_root inventory_file previous_umask relative parent full_path
    local display_path=""
    local result=0

    project_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
        log_error "Cannot inspect untracked-path collisions outside a Git checkout"
        return 1
    }
    previous_umask="$(umask)"
    umask 077
    inventory_file="$(mktemp "${TMPDIR:-/tmp}/pixeagle-update-paths.XXXXXX")" || {
        umask "$previous_umask"
        log_error "Cannot create the private update-path inventory"
        return 1
    }
    umask "$previous_umask"

    if ! git diff --no-renames --name-only -z --diff-filter=A \
        "$from_commit" "$target_commit" > "$inventory_file"; then
        log_error "Cannot compare source trees for untracked-path collisions"
        rm -f -- "$inventory_file"
        return 1
    fi

    while IFS= read -r -d '' relative; do
        case "$relative" in
            ""|.|..|/*|../*|*/../*|*/..)
                printf -v display_path '%q' "$relative"
                log_error "Update candidate contains an unsafe path: $display_path"
                result=1
                break
                ;;
        esac

        parent="$relative"
        while [[ "$parent" == */* ]]; do
            parent="${parent%/*}"
            full_path="$project_root/$parent"
            if [[ -L "$full_path" || ( -e "$full_path" && ! -d "$full_path" ) ]]; then
                if ! git ls-files --error-unmatch -- "$parent" >/dev/null 2>&1; then
                    printf -v display_path '%q' "$parent"
                    log_error "Source update would traverse an untracked or ignored path: $display_path"
                    result=1
                    break 2
                fi
            fi
        done

        full_path="$project_root/$relative"
        if [[ -e "$full_path" || -L "$full_path" ]]; then
            printf -v display_path '%q' "$relative"
            log_error "Source update would overwrite untracked or ignored operator data: $display_path"
            result=1
            break
        fi
    done < "$inventory_file"

    rm -f -- "$inventory_file"
    return "$result"
}

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
    local source_uid source_mode source_links
    local staged_uid staged_mode staged_links

    if [[ ! -e "$source_path" && ! -L "$source_path" ]]; then
        log_error "Cannot preserve pre-update defaults: configs/config_default.yaml is missing"
        return 1
    fi
    if [[ ! -f "$source_path" || -L "$source_path" || ! -s "$source_path" ]]; then
        log_error "Cannot preserve pre-update defaults: tracked defaults must be a non-empty regular file"
        return 1
    fi
    IFS=: read -r source_uid source_mode source_links < <(
        stat -c '%u:%a:%h' -- "$source_path" 2>/dev/null || true
    )
    if [[ "$source_uid" != "$(id -u)" || ! "$source_mode" =~ ^[0-7]{3,4}$ \
        || "$source_links" != 1 ]]; then
        log_error "Cannot preserve pre-update defaults: tracked defaults ownership or link identity is unsafe"
        return 1
    fi

    # A prior failed update may have left the earliest baseline pending. Never
    # replace it with defaults from a newer checkout.
    if [[ -e "$staged_path" || -L "$staged_path" ]]; then
        if [[ ! -f "$staged_path" || -L "$staged_path" || ! -O "$staged_path" ]]; then
            log_error "Pending pre-update defaults are not an owner-controlled regular file"
            return 1
        fi
        IFS=: read -r staged_uid staged_mode staged_links < <(
            stat -c '%u:%a:%h' -- "$staged_path" 2>/dev/null || true
        )
        if [[ "$staged_uid" != "$(id -u)" || "$staged_mode" != 600 \
            || "$staged_links" != 1 ]]; then
            log_error "Pending pre-update defaults must already be an owner-only single-link file"
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

do_sync() {
    local remote="${SYNC_REMOTE:-}"
    local branch="${SYNC_BRANCH:-}"
    local project_root venv_dir candidate_ref candidate_token
    local old_head candidate_head remote_url fetch_err diffstat

    echo ""
    echo -e "  ${BOLD:-}PixEagle Sync${NC:-}"
    echo "  ───────────────────────────────────────────"

    # Verify git repo
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        log_error "Not a git repository"
        return 1
    fi

    # Resolve and validate the configured source authority.
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
    if [[ ! "$remote" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$ ]] \
        || [[ "$remote" == *..* ]]; then
        log_error "Configured update remote name is unsafe: $remote"
        return 2
    fi
    if ! git check-ref-format --branch "$branch" >/dev/null 2>&1; then
        log_error "Configured update branch is invalid: $branch"
        return 2
    fi

    remote_url="$(git remote get-url "$remote" 2>/dev/null)" || {
        log_error "Configured update remote does not exist: $remote"
        return 2
    }
    if ! _validate_update_remote_url "$remote_url"; then
        log_error "Refusing unsupported update remote transport: $remote_url"
        log_detail "Use HTTPS, SSH, or an explicit local/file remote; Git remote helpers are refused."
        return 2
    fi

    echo -e "  Remote:  ${BOLD:-}${remote}${NC:-} (${remote_url})"
    echo -e "  Branch:  ${BOLD:-}${branch}${NC:-}"
    echo ""

    # Refuse hidden state changes. Operators can commit or stash manually first.
    local untracked
    if ! untracked="$(
        git ls-files --others --exclude-standard 2>/dev/null |
            awk -v staged="$_CONFIG_PREUPDATE_RELATIVE" '$0 != staged { print; exit }'
    )"; then
        log_error "Cannot inspect untracked files; refusing source update"
        return 2
    fi
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null || [[ -n "$untracked" ]]; then
        log_error "Worktree has local changes; update requires a clean worktree"
        git status --short
        log_detail "Commit, stash manually, or copy your changes, then rerun make update."
        log_detail "No automatic stash, merge commit, or hard reset was attempted."
        return 2
    fi

    project_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
        log_error "Cannot resolve the Git checkout root"
        return 1
    }
    venv_dir="$(resolve_pixeagle_venv_dir "$project_root")" || return 1
    if ! pixeagle_validate_resource_lock_context \
        exclusive "$project_root" "$venv_dir"; then
        log_error "Source publication is outside the supervised source/venv update transaction"
        return 1
    fi
    old_head="$(git rev-parse --verify 'HEAD^{commit}')" || {
        log_error "Current checkout HEAD is not a commit"
        return 1
    }
    candidate_token="$(tr -d '-' < /proc/sys/kernel/random/uuid 2>/dev/null || true)"
    [[ "$candidate_token" =~ ^[0-9A-Fa-f]{32}$ ]] || {
        log_error "A collision-resistant update candidate identity is unavailable"
        return 1
    }
    candidate_ref="refs/pixeagle/update-candidates/$candidate_token"

    log_info "Fetching the exact candidate branch without tags or submodules..."
    if ! fetch_err="$(git \
        -c protocol.allow=never \
        -c protocol.https.allow=always \
        -c protocol.ssh.allow=always \
        -c protocol.file.allow=always \
        -c protocol.ext.allow=never \
        fetch --no-tags --no-recurse-submodules --force "$remote" \
        "refs/heads/${branch}:${candidate_ref}" 2>&1)"; then
        git update-ref -d "$candidate_ref" >/dev/null 2>&1 || true
        log_error "Fetch failed from ${remote}"
        # Detect common clock-related SSL failures (embedded boards without RTC)
        if echo "$fetch_err" | grep -qi "ssl\|certificate\|not yet valid\|expired"; then
            log_warn "This may be a system clock issue (common on Jetson/Pi without RTC)"
            log_detail "Current system time: $(date)"
            log_detail "Fix: sudo date -s \"$(date -u +'%Y-%m-%d %H:%M:%S' 2>/dev/null || echo '2026-01-01 00:00:00')\" or sudo timedatectl set-ntp true"
        fi
        return 1
    fi

    candidate_head="$(git rev-parse --verify "${candidate_ref}^{commit}")" || {
        git update-ref -d "$candidate_ref" >/dev/null 2>&1 || true
        log_error "Fetched candidate is not a commit"
        return 1
    }
    if ! git merge-base --is-ancestor "$old_head" "$candidate_head"; then
        git update-ref -d "$candidate_ref" >/dev/null 2>&1 || true
        log_error "Update candidate is not a fast-forward descendant of the current HEAD"
        return 1
    fi
    if ! _candidate_has_required_contract "$candidate_head"; then
        git update-ref -d "$candidate_ref" >/dev/null 2>&1 || true
        return 1
    fi
    if ! _target_tree_preserves_untracked_paths "$old_head" "$candidate_head"; then
        git update-ref -d "$candidate_ref" >/dev/null 2>&1 || true
        log_detail "Move or remove the colliding operator path explicitly, then rerun the update."
        return 1
    fi
    if [[ "${PIXEAGLE_UPDATE_REQUIRE_SIGNED_COMMIT:-0}" == "1" ]] \
        && ! git verify-commit "$candidate_head" >/dev/null 2>&1; then
        git update-ref -d "$candidate_ref" >/dev/null 2>&1 || true
        log_error "Update candidate did not pass the required Git signature verification"
        return 1
    fi

    if [[ "$old_head" != "$candidate_head" ]]; then
        log_info "Preserving the current config defaults before update..."
        if ! _stage_preupdate_defaults "$project_root"; then
            git update-ref -d "$candidate_ref" >/dev/null 2>&1 || true
            log_detail "No source update was attempted."
            return 1
        fi
    fi

    if [[ "$old_head" == "$candidate_head" ]]; then
        log_success "Already up to date"
        PIXEAGLE_SYNC_CHANGED=false
    elif git merge --ff-only --quiet "$candidate_ref"; then
        diffstat="$(git diff --stat "$old_head"..HEAD 2>/dev/null | tail -1)"
        if [[ -n "$diffstat" && "$diffstat" != *"0 files"* ]]; then
            log_success "Applied fast-forward updates (${diffstat})"
        else
            log_success "Applied fast-forward updates"
        fi
        PIXEAGLE_SYNC_CHANGED=true
    else
        local merge_failure_head
        merge_failure_head="$(git rev-parse --verify 'HEAD^{commit}' 2>/dev/null || true)"
        if [[ "$merge_failure_head" == "$candidate_head" ]]; then
            PIXEAGLE_SYNC_OLD_HEAD="$old_head"
            PIXEAGLE_SYNC_NEW_HEAD="$candidate_head"
            PIXEAGLE_SYNC_CHANGED=true
            PIXEAGLE_SYNC_REMOTE="$remote"
            PIXEAGLE_SYNC_BRANCH="$branch"
            PIXEAGLE_SYNC_REMOTE_URL="$remote_url"
            export PIXEAGLE_SYNC_OLD_HEAD PIXEAGLE_SYNC_NEW_HEAD PIXEAGLE_SYNC_CHANGED
            export PIXEAGLE_SYNC_REMOTE PIXEAGLE_SYNC_BRANCH PIXEAGLE_SYNC_REMOTE_URL
            log_error "Fast-forward reported failure after publishing the candidate"
        elif [[ "$merge_failure_head" != "$old_head" ]] \
            || ! git diff --quiet --ignore-submodules -- \
            || ! git diff --cached --quiet --ignore-submodules --; then
            PIXEAGLE_SYNC_OLD_HEAD="$old_head"
            PIXEAGLE_SYNC_NEW_HEAD="$candidate_head"
            PIXEAGLE_SYNC_CHANGED=true
            PIXEAGLE_SYNC_REMOTE="$remote"
            PIXEAGLE_SYNC_BRANCH="$branch"
            PIXEAGLE_SYNC_REMOTE_URL="$remote_url"
            export PIXEAGLE_SYNC_OLD_HEAD PIXEAGLE_SYNC_NEW_HEAD PIXEAGLE_SYNC_CHANGED
            export PIXEAGLE_SYNC_REMOTE PIXEAGLE_SYNC_BRANCH PIXEAGLE_SYNC_REMOTE_URL
            log_error "Fast-forward failure left checkout state requiring manual inspection"
        else
            log_error "Fast-forward update was not possible; no merge was attempted"
        fi
        git update-ref -d "$candidate_ref" >/dev/null 2>&1 || true
        log_detail "Inspect divergence with: git log --oneline --graph --decorate HEAD $candidate_head"
        log_detail "Resolve manually, then rerun make update from a clean worktree."
        return 1
    fi

    PIXEAGLE_SYNC_OLD_HEAD="$old_head"
    PIXEAGLE_SYNC_NEW_HEAD="$candidate_head"
    PIXEAGLE_SYNC_REMOTE="$remote"
    PIXEAGLE_SYNC_BRANCH="$branch"
    PIXEAGLE_SYNC_REMOTE_URL="$remote_url"
    export PIXEAGLE_SYNC_OLD_HEAD PIXEAGLE_SYNC_NEW_HEAD PIXEAGLE_SYNC_CHANGED
    export PIXEAGLE_SYNC_REMOTE PIXEAGLE_SYNC_BRANCH PIXEAGLE_SYNC_REMOTE_URL
    if [[ "$(git rev-parse --verify 'HEAD^{commit}')" != "$candidate_head" ]]; then
        git update-ref -d "$candidate_ref" >/dev/null 2>&1 || true
        log_error "Live checkout did not publish the exact fetched candidate"
        return 1
    fi
    git update-ref -d "$candidate_ref" >/dev/null 2>&1 || {
        log_error "Could not remove the temporary update candidate ref"
        return 1
    }

    echo ""
    log_success "Exact source candidate published; reconciliation is still required"
    log_detail "Old HEAD: $old_head"
    log_detail "New HEAD: $candidate_head"
    echo "  ───────────────────────────────────────────"
    echo ""
    return 0
}

# Direct execution would bypass stopped-runtime/resource ownership checks.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    log_error "scripts/lib/sync.sh is internal; use 'make update'"
    exit 2
fi

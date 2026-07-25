#!/bin/bash
# ============================================================================
# scripts/lib/reset-config.sh - PixEagle Config Reset
# ============================================================================
# Resets configs/config.yaml and dashboard/.env to their defaults through the
# same validated, rollback-capable helper used by guided setup.
#
# Usage (standalone):
#   bash scripts/lib/reset-config.sh
#
# Usage (sourced):
#   source scripts/lib/reset-config.sh
#   do_reset_config
# ============================================================================

_RESET_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_RESET_PROJECT_ROOT="$(cd "$_RESET_SCRIPT_DIR/../.." && pwd)"

# Source common.sh for colored logging
if [[ -f "$_RESET_SCRIPT_DIR/common.sh" ]]; then
    # shellcheck source=scripts/lib/common.sh
    source "$_RESET_SCRIPT_DIR/common.sh"
else
    # Minimal fallback if common.sh is missing
    log_info()    { echo "  [INFO] $1"; }
    log_success() { echo "  [OK]   $1"; }
    log_error()   { echo "  [ERR]  $1" >&2; }
    log_warn()    { echo "  [WARN] $1"; }
    log_detail()  { echo "         $1"; }
fi
# shellcheck source=scripts/lib/setup_lock.sh
if ! source "$_RESET_SCRIPT_DIR/setup_lock.sh" 2>/dev/null; then
    log_error "Secure setup-lock helper is unavailable"
    if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
        return 1
    fi
    exit 1
fi

do_reset_config() {
    local project_root="${PIXEAGLE_ROOT:-$_RESET_PROJECT_ROOT}"
    local venv_dir
    if declare -F resolve_pixeagle_venv_dir >/dev/null 2>&1; then
        venv_dir="$(resolve_pixeagle_venv_dir "$project_root")"
    else
        venv_dir="${PIXEAGLE_VENV_DIR:-$project_root/venv}"
    fi
    local venv_python="$venv_dir/bin/python"
    local reset_helper="$project_root/scripts/setup/reset-local-settings.py"

    echo ""
    echo -e "  ${BOLD:-}Resetting Configuration Files${NC:-}"
    echo "  ───────────────────────────────────────────"
    echo ""

    if [[ ! -x "$venv_python" ]]; then
        log_error "PixEagle virtual-environment Python is unavailable: $venv_python"
        return 1
    fi
    if [[ ! -f "$reset_helper" || -L "$reset_helper" ]]; then
        log_error "Validated settings-reset helper is unavailable: $reset_helper"
        return 1
    fi
    if ! "$venv_python" "$reset_helper" \
        --project-root "$project_root" \
        --source "${PIXEAGLE_CONFIG_RESET_SOURCE:-manual_reset}"; then
        log_error "Configuration reset was rolled back"
        return 1
    fi

    echo ""
    log_success "Local settings reset to current defaults. Backups preserved."
    echo "  ───────────────────────────────────────────"
    echo ""
    return 0
}

run_reset_config_entrypoint() {
    local project_root="${PIXEAGLE_ROOT:-$_RESET_PROJECT_ROOT}"
    local venv_dir
    venv_dir="$(resolve_pixeagle_venv_dir "$project_root")" || return 1

    if pixeagle_setup_lock_context_present; then
        pixeagle_acquire_setup_lock "$venv_dir" "configuration reset" 30 || return 1
        do_reset_config
        return
    fi

    pixeagle_run_with_setup_lock \
        "$venv_dir" "configuration reset" 30 \
        env \
        PIXEAGLE_ROOT="$project_root" \
        PIXEAGLE_CONFIG_RESET_SOURCE="${PIXEAGLE_CONFIG_RESET_SOURCE:-manual_reset}" \
        bash "${BASH_SOURCE[0]}"
}

# Standalone guard: acquire the shared setup lock before resetting.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    run_reset_config_entrypoint
fi

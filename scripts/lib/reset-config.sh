#!/bin/bash
# ============================================================================
# scripts/lib/reset-config.sh - PixEagle Config Reset
# ============================================================================
# Resets configs/config.yaml and dashboard/.env to their defaults.
# Creates timestamped backups before overwriting.
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
    source "$_RESET_SCRIPT_DIR/common.sh"
else
    # Minimal fallback if common.sh is missing
    log_info()    { echo "  [INFO] $1"; }
    log_success() { echo "  [OK]   $1"; }
    log_error()   { echo "  [ERR]  $1" >&2; }
    log_warn()    { echo "  [WARN] $1"; }
    log_detail()  { echo "         $1"; }
fi

do_reset_config() {
    local project_root="${PIXEAGLE_ROOT:-$_RESET_PROJECT_ROOT}"
    local config_file="$project_root/configs/config.yaml"
    local config_default="$project_root/configs/config_default.yaml"
    local env_file="$project_root/dashboard/.env"
    local env_default="$project_root/dashboard/env_default.yaml"
    local venv_activate="$project_root/venv/bin/activate"

    echo ""
    echo -e "  ${BOLD:-}Resetting Configuration Files${NC:-}"
    echo "  ───────────────────────────────────────────"
    echo ""

    # --- config.yaml ---
    if [[ ! -f "$config_default" ]]; then
        log_error "Default config not found: $config_default"
        return 1
    fi

    if [[ -f "$config_file" ]]; then
        local backup="$config_file.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$config_file" "$backup"
        log_info "Backed up: $(basename "$backup")"
    fi

    cp "$config_default" "$config_file"
    log_success "Reset: configs/config.yaml"

    # --- dashboard/.env ---
    if [[ -f "$env_file" ]]; then
        local env_backup="$env_file.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$env_file" "$env_backup"
        log_info "Backed up: $(basename "$env_backup")"
    fi

    if [[ -f "$env_default" && -f "$venv_activate" ]]; then
        # shellcheck disable=SC1090
        source "$venv_activate"
        python3 -c "
import yaml
with open('$env_default') as f:
    config = yaml.safe_load(f)
lines = [f'{k}={v}' for k, v in config.items()]
open('$env_file', 'w').write('\n'.join(lines) + '\n')
"
        log_success "Reset: dashboard/.env"
    elif [[ -f "$env_default" ]]; then
        log_warn "venv not found — skipping dashboard/.env conversion"
    else
        log_detail "Skipped: dashboard/env_default.yaml not found"
    fi

    echo ""
    log_success "Config files reset to defaults. Backups preserved."
    echo "  ───────────────────────────────────────────"
    echo ""
    return 0
}

# Standalone guard: run do_reset_config() when executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    do_reset_config
fi

#!/usr/bin/env bash
# Install or remove the optional Bash `pixeagle` project-directory shortcut.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"

# shellcheck source=scripts/lib/common.sh
source "$SCRIPTS_DIR/lib/common.sh"

PROFILE_PATH="${PIXEAGLE_SHELL_PROFILE:-$HOME/.bashrc}"
ACTION="install"
ASSUME_YES=false
DRY_RUN=false
TEMP_PATH=""
BEGIN_MARKER="# >>> PixEagle directory shortcut >>>"
END_MARKER="# <<< PixEagle directory shortcut <<<"

cleanup() {
    [[ -z "$TEMP_PATH" || ! -e "$TEMP_PATH" ]] || rm -f -- "$TEMP_PATH"
}
trap cleanup EXIT

fail() {
    log_error "$1"
    exit 1
}

show_help() {
    cat <<'EOF'
Usage: bash scripts/setup/install-shell-shortcut.sh [OPTIONS]

Install an owner-controlled Bash alias named `pixeagle`. Running it changes the
current shell directory to this PixEagle checkout. It does not start PixEagle,
install a service, or enable boot auto-start.

Options:
  --remove          Remove the managed shortcut block
  --profile PATH    Bash profile to update (default: ~/.bashrc)
  --yes             Skip the confirmation prompt
  --dry-run         Print the planned change without writing
  --help, -h        Show this help
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --remove) ACTION="remove" ;;
            --profile)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --profile"
                PROFILE_PATH="$1"
                ;;
            --yes) ASSUME_YES=true ;;
            --dry-run) DRY_RUN=true ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *) fail "Unknown option: $1" ;;
        esac
        shift
    done
}

validate_profile() {
    [[ -n "${HOME:-}" && "$HOME" == /* ]] || fail "HOME must be an absolute path"
    [[ "$PROFILE_PATH" == /* ]] || fail "Bash profile path must be absolute: $PROFILE_PATH"

    local parent basename canonical_parent owner_uid
    parent="$(dirname -- "$PROFILE_PATH")"
    basename="$(basename -- "$PROFILE_PATH")"
    [[ -d "$parent" && ! -L "$parent" ]] || fail "Profile parent must be a real directory: $parent"
    canonical_parent="$(cd "$parent" && pwd -P)"
    PROFILE_PATH="$canonical_parent/$basename"

    case "$PROFILE_PATH" in
        "$HOME/.bashrc"|"$HOME/.bash_profile") ;;
        *) fail "Refusing to edit a profile outside ~/.bashrc or ~/.bash_profile" ;;
    esac

    if [[ -e "$PROFILE_PATH" || -L "$PROFILE_PATH" ]]; then
        [[ -f "$PROFILE_PATH" && ! -L "$PROFILE_PATH" ]] \
            || fail "Bash profile must be a regular non-symlink file: $PROFILE_PATH"
        owner_uid="$(stat -c '%u' -- "$PROFILE_PATH" 2>/dev/null || true)"
        [[ "$owner_uid" == "$(id -u)" ]] \
            || fail "Bash profile must be owned by the current user: $PROFILE_PATH"
    fi
}

confirm_plan() {
    [[ "$ASSUME_YES" == true || "$DRY_RUN" == true ]] && return 0
    local reply=""
    printf '   Apply this Bash shortcut change? [y/N]: '
    pixeagle_read_user_input reply || return 1
    [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]
}

write_profile() {
    local begin_count end_count alias_value last_byte
    begin_count="$(grep -Fxc "$BEGIN_MARKER" "$PROFILE_PATH" 2>/dev/null || true)"
    end_count="$(grep -Fxc "$END_MARKER" "$PROFILE_PATH" 2>/dev/null || true)"
    [[ "$begin_count" == "$end_count" && "$begin_count" -le 1 ]] \
        || fail "Managed shortcut markers are incomplete or duplicated in $PROFILE_PATH"

    TEMP_PATH="$(mktemp "$(dirname -- "$PROFILE_PATH")/.pixeagle-bashrc.XXXXXX")"
    chmod 0600 -- "$TEMP_PATH"
    if [[ -f "$PROFILE_PATH" ]]; then
        awk -v begin="$BEGIN_MARKER" -v end="$END_MARKER" '
            $0 == begin { managed = 1; next }
            $0 == end { managed = 0; next }
            !managed { print }
        ' "$PROFILE_PATH" > "$TEMP_PATH"
        chmod --reference="$PROFILE_PATH" -- "$TEMP_PATH"
    fi

    if [[ "$ACTION" == "install" ]]; then
        alias_value="$(printf '%q' "cd -- $PIXEAGLE_DIR")"
        if [[ -s "$TEMP_PATH" ]]; then
            last_byte="$(tail -c 1 -- "$TEMP_PATH" | od -An -t u1 | tr -d '[:space:]')"
            [[ "$last_byte" == "10" ]] || printf '\n' >> "$TEMP_PATH"
        fi
        printf '%s\nalias pixeagle=%s\n%s\n' \
            "$BEGIN_MARKER" "$alias_value" "$END_MARKER" >> "$TEMP_PATH"
    fi
    mv -- "$TEMP_PATH" "$PROFILE_PATH"
    TEMP_PATH=""
}

main() {
    parse_args "$@"
    validate_profile
    display_pixeagle_banner "Bash Shortcut" "Optional project-directory command"
    log_info "Action: $ACTION"
    log_info "Profile: $PROFILE_PATH"
    if [[ "$ACTION" == "install" ]]; then
        log_info "Command: pixeagle (changes directory to $PIXEAGLE_DIR)"
    fi

    if [[ "$DRY_RUN" == true ]]; then
        log_success "Dry run complete; no profile file was changed"
        return 0
    fi
    if ! confirm_plan; then
        log_info "Bash shortcut change cancelled"
        return 0
    fi

    write_profile
    if [[ "$ACTION" == "install" ]]; then
        log_success "Bash shortcut installed"
        log_detail "Open a new Bash session or run: source $PROFILE_PATH"
    else
        log_success "Managed Bash shortcut removed"
    fi
}

main "$@"

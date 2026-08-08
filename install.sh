#!/usr/bin/env bash
# PixEagle source-aware bootstrap for maintained Debian-family Linux hosts.

set -euo pipefail

REPO_URL="${PIXEAGLE_REPO_URL:-https://github.com/alireza787b/PixEagle.git}"
BRANCH="${PIXEAGLE_BRANCH:-main}"
PINNED_COMMIT="${PIXEAGLE_COMMIT:-}"
INSTALL_DIR="${PIXEAGLE_HOME:-$HOME/PixEagle}"
EXISTING_CHECKOUT=false
SETUP_RECONCILED=false
SOURCE_MODE=""
SOURCE_HEAD=""
CLONE_STAGING_DIR=""
GUIDED_INPUT_MODE="unresolved"
BROWSER_LAB_STARTED=false
BROWSER_LAB_URL=""
BROWSER_LAB_MODE=""
BROWSER_LAB_HOST=""
BROWSER_CREDENTIALS_REUSED=false
SERVICE_ONBOARDING_REVIEWED=false
BOOTSTRAP_PRIVILEGE_COMMAND=()

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info() { printf '   %b[*]%b %s\n' "$CYAN" "$NC" "$1"; }
ok() { printf '   %b[OK]%b %s\n' "$GREEN" "$NC" "$1"; }
warn() { printf '   %b[WARN]%b %s\n' "$YELLOW" "$NC" "$1"; }
fail() { printf '   %b[ERROR]%b %s\n' "$RED" "$NC" "$1" >&2; exit 1; }

show_banner() {
    printf '\n%b' "$CYAN$BOLD"
    cat <<'ASCIIART'
 _____ _      ______            _
 |  __ (_)    |  ____|          | |
 | |__) |__  _| |__   __ _  __ _| | ___
 |  ___/ \ \/ /  __| / _` |/ _` | |/ _ \
 | |   | |>  <| |___| (_| | (_| | |  __/
 |_|   |_/_/\_\______\__,_|\__, |_|\___|
                            __/ |
                           |___/
ASCIIART
    printf '%b\n  %bInstaller%b\n\n' "$NC" "$BOLD" "$NC"
}

has_interactive_input() {
    [[ "${PIXEAGLE_NONINTERACTIVE:-0}" != "1" ]] || return 1
    [[ -t 0 ]] && return 0
    ( : </dev/tty ) 2>/dev/null
}

read_user_input() {
    local __pixeagle_destination="$1"
    local __pixeagle_read_value=""

    [[ "$__pixeagle_destination" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || return 2
    if [[ -t 0 ]]; then
        IFS= read -r __pixeagle_read_value || return 1
    elif ( : </dev/tty ) 2>/dev/null; then
        IFS= read -r __pixeagle_read_value </dev/tty || return 1
    else
        return 1
    fi
    printf -v "$__pixeagle_destination" '%s' "$__pixeagle_read_value"
}

truthy() {
    case "${1:-}" in
        1|true|TRUE|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

# The bootstrap reads its program from stdin in the documented `curl | bash`
# workflow. Once a controlling terminal is verified, guided children must read
# from that terminal explicitly rather than inheriting the installer pipe.
run_guided_command() {
    case "$GUIDED_INPUT_MODE" in
        tty)
            "$@" </dev/tty
            ;;
        noninteractive)
            "$@"
            ;;
        *)
            fail "Internal input mode was not prepared before guided setup."
            ;;
    esac
}

show_help() {
    cat <<'EOF'
Usage: bash install.sh

Fresh host:
  Without PIXEAGLE_COMMIT, clone a mutable branch for lab/development use.
  With PIXEAGLE_COMMIT=<exact 40-hex commit>, create a detached production/RPi
  checkout and verify FETCH_HEAD and checkout HEAD before publishing it.

Existing checkout:
  Delegate to scripts/update.sh, which can ask to stop a runtime owned by this
  checkout. It then requires a clean worktree and explicit setup repair with a
  branch-based fast-forward source update. Valid components and operator data
  are preserved. Exact-commit installs are intentionally fresh-checkout only.

Environment:
  PIXEAGLE_HOME                         Install directory (default: ~/PixEagle)
  PIXEAGLE_REPO_URL                     Source repository
  PIXEAGLE_BRANCH                       Mutable lab/update branch (default: main)
  PIXEAGLE_COMMIT                       Exact 40-hex production/RPi source pin
  PIXEAGLE_INSTALL_PROFILE=core|full    Explicit setup profile
  PIXEAGLE_OPTIONAL_COMPONENTS=LIST     Explicit comma-separated optional setup:
                                        dlib,gstreamer,shell-shortcut
  PIXEAGLE_NONINTERACTIVE=1             No prompts; profile must be explicit
  PIXEAGLE_INSTALL_BOOTSTRAP_PACKAGES=1 Allow unattended apt installation of
                                        missing git/python3 prerequisites
  PIXEAGLE_UPDATE_STOP_RUNTIME=1        Allow owned runtime stop during automation
  PIXEAGLE_ACCEPT_GENERATED_BACKUPS=1   Preserve/ignore known setup backup files
  PIXEAGLE_START_BROWSER_LAB=1          Explicit unattended browser-lab start
  PIXEAGLE_QUICK_DEMO_HOST=IP_OR_HOST   Required with unattended browser-lab start
  PIXEAGLE_ALLOW_PUBLIC_HTTP_DEMO=1     Required for unattended public HTTP lab
  PIXEAGLE_ALLOW_UNVERIFIED_APT_DISTRO=1
  PIXEAGLE_ALLOW_UNVERIFIED_ARCH=1      Expert test overrides
EOF
}

check_platform() {
    [[ "$(uname -s)" == "Linux" ]] || fail \
        "PixEagle guided bootstrap currently supports Linux only; use a maintained Debian-family Linux host or WSL 2."

    local arch
    arch="$(uname -m)"
    case "$arch" in
        x86_64|aarch64|arm64) ;;
        *)
            [[ "${PIXEAGLE_ALLOW_UNVERIFIED_ARCH:-0}" == "1" ]] || fail \
                "Unsupported guided-bootstrap architecture '$arch' (expected x86_64 or ARM64)."
            warn "Proceeding on unverified architecture '$arch' by explicit override"
            ;;
    esac

    [[ -r /etc/os-release ]] || fail "Cannot identify Linux distribution from /etc/os-release."
    local distro_id distro_like
    distro_id="$(. /etc/os-release; printf '%s' "${ID:-unknown}")"
    distro_like="$(. /etc/os-release; printf '%s' "${ID_LIKE:-}")"
    distro_id="${distro_id,,}"
    distro_like="${distro_like,,}"
    if [[ "$distro_id" != "ubuntu" && "$distro_id" != "debian" && \
          "$distro_id" != "raspbian" && "$distro_like" != *debian* && \
          "$distro_like" != *ubuntu* ]]; then
        [[ "${PIXEAGLE_ALLOW_UNVERIFIED_APT_DISTRO:-0}" == "1" ]] || fail \
            "Guided bootstrap is maintained for Debian-family Linux."
        warn "Proceeding on an unverified apt-compatible distribution by explicit override"
    fi
    ok "Platform accepted: $distro_id / $arch"
}

prepare_bootstrap_privilege() {
    BOOTSTRAP_PRIVILEGE_COMMAND=()
    if [[ "$EUID" -eq 0 ]]; then
        return 0
    fi

    command -v sudo >/dev/null 2>&1 || fail \
        "Administrator access is required. Install sudo or install the missing packages as root, then rerun."

    info "Administrator access is required for bootstrap packages"
    if [[ "$GUIDED_INPUT_MODE" == "tty" ]]; then
        printf "   sudo will ask for this account's password; PixEagle does not read or store it.\n"
        run_guided_command sudo -v || fail "Administrator authentication failed; no packages were installed."
        BOOTSTRAP_PRIVILEGE_COMMAND=(sudo)
    else
        sudo -n -v >/dev/null 2>&1 || fail \
            "Unattended prerequisite installation requires an existing sudo ticket or root."
        BOOTSTRAP_PRIVILEGE_COMMAND=(sudo -n)
    fi
}

run_bootstrap_as_root() {
    if (( ${#BOOTSTRAP_PRIVILEGE_COMMAND[@]} == 0 )); then
        "$@"
    else
        "${BOOTSTRAP_PRIVILEGE_COMMAND[@]}" "$@"
    fi
}

install_bootstrap_packages() {
    local -a packages=("$@")

    command -v apt-get >/dev/null 2>&1 || fail \
        "apt-get is unavailable; install these prerequisites with the host package manager: ${packages[*]}."
    prepare_bootstrap_privilege

    info "Updating package lists"
    run_bootstrap_as_root env DEBIAN_FRONTEND=noninteractive apt-get update \
        || fail "Package-list update failed; no bootstrap packages were installed."
    info "Installing bootstrap packages: ${packages[*]}"
    run_bootstrap_as_root env DEBIAN_FRONTEND=noninteractive \
        apt-get install -y --no-install-recommends "${packages[@]}" \
        || fail "Bootstrap package installation failed: ${packages[*]}."
}

check_prerequisites() {
    local -a missing=()
    local -a packages=()
    local command_name
    local reply=""
    local policy="${PIXEAGLE_INSTALL_BOOTSTRAP_PACKAGES:-}"

    for command_name in git python3; do
        command -v "$command_name" >/dev/null 2>&1 || missing+=("$command_name")
    done
    if (( ${#missing[@]} == 0 )); then
        ok "Bootstrap prerequisites available"
        return 0
    fi

    for command_name in "${missing[@]}"; do
        case "$command_name" in
            git) packages+=(git) ;;
            python3) packages+=(python3) ;;
        esac
    done

    warn "Missing bootstrap prerequisites: ${missing[*]}"
    case "$policy" in
        1) ;;
        0) fail "Bootstrap prerequisite installation was disabled; missing: ${missing[*]}." ;;
        "")
            if [[ "$GUIDED_INPUT_MODE" != "tty" ]]; then
                fail "Install ${packages[*]} first, or rerun unattended with PIXEAGLE_INSTALL_BOOTSTRAP_PACKAGES=1."
            fi
            while true; do
                printf '   Install missing bootstrap packages now? [Y/n]: '
                if ! read_user_input reply; then
                    fail "Terminal input closed before prerequisite installation was confirmed."
                fi
                case "$reply" in
                    ""|[Yy]|[Yy][Ee][Ss]) break ;;
                    [Nn]|[Nn][Oo])
                        fail "Missing prerequisites were left unchanged: ${missing[*]}."
                        ;;
                    *) warn "Please enter y or n." ;;
                esac
            done
            ;;
        *) fail "PIXEAGLE_INSTALL_BOOTSTRAP_PACKAGES must be 0 or 1." ;;
    esac

    install_bootstrap_packages "${packages[@]}"
    for command_name in "${missing[@]}"; do
        command -v "$command_name" >/dev/null 2>&1 || fail \
            "Package installation completed, but '$command_name' is still unavailable."
    done
    ok "Bootstrap prerequisites available"
}

validate_source_policy() {
    if [[ -n "$PINNED_COMMIT" ]]; then
        [[ "$PINNED_COMMIT" =~ ^[0-9A-Fa-f]{40}$ ]] || fail \
            "PIXEAGLE_COMMIT must be one exact 40-hex Git commit."
        [[ ! -v PIXEAGLE_BRANCH ]] || fail \
            "Do not combine PIXEAGLE_COMMIT with PIXEAGLE_BRANCH; the source request is ambiguous."
        PINNED_COMMIT="${PINNED_COMMIT,,}"
        SOURCE_MODE="production/RPi exact-commit"
        info "Exact source pin requested: $PINNED_COMMIT"
        return
    fi

    git check-ref-format "refs/heads/$BRANCH" >/dev/null 2>&1 || fail \
        "Invalid PIXEAGLE_BRANCH value: $BRANCH"
    SOURCE_MODE="mutable lab/development branch"
    warn "No PIXEAGLE_COMMIT supplied; '$BRANCH' is mutable and this path is for lab/development only"
    warn "Use an exact reviewed 40-hex PIXEAGLE_COMMIT for production or Raspberry Pi acceptance"
}

prepare_noninteractive_profile() {
    if [[ "${PIXEAGLE_NONINTERACTIVE:-0}" == "1" ]]; then
        case "${PIXEAGLE_INSTALL_PROFILE:-}" in
            core|CORE|full|FULL|1|2) ;;
            *) fail "PIXEAGLE_NONINTERACTIVE=1 requires PIXEAGLE_INSTALL_PROFILE=core|full." ;;
        esac
        GUIDED_INPUT_MODE="noninteractive"
        return
    fi

    if has_interactive_input; then
        GUIDED_INPUT_MODE="tty"
        info "Interactive terminal detected; setup will pause for your choices"
        return
    fi

    GUIDED_INPUT_MODE="noninteractive"
    export PIXEAGLE_NONINTERACTIVE=1
    export PIXEAGLE_INSTALL_PROFILE="${PIXEAGLE_INSTALL_PROFILE:-core}"
    info "No controlling terminal is available; using profile '${PIXEAGLE_INSTALL_PROFILE}'"
    info "For an unattended Full install, set PIXEAGLE_NONINTERACTIVE=1 PIXEAGLE_INSTALL_PROFILE=full"
}

inspect_existing_checkout() {
    [[ -z "$PINNED_COMMIT" ]] || fail \
        "PIXEAGLE_COMMIT is fresh-install only; this existing checkout was not changed."
    local status
    if ! status="$(git -C "$INSTALL_DIR" status --porcelain --untracked-files=all 2>/dev/null)"; then
        fail "Cannot inspect the existing checkout; refusing automatic update."
    fi
    if [[ -n "$status" ]] && only_generated_dashboard_backups_are_untracked; then
        preserve_generated_dashboard_backups
        if ! status="$(git -C "$INSTALL_DIR" status --porcelain --untracked-files=all 2>/dev/null)"; then
            fail "Cannot recheck the existing checkout after preserving generated backups."
        fi
    fi
    if [[ -n "$status" ]]; then
        git -C "$INSTALL_DIR" status --short >&2 || true
        fail "Existing checkout has local changes. Commit them, or run 'git stash push --include-untracked', before updating."
    fi

    local current_branch
    current_branch="$(git -C "$INSTALL_DIR" branch --show-current 2>/dev/null || true)"
    [[ "$current_branch" == "$BRANCH" ]] || fail \
        "Existing checkout branch '$current_branch' does not match requested branch '$BRANCH'."
    [[ -f "$INSTALL_DIR/scripts/update.sh" ]] || fail \
        "Existing checkout predates the safe updater; stop PixEagle and upgrade through a reviewed intermediate release."
    ok "Existing clean checkout found: $current_branch"
}

only_generated_dashboard_backups_are_untracked() {
    local inventory_path=""
    local path=""
    local found=false

    git -C "$INSTALL_DIR" diff --quiet --ignore-submodules=none -- \
        || return 1
    git -C "$INSTALL_DIR" diff --cached --quiet --ignore-submodules=none -- \
        || return 1

    inventory_path="$(mktemp "${TMPDIR:-/tmp}/pixeagle-untracked.XXXXXX")" \
        || return 1
    if ! git -C "$INSTALL_DIR" \
        ls-files --others --exclude-standard -z > "$inventory_path"; then
        rm -f -- "$inventory_path"
        return 1
    fi
    while IFS= read -r -d '' path; do
        found=true
        case "$path" in
            dashboard/backups/*) ;;
            *)
                rm -f -- "$inventory_path"
                return 1
                ;;
        esac
    done < "$inventory_path"
    rm -f -- "$inventory_path"
    [[ "$found" == true ]]
}

preserve_generated_dashboard_backups() {
    local exclude_path="$INSTALL_DIR/.git/info/exclude"
    local reply=""
    local policy="${PIXEAGLE_ACCEPT_GENERATED_BACKUPS:-}"

    case "$policy" in
        ""|0|1) ;;
        *) fail "PIXEAGLE_ACCEPT_GENERATED_BACKUPS must be 0 or 1." ;;
    esac

    warn "Found only generated dashboard settings backups."
    printf '   They are operator data and will be preserved outside source updates.\n'
    if [[ "$policy" == "0" ]]; then
        fail "Generated-backup preservation was declined; no Git metadata was changed."
    elif [[ "$policy" != "1" ]]; then
        if [[ "$GUIDED_INPUT_MODE" != "tty" ]]; then
            fail "Rerun interactively, or set PIXEAGLE_ACCEPT_GENERATED_BACKUPS=1."
        fi
        printf '   Preserve these backups and continue? [Y/n]: '
        if ! read_user_input reply; then
            fail "Could not read generated-backup confirmation."
        fi
        case "$reply" in
            ""|[Yy]|[Yy][Ee][Ss]) ;;
            [Nn]|[Nn][Oo])
                fail "Generated backups were left unchanged; update was not started."
                ;;
            *) fail "Please answer y or n, then rerun the installer." ;;
        esac
    fi

    [[ ! -L "$INSTALL_DIR/.git/info" ]] \
        || fail "Git info path is a symbolic link; refusing compatibility repair."
    mkdir -p -- "$INSTALL_DIR/.git/info"
    [[ ! -e "$exclude_path" || ( -f "$exclude_path" && ! -L "$exclude_path" ) ]] \
        || fail "Git exclude path is not a regular file; refusing compatibility repair."
    if ! grep -Fqx '/dashboard/backups/' "$exclude_path" 2>/dev/null; then
        printf '\n# PixEagle generated operator settings backups\n/dashboard/backups/\n' \
            >> "$exclude_path"
    fi
    ok "Generated dashboard backups preserved and excluded from source updates"
}

cleanup_clone_staging() {
    [[ -n "$CLONE_STAGING_DIR" && -d "$CLONE_STAGING_DIR" ]] || return 0
    case "$(basename -- "$CLONE_STAGING_DIR")" in
        .pixeagle-bootstrap.*)
            rm -rf -- "$CLONE_STAGING_DIR"
            ;;
        *)
            warn "Refusing to remove unexpected bootstrap staging path: $CLONE_STAGING_DIR"
            ;;
    esac
}

trap cleanup_clone_staging EXIT

prepare_clone_staging() {
    local install_parent install_name
    install_parent="$(dirname -- "$INSTALL_DIR")"
    install_name="$(basename -- "$INSTALL_DIR")"
    [[ -n "$install_name" && "$install_name" != "." && "$install_name" != "/" ]] || fail \
        "Invalid PIXEAGLE_HOME install path: $INSTALL_DIR"
    mkdir -p -- "$install_parent"
    install_parent="$(cd -- "$install_parent" && pwd -P)"
    INSTALL_DIR="$install_parent/$install_name"
    CLONE_STAGING_DIR="$(mktemp -d "$install_parent/.pixeagle-bootstrap.XXXXXX")" || fail \
        "Could not create private checkout staging directory."
}

clone_pinned_commit() {
    local fetched_head checkout_head
    info "Fetching exact commit $PINNED_COMMIT into private staging"
    git -C "$CLONE_STAGING_DIR" init --quiet
    git -C "$CLONE_STAGING_DIR" remote add origin "$REPO_URL"
    git -C "$CLONE_STAGING_DIR" fetch --quiet --no-tags --depth 1 origin "$PINNED_COMMIT"
    fetched_head="$(git -C "$CLONE_STAGING_DIR" rev-parse --verify 'FETCH_HEAD^{commit}')" || fail \
        "Fetched source is not a commit."
    [[ "$fetched_head" == "$PINNED_COMMIT" ]] || fail \
        "Fetched commit '$fetched_head' does not match requested '$PINNED_COMMIT'."

    git -C "$CLONE_STAGING_DIR" -c advice.detachedHead=false \
        checkout --quiet --detach "$PINNED_COMMIT"
    checkout_head="$(git -C "$CLONE_STAGING_DIR" rev-parse --verify 'HEAD^{commit}')" || fail \
        "Cannot verify staged checkout HEAD."
    [[ "$checkout_head" == "$PINNED_COMMIT" ]] || fail \
        "Checkout HEAD '$checkout_head' does not match requested '$PINNED_COMMIT'."
    if git -C "$CLONE_STAGING_DIR" symbolic-ref --quiet HEAD >/dev/null 2>&1; then
        fail "Exact-commit checkout unexpectedly remained attached to a mutable branch."
    fi
    SOURCE_HEAD="$checkout_head"
}

clone_mutable_lab_branch() {
    local checkout_branch
    info "Cloning mutable lab/development branch '$BRANCH' from $REPO_URL"
    git clone --quiet --depth 1 --single-branch --branch "$BRANCH" -- \
        "$REPO_URL" "$CLONE_STAGING_DIR"
    checkout_branch="$(git -C "$CLONE_STAGING_DIR" branch --show-current)"
    [[ "$checkout_branch" == "$BRANCH" ]] || fail \
        "Cloned branch '$checkout_branch' does not match requested '$BRANCH'."
    SOURCE_HEAD="$(git -C "$CLONE_STAGING_DIR" rev-parse --verify 'HEAD^{commit}')" || fail \
        "Cannot verify mutable lab checkout HEAD."
}

publish_staged_checkout() {
    [[ ! -e "$INSTALL_DIR" && ! -L "$INSTALL_DIR" ]] || fail \
        "Install path appeared during checkout staging; refusing to overwrite it: $INSTALL_DIR"
    mv -- "$CLONE_STAGING_DIR" "$INSTALL_DIR"
    CLONE_STAGING_DIR=""
    ok "Repository checkout published only after source verification"
}

confirm_existing_update() {
    if [[ "$GUIDED_INPUT_MODE" != "tty" ]]; then
        return 0
    fi
    local reply=""

    printf '\n'
    info "Recommended action: update source and repair this installation in place"
    printf '   Preserves: config, credentials, models, recordings, logs, and evidence\n'
    printf '   Reuses:    verified components whose source/dependency contracts still match\n'
    printf '   Reset:     never performed by this command\n'
    while true; do
        printf '   Update and repair this checkout? [Y/n]: '
        if ! read_user_input reply; then
            printf '\n'
            warn "Could not read the terminal response; existing checkout left unchanged"
            return 1
        fi
        case "$reply" in
            ""|[Yy]|[Yy][Ee][Ss]) return 0 ;;
            [Nn]|[Nn][Oo]) return 1 ;;
            *) warn "Please enter y or n." ;;
        esac
    done
}

legacy_updater_has_owned_manual_runtime() {
    PIXEAGLE_EXISTING_ROOT="$INSTALL_DIR" bash -c '
set -euo pipefail
root="$PIXEAGLE_EXISTING_ROOT"
source "$root/scripts/lib/runtime_ownership.sh"
socket="$(pixeagle_tmux_socket_name "$root" manual)"
if command -v tmux >/dev/null 2>&1 \
    && pixeagle_tmux_session_exists "$socket" pixeagle \
    && pixeagle_tmux_session_is_owned "$socket" pixeagle "$root" manual; then
    exit 0
fi
owned_pid=""
IFS= read -r owned_pid < <(
    pixeagle_owned_pids "$root" "$(id -u)" manual
) || true
[[ -n "$owned_pid" ]]
'
}

prepare_legacy_updater_runtime() {
    local updater="$INSTALL_DIR/scripts/update.sh"
    local reply=""

    # One-release bridge: an older checkout cannot offer the canonical
    # confirmed stop until its updater has itself been updated.
    grep -Fq "ensure_runtime_stopped_before_update" "$updater" 2>/dev/null \
        && return 0
    legacy_updater_has_owned_manual_runtime || return 0

    if [[ "${PIXEAGLE_UPDATE_STOP_RUNTIME:-}" == "1" ]]; then
        info "Stopping the owned manual runtime for updater compatibility"
    elif [[ "${PIXEAGLE_UPDATE_STOP_RUNTIME:-}" == "0" ]]; then
        fail "Update requires a stopped runtime; automatic stop was disabled."
    elif [[ "$GUIDED_INPUT_MODE" == "tty" ]]; then
        warn "The installed updater requires PixEagle to stop before it can be updated."
        printf '   Stop the owned manual runtime and continue? [Y/n]: '
        if ! read_user_input reply; then
            fail "Could not read runtime-stop confirmation."
        fi
        case "$reply" in
            ""|[Yy]|[Yy][Ee][Ss]) ;;
            [Nn]|[Nn][Oo]) fail "Update cancelled; the active runtime was not changed." ;;
            *) fail "Please answer y or n, then rerun the installer." ;;
        esac
    else
        fail "PixEagle is running. Stop it first, or set PIXEAGLE_UPDATE_STOP_RUNTIME=1."
    fi

    run_guided_command make -C "$INSTALL_DIR" stop \
        || fail "The ownership-aware manual runtime stop did not complete."
}

clone_or_reconcile() {
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        EXISTING_CHECKOUT=true
        inspect_existing_checkout
        if ! confirm_existing_update; then
            info "Existing checkout left unchanged"
            return 0
        fi

        prepare_legacy_updater_runtime
        info "Running the ownership-aware stopped-runtime updater"
        (
            cd "$INSTALL_DIR"
            run_guided_command env \
                SYNC_REMOTE=origin \
                SYNC_BRANCH="$BRANCH" \
                PIXEAGLE_BOOTSTRAP_CONTEXT=1 \
                PIXEAGLE_SETUP_ACTION=update-repair \
                bash scripts/update.sh
        )
        SOURCE_HEAD="$(git -C "$INSTALL_DIR" rev-parse --verify 'HEAD^{commit}')" || fail \
            "Cannot verify checkout HEAD after scripts/update.sh."
        SETUP_RECONCILED=true
        return 0
    fi

    [[ ! -e "$INSTALL_DIR" && ! -L "$INSTALL_DIR" ]] || fail \
        "Install path exists but is not a Git checkout: $INSTALL_DIR"
    prepare_clone_staging
    if [[ -n "$PINNED_COMMIT" ]]; then
        clone_pinned_commit
    else
        clone_mutable_lab_branch
    fi
    publish_staged_checkout
}

classify_browser_host() {
    python3 "$INSTALL_DIR/scripts/setup/browser_hosts.py" --classify "$1"
}

prompt_browser_host() {
    local default_host="$1"
    local destination="$2"
    local reply=""

    [[ "$destination" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || return 2
    while true; do
        printf '   Browser-reachable device IP or hostname [%s]: ' "${default_host:-required}"
        if ! read_user_input reply; then
            printf '\n'
            fail "Terminal input closed before browser access was configured."
        fi
        reply="${reply:-$default_host}"
        if [[ -n "$reply" && "$reply" != *[[:space:]]* ]]; then
            printf -v "$destination" '%s' "$reply"
            return 0
        fi
        warn "Enter one IP address or hostname without spaces."
    done
}

prompt_browser_access_mode() {
    local preferred_host="${1:-}"
    local reply=""
    local replacement=""
    local address=""
    local interface=""
    local scope=""
    local primary=""
    local default_marker=""
    local default_index=1
    local index=0
    local -a addresses=()
    local -a labels=()

    if [[ -n "$preferred_host" ]]; then
        addresses+=("$preferred_host")
        labels+=("$preferred_host (requested)")
    fi
    while IFS=$'\t' read -r address interface scope primary; do
        [[ -n "$address" ]] || continue
        if [[ -n "$preferred_host" && "$address" == "$preferred_host" ]]; then
            continue
        fi
        addresses+=("$address")
        if [[ "$primary" == "yes" ]]; then
            labels+=("$address ($interface, $scope, primary route)")
        else
            labels+=("$address ($interface, $scope)")
        fi
    done < <(python3 "$INSTALL_DIR/scripts/setup/browser_hosts.py" --format tsv)

    if [[ ${#addresses[@]} -eq 0 ]]; then
        prompt_browser_host "" replacement
        BROWSER_LAB_MODE="network"
        BROWSER_LAB_HOST="$replacement"
        info "Network lab will listen on all interfaces (0.0.0.0); open the selected device address"
        return 0
    fi

    while true; do
        printf '\n'
        printf '   Dashboard access (Enter enables network access on 0.0.0.0):\n'
        for index in "${!addresses[@]}"; do
            default_marker=""
            if (( index == 0 )); then
                default_marker=" [default]"
            fi
            printf '      %d) %s%s\n' "$((index + 1))" "${labels[$index]}" "$default_marker"
        done
        printf '      l) Local only (127.0.0.1)\n'
        printf '      c) Custom IP or hostname\n'
        printf '   Select [Enter=%d]: ' "$default_index"
        if ! read_user_input reply; then
            printf '\n'
            fail "Terminal input closed before dashboard access was selected."
        fi
        case "$reply" in
            "") reply="$default_index" ;;
        esac
        case "$reply" in
            [1-9]|[1-9][0-9]*)
                index=$((reply - 1))
                if (( index < 0 || index >= ${#addresses[@]} )); then
                    warn "Choose a listed number, l, or c."
                    continue
                fi
                BROWSER_LAB_MODE="network"
                BROWSER_LAB_HOST="${addresses[$index]}"
                info "Network lab will listen on all interfaces (0.0.0.0); open the selected device address"
                return 0
                ;;
            l|L)
                BROWSER_LAB_MODE="local"
                BROWSER_LAB_HOST="127.0.0.1"
                return 0
                ;;
            c|C)
                prompt_browser_host "${addresses[0]}" replacement
                BROWSER_LAB_MODE="network"
                BROWSER_LAB_HOST="$replacement"
                info "Network lab will listen on all interfaces (0.0.0.0); open the selected device address"
                return 0
                ;;
            *) warn "Choose a listed number, l, or c." ;;
        esac
    done
}

start_browser_lab() {
    [[ "$SETUP_RECONCILED" == "true" ]] || return 0

    local host="${PIXEAGLE_QUICK_DEMO_HOST:-}"
    local scope=""
    local allow_public=0
    local open_firewall="${PIXEAGLE_QUICK_DEMO_OPEN_FIREWALL:-1}"
    local secret_dir="${PIXEAGLE_QUICK_DEMO_SECRET_DIR:-$HOME/.config/pixeagle/secrets}"
    local user_file="${SESSION_USER_FILE:-$secret_dir/demo-browser-users.json}"
    local rotate_credentials="${PIXEAGLE_ROTATE_DEMO_CREDENTIALS:-0}"
    local reply=""

    if [[ "$GUIDED_INPUT_MODE" == "tty" ]]; then
        prompt_browser_access_mode "$host"
        host="$BROWSER_LAB_HOST"
        if [[ "$BROWSER_LAB_MODE" == "local" ]]; then
            info "Local browser lab will require the dashboard login on this computer"
            open_firewall=0
        fi
        scope="$(classify_browser_host "$host")"
        [[ "$scope" != "invalid" && "$scope" != "unsupported" ]] || fail "'$host' is not a usable browser address."
        if [[ "$scope" == "public" ]]; then
            warn "Temporary public HTTP lab; use only for testing. HTTPS guide: https://github.com/alireza787b/PixEagle/blob/main/docs/setup/production-remote-reverse-proxy.md"
        fi
    else
        truthy "${PIXEAGLE_START_BROWSER_LAB:-0}" || return 0
        BROWSER_LAB_MODE="network"
        [[ -n "$host" ]] || fail \
            "PIXEAGLE_START_BROWSER_LAB=1 requires PIXEAGLE_QUICK_DEMO_HOST=<device-ip>."
        scope="$(classify_browser_host "$host")"
        [[ "$scope" != "invalid" && "$scope" != "unsupported" ]] || fail "'$host' is not a usable browser address."
    fi

    if [[ "$scope" == "public" ]]; then
        allow_public=1
        if [[ "$GUIDED_INPUT_MODE" != "tty" ]] && \
           ! truthy "${PIXEAGLE_ALLOW_PUBLIC_HTTP_DEMO:-0}"; then
            fail "A non-interactive public HTTP lab also requires PIXEAGLE_ALLOW_PUBLIC_HTTP_DEMO=1."
        fi
    fi

    if [[ -f "$user_file" ]] && ! truthy "$rotate_credentials"; then
        if [[ "$GUIDED_INPUT_MODE" == "tty" ]]; then
            while true; do
                printf '   Keep the existing dashboard login? [Y/n]: '
                if ! read_user_input reply; then
                    printf '\n'
                    fail "Terminal input closed before the dashboard login was confirmed."
                fi
                case "$reply" in
                    ""|[Yy]|[Yy][Ee][Ss])
                        BROWSER_CREDENTIALS_REUSED=true
                        break
                        ;;
                    [Nn]|[Nn][Oo])
                        rotate_credentials=1
                        info "Choose a replacement login next; Enter keeps admin/admin"
                        break
                        ;;
                    *) warn "Please enter y or n." ;;
                esac
            done
        else
            BROWSER_CREDENTIALS_REUSED=true
        fi
    fi

    info "Applying the explicit browser-lab profile and starting PixEagle"
    if ! run_guided_command env \
        PIXEAGLE_BOOTSTRAP_CONTEXT=1 \
        PIXEAGLE_LAUNCH_COMPACT=1 \
        LAN_HOST="$host" \
        ALLOW_PUBLIC_HTTP_DEMO="$allow_public" \
        OPEN_FIREWALL="$open_firewall" \
        START_DEMO=1 \
        DEMO_CREDENTIAL_MODE=prompt \
        ROTATE_DEMO_CREDENTIALS="$rotate_credentials" \
        make --no-print-directory -C "$INSTALL_DIR" quick-browser-demo; then
        fail "Browser lab did not become ready. Review the quick-demo output above."
    fi

    BROWSER_LAB_STARTED=true
    BROWSER_LAB_URL="http://$host:3040/"
}

run_update_service_onboarding() {
    [[ "$EXISTING_CHECKOUT" == "true" ]] || return 0
    [[ "$SETUP_RECONCILED" == "true" ]] || return 0
    [[ "$GUIDED_INPUT_MODE" == "tty" ]] || return 0
    [[ -f "$INSTALL_DIR/scripts/init.sh" ]] || fail \
        "Missing initializer after update; managed-service choices cannot be reviewed."

    info "Reviewing optional managed-service settings"
    run_guided_command env \
        PIXEAGLE_SERVICE_INSTALL_DEFAULT=n \
        bash "$INSTALL_DIR/scripts/init.sh" --service-onboarding-only
    SERVICE_ONBOARDING_REVIEWED=true
}

run_fresh_initializer() {
    [[ "$EXISTING_CHECKOUT" == "false" ]] || return 0
    [[ -f "$INSTALL_DIR/scripts/init.sh" ]] || fail "Missing initializer after clone."
    info "Running guided initializer"
    (
        cd "$INSTALL_DIR"
        run_guided_command env \
            PIXEAGLE_BOOTSTRAP_CONTEXT=1 \
            PIXEAGLE_SETUP_ACTION=fresh \
            bash scripts/init.sh
    )
    SETUP_RECONCILED=true
}

show_result() {
    printf '\n'
    if [[ "$SETUP_RECONCILED" == "true" ]]; then
        printf '%b------------------------------------------------------------%b\n' "$CYAN" "$NC"
        printf '%bPixEagle is ready%b\n' "$BOLD" "$NC"
        printf '%b------------------------------------------------------------%b\n' "$CYAN" "$NC"
        printf '   Source mode: %s\n' "$SOURCE_MODE"
        printf '   Source HEAD: %s\n' "$SOURCE_HEAD"
        if [[ "$BROWSER_LAB_STARTED" == "true" ]]; then
            printf '   Dashboard: %s\n' "$BROWSER_LAB_URL"
            if [[ "$BROWSER_CREDENTIALS_REUSED" == "true" ]]; then
                printf '   Login: existing dashboard account preserved\n'
            else
                printf '   Login: selected above (Enter kept admin/admin)\n'
            fi
            if [[ "$BROWSER_LAB_MODE" == "local" ]]; then
                printf '   Access: this computer only\n'
            fi
            printf '   Runtime: manual browser lab; boot policy unchanged\n'
            printf '   Stop: cd %q && make stop\n' "$INSTALL_DIR"
        else
            printf '   Runtime: not started\n'
            printf '   Test: cd %q && make demo\n' "$INSTALL_DIR"
        fi
        if [[ "$SERVICE_ONBOARDING_REVIEWED" == "true" ]]; then
            printf '   Service: choices reviewed above; use pixeagle-service status\n'
        elif [[ "$EXISTING_CHECKOUT" == "true" ]]; then
            printf '   Service: existing installation and boot policy preserved\n'
        fi
        printf '   PX4: route MAVLink to 127.0.0.1:14540 and 127.0.0.1:14569\n'
        printf '   Security: browser setup does not open TCP 50051; block it on untrusted interfaces\n'
        printf '   Guide: https://github.com/alireza787b/PixEagle/blob/main/docs/drone-interface/04-infrastructure/port-configuration.md\n'
    else
        printf '%bNo changes made%b\n' "$YELLOW" "$NC"
        printf '   To reconcile later, stop PixEagle and rerun this installer.\n'
    fi
}

main() {
    if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
        show_help
        return 0
    fi
    [[ $# -eq 0 ]] || fail "Unknown argument: $1"

    show_banner
    check_platform
    prepare_noninteractive_profile
    check_prerequisites
    validate_source_policy
    clone_or_reconcile
    run_fresh_initializer
    run_update_service_onboarding
    start_browser_lab
    show_result
}

main "$@"

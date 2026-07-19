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
    printf '\n%bPixEagle Bootstrap%b\n\n' "$BOLD" "$NC"
}

show_help() {
    cat <<'EOF'
Usage: bash install.sh

Fresh host:
  Without PIXEAGLE_COMMIT, clone a mutable branch for lab/development use.
  With PIXEAGLE_COMMIT=<exact 40-hex commit>, create a detached production/RPi
  checkout and verify FETCH_HEAD and checkout HEAD before publishing it.

Existing checkout:
  Delegate to scripts/update.sh, which requires a stopped runtime, clean
  worktree, branch-based fast-forward source update, and explicit setup
  reconciliation. Exact-commit installs are intentionally fresh-checkout only.

Environment:
  PIXEAGLE_HOME                         Install directory (default: ~/PixEagle)
  PIXEAGLE_REPO_URL                     Source repository
  PIXEAGLE_BRANCH                       Mutable lab/update branch (default: main)
  PIXEAGLE_COMMIT                       Exact 40-hex production/RPi source pin
  PIXEAGLE_INSTALL_PROFILE=core|full    Explicit setup profile
  PIXEAGLE_NONINTERACTIVE=1             No prompts; profile must be explicit
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

check_prerequisites() {
    local missing=()
    local command_name
    for command_name in git python3 bash; do
        command -v "$command_name" >/dev/null 2>&1 || missing+=("$command_name")
    done
    (( ${#missing[@]} == 0 )) || fail \
        "Missing prerequisites: ${missing[*]}. Install them with apt and rerun."
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
        return
    fi

    if [[ ! -r /dev/tty || ! -w /dev/tty ]]; then
        export PIXEAGLE_NONINTERACTIVE=1
        export PIXEAGLE_INSTALL_PROFILE="${PIXEAGLE_INSTALL_PROFILE:-core}"
        info "No interactive terminal detected; selecting the Core profile"
    fi
}

inspect_existing_checkout() {
    [[ -z "$PINNED_COMMIT" ]] || fail \
        "PIXEAGLE_COMMIT is fresh-install only; this existing checkout was not changed."
    local status
    if ! status="$(git -C "$INSTALL_DIR" status --porcelain --untracked-files=all 2>/dev/null)"; then
        fail "Cannot inspect the existing checkout; refusing automatic update."
    fi
    if [[ -n "$status" ]]; then
        git -C "$INSTALL_DIR" status --short >&2 || true
        fail "Existing checkout has local changes; commit or stash them manually before updating."
    fi

    local current_branch
    current_branch="$(git -C "$INSTALL_DIR" branch --show-current 2>/dev/null || true)"
    [[ "$current_branch" == "$BRANCH" ]] || fail \
        "Existing checkout branch '$current_branch' does not match requested branch '$BRANCH'."
    [[ -f "$INSTALL_DIR/scripts/update.sh" ]] || fail \
        "Existing checkout predates the safe updater; stop PixEagle and upgrade through a reviewed intermediate release."
    ok "Existing clean checkout found: $current_branch"
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
    if [[ "${PIXEAGLE_NONINTERACTIVE:-0}" == "1" || ! -r /dev/tty || ! -w /dev/tty ]]; then
        return 0
    fi
    local reply=""
    printf '   Update and reconcile this stopped checkout? [Y/n]: ' >/dev/tty
    read -r reply </dev/tty || reply="n"
    [[ -z "$reply" || "$reply" =~ ^[Yy]$ ]]
}

clone_or_reconcile() {
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        EXISTING_CHECKOUT=true
        inspect_existing_checkout
        if ! confirm_existing_update; then
            info "Existing checkout left unchanged"
            return 0
        fi

        info "Running the ownership-aware stopped-runtime updater"
        (
            cd "$INSTALL_DIR"
            SYNC_REMOTE=origin SYNC_BRANCH="$BRANCH" bash scripts/update.sh
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

run_fresh_initializer() {
    [[ "$EXISTING_CHECKOUT" == "false" ]] || return 0
    [[ -f "$INSTALL_DIR/scripts/init.sh" ]] || fail "Missing initializer after clone."
    info "Running guided initializer"
    (
        cd "$INSTALL_DIR"
        bash scripts/init.sh
    )
    SETUP_RECONCILED=true
}

show_result() {
    printf '\n'
    if [[ "$SETUP_RECONCILED" == "true" ]]; then
        printf '%bBootstrap Finished%b\n' "$GREEN" "$NC"
        printf '   Checkout: %s\n' "$INSTALL_DIR"
        printf '   Source mode: %s\n' "$SOURCE_MODE"
        printf '   Source HEAD: %s\n' "$SOURCE_HEAD"
        printf '   Review the init summary above before starting services.\n'
        printf '   Resolve any degraded or manual-follow-up items, then rerun make init.\n'
        printf '   Start only after the init summary is ready for your use case.\n'
        printf '   Beginner test (recorded video, no PX4):\n'
        printf '   Next: cd %q && make demo\n' "$INSTALL_DIR"
        printf '   Configure a live source and explicit PX4 mode before vehicle use.\n'
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
    check_prerequisites
    validate_source_policy
    prepare_noninteractive_profile
    clone_or_reconcile
    run_fresh_initializer
    show_result
}

main "$@"

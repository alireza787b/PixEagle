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
  Delegate to scripts/update.sh, which requires a stopped runtime, clean
  worktree, branch-based fast-forward source update, and explicit setup
  repair. Valid components and operator data are preserved. Exact-commit
  installs are intentionally fresh-checkout only.

Environment:
  PIXEAGLE_HOME                         Install directory (default: ~/PixEagle)
  PIXEAGLE_REPO_URL                     Source repository
  PIXEAGLE_BRANCH                       Mutable lab/update branch (default: main)
  PIXEAGLE_COMMIT                       Exact 40-hex production/RPi source pin
  PIXEAGLE_INSTALL_PROFILE=core|full    Explicit setup profile
  PIXEAGLE_OPTIONAL_COMPONENTS=LIST     Explicit comma-separated optional setup:
                                        dlib,gstreamer,shell-shortcut
  PIXEAGLE_NONINTERACTIVE=1             No prompts; profile must be explicit
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

detect_browser_host() {
    local detected=""
    if command -v ip >/dev/null 2>&1; then
        detected="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}' || true)"
    fi
    if [[ -z "$detected" ]] && command -v hostname >/dev/null 2>&1; then
        detected="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
    fi
    printf '%s\n' "$detected"
}

classify_browser_host() {
    python3 - "$1" <<'PY'
import ipaddress
import sys

host = sys.argv[1].strip().strip("[]")
try:
    address = ipaddress.ip_address(host)
except ValueError:
    print("hostname")
    raise SystemExit(0)

private_ranges = tuple(
    ipaddress.ip_network(value)
    for value in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "169.254.0.0/16",
        "fc00::/7",
        "fe80::/10",
    )
)
if any(address in network for network in private_ranges):
    print("private")
elif address.is_loopback or address.is_unspecified or address.is_multicast or address.is_reserved:
    print("invalid")
else:
    print("public")
PY
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
    local host="$1"
    local reply=""
    local replacement=""

    while true; do
        printf '\n'
        printf '   Dashboard access [Enter=http://%s:3040, 2=local only, 3=change address]: ' "$host"
        if ! read_user_input reply; then
            printf '\n'
            fail "Terminal input closed before dashboard access was selected."
        fi
        case "$reply" in
            ""|1)
                BROWSER_LAB_MODE="network"
                BROWSER_LAB_HOST="$host"
                return 0
                ;;
            2)
                BROWSER_LAB_MODE="local"
                BROWSER_LAB_HOST="127.0.0.1"
                return 0
                ;;
            3)
                prompt_browser_host "$host" replacement
                BROWSER_LAB_MODE="network"
                BROWSER_LAB_HOST="$replacement"
                return 0
                ;;
            *) warn "Press Enter, 2, or 3." ;;
        esac
    done
}

start_browser_lab() {
    [[ "$SETUP_RECONCILED" == "true" ]] || return 0

    local host="${PIXEAGLE_QUICK_DEMO_HOST:-}"
    local scope=""
    local allow_public=0
    local open_firewall="${PIXEAGLE_QUICK_DEMO_OPEN_FIREWALL:-1}"

    if [[ "$GUIDED_INPUT_MODE" == "tty" ]]; then
        host="${host:-$(detect_browser_host)}"
        [[ -n "$host" ]] || prompt_browser_host "" host
        prompt_browser_access_mode "$host"
        host="$BROWSER_LAB_HOST"
        if [[ "$BROWSER_LAB_MODE" == "local" ]]; then
            info "Starting the local bundled-video demo"
            if ! run_guided_command make -C "$INSTALL_DIR" demo; then
                fail "Local demo did not become ready. Review the demo output above."
            fi
            BROWSER_LAB_STARTED=true
            BROWSER_LAB_URL="http://127.0.0.1:3040/"
            return 0
        fi
        scope="$(classify_browser_host "$host")"
        [[ "$scope" != "invalid" ]] || fail "'$host' is not a usable browser address."
        if [[ "$scope" == "public" ]]; then
            warn "Temporary public HTTP lab; use only for testing. HTTPS guide: https://github.com/alireza787b/PixEagle/blob/main/docs/setup/production-remote-reverse-proxy.md"
        fi
    else
        truthy "${PIXEAGLE_START_BROWSER_LAB:-0}" || return 0
        BROWSER_LAB_MODE="network"
        [[ -n "$host" ]] || fail \
            "PIXEAGLE_START_BROWSER_LAB=1 requires PIXEAGLE_QUICK_DEMO_HOST=<device-ip>."
        scope="$(classify_browser_host "$host")"
        [[ "$scope" != "invalid" ]] || fail "'$host' is not a usable browser address."
    fi

    if [[ "$scope" == "public" ]]; then
        allow_public=1
        if [[ "$GUIDED_INPUT_MODE" != "tty" ]] && \
           ! truthy "${PIXEAGLE_ALLOW_PUBLIC_HTTP_DEMO:-0}"; then
            fail "A non-interactive public HTTP lab also requires PIXEAGLE_ALLOW_PUBLIC_HTTP_DEMO=1."
        fi
    fi

    info "Applying the explicit browser-lab profile and starting PixEagle"
    if ! run_guided_command env \
        LAN_HOST="$host" \
        ALLOW_PUBLIC_HTTP_DEMO="$allow_public" \
        OPEN_FIREWALL="$open_firewall" \
        START_DEMO=1 \
        DEMO_CREDENTIAL_MODE=prompt \
        make -C "$INSTALL_DIR" quick-browser-demo; then
        fail "Browser lab did not become ready. Review the quick-demo output above."
    fi

    BROWSER_LAB_STARTED=true
    BROWSER_LAB_URL="http://$host:3040/"
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
        printf '%bBootstrap Finished%b\n' "$GREEN" "$NC"
        printf '   Checkout: %s\n' "$INSTALL_DIR"
        printf '   Source mode: %s\n' "$SOURCE_MODE"
        printf '   Source HEAD: %s\n' "$SOURCE_HEAD"
        if [[ "$BROWSER_LAB_STARTED" == "true" ]]; then
            printf '   Dashboard: %s\n' "$BROWSER_LAB_URL"
            if [[ "$BROWSER_LAB_MODE" == "network" ]]; then
                printf '   Login: the username/password selected above (Enter kept admin/admin).\n'
            else
                printf '   Access: local host only; no remote browser exposure was enabled.\n'
            fi
            printf '   Verified locally: dashboard/backend startup gates passed.\n'
            printf '   Stop: cd %q && make stop\n' "$INSTALL_DIR"
            if [[ "$BROWSER_LAB_MODE" == "network" ]]; then
                printf '   Note: a provider/cloud firewall is outside this host and may still need TCP 3040 and 5077 allowed.\n'
            fi
        else
            printf '   No runtime was started. Local verification (bundled video, no PX4):\n'
            printf '   cd %q && make demo\n' "$INSTALL_DIR"
            printf '   Browser lab: cd %q && make quick-browser-demo LAN_HOST=<device-ip>\n' "$INSTALL_DIR"
        fi
        printf '   Configured PX4 operation: review the source/PX4 settings, then run make run.\n'
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
    start_browser_lab
    show_result
}

main "$@"

#!/usr/bin/env bash
# Deterministic optional dlib tracker installer. It never changes swap settings.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"

DLIB_VERSION="20.0.1"
DLIB_ARCHIVE_URL="https://files.pythonhosted.org/packages/25/1e/17570a07f9db19014f5df9cc5de2b4acfb47834e9921e019372b51d7cc03/dlib-20.0.1.tar.gz"
DLIB_ARCHIVE_SHA256="7cb2a09467de032332c743bc967007f016598c66c9c9ebc54a5b66d3d9e46d54"
ARCHIVE_OVERRIDE=""
ARCHIVE_SHA256_OVERRIDE=""
DRY_RUN=false
ASSUME_YES=false
SKIP_SYSTEM_PACKAGES=false
TEMP_DIR=""

# shellcheck source=scripts/lib/common.sh
source "$SCRIPTS_DIR/lib/common.sh"
# shellcheck source=scripts/lib/setup_lock.sh
source "$SCRIPTS_DIR/lib/setup_lock.sh"
# shellcheck source=scripts/lib/venv_transaction.sh
source "$SCRIPTS_DIR/lib/venv_transaction.sh"
VENV_DIR="$(resolve_pixeagle_venv_dir "$PIXEAGLE_DIR")"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

cleanup() {
    local exit_code=$?
    trap - EXIT
    [[ -z "$TEMP_DIR" || ! -d "$TEMP_DIR" ]] || rm -rf -- "$TEMP_DIR"
    if ! pixeagle_finalize_venv_transaction; then
        log_error "Virtual-environment rollback was incomplete"
        [[ "$exit_code" -ne 0 ]] || exit_code=1
    fi
    pixeagle_release_setup_lock
    exit "$exit_code"
}
trap cleanup EXIT

show_help() {
    cat <<'USAGE'
Usage: bash scripts/setup/install-dlib.sh [OPTIONS]

Install the optional dlib tracker backend from a pinned, SHA-256-verified source
archive. The build may be slow on ARM. This script never creates or edits swap.

Options:
  --dry-run                    Show the plan without downloads or changes
  --yes                        Accept the displayed build plan
  --skip-system-packages       Do not run apt; require tools to exist already
  --archive <path|https-url>   Expert source-archive override
  --archive-sha256 <digest>    Required digest for an archive override
  --help, -h                   Show this help
USAGE
}

fail() {
    log_error "$1"
    exit 1
}

valid_sha256() {
    [[ "$1" =~ ^[0-9a-fA-F]{64}$ ]]
}

verify_sha256() {
    local path="$1"
    local expected="${2,,}"
    "$VENV_PYTHON" - "$path" "$expected" <<'PY'
import hashlib
import pathlib
import sys

digest = hashlib.sha256()
with pathlib.Path(sys.argv[1]).open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
raise SystemExit(0 if digest.hexdigest() == sys.argv[2] else 1)
PY
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) DRY_RUN=true ;;
            --yes) ASSUME_YES=true ;;
            --skip-system-packages) SKIP_SYSTEM_PACKAGES=true ;;
            --archive)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --archive"
                ARCHIVE_OVERRIDE="$1"
                ;;
            --archive-sha256)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --archive-sha256"
                ARCHIVE_SHA256_OVERRIDE="${1,,}"
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                fail "Unknown option: $1"
                ;;
        esac
        shift
    done
}

check_environment() {
    [[ -x "$VENV_PYTHON" ]] || fail "Missing venv Python: $VENV_PYTHON (run make init)"
    [[ -x "$VENV_PIP" ]] || fail "Missing venv pip: $VENV_PIP (run make init)"

    if [[ -n "$ARCHIVE_OVERRIDE" && -z "$ARCHIVE_SHA256_OVERRIDE" ]]; then
        fail "--archive requires --archive-sha256"
    fi
    if [[ -n "$ARCHIVE_SHA256_OVERRIDE" && -z "$ARCHIVE_OVERRIDE" ]]; then
        fail "--archive-sha256 requires --archive"
    fi
    valid_sha256 "${ARCHIVE_SHA256_OVERRIDE:-$DLIB_ARCHIVE_SHA256}" \
        || fail "A valid source archive SHA-256 is required"

    if [[ "$SKIP_SYSTEM_PACKAGES" == "true" ]]; then
        command -v cmake >/dev/null 2>&1 || fail "cmake is required"
        command -v c++ >/dev/null 2>&1 || fail "A C++ compiler is required"
    elif ! command -v apt-get >/dev/null 2>&1; then
        fail "Automatic prerequisites support Debian/Ubuntu only; install cmake, a C++ compiler, Python headers, and OpenBLAS, then use --skip-system-packages"
    fi
}

print_plan() {
    local source="${ARCHIVE_OVERRIDE:-$DLIB_ARCHIVE_URL}"
    local digest="${ARCHIVE_SHA256_OVERRIDE:-$DLIB_ARCHIVE_SHA256}"
    echo ""
    echo "  PixEagle Optional dlib Plan"
    echo "  ---------------------------"
    echo "  Version:             $DLIB_VERSION"
    echo "  Source:              $source"
    echo "  SHA-256:             $digest"
    echo "  Python environment:  $VENV_DIR"
    if [[ "$SKIP_SYSTEM_PACKAGES" == "true" ]]; then
        echo "  System packages:     verify existing tools only"
    else
        echo "  System packages:     cmake, build-essential, python3-dev, libopenblas-dev"
    fi
    echo "  Swap changes:        never"
    echo ""
}

confirm_plan() {
    [[ "$DRY_RUN" == "true" || "$ASSUME_YES" == "true" ]] && return 0
    local reply
    read -r -p "Build and install optional dlib now? [y/N]: " reply
    [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]
}

install_system_packages() {
    [[ "$SKIP_SYSTEM_PACKAGES" == "true" ]] && return 0
    if ! pixeagle_running_as_root; then
        log_info "Administrator access is required for dlib build prerequisites"
        if ! pixeagle_sudo_validate; then
            fail "$(pixeagle_sudo_failure_message)"
        fi
    fi
    pixeagle_sudo_run apt-get update
    pixeagle_sudo_run apt-get install -y \
        cmake build-essential python3-dev libopenblas-dev
}

resolve_archive() {
    local source="${ARCHIVE_OVERRIDE:-$DLIB_ARCHIVE_URL}"
    local digest="${ARCHIVE_SHA256_OVERRIDE:-$DLIB_ARCHIVE_SHA256}"
    local destination="$TEMP_DIR/dlib-source.tar.gz"

    if [[ -f "$source" ]]; then
        verify_sha256 "$source" "$digest" || fail "dlib archive SHA-256 verification failed"
        printf '%s\n' "$source"
        return 0
    fi
    [[ "$source" =~ ^https:// ]] || fail "Archive must be a local file or HTTPS URL"

    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$source" -o "$destination"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$destination" "$source"
    else
        fail "curl or wget is required to download dlib"
    fi
    verify_sha256 "$destination" "$digest" || fail "Downloaded dlib archive SHA-256 verification failed"
    printf '%s\n' "$destination"
}

install_dlib() {
    TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/pixeagle-dlib.XXXXXX")"
    local archive
    archive="$(resolve_archive)"
    "$VENV_PIP" install --no-deps --no-build-isolation --no-cache-dir "$archive"
    "$VENV_PYTHON" - "$DLIB_VERSION" <<'PY'
import dlib
import sys

version = getattr(dlib, "__version__", "unknown")
if version != sys.argv[1]:
    raise SystemExit(f"Expected dlib {sys.argv[1]}, imported {version}")
tracker = dlib.correlation_tracker()
if tracker is None:
    raise SystemExit("dlib correlation_tracker API is unavailable")
print(f"dlib {version} and correlation_tracker are ready")
PY
}

main() {
    parse_args "$@"
    if ! pixeagle_acquire_setup_lock "$VENV_DIR" "dlib dependency setup" 30; then
        fail "Another PixEagle setup operation is active"
    fi
    check_environment
    print_plan
    if [[ "$DRY_RUN" == "true" ]]; then
        log_success "Dry-run complete; no packages or files were changed"
        return 0
    fi
    if ! confirm_plan; then
        log_info "dlib installation cancelled"
        return 0
    fi
    install_system_packages
    if ! pixeagle_begin_venv_transaction "$VENV_DIR" "dlib dependency setup"; then
        fail "Could not create the exact dlib rollback boundary"
    fi
    install_dlib
    if ! pixeagle_commit_venv_transaction; then
        fail "Could not commit the verified dlib environment"
    fi
    log_success "Optional dlib tracker dependency is ready"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    if pixeagle_setup_lock_context_present; then
        main "$@"
    else
        trap - EXIT
        pixeagle_run_with_setup_lock \
            "$VENV_DIR" "dlib dependency setup" 30 bash "${BASH_SOURCE[0]}" "$@"
    fi
fi

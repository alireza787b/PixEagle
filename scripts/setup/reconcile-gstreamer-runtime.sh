#!/usr/bin/env bash
# One optional runtime reconciliation for setup, update/repair and direct OpenCV builds.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/../lib/common.sh"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/../lib/setup_lock.sh"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/../lib/venv_transaction.sh"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/gstreamer-runtime.env"

mode=install
case "${1:-}" in
    --verify-only) mode=verify ;;
    --dry-run) mode=preview ;;
    "") ;;
    --help|-h)
        echo 'Usage: bash scripts/setup/reconcile-gstreamer-runtime.sh [--verify-only|--dry-run]'
        echo 'Adds optional WebRTC bindings/plugins to the existing PixEagle venv; does not rebuild OpenCV.'
        exit 0 ;;
    *) log_error "Unknown option: $1"; exit 2 ;;
esac
[[ $# -le 1 ]] || { log_error 'Unexpected arguments'; exit 2; }
python="$(resolve_pixeagle_venv_python "$PROJECT_ROOT")"
[[ -x "$python" ]] || { log_error 'Run make init first to create the PixEagle environment'; exit 1; }
probe() { "$python" "$SCRIPT_DIR/check-native-media-runtime.py"; }
if [[ "$mode" == verify ]]; then
    probe
    exit $?
fi
if [[ "$mode" == preview ]]; then
    log_info 'Optional media runtime: distro ICE/DTLS/SRTP/SCTP and H.264/VP8 plugins; isolated Python GI bindings'
    log_info "If no packaged rtpgccbwe exists, build only gst-plugin-rtp $PIXEAGLE_GST_RS_VERSION at $PIXEAGLE_GST_RS_REVISION with Cargo --locked"
    log_detail 'No service, source, engine, network, credential or flight setting is changed.'
    exit 0
fi
venv_dir="$(resolve_pixeagle_venv_dir "$PROJECT_ROOT")"
if ! pixeagle_setup_lock_context_present; then
    pixeagle_run_with_setup_lock "$venv_dir" "optional media runtime setup" 30 bash "${BASH_SOURCE[0]}" "$@"
    exit $?
fi
pixeagle_acquire_setup_lock "$venv_dir" "optional media runtime setup" 30
source_dir=""
plugin_tmp=""
cleanup() {
    local status=$?
    trap - EXIT
    [[ -z "$source_dir" ]] || rm -rf -- "$source_dir"
    [[ -z "$plugin_tmp" ]] || rm -f -- "$plugin_tmp"
    if ! pixeagle_finalize_venv_transaction; then
        log_error 'Optional runtime environment rollback was incomplete'
        status=1
    fi
    pixeagle_release_setup_lock
    exit "$status"
}
trap cleanup EXIT
if probe >/dev/null 2>&1; then
    log_success 'Optional WebRTC runtime already available; reusing it'
    exit 0
fi
if ! command -v apt-get >/dev/null || ! command -v apt-cache >/dev/null; then
    log_error 'Automatic optional runtime installation currently supports Debian-family Linux'
    exit 1
fi
apt_refreshed=false
install_packages() {
    if [[ "$apt_refreshed" == false ]]; then
        pixeagle_sudo_run apt-get update
        apt_refreshed=true
    fi
    pixeagle_sudo_run apt-get install -y "$@"
}

# Missing native dependencies do not disable the established browser/JPEG providers.
packages=(gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good
          gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav
          gstreamer1.0-nice gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0
          gir1.2-gst-plugins-bad-1.0)
missing_packages=()
for package in "${packages[@]}"; do
    if [[ "$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)" != 'install ok installed' ]]; then
        missing_packages+=("$package")
    fi
done
if [[ ${#missing_packages[@]} -gt 0 ]]; then
    log_info 'Installing optional media runtime dependencies'
    install_packages "${missing_packages[@]}"
fi
if ! "$python" -c 'import gi' >/dev/null 2>&1; then
    # Build into this venv. Importing all system dist-packages can shadow application dependencies.
    python_version="$("$python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    python_headers=()
    if ! "$python" -c 'import pathlib, sysconfig; raise SystemExit(not (pathlib.Path(sysconfig.get_path("include")) / "Python.h").is_file())'; then
        python_headers+=("python${python_version}-dev")
    fi
    install_packages build-essential pkg-config libcairo2-dev \
        libgirepository1.0-dev "${python_headers[@]}"
    pixeagle_begin_venv_transaction "$venv_dir" "optional media Python bindings"
    "$python" -m pip install -r "$PROJECT_ROOT/requirements-gstreamer.txt"
fi
if probe >/dev/null 2>&1; then
    pixeagle_commit_venv_transaction
    log_success 'Optional WebRTC runtime ready; product qualification gates still apply'
    exit 0
fi
# Prefer the configured distribution repository to a source build when it provides this plugin.
if command -v gst-inspect-1.0 >/dev/null && ! gst-inspect-1.0 rtpgccbwe >/dev/null 2>&1; then
    if apt-cache show gstreamer1.0-plugins-rs >/dev/null 2>&1; then
        install_packages gstreamer1.0-plugins-rs
    fi
fi
if ! gst-inspect-1.0 rtpgccbwe >/dev/null 2>&1; then
    log_info 'Preparing the pinned congestion-control plugin (one-time optional build)'
    install_packages cargo rustc git pkg-config libssl-dev \
        libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev
    rust_version="$(rustc --version | awk '{print $2}')"
    if ! dpkg --compare-versions "$rust_version" ge "$PIXEAGLE_GST_RUST_MINIMUM"; then
        log_error "Distro Rust $rust_version is older than required $PIXEAGLE_GST_RUST_MINIMUM"
        log_detail 'Browser WebRTC and JPEG remain available. See the optional GStreamer installation guide.'
        exit 1
    fi
    venv_root="$("$python" -c 'import sys; print(sys.prefix)')"
    cache_root="${XDG_CACHE_HOME:-$HOME/.cache}/pixeagle/gstreamer/$PIXEAGLE_GST_RS_REVISION/$(uname -m)"
    [[ "$cache_root" == /* ]] || { log_error 'XDG_CACHE_HOME must be absolute'; exit 1; }
    mkdir -p "$cache_root"
    # A disposable checkout cannot overwrite an existing user's source clone.
    source_dir="$(mktemp -d "$cache_root/source.XXXXXX")"
    git -C "$source_dir" init -q
    git -C "$source_dir" fetch -q --depth 1 "$PIXEAGLE_GST_RS_REPOSITORY" "$PIXEAGLE_GST_RS_REVISION"
    git -C "$source_dir" checkout -q --detach FETCH_HEAD
    [[ "$(git -C "$source_dir" rev-parse HEAD)" == "$PIXEAGLE_GST_RS_REVISION" ]] || exit 1
    # Keep Cargo.lock intact. Two jobs bound memory/thermal pressure on companion computers.
    CARGO_TARGET_DIR="$cache_root/target" cargo build --locked --release --jobs 2 \
        --manifest-path "$source_dir/Cargo.toml" -p gst-plugin-rtp
    pixeagle_begin_venv_transaction "$venv_dir" "optional media plugin installation"
    plugin_dir="$venv_root/lib/gstreamer-1.0"
    mkdir -p "$plugin_dir"
    plugin_tmp="$(mktemp "$plugin_dir/.libgstrsrtp.XXXXXX")"
    install -m 0644 "$cache_root/target/release/libgstrsrtp.so" "$plugin_tmp"
    mv -f -- "$plugin_tmp" "$plugin_dir/libgstrsrtp.so"
fi
if ! probe; then
    log_error 'Optional native media runtime is incomplete; existing browser WebRTC/JPEG remain available'
    exit 1
fi
pixeagle_commit_venv_transaction
log_success 'Optional WebRTC runtime ready; no additional operator configuration is required'

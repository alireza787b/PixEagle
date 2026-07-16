#!/usr/bin/env bash

# ============================================================================
# scripts/setup/build-opencv.sh - Build OpenCV with GStreamer Support
# ============================================================================
# This script builds OpenCV from source with GStreamer support.
#
# Features:
#   - Professional UX with progress indicators and colors
#   - Pre-flight checks (disk space, RAM, dependencies)
#   - Explicit opt-in temporary swap on low-memory systems (cleaned up after build)
#   - Memory-aware parallelism (2-2.5GB per job based on RAM, CUDA-aware)
#   - Platform auto-detection: Jetson (CUDA), Raspberry Pi (NEON), ARM, x86
#   - GStreamer support for video input and QGC/GCS output
#   - Headless companion build by default; optional GTK/OpenGL with OPENCV_GUI=1
#   - Deferred replacement and automatic rollback of the active OpenCV runtime
#   - Installs into PixEagle virtual environment
#   - Verifies GStreamer support after build
#
# Requirements:
#   - Debian-based Linux (Ubuntu, Raspberry Pi OS, Jetson)
#   - 10GB+ free disk space
#   - 2GB+ RAM (6GB RAM+swap for the build; 8GB+ RAM recommended)
#   - 1-2 hours build time (depends on CPU cores and memory)
#
# Usage: bash scripts/setup/build-opencv.sh [-h|--help] [-v|--version]
#
# Author: Alireza Ghaderi
# Version: 3.0.0
# License: MIT
# ============================================================================

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================
TOTAL_STEPS=9
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
OPENCV_VERSION="4.13.0"
OPENCV_SOURCE_COMMIT="fe38fc608f6acb8b68953438a62305d8318f4fcd"
OPENCV_CONTRIB_SOURCE_COMMIT="d99ad2a188210cc35067c2e60076eed7c2442bc3"
OPENCV_EXPECTED_ARCHIVE_SHA256="a422fc0ce3ee59a4b970ce1c5e8849ac9d6940be4a431960e13f7181f0e955e7"
OPENCV_EXPECTED_TREE_SHA256="d5d748793ff5357e36932a1c2e851df4ef68575c97653128ef67279b0b22d570"
OPENCV_CONTRIB_EXPECTED_ARCHIVE_SHA256="3fc521a16314978de02d5b33e657a09a9567429d5801d3fb94e35581ea44d729"
OPENCV_CONTRIB_EXPECTED_TREE_SHA256="920a1c5aaaa62f7b5110b85043cc4120079e5a5af9865fab59208cce6259f7bd"
REQUIRED_DISK_GB=10
REQUIRED_RAM_GB=2
VERSION="3.0.0"
OPENCV_GUI="${OPENCV_GUI:-0}"
OPENCV_ALLOW_TEMP_SWAP="${OPENCV_ALLOW_TEMP_SWAP:-0}"
REPORT_JSON=""
REPORT_STATUS="not_started"
REPORT_ERROR=""
RUNTIME_EVIDENCE='{}'
SOURCE_EVIDENCE='{}'
BUILD_EVIDENCE='{}'
OPENCV_WORK_ROOT=""
OPENCV_WORK_IDENTITY=""
OPENCV_SOURCE_DIR=""
OPENCV_CONTRIB_SOURCE_DIR=""
OPENCV_BUILD_DIR=""
OPENCV_DOWNLOAD_DIR=""
OPENCV_HOOKS_DIR=""
OPENCV_EMPTY_TEMPLATE_DIR=""
OPENCV_SOURCE_TREE_SHA256=""
OPENCV_CONTRIB_SOURCE_TREE_SHA256=""
OPENCV_SOURCE_ARCHIVE_SHA256=""
OPENCV_CONTRIB_SOURCE_ARCHIVE_SHA256=""
OPENCV_SOURCE_TAG_OBJECT=""
OPENCV_CONTRIB_SOURCE_TAG_OBJECT=""
OPENCV_WORK_CLEANUP_STATUS="not_created"

# Source shared functions with fallback
# shellcheck source=/dev/null
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
    # Symbols
    CHECK="[✓]"; WARN="[!]"; VIDEO="[Video]"; CLOCK="[time]"; PARTY=""
    log_info() { echo -e "   ${CYAN}[*]${NC} $1"; }
    log_success() { echo -e "   ${GREEN}[✓]${NC} $1"; }
    log_warn() { echo -e "   ${YELLOW}[!]${NC} $1"; }
    log_error() { echo -e "   ${RED}[✗]${NC} $1"; }
    log_step() { echo -e "\n${CYAN}━━━ Step $1/${TOTAL_STEPS}: $2 ━━━${NC}"; }
    log_detail() { echo -e "      ${DIM}$1${NC}"; }
    display_pixeagle_banner() {
        echo -e "\n${CYAN}${BOLD}PixEagle${NC}"
        [[ -n "${1:-}" ]] && echo -e "  ${BOLD}$1${NC}"
        [[ -n "${2:-}" ]] && echo -e "  ${DIM}$2${NC}"
        echo ""
    }
fi
# shellcheck source=/dev/null
if ! source "$SCRIPTS_DIR/lib/setup_lock.sh" 2>/dev/null; then
    echo "Error: Could not source the required setup lock helper" >&2
    exit 1
fi

if declare -F resolve_pixeagle_venv_dir >/dev/null 2>&1; then
    VENV_DIR="$(resolve_pixeagle_venv_dir "$PIXEAGLE_DIR")"
else
    VENV_DIR="${PIXEAGLE_VENV_DIR:-$PIXEAGLE_DIR/venv}"
fi

# ============================================================================
# Spinner for Long Operations
# ============================================================================
spinner_pid=""

start_spinner() {
    local msg="$1"
    local chars="⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    (
        while true; do
            for ((i=0; i<${#chars}; i++)); do
                printf "\r        ${CYAN}%s${NC} %s" "${chars:$i:1}" "$msg"
                sleep 0.1
            done
        done
    ) &
    spinner_pid=$!
}

stop_spinner() {
    if [[ -n "$spinner_pid" ]]; then
        kill "$spinner_pid" 2>/dev/null
        wait "$spinner_pid" 2>/dev/null || true
        spinner_pid=""
        printf "\r        \033[K"
    fi
}

TEMP_SWAP_FILE=""
TEMP_SWAP_FD=""
TEMP_SWAP_FD_PATH=""
TEMP_SWAP_ACTIVE=false
OPENCV_BACKUP_DIR=""
OPENCV_BACKUP_IDENTITY=""
OPENCV_STAGE_DIR=""
OPENCV_REPLACEMENT_STARTED=false
OPENCV_REPLACEMENT_COMMITTED=false

assert_temp_swap_descriptor() {
    if [[ ! "$TEMP_SWAP_FD" =~ ^[0-9]+$ ]] || [[ -z "$TEMP_SWAP_FD_PATH" ]]; then
        log_error "Temporary swap descriptor is not open"
        return 1
    fi

    local descriptor_uid descriptor_mode descriptor_links
    IFS='|' read -r descriptor_uid descriptor_mode descriptor_links < <(
        LC_ALL=C stat -Lc '%u|%a|%h' -- "$TEMP_SWAP_FD_PATH" 2>/dev/null
    )
    if [[ ! -f "$TEMP_SWAP_FD_PATH" ]] \
        || [[ "$descriptor_uid" != "$(id -u)" ]] \
        || [[ "$descriptor_mode" != "600" ]] \
        || [[ "$descriptor_links" != "1" ]]; then
        log_error "Temporary swap descriptor failed owner/type/mode/link validation"
        return 1
    fi
}

cleanup_temp_swap() {
    local descriptor_valid=false
    if assert_temp_swap_descriptor; then
        descriptor_valid=true
    fi

    if [[ "$TEMP_SWAP_ACTIVE" == true ]]; then
        if [[ "$descriptor_valid" != true ]] || ! sudo swapoff -- "$TEMP_SWAP_FD_PATH" 2>/dev/null; then
            log_error "Could not deactivate the temporary OpenCV swap file"
            return 1
        fi
        TEMP_SWAP_ACTIVE=false
    fi

    if [[ -n "$TEMP_SWAP_FILE" && -e "$TEMP_SWAP_FILE" ]]; then
        if [[ "$descriptor_valid" == true && "$TEMP_SWAP_FILE" -ef "$TEMP_SWAP_FD_PATH" ]]; then
            rm -f -- "$TEMP_SWAP_FILE"
        else
            log_warn "Refusing to remove a replaced temporary swap path: $TEMP_SWAP_FILE"
        fi
    fi

    if [[ "$TEMP_SWAP_FD" =~ ^[0-9]+$ ]]; then
        exec {TEMP_SWAP_FD}>&-
    fi
    TEMP_SWAP_FILE=""
    TEMP_SWAP_FD=""
    TEMP_SWAP_FD_PATH=""
}

create_temp_swap_backing_file() {
    local swap_dir="${1:-/var/tmp}"
    if [[ ! -d "$swap_dir" ]]; then
        log_error "Temporary swap directory does not exist: $swap_dir"
        return 1
    fi

    local previous_umask
    previous_umask="$(umask)"
    umask 077
    if ! TEMP_SWAP_FILE="$(mktemp -- "$swap_dir/pixeagle-opencv-swap.XXXXXX")"; then
        umask "$previous_umask"
        log_error "Could not create a private temporary swap file"
        return 1
    fi
    umask "$previous_umask"

    if ! chmod 600 -- "$TEMP_SWAP_FILE" || ! exec {TEMP_SWAP_FD}<>"$TEMP_SWAP_FILE"; then
        rm -f -- "$TEMP_SWAP_FILE"
        TEMP_SWAP_FILE=""
        TEMP_SWAP_FD=""
        log_error "Could not secure the temporary swap file"
        return 1
    fi
    TEMP_SWAP_FD_PATH="/proc/$$/fd/$TEMP_SWAP_FD"

    if ! assert_temp_swap_descriptor || [[ ! "$TEMP_SWAP_FILE" -ef "$TEMP_SWAP_FD_PATH" ]]; then
        cleanup_temp_swap || true
        log_error "Temporary swap file identity validation failed"
        return 1
    fi
}

is_safe_relative_install_path() {
    local relative_path="$1"
    [[ -n "$relative_path" && "$relative_path" != /* && "$relative_path" != */ ]] || return 1
    [[ "$relative_path" != *//* ]] || return 1

    local component
    local -a components=()
    IFS='/' read -r -a components <<< "$relative_path"
    for component in "${components[@]}"; do
        [[ -n "$component" && "$component" != "." && "$component" != ".." ]] || return 1
    done
}

assert_venv_destination_path() {
    local destination="$1"
    local relative_path
    case "$destination" in
        "$VENV_DIR"/*)
            relative_path="${destination#"$VENV_DIR"/}"
            ;;
        *)
            log_error "OpenCV destination is outside the selected venv: $destination"
            return 1
            ;;
    esac
    if ! is_safe_relative_install_path "$relative_path"; then
        log_error "OpenCV destination contains an unsafe venv-relative path: $destination"
        return 1
    fi

    local probe="$destination"
    local parent
    while [[ ! -e "$probe" && ! -L "$probe" ]]; do
        parent=$(dirname "$probe")
        if [[ "$parent" == "$probe" ]]; then
            log_error "Could not resolve an existing ancestor for OpenCV destination: $destination"
            return 1
        fi
        probe="$parent"
    done

    local canonical_probe
    canonical_probe=$(realpath -e -- "$probe" 2>/dev/null || true)
    case "$canonical_probe" in
        "$VENV_DIR"|"$VENV_DIR"/*) return 0 ;;
        *)
            log_error "OpenCV destination resolves outside the selected venv: $destination"
            return 1
            ;;
    esac
}

remove_existing_opencv_artifacts() {
    local site_packages="$1"
    local removal_failed=false
    local path
    local -a paths=()

    shopt -s nullglob
    paths=(
        "$site_packages/cv2"
        "$site_packages"/cv2*.so
        "$site_packages"/opencv*.dist-info
        "$site_packages"/opencv*.egg-info
        "$site_packages"/opencv*.libs
        "$VENV_DIR/include/opencv4"
        "$VENV_DIR/share/opencv4"
        "$VENV_DIR/share/OpenCV"
        "$VENV_DIR/share/licenses/opencv4"
        "$VENV_DIR/lib/cmake/opencv4"
        "$VENV_DIR/lib/pkgconfig/opencv4.pc"
        "$VENV_DIR/lib"/libopencv*
        "$VENV_DIR/bin"/opencv_*
    )
    shopt -u nullglob

    for path in "${paths[@]}"; do
        if ! assert_venv_destination_path "$path"; then
            removal_failed=true
            continue
        fi
        if ! rm -rf -- "$path" 2>/dev/null; then
            log_error "Could not remove the previous OpenCV artifact: $path"
            removal_failed=true
            continue
        fi
        if [[ -e "$path" || -L "$path" ]]; then
            log_error "Previous OpenCV artifact remains after removal: $path"
            removal_failed=true
        fi
    done

    [[ "$removal_failed" == false ]]
}

assert_opencv_backup_dir() {
    [[ -n "$OPENCV_BACKUP_DIR" ]] || return 1
    case "$OPENCV_BACKUP_DIR" in
        /var/tmp/pixeagle-opencv-backup.[A-Za-z0-9]*) ;;
        *) return 1 ;;
    esac
    [[ -d "$OPENCV_BACKUP_DIR" && ! -L "$OPENCV_BACKUP_DIR" ]] || return 1
    [[ "$(stat -Lc '%d:%i:%u:%a' -- "$OPENCV_BACKUP_DIR" 2>/dev/null || true)" == \
        "$OPENCV_BACKUP_IDENTITY" ]]
}

remove_opencv_backup_dir() {
    [[ -n "$OPENCV_BACKUP_DIR" ]] || return 0
    if ! assert_opencv_backup_dir; then
        log_error "Refusing to remove an OpenCV rollback directory whose identity changed"
        return 1
    fi
    rm -rf -- "$OPENCV_BACKUP_DIR" || return 1
    [[ ! -e "$OPENCV_BACKUP_DIR" && ! -L "$OPENCV_BACKUP_DIR" ]] || return 1
    OPENCV_BACKUP_DIR=""
    OPENCV_BACKUP_IDENTITY=""
}

restore_previous_opencv() {
    [[ "$OPENCV_REPLACEMENT_STARTED" == true ]] || return 0
    [[ "$OPENCV_REPLACEMENT_COMMITTED" == false ]] || return 0
    if ! assert_opencv_backup_dir; then
        log_error "OpenCV rollback directory failed identity validation"
        return 1
    fi

    log_warn "Restoring the previous OpenCV runtime after an incomplete replacement..."
    local site_packages
    site_packages=$("$VENV_DIR/bin/python" -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null || true)
    site_packages=$(realpath -e -- "$site_packages" 2>/dev/null || true)
    if [[ -z "$site_packages" ]] || ! assert_venv_destination_path "$site_packages"; then
        log_error "Could not resolve site-packages for OpenCV rollback"
        return 1
    fi

    local restore_failed=false
    local install_targets="$OPENCV_BACKUP_DIR/install-targets.txt"
    if [[ -f "$install_targets" ]]; then
        while IFS= read -r installed_path; do
            case "$installed_path" in
                "$VENV_DIR"/*)
                    if ! assert_venv_destination_path "$installed_path"; then
                        restore_failed=true
                        continue
                    fi
                    if [[ -d "$installed_path" && ! -L "$installed_path" ]]; then
                        if ! rmdir -- "$installed_path" 2>/dev/null; then
                            log_error "Could not remove replacement directory during rollback: $installed_path"
                            restore_failed=true
                        fi
                    elif ! rm -f -- "$installed_path" 2>/dev/null; then
                        log_error "Could not remove replacement path during rollback: $installed_path"
                        restore_failed=true
                    fi
                    ;;
            esac
        done < "$install_targets"
    fi

    local path
    shopt -s nullglob
    for path in "$site_packages/cv2" "$site_packages"/cv2*.so \
        "$site_packages"/opencv*.dist-info "$site_packages"/opencv*.egg-info \
        "$site_packages"/opencv*.libs; do
        if ! rm -rf -- "$path" 2>/dev/null; then
            log_error "Could not remove replacement OpenCV artifact during rollback: $path"
            restore_failed=true
        fi
    done
    for path in "$VENV_DIR/lib"/libopencv*; do
        if ! rm -f -- "$path" 2>/dev/null; then
            log_error "Could not remove replacement OpenCV library during rollback: $path"
            restore_failed=true
        fi
    done
    shopt -u nullglob

    if [[ -d "$OPENCV_BACKUP_DIR/site-packages" ]]; then
        if ! cp -a "$OPENCV_BACKUP_DIR/site-packages/." "$site_packages/"; then
            log_error "Could not restore backed-up OpenCV site-packages artifacts"
            restore_failed=true
        fi
    fi
    if [[ -d "$OPENCV_BACKUP_DIR/lib" ]]; then
        if ! cp -a "$OPENCV_BACKUP_DIR/lib/." "$VENV_DIR/lib/"; then
            log_error "Could not restore backed-up OpenCV libraries"
            restore_failed=true
        fi
    fi
    if [[ -d "$OPENCV_BACKUP_DIR/manifest" ]]; then
        if ! cp -a "$OPENCV_BACKUP_DIR/manifest/." "$VENV_DIR/"; then
            log_error "Could not restore pre-existing OpenCV install-manifest targets"
            restore_failed=true
        fi
    fi
    if [[ -d "$OPENCV_BACKUP_DIR/venv-layout" ]]; then
        if ! cp -a "$OPENCV_BACKUP_DIR/venv-layout/." "$VENV_DIR/"; then
            log_error "Could not restore the previous native OpenCV venv layout"
            restore_failed=true
        fi
    fi
    if [[ "$restore_failed" == true ]]; then
        log_error "OpenCV rollback was incomplete; preserving backup at $OPENCV_BACKUP_DIR"
        return 1
    fi
    log_success "Previous OpenCV runtime restored"
}

write_report_json() {
    local exit_code="$1"
    [[ -n "$REPORT_JSON" ]] || return 0

    python3 - "$REPORT_JSON" "$exit_code" "$REPORT_STATUS" "$REPORT_ERROR" \
        "$PIXEAGLE_DIR" "$SCRIPT_DIR" "$VENV_DIR" "$OPENCV_VERSION" \
        "$OPENCV_SOURCE_COMMIT" "$OPENCV_CONTRIB_SOURCE_COMMIT" "$VERSION" \
        "$OPENCV_GUI" "${OPENCV_CUDA:-0}" "${OPENCV_DNN_CUDA:-0}" \
        "$OPENCV_WORK_CLEANUP_STATUS" "$OPENCV_WORK_ROOT" \
        3<<<"$RUNTIME_EVIDENCE" 4<<<"$SOURCE_EVIDENCE" \
        5<<<"$BUILD_EVIDENCE" <<'PY'
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    report_path_raw,
    exit_code_raw,
    status,
    error,
    root_raw,
    script_dir_raw,
    venv_raw,
    opencv_version,
    opencv_commit,
    contrib_commit,
    builder_version,
    gui_raw,
    cuda_raw,
    dnn_cuda_raw,
    work_cleanup_status,
    work_root_raw,
) = sys.argv[1:]
runtime_raw = os.fdopen(3, encoding="utf-8").read()
source_raw = os.fdopen(4, encoding="utf-8").read()
build_raw = os.fdopen(5, encoding="utf-8").read()
sys.path.insert(0, script_dir_raw)
from evidence_path import atomic_write_json


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_evidence(path):
    path = Path(path).resolve()
    if not path.is_file():
        return None
    return {"path": str(path), "size": path.stat().st_size, "sha256": sha256_file(path)}


def command_version(*command):
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return output[0] if completed.returncode == 0 and output else None


try:
    runtime = json.loads(runtime_raw) if runtime_raw else {}
except json.JSONDecodeError:
    runtime = {"unparsed": runtime_raw}
try:
    sources = json.loads(source_raw) if source_raw else {}
except json.JSONDecodeError:
    sources = {"unparsed": source_raw}
try:
    build_evidence = json.loads(build_raw) if build_raw else {}
except json.JSONDecodeError:
    build_evidence = {"unparsed": build_raw}

root = Path(root_raw).resolve()
inputs = {}
for path in (root / "scripts/setup/build-opencv.sh",):
    evidence = file_evidence(path)
    if evidence:
        inputs[str(path)] = evidence

payload = {
    "schema_version": 2,
    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "status": status,
    "exit_code": int(exit_code_raw),
    "error": error or None,
    "builder_version": builder_version,
    "selection": {
        "venv": str(Path(venv_raw).resolve()),
        "opencv_version": opencv_version,
        "gstreamer_required": True,
        "gui": gui_raw == "1",
        "cuda": cuda_raw == "1",
        "dnn_cuda": dnn_cuda_raw == "1",
    },
    "sources": sources,
    "reproducibility": {
        "fully_reproducible": False,
        "source_selection": "transient bare tag fetch, pinned commit verification, and validated archive export",
        "unlocked_inputs": [
            "Debian packages and native GStreamer/FFmpeg libraries",
            "compiler, CMake, linker, and host toolchain",
            "NumPy and the pre-existing Core Python environment",
        ],
        "claim": (
            "Pinned source commits plus a runtime fingerprint provide provenance, "
            "not a byte-reproducible build or signed source-artifact attestation."
        ),
    },
    "host": {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cmake": command_version("cmake", "--version"),
        "compiler": command_version("c++", "--version"),
        "gstreamer": command_version("pkg-config", "--modversion", "gstreamer-1.0"),
    },
    "inputs": inputs,
    "build_evidence": build_evidence,
    "work_root_cleanup": work_cleanup_status,
    "installed_runtime": runtime,
}

report_path = Path(report_path_raw).expanduser().absolute()
if work_root_raw:
    work_root = Path(work_root_raw).resolve()
    if report_path == work_root or work_root in report_path.parents:
        raise SystemExit("OpenCV evidence path must be outside the transient work root")
atomic_write_json(str(report_path), payload)
PY

    log_info "Wrote OpenCV build evidence: $REPORT_JSON"
}

collect_opencv_build_evidence() {
    [[ -n "$OPENCV_WORK_ROOT" && -d "$OPENCV_WORK_ROOT" ]] || {
        BUILD_EVIDENCE='{}'
        return 0
    }
    BUILD_EVIDENCE="$(python3 - "$OPENCV_WORK_ROOT" "$OPENCV_BUILD_DIR" \
        "$OPENCV_DOWNLOAD_DIR" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

work_root = Path(sys.argv[1]).resolve(strict=True)
build_dir = Path(sys.argv[2]).resolve(strict=True)
download_dir = Path(sys.argv[3]).resolve(strict=True)


def evidence(path: Path):
    resolved = path.resolve(strict=True)
    if work_root not in resolved.parents:
        raise SystemExit(f"evidence path escaped work root: {resolved}")
    digest = hashlib.sha256()
    size = 0
    with resolved.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    if size != resolved.stat().st_size:
        raise SystemExit(f"evidence input changed while hashing: {resolved}")
    return {
        "path": resolved.relative_to(work_root).as_posix(),
        "size": size,
        "sha256": digest.hexdigest(),
    }


build_files = []
for name in ("CMakeCache.txt", "cmake_output.log", "build_output.log", "install_manifest.txt"):
    path = build_dir / name
    if path.is_file() and not path.is_symlink():
        build_files.append(evidence(path))

downloads = []
for path in sorted(download_dir.rglob("*")):
    if path.is_file() and not path.is_symlink():
        downloads.append(evidence(path))
        if len(downloads) > 10_000:
            raise SystemExit("OpenCV download evidence exceeded entry bound")

print(json.dumps({
    "build_files": build_files,
    "downloads": downloads,
    "download_manifest_scope": "regular files in the private OpenCV download cache",
}, sort_keys=True, separators=(",", ":")))
PY
)"
}

cleanup() {
    stop_spinner
    local cleanup_succeeded=true
    if ! restore_previous_opencv; then
        cleanup_succeeded=false
    fi
    if [[ -n "$OPENCV_BACKUP_DIR" ]]; then
        if [[ "$OPENCV_REPLACEMENT_COMMITTED" == true || "$cleanup_succeeded" == true ]]; then
            if ! remove_opencv_backup_dir; then
                cleanup_succeeded=false
            fi
        else
            log_error "Retained OpenCV recovery backup: $OPENCV_BACKUP_DIR"
        fi
    fi
    # Remove temporary swap if we created one.
    if [[ -n "$TEMP_SWAP_FILE" || "$TEMP_SWAP_FD" =~ ^[0-9]+$ ]]; then
        log_info "Cleaning up temporary swap file..."
        if cleanup_temp_swap; then
            log_success "Temporary swap removed"
        else
            cleanup_succeeded=false
        fi
    fi
    if ! collect_opencv_build_evidence; then
        log_error "Could not collect bounded OpenCV build evidence before cleanup"
        cleanup_succeeded=false
    fi
    if ! remove_opencv_work_root; then
        cleanup_succeeded=false
    fi
    OPENCV_STAGE_DIR=""
    [[ "$cleanup_succeeded" == true ]]
}

on_exit() {
    local exit_code=$?
    trap - EXIT
    if [[ "$exit_code" -ne 0 && "$REPORT_STATUS" != "failed" \
        && "$REPORT_STATUS" != "interrupted" ]]; then
        REPORT_STATUS="failed"
        REPORT_ERROR="${REPORT_ERROR:-builder exited with code $exit_code}"
    fi
    if [[ "$exit_code" -eq 0 && "$REPORT_STATUS" == "running" ]]; then
        REPORT_STATUS="failed"
        REPORT_ERROR="builder exited without a terminal status"
        exit_code=1
    fi
    if ! cleanup; then
        [[ "$exit_code" -ne 0 ]] || exit_code=1
        if [[ "$REPORT_STATUS" == "success" && "$OPENCV_REPLACEMENT_COMMITTED" == true ]]; then
            REPORT_STATUS="installed_cleanup_failed"
            REPORT_ERROR="verified OpenCV runtime was retained, but post-build cleanup was incomplete"
            log_error "$REPORT_ERROR"
        elif [[ "$REPORT_STATUS" == "success" ]]; then
            REPORT_STATUS="failed"
            REPORT_ERROR="post-build cleanup was incomplete before commit"
        fi
    fi
    if ! write_report_json "$exit_code"; then
        if [[ "$OPENCV_REPLACEMENT_COMMITTED" == true ]]; then
            REPORT_STATUS="installed_evidence_failed"
            REPORT_ERROR="verified OpenCV runtime was committed, but evidence publication failed"
            log_error "$REPORT_ERROR: $REPORT_JSON"
            log_error "The installed runtime was retained; this failure does not mean rollback occurred"
            exit_code=74
        else
            log_error "Could not write requested OpenCV build evidence: $REPORT_JSON"
            [[ "$exit_code" -ne 0 ]] || exit_code=1
        fi
    fi
    pixeagle_release_setup_lock
    exit "$exit_code"
}
trap on_exit EXIT
opencv_interrupted() {
    local signal_name="$1"
    local exit_code="$2"
    REPORT_STATUS="interrupted"
    REPORT_ERROR="builder interrupted by $signal_name"
    exit "$exit_code"
}
trap 'opencv_interrupted INT 130' INT
trap 'opencv_interrupted TERM 143' TERM
trap 'opencv_interrupted HUP 129' HUP

# ============================================================================
# Banner Display
# ============================================================================
display_banner() {
    display_pixeagle_banner "${VIDEO} OpenCV Build with GStreamer" \
        "Builds OpenCV ${OPENCV_VERSION} with GStreamer support"

    # Warning about build time
    echo -e "   ${YELLOW}${WARN}${NC}  ${BOLD}This build takes 1-2 hours.${NC} Ensure you have:"
    echo -e "       • ${REQUIRED_DISK_GB}GB+ free disk space"
    echo -e "       • ${REQUIRED_RAM_GB}GB+ RAM and 6GB+ RAM+swap (8GB+ RAM recommended)"
    echo -e "       • Stable internet connection"
    echo -e "       • Power supply (for laptops)"
    echo ""
}

# ============================================================================
# Parse Arguments
# ============================================================================
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                echo "Usage: bash scripts/setup/build-opencv.sh [OPTIONS]"
                echo ""
                echo "Build OpenCV ${OPENCV_VERSION} with GStreamer support for PixEagle."
                echo ""
                echo "Options:"
                echo "  -h, --help          Show this help message"
                echo "  -v, --version       Show script version"
                echo "  --skip-confirm      Skip confirmation prompts"
                echo "  --report-json PATH  Write owner-only build/runtime evidence JSON"
                echo ""
                echo "Environment:"
                echo "  OPENCV_GUI=1             Also build GTK/OpenGL desktop display support"
                echo "  OPENCV_ALLOW_TEMP_SWAP=1 Allow a temporary swap file below 6GB RAM+swap"
                echo ""
                echo "Requirements:"
                echo "  - ${REQUIRED_DISK_GB}GB+ free disk space"
                echo "  - ${REQUIRED_RAM_GB}GB+ RAM"
                echo "  - 1-2 hours build time"
                echo ""
                echo "This builder requires GStreamer. The Core contrib wheel is the"
                echo "explicit non-GStreamer fallback; no fallback is installed implicitly."
                exit 0
                ;;
            -v|--version)
                echo "build-opencv.sh version $VERSION"
                exit 0
                ;;
            --skip-confirm)
                SKIP_CONFIRM=true
                shift
                ;;
            --report-json)
                shift
                [[ $# -gt 0 ]] || {
                    REPORT_STATUS="failed"
                    REPORT_ERROR="Missing value for --report-json"
                    log_error "$REPORT_ERROR"
                    exit 2
                }
                REPORT_JSON="$1"
                shift
                ;;
            *)
                REPORT_STATUS="failed"
                REPORT_ERROR="Unknown option: $1"
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

SKIP_CONFIRM=false

# ============================================================================
# Explicit Temporary Swap Management
# ============================================================================
# Creates a temporary swap file only when total memory (RAM+swap) is below 6GB
# and the operator explicitly sets OPENCV_ALLOW_TEMP_SWAP=1.
# The swap is a safety net against OOM-kill, NOT a performance tool — actual
# build parallelism is calculated from RAM only (see compile_opencv).
# Cleaned up automatically on exit (success, failure, Ctrl-C) via trap.
#
# Design decisions:
#   - Never changes swap unless the operator opts in
#   - Swap size calculated dynamically (target: 6GB total RAM+swap)
#   - Uses /var/tmp so the file persists if the script is interrupted
#   - Requires sudo (already acquired for apt-get earlier in the flow)
ensure_build_memory() {
    local total_ram_mb
    total_ram_mb=$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}')
    local existing_swap_mb
    existing_swap_mb=$(free -m 2>/dev/null | awk '/^Swap:/ {print $2}')
    local total_mb=$((total_ram_mb + existing_swap_mb))

    # Target: RAM + swap should be at least 6GB total.  This ensures the OOM
    # killer stays away even if a few GCC processes spike simultaneously.
    # The actual parallelism is capped by RAM (see compile_opencv), so this
    # swap is a safety net, not a performance boost.
    local target_mb=6000

    if [[ $total_mb -ge $target_mb ]]; then
        return 0  # Already enough memory
    fi

    log_warn "Only ${total_mb}MB usable memory (${total_ram_mb}MB RAM + ${existing_swap_mb}MB swap)"
    if [[ "$OPENCV_ALLOW_TEMP_SWAP" != "1" ]]; then
        log_error "OpenCV build requires at least ${target_mb}MB RAM+swap"
        log_detail "Provision swap yourself, or explicitly allow a temporary file with:"
        log_detail "OPENCV_ALLOW_TEMP_SWAP=1 bash scripts/setup/build-opencv.sh"
        return 1
    fi

    local needed_mb=$((target_mb - total_mb))
    # Round up to nearest 512MB for filesystem alignment
    needed_mb=$(( ((needed_mb + 511) / 512) * 512 ))

    log_info "Creating ${needed_mb}MB temporary swap to prevent OOM during build..."

    if ! create_temp_swap_backing_file /var/tmp; then
        return 1
    fi

    # The descriptor pins the mktemp-created inode across all privileged work.
    # fallocate is fast and preferred; dd is the fallback for older kernels/fs.
    if fallocate -l "${needed_mb}M" "$TEMP_SWAP_FD_PATH" 2>/dev/null; then
        : # success
    elif dd if=/dev/zero of="$TEMP_SWAP_FD_PATH" bs=1M count="$needed_mb" status=none 2>/dev/null; then
        : # success via dd
    else
        log_error "Could not create the explicitly requested temporary swap file"
        cleanup_temp_swap || true
        return 1
    fi

    if ! assert_temp_swap_descriptor; then
        cleanup_temp_swap || true
        return 1
    fi
    if mkswap "$TEMP_SWAP_FD_PATH" >/dev/null 2>&1 \
        && sudo swapon -- "$TEMP_SWAP_FD_PATH" 2>/dev/null; then
        TEMP_SWAP_ACTIVE=true
        local new_swap_mb
        new_swap_mb=$(free -m 2>/dev/null | awk '/^Swap:/ {print $2}')
        local new_total=$((total_ram_mb + new_swap_mb))
        log_success "Temporary swap active — now ${new_total}MB usable (will be removed after build)"
    else
        log_error "Could not activate the explicitly requested temporary swap file"
        cleanup_temp_swap || true
        return 1
    fi
}

# ============================================================================
# Platform Detection
# ============================================================================
# Detect Jetson, Raspberry Pi, or generic ARM vs x86
detect_platform() {
    PLATFORM="generic"
    ARCH="$(uname -m)"
    HAS_CUDA=false
    IS_JETSON=false
    IS_RPI=false

    # Detect NVIDIA Jetson (Nano, TX2, Xavier, Orin)
    if [[ -f /etc/nv_tegra_release ]] || [[ -d /usr/local/cuda ]] && [[ "$ARCH" == "aarch64" ]]; then
        IS_JETSON=true
        HAS_CUDA=true
        PLATFORM="jetson"
        # Detect Jetson model for CUDA arch
        CUDA_ARCH=""
        if grep -qi "nano" /proc/device-tree/model 2>/dev/null; then
            CUDA_ARCH="5.3"      # Maxwell (Nano)
        elif grep -qi "tx2" /proc/device-tree/model 2>/dev/null; then
            CUDA_ARCH="6.2"      # Pascal (TX2)
        elif grep -qi "xavier" /proc/device-tree/model 2>/dev/null; then
            CUDA_ARCH="7.2"      # Volta (Xavier NX/AGX)
        elif grep -qi "orin" /proc/device-tree/model 2>/dev/null; then
            CUDA_ARCH="8.7"      # Ampere (Orin)
        else
            CUDA_ARCH="5.3"      # Safe default for unknown Jetson
        fi
    # Detect Raspberry Pi
    elif grep -qi "raspberry" /proc/device-tree/model 2>/dev/null; then
        IS_RPI=true
        PLATFORM="rpi"
    # Detect generic ARM
    elif [[ "$ARCH" == "aarch64" ]] || [[ "$ARCH" == "armv7l" ]]; then
        PLATFORM="arm"
    fi
}

# ============================================================================
# Sudo Password Prompt
# ============================================================================
prompt_sudo() {
    echo ""
    echo -e "${YELLOW}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║${NC}                                                                          ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}   ${BOLD}🔐 SUDO PASSWORD REQUIRED${NC}                                              ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}                                                                          ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}   System packages need to be installed. Please enter your password       ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}   when prompted below.                                                   ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}                                                                          ${YELLOW}║${NC}"
    echo -e "${YELLOW}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    if ! sudo -v; then
        log_error "Failed to authenticate. Please try again."
        exit 1
    fi
    echo ""
}

# ============================================================================
# Pre-flight Checks (Step 1)
# ============================================================================
check_prerequisites() {
    log_step 1 "Checking prerequisites..."
    local errors=0

    # Check OS
    if [[ "$(uname -s)" != "Linux" ]]; then
        log_error "This script only supports Linux"
        errors=$((errors + 1))
    else
        local os_name=""
        if [[ -f /etc/os-release ]]; then
            os_name=$(grep PRETTY_NAME /etc/os-release | cut -d'"' -f2)
        fi
        log_success "OS: Linux ${os_name:+($os_name)}"
    fi

    # Check disk space
    local available_gb
    available_gb=$(df -BG /var/tmp 2>/dev/null | awk 'NR==2 {print $4}' | tr -d 'G')
    if [[ -n "$available_gb" ]] && [[ "$available_gb" -lt "$REQUIRED_DISK_GB" ]]; then
        log_error "Insufficient disk space: ${available_gb}GB available, ${REQUIRED_DISK_GB}GB required"
        errors=$((errors + 1))
    else
        log_success "Disk space: ${available_gb}GB available"
    fi

    # Detect platform FIRST — needed for CUDA-aware memory budget below
    detect_platform
    log_info "Platform: ${PLATFORM} (${ARCH})"
    if [[ "$IS_JETSON" == true ]]; then
        log_info "NVIDIA Jetson detected — CUDA ${CUDA_ARCH}, NEON enabled"
    elif [[ "$IS_RPI" == true ]]; then
        log_info "Raspberry Pi detected — NEON + VFPv3 enabled"
    fi

    # Check RAM and calculate safe parallel jobs.
    # Parallelism is based on RAM only (swap is too slow for parallel GCC).
    local total_ram_mb
    total_ram_mb=$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}')
    local swap_mb
    swap_mb=$(free -m 2>/dev/null | awk '/^Swap:/ {print $2}')
    # Budget per job from RAM (not swap), reserving 1GB for OS.
    # CUDA builds (nvcc) use more memory than pure GCC builds.
    local available_ram_mb=$((total_ram_mb - 1024))
    [[ $available_ram_mb -lt 1500 ]] && available_ram_mb=1500
    local mem_per_job_mb=2000
    [[ "$HAS_CUDA" == true ]] && mem_per_job_mb=2500
    local safe_jobs=$((available_ram_mb / mem_per_job_mb))
    [[ $safe_jobs -lt 1 ]] && safe_jobs=1

    if [[ $total_ram_mb -lt 6000 ]]; then
        log_warn "Limited RAM: ${total_ram_mb}MB RAM + ${swap_mb}MB swap"
        log_detail "Parallel jobs limited to -j${safe_jobs} (based on RAM, not swap)"
        if [[ "$OPENCV_ALLOW_TEMP_SWAP" == "1" ]]; then
            log_detail "Temporary swap creation was explicitly enabled for this run"
        else
            log_detail "Provide 6GB RAM+swap or opt in with OPENCV_ALLOW_TEMP_SWAP=1"
        fi
    else
        log_success "RAM: ${total_ram_mb}MB + ${swap_mb}MB swap"
    fi

    # Check PixEagle venv
    if [[ ! -d "$VENV_DIR" ]] || [[ ! -f "$VENV_DIR/bin/activate" ]]; then
        log_error "PixEagle virtual environment not found"
        log_detail "Run 'make init' (or 'bash scripts/init.sh') first"
        errors=$((errors + 1))
    else
        local canonical_venv
        canonical_venv=$(realpath -e -- "$VENV_DIR" 2>/dev/null || true)
        if [[ -z "$canonical_venv" || ! -d "$canonical_venv" || ! -x "$canonical_venv/bin/python" ]]; then
            log_error "PixEagle virtual environment could not be resolved safely"
            errors=$((errors + 1))
        else
            VENV_DIR="$canonical_venv"
            log_success "PixEagle venv found: $VENV_DIR"
        fi
    fi

    # Check required commands
    for cmd in git cmake make pkg-config; do
        if ! command -v "$cmd" &>/dev/null; then
            log_warn "Missing command: $cmd (will be installed)"
        fi
    done

    # Check Python version
    if [[ -f "$VENV_DIR/bin/python" ]]; then
        local python_version
        python_version=$("$VENV_DIR/bin/python" --version 2>&1 | awk '{print $2}')
        log_success "Python: ${python_version}"
    fi

    # Estimate build time
    local cpu_cores
    cpu_cores=$(nproc 2>/dev/null || echo "1")
    log_info "CPU cores: ${cpu_cores} (will use all for parallel build)"

    if [[ $errors -gt 0 ]]; then
        echo ""
        log_error "Prerequisites check failed with $errors error(s)"
        exit 1
    fi

    # Confirm with user
    if [[ "$SKIP_CONFIRM" != true ]]; then
        echo ""
        echo -e "        ${YELLOW}Ready to build OpenCV ${OPENCV_VERSION} with GStreamer.${NC}"
        if [[ "$OPENCV_GUI" == "1" ]]; then
            log_detail "Desktop GTK/OpenGL support: enabled"
        else
            log_detail "Desktop GTK/OpenGL support: disabled (headless companion default)"
        fi
        echo -e "        ${DIM}This will take approximately 1-2 hours.${NC}"
        echo -en "        Continue? [Y/n]: "
        read -r REPLY
        echo ""
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            log_info "Build cancelled by user"
            REPORT_STATUS="cancelled"
            exit 0
        fi
    fi
}

# ============================================================================
# Install System Dependencies (Step 2)
# ============================================================================
install_dependencies() {
    log_step 2 "Installing system dependencies..."

    prompt_sudo

    start_spinner "Updating package lists..."
    if sudo apt-get update -qq 2>&1; then
        stop_spinner
        log_success "Package lists updated"
    else
        stop_spinner
        log_warn "apt update had warnings (continuing)"
    fi

    # Core build packages (always needed)
    local core_packages=(
        build-essential
        cmake
        git
        pkg-config
        python3-dev
    )

    # GStreamer packages
    local gstreamer_packages=(
        libgstreamer1.0-dev
        libgstreamer-plugins-base1.0-dev
        gstreamer1.0-tools
        gstreamer1.0-libav
        gstreamer1.0-plugins-base
        gstreamer1.0-plugins-good
        gstreamer1.0-plugins-bad
        gstreamer1.0-plugins-ugly
    )

    # Optional GStreamer packages (may not exist on all distros)
    local optional_gstreamer=(
        gstreamer1.0-rtsp
        libgstrtspserver-1.0-dev
    )

    # Video/Image libraries
    local media_packages=(
        libavcodec-dev
        libavformat-dev
        libavutil-dev
        libswscale-dev
        libswresample-dev
        libv4l-dev
        v4l-utils
        libjpeg-dev
        libpng-dev
        libtiff-dev
        libwebp-dev
    )

    # Optional media packages (may not exist on all distros)
    local optional_media=(
        libxvidcore-dev
        libx264-dev
    )

    # GUI + OpenGL packages are optional on companion/headless systems.
    local gui_packages=(
        gstreamer1.0-gl
        gstreamer1.0-gtk3
        libgtk-3-dev
        libgtk2.0-dev
        libgl1-mesa-dev
        libglu1-mesa-dev
    )

    # Math / linear algebra packages
    local math_packages=(
        libatlas-base-dev
        gfortran
        libtbb-dev
        libeigen3-dev
    )

    # Install core packages first (required)
    log_info "Installing core build packages..."
    if ! sudo apt-get install -y "${core_packages[@]}" 2>&1 | tail -5; then
        log_error "Failed to install core packages"
        exit 1
    fi
    log_success "Core packages installed"

    # Install GStreamer packages (required for our use case)
    log_info "Installing GStreamer packages..."
    if ! sudo apt-get install -y "${gstreamer_packages[@]}" 2>&1 | tail -5; then
        log_error "Failed to install GStreamer packages"
        exit 1
    fi
    log_success "GStreamer packages installed"

    # Install optional GStreamer (ignore errors)
    log_info "Installing optional GStreamer packages..."
    for pkg in "${optional_gstreamer[@]}"; do
        sudo apt-get install -y "$pkg" >/dev/null 2>&1 || log_warn "Optional package $pkg not available (OK)"
    done

    # Install media packages
    log_info "Installing media/video packages..."
    if ! sudo apt-get install -y "${media_packages[@]}" 2>&1 | tail -5; then
        log_warn "Some media packages failed (continuing)"
    fi

    # Install optional media (ignore errors)
    for pkg in "${optional_media[@]}"; do
        sudo apt-get install -y "$pkg" >/dev/null 2>&1 || log_warn "Optional package $pkg not available (OK)"
    done

    if [[ "$OPENCV_GUI" == "1" ]]; then
        log_info "Installing optional GUI packages..."
        if ! sudo apt-get install -y "${gui_packages[@]}" >/dev/null 2>&1; then
            log_error "OPENCV_GUI=1 was requested but GUI dependencies could not be installed"
            exit 1
        fi
    else
        log_info "Skipping GTK/OpenGL packages for the headless companion build"
    fi

    # Install math packages
    log_info "Installing math packages..."
    sudo apt-get install -y "${math_packages[@]}" >/dev/null 2>&1 || log_warn "Math packages may be missing"

    log_success "System dependencies installed"
}

# ============================================================================
# Configure GStreamer Environment (Step 3)
# ============================================================================
setup_gstreamer_env() {
    log_step 3 "Configuring GStreamer environment..."

    # Verify GStreamer is available
    if pkg-config --exists gstreamer-1.0 2>/dev/null; then
        local gst_version
        gst_version=$(pkg-config --modversion gstreamer-1.0 2>/dev/null)
        log_success "GStreamer ${gst_version} found"
    else
        log_error "GStreamer development metadata is unavailable to pkg-config"
        log_detail "Install the GStreamer development packages before building OpenCV"
        exit 1
    fi

    if command -v gst-inspect-1.0 >/dev/null 2>&1; then
        log_success "GStreamer plugin discovery is available"
    else
        log_error "gst-inspect-1.0 is unavailable after dependency installation"
        exit 1
    fi
}

# ============================================================================
# Acquire And Export OpenCV Sources (Step 4)
# ============================================================================
create_opencv_work_root() {
    local previous_umask
    previous_umask="$(umask)"
    umask 077
    OPENCV_WORK_ROOT="$(mktemp -d /var/tmp/pixeagle-opencv-build.XXXXXX)" || {
        umask "$previous_umask"
        log_error "Could not create the private OpenCV work root"
        return 1
    }
    umask "$previous_umask"
    chmod 0700 -- "$OPENCV_WORK_ROOT" || return 1
    OPENCV_WORK_IDENTITY="$(stat -Lc '%d:%i:%u:%a' -- "$OPENCV_WORK_ROOT")" || return 1
    [[ "$OPENCV_WORK_IDENTITY" == *":$(id -u):700" ]] || return 1

    mkdir -m 0700 \
        "$OPENCV_WORK_ROOT/fetch" \
        "$OPENCV_WORK_ROOT/archives" \
        "$OPENCV_WORK_ROOT/source" \
        "$OPENCV_WORK_ROOT/build" \
        "$OPENCV_WORK_ROOT/downloads" \
        "$OPENCV_WORK_ROOT/stage" \
        "$OPENCV_WORK_ROOT/hooks-disabled" \
        "$OPENCV_WORK_ROOT/empty-template" \
        "$OPENCV_WORK_ROOT/git-home" \
        "$OPENCV_WORK_ROOT/git-config"

    OPENCV_SOURCE_DIR="$OPENCV_WORK_ROOT/source/opencv"
    OPENCV_CONTRIB_SOURCE_DIR="$OPENCV_WORK_ROOT/source/opencv_contrib"
    OPENCV_BUILD_DIR="$OPENCV_WORK_ROOT/build"
    OPENCV_DOWNLOAD_DIR="$OPENCV_WORK_ROOT/downloads"
    OPENCV_STAGE_DIR="$OPENCV_WORK_ROOT/stage"
    OPENCV_HOOKS_DIR="$OPENCV_WORK_ROOT/hooks-disabled"
    OPENCV_EMPTY_TEMPLATE_DIR="$OPENCV_WORK_ROOT/empty-template"
    OPENCV_WORK_CLEANUP_STATUS="pending"
}

assert_opencv_work_root() {
    [[ -n "$OPENCV_WORK_ROOT" ]] || return 1
    case "$OPENCV_WORK_ROOT" in
        /var/tmp/pixeagle-opencv-build.[A-Za-z0-9]*) ;;
        *) return 1 ;;
    esac
    [[ -d "$OPENCV_WORK_ROOT" && ! -L "$OPENCV_WORK_ROOT" ]] || return 1
    [[ "$(stat -Lc '%d:%i:%u:%a' -- "$OPENCV_WORK_ROOT" 2>/dev/null || true)" == \
        "$OPENCV_WORK_IDENTITY" ]]
}

remove_opencv_work_root() {
    [[ -n "$OPENCV_WORK_ROOT" ]] || {
        OPENCV_WORK_CLEANUP_STATUS="not_created"
        return 0
    }
    if ! assert_opencv_work_root; then
        OPENCV_WORK_CLEANUP_STATUS="identity_refused"
        log_error "Refusing to remove an OpenCV work root whose identity changed"
        return 1
    fi
    if ! rm -rf -- "$OPENCV_WORK_ROOT"; then
        OPENCV_WORK_CLEANUP_STATUS="remove_failed"
        return 1
    fi
    if [[ -e "$OPENCV_WORK_ROOT" || -L "$OPENCV_WORK_ROOT" ]]; then
        OPENCV_WORK_CLEANUP_STATUS="remove_incomplete"
        return 1
    fi
    OPENCV_WORK_CLEANUP_STATUS="removed"
    return 0
}

opencv_git() {
    local variable
    local -a clean_environment=(
        -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE \
        -u GIT_OBJECT_DIRECTORY -u GIT_ALTERNATE_OBJECT_DIRECTORIES \
        -u GIT_COMMON_DIR -u GIT_CONFIG -u GIT_CONFIG_COUNT \
        -u GIT_CONFIG_PARAMETERS -u GIT_CONFIG_SYSTEM \
        -u GIT_SSH -u GIT_SSH_COMMAND -u GIT_ATTR_SOURCE
    )
    while IFS='=' read -r variable _value; do
        case "$variable" in
            GIT_CONFIG_KEY_*|GIT_CONFIG_VALUE_*) clean_environment+=(-u "$variable") ;;
        esac
    done < <(env)

    env "${clean_environment[@]}" \
        HOME="$OPENCV_WORK_ROOT/git-home" \
        XDG_CONFIG_HOME="$OPENCV_WORK_ROOT/git-config" \
        GIT_CONFIG_NOSYSTEM=1 \
        GIT_CONFIG_GLOBAL=/dev/null \
        GIT_ATTR_NOSYSTEM=1 \
        GIT_TERMINAL_PROMPT=0 \
        GIT_ASKPASS=/bin/false \
        SSH_ASKPASS=/bin/false \
        GIT_ALLOW_PROTOCOL=https \
        git -c "core.hooksPath=$OPENCV_HOOKS_DIR" \
            -c "init.templateDir=$OPENCV_EMPTY_TEMPLATE_DIR" "$@"
}

validate_and_extract_opencv_archive() {
    local archive="$1"
    local destination="$2"
    python3 - "$archive" "$destination" "$OPENCV_WORK_ROOT" <<'PY'
import hashlib
import os
import shutil
import stat
import sys
import tarfile
from pathlib import Path, PurePosixPath

archive = Path(sys.argv[1]).resolve(strict=True)
destination = Path(sys.argv[2])
work_root = Path(sys.argv[3]).resolve(strict=True)
if destination.exists() or destination.is_symlink():
    raise SystemExit("source export destination already exists")
if destination.parent.resolve(strict=True) != (work_root / "source").resolve(strict=True):
    raise SystemExit("source export destination is outside the private work root")


def normalized_parts(value: str) -> tuple[str, ...]:
    if not value or value.startswith(("/", "\\")) or "\\" in value:
        raise SystemExit(f"unsafe archive path: {value!r}")
    parts = PurePosixPath(value).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise SystemExit(f"unsafe archive path: {value!r}")
    return parts


def resolve_link(member_name: str, target: str) -> None:
    if not target or target.startswith(("/", "\\")) or "\\" in target:
        raise SystemExit(f"unsafe archive symlink target: {target!r}")
    target_parts = PurePosixPath(target).parts
    combined = list(PurePosixPath(member_name).parent.parts) + list(target_parts)
    stack: list[str] = []
    for part in combined:
        if part == "..":
            if not stack:
                raise SystemExit(f"archive symlink escapes source root: {member_name}")
            stack.pop()
        elif part not in ("", "."):
            stack.append(part)


with tarfile.open(archive, mode="r:*") as source:
    members = source.getmembers()
    if len(members) > 250_000:
        raise SystemExit("source archive has too many entries")
    total_size = 0
    seen: set[tuple[str, ...]] = set()
    for member in members:
        parts = normalized_parts(member.name.rstrip("/"))
        if parts in seen:
            raise SystemExit(f"duplicate source archive path: {member.name}")
        seen.add(parts)
        if member.islnk() or member.isdev() or member.isfifo():
            raise SystemExit(f"unsupported source archive entry: {member.name}")
        if not (member.isdir() or member.isfile() or member.issym()):
            raise SystemExit(f"unsupported source archive entry: {member.name}")
        if member.isfile():
            total_size += member.size
            if member.size > 1_000_000_000 or total_size > 2_000_000_000:
                raise SystemExit("source archive exceeds extraction bounds")
        if member.issym():
            resolve_link(member.name, member.linkname)

    destination.mkdir(mode=0o700)

    def output_path(member: tarfile.TarInfo) -> Path:
        return destination.joinpath(*normalized_parts(member.name.rstrip("/")))

    for member in sorted((item for item in members if item.isdir()), key=lambda item: len(PurePosixPath(item.name).parts)):
        output_path(member).mkdir(mode=member.mode & 0o755 or 0o700, parents=True, exist_ok=True)
    for member in (item for item in members if item.isfile()):
        output = output_path(member)
        output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if any(parent.is_symlink() for parent in output.parents if parent != destination.parent):
            raise SystemExit(f"symlinked source parent: {member.name}")
        source_file = source.extractfile(member)
        if source_file is None:
            raise SystemExit(f"cannot read source archive member: {member.name}")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(output, flags, member.mode & 0o755 or 0o600)
        copied = 0
        with source_file, os.fdopen(descriptor, "wb") as target:
            while True:
                chunk = source_file.read(1024 * 1024)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > member.size:
                    raise SystemExit(f"source member exceeded declared size: {member.name}")
                target.write(chunk)
        if copied != member.size:
            raise SystemExit(f"source member size changed while reading: {member.name}")
    for member in (item for item in members if item.issym()):
        output = output_path(member)
        output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.symlink(member.linkname, output)

for path in destination.rglob("*"):
    if path.name == ".git":
        raise SystemExit("Git metadata appeared in exported source")
    if path.is_symlink():
        resolved = path.resolve(strict=False)
        if not resolved.is_relative_to(destination.resolve(strict=True)):
            raise SystemExit(f"exported symlink escapes source root: {path}")
PY
}

opencv_source_tree_digest() {
    local source_root="$1"
    python3 - "$source_root" <<'PY'
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve(strict=True)
digest = hashlib.sha256()
for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
    relative = path.relative_to(root).as_posix()
    metadata = path.lstat()
    if stat.S_ISDIR(metadata.st_mode):
        record = ["directory", relative, stat.S_IMODE(metadata.st_mode)]
        digest.update(json.dumps(record, separators=(",", ":")).encode() + b"\0")
    elif stat.S_ISLNK(metadata.st_mode):
        record = ["symlink", relative, os.readlink(path)]
        digest.update(json.dumps(record, separators=(",", ":")).encode() + b"\0")
    elif stat.S_ISREG(metadata.st_mode):
        content = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                content.update(chunk)
        if size != metadata.st_size:
            raise SystemExit(f"source changed while hashing: {relative}")
        record = ["file", relative, stat.S_IMODE(metadata.st_mode), size, content.hexdigest()]
        digest.update(json.dumps(record, separators=(",", ":")).encode() + b"\0")
    else:
        raise SystemExit(f"unsupported exported source entry: {relative}")
print(digest.hexdigest())
PY
}

prepare_opencv_source() {
    local name="$1"
    local repository_url="$2"
    local repository_dir="$3"
    local expected_commit="$4"
    local tag_ref="refs/tags/${OPENCV_VERSION}"
    local source_dir="$5"
    local archive="$OPENCV_WORK_ROOT/archives/${name}.tar"
    local local_ref="refs/pixeagle/source-tag"

    case "$repository_url" in
        https://github.com/opencv/opencv.git|https://github.com/opencv/opencv_contrib.git) ;;
        *) log_error "Refusing unexpected OpenCV source URL: $repository_url"; return 1 ;;
    esac
    [[ ! -e "$repository_dir" && ! -L "$repository_dir" ]] || return 1
    opencv_git init --bare --quiet "$repository_dir" || return 1
    opencv_git --git-dir="$repository_dir" remote add origin "$repository_url" || return 1

    start_spinner "Fetching pinned ${name} tag into a private bare repository..."
    if ! opencv_git --git-dir="$repository_dir" fetch --force --no-tags --depth=1 \
        --no-recurse-submodules origin "${tag_ref}:${local_ref}" >/dev/null 2>&1; then
        stop_spinner
        log_error "Failed to fetch the pinned ${name} ${OPENCV_VERSION} tag"
        return 1
    fi
    stop_spinner

    local tag_object resolved_commit archive_digest tree_digest
    local expected_archive_digest expected_tree_digest
    if [[ "$name" == "opencv" ]]; then
        expected_archive_digest="$OPENCV_EXPECTED_ARCHIVE_SHA256"
        expected_tree_digest="$OPENCV_EXPECTED_TREE_SHA256"
    else
        expected_archive_digest="$OPENCV_CONTRIB_EXPECTED_ARCHIVE_SHA256"
        expected_tree_digest="$OPENCV_CONTRIB_EXPECTED_TREE_SHA256"
    fi
    tag_object="$(opencv_git --git-dir="$repository_dir" rev-parse "$local_ref" 2>/dev/null || true)"
    resolved_commit="$(opencv_git --git-dir="$repository_dir" rev-parse "${local_ref}^{}" 2>/dev/null || true)"
    if [[ "$resolved_commit" != "$expected_commit" ]]; then
        log_error "$name ${OPENCV_VERSION} resolved to an unexpected commit"
        log_detail "Expected: $expected_commit"
        log_detail "Resolved: ${resolved_commit:-<missing>}"
        return 1
    fi

    opencv_git --git-dir="$repository_dir" archive --format=tar \
        --output="$archive" "$expected_commit" || return 1
    archive_digest="$(sha256sum -- "$archive" | awk '{print $1}')"
    [[ "$archive_digest" =~ ^[0-9a-f]{64}$ ]] || return 1
    validate_and_extract_opencv_archive "$archive" "$source_dir" || return 1
    tree_digest="$(opencv_source_tree_digest "$source_dir")" || return 1
    if [[ "$archive_digest" != "$expected_archive_digest" \
        || "$tree_digest" != "$expected_tree_digest" ]]; then
        log_error "$name source export does not match the checked-in pinned digests"
        log_detail "Archive expected/actual: $expected_archive_digest / $archive_digest"
        log_detail "Tree expected/actual: $expected_tree_digest / $tree_digest"
        return 1
    fi

    if [[ "$name" == "opencv" ]]; then
        OPENCV_SOURCE_TAG_OBJECT="$tag_object"
        OPENCV_SOURCE_ARCHIVE_SHA256="$archive_digest"
        OPENCV_SOURCE_TREE_SHA256="$tree_digest"
    else
        OPENCV_CONTRIB_SOURCE_TAG_OBJECT="$tag_object"
        OPENCV_CONTRIB_SOURCE_ARCHIVE_SHA256="$archive_digest"
        OPENCV_CONTRIB_SOURCE_TREE_SHA256="$tree_digest"
    fi
    log_success "$name ${OPENCV_VERSION} exported from pinned commit ${expected_commit:0:12}"
}

build_opencv_source_evidence() {
    SOURCE_EVIDENCE="$(python3 - \
        "$OPENCV_VERSION" \
        "$OPENCV_SOURCE_COMMIT" "$OPENCV_SOURCE_TAG_OBJECT" \
        "$OPENCV_SOURCE_ARCHIVE_SHA256" "$OPENCV_SOURCE_TREE_SHA256" \
        "$OPENCV_CONTRIB_SOURCE_COMMIT" "$OPENCV_CONTRIB_SOURCE_TAG_OBJECT" \
        "$OPENCV_CONTRIB_SOURCE_ARCHIVE_SHA256" \
        "$OPENCV_CONTRIB_SOURCE_TREE_SHA256" <<'PY'
import json
import sys

(
    version,
    opencv_commit,
    opencv_tag,
    opencv_archive,
    opencv_tree,
    contrib_commit,
    contrib_tag,
    contrib_archive,
    contrib_tree,
) = sys.argv[1:]
print(json.dumps({
    "selection": "exact tag ref peeled to a pinned commit in a transient bare repository",
    "tag": version,
    "opencv": {
        "repository": "https://github.com/opencv/opencv.git",
        "expected_commit": opencv_commit,
        "resolved_commit": opencv_commit,
        "tag_object": opencv_tag,
        "archive_sha256": opencv_archive,
        "exported_tree_sha256": opencv_tree,
    },
    "opencv_contrib": {
        "repository": "https://github.com/opencv/opencv_contrib.git",
        "expected_commit": contrib_commit,
        "resolved_commit": contrib_commit,
        "tag_object": contrib_tag,
        "archive_sha256": contrib_archive,
        "exported_tree_sha256": contrib_tree,
    },
}, sort_keys=True, separators=(",", ":")))
PY
)" || return 1
}

assert_opencv_sources_unchanged() {
    local opencv_digest contrib_digest
    opencv_digest="$(opencv_source_tree_digest "$OPENCV_SOURCE_DIR")" || return 1
    contrib_digest="$(opencv_source_tree_digest "$OPENCV_CONTRIB_SOURCE_DIR")" || return 1
    if [[ "$opencv_digest" != "$OPENCV_SOURCE_TREE_SHA256" ]] \
        || [[ "$contrib_digest" != "$OPENCV_CONTRIB_SOURCE_TREE_SHA256" ]]; then
        log_error "OpenCV source export changed after acquisition"
        return 1
    fi
}

clone_opencv() {
    log_step 4 "Preparing pinned OpenCV ${OPENCV_VERSION} sources..."

    create_opencv_work_root || exit 1

    prepare_opencv_source \
        "opencv" \
        "https://github.com/opencv/opencv.git" \
        "$OPENCV_WORK_ROOT/fetch/opencv.git" \
        "$OPENCV_SOURCE_COMMIT" \
        "$OPENCV_SOURCE_DIR"
    prepare_opencv_source \
        "opencv_contrib" \
        "https://github.com/opencv/opencv_contrib.git" \
        "$OPENCV_WORK_ROOT/fetch/opencv_contrib.git" \
        "$OPENCV_CONTRIB_SOURCE_COMMIT" \
        "$OPENCV_CONTRIB_SOURCE_DIR"
    build_opencv_source_evidence || exit 1
}

# ============================================================================
# Setup Python Environment (Step 5)
# ============================================================================
setup_python_env() {
    log_step 5 "Setting up Python environment..."

    # Activate PixEagle venv
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
    log_success "Activated PixEagle virtual environment"

    log_info "Keeping the active OpenCV runtime in place until compilation succeeds"

    if ! "$VENV_DIR/bin/python" - <<'PY'
import sys
from pathlib import Path

import numpy

module_path = Path(numpy.__file__).resolve()
venv_path = Path(sys.prefix).resolve()
if not module_path.is_relative_to(venv_path):
    raise SystemExit(f"NumPy resolved outside the selected venv: {module_path}")
PY
    then
        log_error "A working NumPy installation in the selected PixEagle venv is required"
        log_detail "Run the Core setup first: PIXEAGLE_INSTALL_PROFILE=core make init"
        exit 1
    fi
    log_success "Using the existing venv NumPy build dependency"
}

prepare_opencv_replacement() {
    local site_packages
    site_packages=$("$VENV_DIR/bin/python" -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null || true)
    site_packages=$(realpath -e -- "$site_packages" 2>/dev/null || true)
    if [[ -z "$site_packages" || ! -d "$site_packages" ]] \
        || ! assert_venv_destination_path "$site_packages"; then
        log_error "Could not resolve the PixEagle venv site-packages directory"
        exit 1
    fi

    local install_manifest="$OPENCV_BUILD_DIR/install_manifest.txt"
    local staged_prefix="${OPENCV_STAGE_DIR}${VENV_DIR}"
    if [[ -z "$OPENCV_STAGE_DIR" || ! -d "$staged_prefix" || ! -s "$install_manifest" ]]; then
        log_error "Staged OpenCV installation or install manifest is unavailable"
        exit 1
    fi

    OPENCV_BACKUP_DIR=$(mktemp -d "/var/tmp/pixeagle-opencv-backup.XXXXXX")
    chmod 0700 -- "$OPENCV_BACKUP_DIR"
    OPENCV_BACKUP_IDENTITY="$(stat -Lc '%d:%i:%u:%a' -- "$OPENCV_BACKUP_DIR")"
    if [[ "$OPENCV_BACKUP_IDENTITY" != *":$(id -u):700" ]]; then
        log_error "OpenCV rollback directory failed owner/mode validation"
        exit 1
    fi
    mkdir -p \
        "$OPENCV_BACKUP_DIR/site-packages" \
        "$OPENCV_BACKUP_DIR/lib" \
        "$OPENCV_BACKUP_DIR/manifest" \
        "$OPENCV_BACKUP_DIR/venv-layout"

    local installed_path
    local relative_path
    local target_path
    while IFS= read -r installed_path; do
        case "$installed_path" in
            "$staged_prefix"/*)
                relative_path="${installed_path#"$staged_prefix"/}"
                ;;
            "$VENV_DIR"/*)
                relative_path="${installed_path#"$VENV_DIR"/}"
                ;;
            *)
                log_error "OpenCV install manifest contains a path outside the PixEagle venv: $installed_path"
                exit 1
                ;;
        esac
        if ! is_safe_relative_install_path "$relative_path"; then
            log_error "OpenCV install manifest contains an unsafe relative path: $installed_path"
            exit 1
        fi
        target_path="$VENV_DIR/$relative_path"
        if ! assert_venv_destination_path "$target_path"; then
            exit 1
        fi
        printf '%s\n' "$target_path" >> "$OPENCV_BACKUP_DIR/install-targets.txt"
        if [[ -e "$target_path" || -L "$target_path" ]]; then
            mkdir -p "$OPENCV_BACKUP_DIR/manifest/$(dirname "$relative_path")"
            cp -a -- "$target_path" "$OPENCV_BACKUP_DIR/manifest/$relative_path"
        fi
    done < "$install_manifest"

    if [[ ! -s "$OPENCV_BACKUP_DIR/install-targets.txt" ]]; then
        log_error "OpenCV staged install produced an empty target manifest"
        exit 1
    fi

    local path
    shopt -s nullglob
    for path in "$site_packages/cv2" "$site_packages"/cv2*.so \
        "$site_packages"/opencv*.dist-info "$site_packages"/opencv*.egg-info \
        "$site_packages"/opencv*.libs; do
        cp -a "$path" "$OPENCV_BACKUP_DIR/site-packages/"
    done
    for path in "$VENV_DIR/lib"/libopencv*; do
        cp -a "$path" "$OPENCV_BACKUP_DIR/lib/"
    done
    for path in \
        "$VENV_DIR/include/opencv4" \
        "$VENV_DIR/share/opencv4" \
        "$VENV_DIR/share/OpenCV" \
        "$VENV_DIR/share/licenses/opencv4" \
        "$VENV_DIR/lib/cmake/opencv4" \
        "$VENV_DIR/lib/pkgconfig/opencv4.pc" \
        "$VENV_DIR/lib"/libopencv* \
        "$VENV_DIR/bin"/opencv_*; do
        if ! assert_venv_destination_path "$path"; then
            exit 1
        fi
        if [[ -e "$path" || -L "$path" ]]; then
            relative_path="${path#"$VENV_DIR"/}"
            mkdir -p "$OPENCV_BACKUP_DIR/venv-layout/$(dirname "$relative_path")"
            cp -a -- "$path" "$OPENCV_BACKUP_DIR/venv-layout/$relative_path"
        fi
    done
    shopt -u nullglob

    OPENCV_REPLACEMENT_STARTED=true
    log_info "Compiled successfully; replacing the active OpenCV runtime with rollback protection..."
    if ! "$VENV_DIR/bin/python" -m pip uninstall -y \
        opencv-python opencv-contrib-python opencv-python-headless opencv-contrib-python-headless \
        >/dev/null 2>&1; then
        log_error "Could not uninstall the previous OpenCV wheel packages"
        exit 1
    fi
    if ! remove_existing_opencv_artifacts "$site_packages"; then
        log_error "Previous OpenCV cleanup was incomplete; staged files were not installed"
        exit 1
    fi
}

stage_opencv_installation() {
    [[ -n "$OPENCV_STAGE_DIR" && -d "$OPENCV_STAGE_DIR" ]] || {
        log_error "Private OpenCV staging directory is unavailable"
        exit 1
    }
    assert_opencv_sources_unchanged || exit 1
    start_spinner "Staging compiled OpenCV installation..."
    if DESTDIR="$OPENCV_STAGE_DIR" cmake --install "$OPENCV_BUILD_DIR" >/dev/null 2>&1; then
        stop_spinner
    else
        stop_spinner
        log_error "Could not stage the compiled OpenCV installation"
        exit 1
    fi

    if [[ ! -d "${OPENCV_STAGE_DIR}${VENV_DIR}" ]] \
        || [[ ! -s "$OPENCV_BUILD_DIR/install_manifest.txt" ]]; then
        log_error "Staged OpenCV installation is incomplete"
        exit 1
    fi
    log_success "Compiled OpenCV staged without changing the active runtime"
}

# ============================================================================
# Create Build Directory (Step 6)
# ============================================================================
prepare_build() {
    log_step 6 "Preparing build directory..."

    [[ -n "$OPENCV_BUILD_DIR" && -d "$OPENCV_BUILD_DIR" && ! -L "$OPENCV_BUILD_DIR" ]] || {
        log_error "Private OpenCV build directory is unavailable"
        exit 1
    }
    [[ -z "$(find "$OPENCV_BUILD_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]] || {
        log_error "Private OpenCV build directory was not empty"
        exit 1
    }
    cd "$OPENCV_BUILD_DIR"
    log_success "Build directory ready in the private work root"
}

# ============================================================================
# Configure CMake (Step 7)
# ============================================================================
configure_cmake() {
    log_step 7 "Configuring CMake build..."

    log_info "This may take a few minutes..."

    local gui_backend="OFF"
    if [[ "$OPENCV_GUI" == "1" ]]; then
        gui_backend="ON"
    fi

    local cmake_args=(
        -D CMAKE_BUILD_TYPE=Release
        -D CMAKE_INSTALL_PREFIX="$VENV_DIR"
        -D OPENCV_EXTRA_MODULES_PATH="$OPENCV_CONTRIB_SOURCE_DIR/modules"
        -D OPENCV_DOWNLOAD_PATH="$OPENCV_DOWNLOAD_DIR"
        -D WITH_GSTREAMER=ON
        -D WITH_GTK="$gui_backend"
        -D WITH_OPENGL="$gui_backend"
        -D WITH_FFMPEG=ON
        -D WITH_V4L=ON
        -D WITH_TBB=ON
        -D BUILD_EXAMPLES=OFF
        -D BUILD_TESTS=OFF
        -D BUILD_PERF_TESTS=OFF
        -D BUILD_DOCS=OFF
        -D PYTHON3_EXECUTABLE="$VENV_DIR/bin/python"
        -D PYTHON3_INCLUDE_DIR="$("$VENV_DIR/bin/python" -c 'import sysconfig; print(sysconfig.get_path("include"))')"
        -D PYTHON3_LIBRARY="$("$VENV_DIR/bin/python" -c 'import os, sysconfig; print(os.path.join(sysconfig.get_config_var("LIBDIR"), sysconfig.get_config_var("LDLIBRARY")))' 2>/dev/null || echo "")"
        -D Python3_FIND_REGISTRY=NEVER
        -D Python3_FIND_IMPLEMENTATIONS=CPython
        -D Python3_FIND_STRATEGY=LOCATION
    )

    # Platform-specific CMake flags
    if [[ "$IS_JETSON" == true ]]; then
        # CUDA is opt-in because:
        #   - This script's purpose is GStreamer support, not CUDA
        #   - CUDA compilation adds 30-60 min and needs 2-3x more RAM per job
        #   - PixEagle uses PyTorch (ultralytics) for inference, not OpenCV CUDA
        #   - OpenCV CUDA is for cv2.cuda functions (resize, threshold, etc.)
        # Enable with: OPENCV_CUDA=1 bash scripts/setup/build-opencv.sh
        if [[ "${OPENCV_CUDA:-0}" == "1" ]]; then
            log_info "Adding Jetson CUDA flags (CUDA arch ${CUDA_ARCH}) — opt-in via OPENCV_CUDA=1"
            cmake_args+=(
                -D WITH_CUDA=ON
                -D CUDA_ARCH_BIN="${CUDA_ARCH}"
                -D CUDA_ARCH_PTX=""
                -D WITH_CUDNN=ON
                -D CUDA_FAST_MATH=ON
                -D WITH_CUBLAS=ON
            )
            # DNN CUDA is a further opt-in (extremely memory-heavy)
            if [[ "${OPENCV_DNN_CUDA:-0}" == "1" ]]; then
                log_info "OPENCV_DNN_CUDA enabled — expect 3-5GB/job peak memory"
                cmake_args+=( -D OPENCV_DNN_CUDA=ON )
            else
                cmake_args+=( -D OPENCV_DNN_CUDA=OFF )
            fi
        else
            log_info "Jetson detected but CUDA disabled (not needed for GStreamer)"
            log_detail "To enable: OPENCV_CUDA=1 bash scripts/setup/build-opencv.sh"
            HAS_CUDA=false  # Override so memory budget uses GCC values
        fi
        # Always enable NEON on Jetson (ARM optimization, no extra memory cost)
        cmake_args+=( -D ENABLE_NEON=ON )
    elif [[ "$ARCH" == "aarch64" ]]; then
        log_info "Adding ARM64 NEON optimization flags"
        cmake_args+=( -D ENABLE_NEON=ON )
    elif [[ "$ARCH" == "armv7l" ]]; then
        log_info "Adding ARM32 NEON + VFPv3 optimization flags"
        cmake_args+=(
            -D ENABLE_NEON=ON
            -D ENABLE_VFPV3=ON
            -D CPU_BASELINE=NEON
        )
    fi

    start_spinner "Running CMake configuration..."
    if cmake -S "$OPENCV_SOURCE_DIR" -B "$OPENCV_BUILD_DIR" \
        "${cmake_args[@]}" > "$OPENCV_BUILD_DIR/cmake_output.log" 2>&1; then
        stop_spinner
        log_success "CMake configuration complete"
    else
        stop_spinner
        log_error "CMake configuration failed"
        log_detail "CMake evidence will be retained in the requested JSON report"
        exit 1
    fi

    # Verify GStreamer is enabled
    if grep -q "GStreamer:.*YES" "$OPENCV_BUILD_DIR/cmake_output.log" 2>/dev/null; then
        log_success "GStreamer support enabled in build"
    else
        log_error "CMake completed without enabling the required GStreamer backend"
        log_detail "Request --report-json to retain bounded CMake evidence"
        exit 1
    fi
}

# ============================================================================
# Compile OpenCV (Step 8)
# ============================================================================
compile_opencv() {
    log_step 8 "Compiling OpenCV... ${CLOCK} (this takes 1-2 hours)"

    local cpu_cores
    cpu_cores=$(nproc 2>/dev/null || echo "1")

    # Calculate safe parallelism based on PHYSICAL RAM only.
    # Swap prevents OOM-kill but is ~100x slower than RAM — running many
    # parallel GCC jobs backed by swap causes thrashing and eventual failure.
    local make_jobs
    local total_ram_mb
    total_ram_mb=$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}')
    local swap_mb
    swap_mb=$(free -m 2>/dev/null | awk '/^Swap:/ {print $2}')

    # Reserve ~1GB for the OS and other processes
    local available_ram_mb=$((total_ram_mb - 1024))
    [[ $available_ram_mb -lt 1500 ]] && available_ram_mb=1500

    # nvcc (CUDA compiler) uses 2-3GB per compilation unit vs ~1.5-2GB for gcc.
    # Budget accordingly based on whether CUDA is enabled.
    local mem_per_job_mb=2000
    if [[ "$HAS_CUDA" == true ]]; then
        mem_per_job_mb=2500
        log_info "CUDA build detected — using ${mem_per_job_mb}MB/job budget (nvcc is memory-heavy)"
    fi

    local mem_safe_jobs=$((available_ram_mb / mem_per_job_mb))
    [[ $mem_safe_jobs -lt 1 ]] && mem_safe_jobs=1

    # Use the lesser of CPU cores and memory-safe jobs
    if [[ $mem_safe_jobs -lt $cpu_cores ]]; then
        make_jobs=$mem_safe_jobs
        log_warn "Memory-limited build: -j${make_jobs} (${total_ram_mb}MB RAM, ${swap_mb}MB swap, ~${mem_per_job_mb}MB/job)"
        if [[ $make_jobs -eq 1 ]]; then
            log_info "This will be SLOW (~2-3 hours) but should complete without OOM"
        fi
    else
        make_jobs="$cpu_cores"
        log_info "Using ${make_jobs} parallel jobs (${total_ram_mb}MB RAM available)"
    fi

    log_info "Go grab a coffee... ${VIDEO}"
    echo ""

    # Run make with progress
    local start_time
    start_time=$(date +%s)

    echo -e "        ${CYAN}Build progress:${NC}"

    # Save full build output for diagnostics on failure
    local build_log="$OPENCV_BUILD_DIR/build_output.log"

    # Compile with appropriate parallelism
    if cmake --build "$OPENCV_BUILD_DIR" --parallel "$make_jobs" 2>&1 \
        | tee "$build_log" | while IFS= read -r line; do
        # Parse make output for progress
        if [[ "$line" =~ ^\[\ *([0-9]+)%\] ]]; then
            local percent="${BASH_REMATCH[1]}"
            printf "\r        ${DIM}→ Building: [%3d%%]${NC}" "$percent"
        fi
    done; then
        echo ""
        log_success "Compilation complete"
    else
        echo ""
        log_error "Compilation failed"
        # Check if OOM killer was involved
        if dmesg 2>/dev/null | tail -20 | grep -qi "out of memory\|oom-kill\|killed process"; then
            log_error "OOM killer detected — not enough RAM for -j${make_jobs}"
            log_detail "Your system ran out of memory during compilation."
            if [[ "$HAS_CUDA" == true ]] && [[ "${OPENCV_DNN_CUDA:-0}" == "1" ]]; then
                log_detail "Try without DNN CUDA: unset OPENCV_DNN_CUDA and re-run"
            fi
        fi
        # Show last few error lines from the build log
        if [[ -f "$build_log" ]]; then
            log_detail "Last lines of build output:"
            tail -10 "$build_log" | while IFS= read -r errline; do
                log_detail "  $errline"
            done
            log_detail "Build evidence will be retained in the requested JSON report"
        fi
        exit 1
    fi

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local minutes=$((duration / 60))
    log_info "Build time: ${minutes} minutes"

    # Stage first so the complete destination manifest is known before any live
    # venv path is changed. The EXIT trap restores every overwritten target.
    stage_opencv_installation
    prepare_opencv_replacement

    start_spinner "Installing staged OpenCV into the virtual environment..."
    if cp -a "${OPENCV_STAGE_DIR}${VENV_DIR}/." "$VENV_DIR/"; then
        stop_spinner
        log_success "Installed to $VENV_DIR"
    else
        stop_spinner
        log_error "Installation failed"
        exit 1
    fi
}

# ============================================================================
# Verify Installation (Step 9)
# ============================================================================
verify_installation() {
    log_step 9 "Verifying the replacement OpenCV runtime..."

    local test_result
    if ! test_result=$(PIXEAGLE_EXPECTED_OPENCV_VERSION="$OPENCV_VERSION" \
        PIXEAGLE_EXPECTED_VENV="$VENV_DIR" \
        timeout 30s "$VENV_DIR/bin/python" 2>&1 << 'PYEOF'
try:
    import hashlib
    import json
    import os
    import re
    from pathlib import Path
    from tempfile import TemporaryDirectory

    import cv2
    import numpy as np

    build_info = cv2.getBuildInformation()
    version = cv2.__version__
    module_path = Path(cv2.__file__).resolve()
    expected_venv = Path(os.environ["PIXEAGLE_EXPECTED_VENV"]).resolve()

    def sha256_file(path):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def file_evidence(path):
        path = Path(path).resolve()
        return {
            "path": str(path),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }

    def build_feature_enabled(name):
        return re.search(
            rf"^\s*{re.escape(name)}\s*:\s*YES\b",
            build_info,
            flags=re.IGNORECASE | re.MULTILINE,
        ) is not None

    legacy = getattr(cv2, "legacy", None)

    def instantiate_tracker(name):
        factory = getattr(cv2, name, None)
        if not callable(factory):
            factory = getattr(legacy, name, None)
        return callable(factory) and factory() is not None

    csrt = instantiate_tracker("TrackerCSRT_create")
    kcf = instantiate_tracker("TrackerKCF_create")

    with TemporaryDirectory(prefix="pixeagle-opencv-verify-") as temp_dir:
        sink_path = Path(temp_dir) / "frame.raw"
        escaped_sink = str(sink_path).replace("\\", "\\\\").replace('"', '\\"')
        writer = cv2.VideoWriter(
            f'appsrc ! videoconvert ! filesink location="{escaped_sink}" sync=false',
            cv2.CAP_GSTREAMER,
            0,
            5.0,
            (16, 16),
            True,
        )
        writer_opened = writer.isOpened()
        try:
            if writer_opened:
                writer.write(np.zeros((16, 16, 3), dtype=np.uint8))
        finally:
            writer.release()
        sink_observed = writer_opened and sink_path.is_file() and sink_path.stat().st_size > 0

    native_files = [module_path]
    for pattern in ("cv2*.so", "cv2*.pyd", "cv2*.dylib"):
        for candidate in sorted(module_path.parent.rglob(pattern)):
            resolved = candidate.resolve()
            if resolved.is_file() and resolved not in native_files:
                native_files.append(resolved)

    runtime_evidence = {
        "version": version,
        "module_file": str(module_path),
        "build_information_sha256": hashlib.sha256(build_info.encode()).hexdigest(),
        "gstreamer": build_feature_enabled("GStreamer"),
        "ffmpeg": build_feature_enabled("FFMPEG"),
        "tracker_csrt_instantiated": csrt,
        "tracker_kcf_instantiated": kcf,
        "gstreamer_sink_observed": sink_observed,
        "fingerprinted_files": [file_evidence(path) for path in native_files],
        "fingerprint_scope": "OpenCV build information and loaded cv2 files",
    }

    print(f"VERSION:{version}")
    print(f"MODULE_PATH:{module_path}")
    print(f"PATH_IN_VENV:{module_path.is_relative_to(expected_venv)}")
    print(f"VERSION_MATCH:{version == os.environ['PIXEAGLE_EXPECTED_OPENCV_VERSION']}")
    print(f"GSTREAMER:{build_feature_enabled('GStreamer')}")
    print(f"FFMPEG:{build_feature_enabled('FFMPEG')}")
    print(f"TRACKER_CSRT_INSTANTIATED:{csrt}")
    print(f"TRACKER_KCF_INSTANTIATED:{kcf}")
    print(f"GSTREAMER_SINK_OBSERVED:{sink_observed}")
    print("RUNTIME_JSON:" + json.dumps(runtime_evidence, sort_keys=True, separators=(",", ":")))
except Exception as e:
    print(f"ERROR:{type(e).__name__}:{e}")
PYEOF
    ); then
        log_error "OpenCV verification timed out or could not start"
        exit 1
    fi

    local cv_version
    cv_version=$(echo "$test_result" | grep "VERSION:" | cut -d':' -f2 || true)
    local module_path
    module_path=$(echo "$test_result" | grep "MODULE_PATH:" | cut -d':' -f2- || true)

    if [[ -n "$cv_version" ]]; then
        log_success "OpenCV ${cv_version} imported from ${module_path}"
    else
        log_error "OpenCV import failed"
        log_detail "$test_result"
        exit 1
    fi

    local check
    for check in PATH_IN_VENV VERSION_MATCH GSTREAMER FFMPEG \
        TRACKER_CSRT_INSTANTIATED TRACKER_KCF_INSTANTIATED GSTREAMER_SINK_OBSERVED; do
        if ! grep -q "^${check}:True$" <<<"$test_result"; then
            log_error "OpenCV replacement verification failed: ${check}"
            log_detail "$test_result"
            exit 1
        fi
    done

    RUNTIME_EVIDENCE=$(sed -n 's/^RUNTIME_JSON://p' <<<"$test_result")
    if [[ -z "$RUNTIME_EVIDENCE" ]]; then
        log_error "OpenCV verification did not produce runtime fingerprint evidence"
        log_detail "$test_result"
        exit 1
    fi

    local provider_evidence
    if ! provider_evidence="$("$VENV_DIR/bin/python" \
        "$SCRIPT_DIR/opencv_provider_probe.py")"; then
        log_error "Complete source-provider ownership fingerprint failed"
        exit 1
    fi
    RUNTIME_EVIDENCE="$(python3 - \
        3<<<"$RUNTIME_EVIDENCE" 4<<<"$provider_evidence" <<'PY'
import json
import os

functional = json.load(os.fdopen(3, encoding="utf-8"))
provider = json.load(os.fdopen(4, encoding="utf-8"))
if provider.get("provider_kind") != "source_gstreamer":
    raise SystemExit("built OpenCV was not classified as the source/GStreamer provider")
print(json.dumps({
    "provider": provider,
    "functional_verification": functional,
}, sort_keys=True, separators=(",", ":")))
PY
)" || {
        log_error "Could not combine OpenCV provider and functional evidence"
        exit 1
    }

    log_success "Verified venv path, exact version, instantiated trackers, FFmpeg, and an observed GStreamer sink"

    OPENCV_REPLACEMENT_COMMITTED=true
}

# ============================================================================
# Summary Display
# ============================================================================
show_summary() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "                          ${PARTY} ${BOLD}OpenCV Build Complete!${NC} ${PARTY}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "   ${GREEN}${CHECK}${NC} OpenCV ${OPENCV_VERSION} built from source"
    echo -e "   ${GREEN}${CHECK}${NC} GStreamer support enabled"
    echo -e "   ${GREEN}${CHECK}${NC} Installed to PixEagle venv"
    if [[ -n "$REPORT_JSON" ]]; then
        echo -e "   ${GREEN}${CHECK}${NC} Build/runtime evidence requested at $REPORT_JSON"
    else
        echo -e "   ${YELLOW}${WARN}${NC} No JSON evidence path requested"
    fi
    echo ""
    echo -e "   ${CYAN}${BOLD}📋 Next Steps:${NC}"
    echo -e "      1. If needed, create/apply a local override and set:"
    echo -e "         ${DIM}VideoSource.USE_GSTREAMER: true${NC}"
    echo -e "      2. Configure your video source through the dashboard or local override"
    echo -e "      3. Run PixEagle: ${BOLD}bash scripts/run.sh${NC}"
    echo ""
    echo -e "   ${YELLOW}${BOLD}💡 Test GStreamer support:${NC}"
    echo -e "      ${DIM}source ${VENV_DIR#"$PIXEAGLE_DIR"/}/bin/activate${NC}"
    echo -e "      ${DIM}python -c \"import cv2; print(cv2.getBuildInformation())\" | grep GStreamer${NC}"
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ============================================================================
# Main Execution
# ============================================================================
main() {
    parse_args "$@"
    if ! pixeagle_acquire_setup_lock "$VENV_DIR" "OpenCV source build" 30; then
        log_error "Another PixEagle setup operation is active"
        exit 1
    fi
    REPORT_STATUS="running"
    if [[ -n "$REPORT_JSON" ]]; then
        if ! REPORT_JSON="$(python3 "$SCRIPT_DIR/evidence_path.py" "$REPORT_JSON")"; then
            log_error "OpenCV evidence destination failed owner/type/write preflight"
            exit 1
        fi
    fi
    if [[ "$OPENCV_GUI" != "0" && "$OPENCV_GUI" != "1" ]]; then
        log_error "OPENCV_GUI must be 0 or 1"
        exit 2
    fi
    if [[ "$OPENCV_ALLOW_TEMP_SWAP" != "0" && "$OPENCV_ALLOW_TEMP_SWAP" != "1" ]]; then
        log_error "OPENCV_ALLOW_TEMP_SWAP must be 0 or 1"
        exit 2
    fi
    display_banner
    check_prerequisites
    install_dependencies
    setup_gstreamer_env
    clone_opencv
    setup_python_env
    prepare_build
    configure_cmake
    # Ensure enough memory before the heavy compilation step. Temporary swap
    # is created only after explicit operator opt-in and is removed on exit.
    ensure_build_memory
    compile_opencv
    verify_installation
    REPORT_STATUS="success"
    show_summary
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    if pixeagle_setup_lock_context_present; then
        main "$@"
    else
        trap - EXIT
        pixeagle_run_with_setup_lock \
            "$VENV_DIR" "OpenCV source build" 30 bash "${BASH_SOURCE[0]}" "$@"
    fi
fi

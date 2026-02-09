#!/bin/bash

# ============================================================================
# scripts/setup/install-ai-deps.sh - Safe AI dependency installer
# ============================================================================
# Installs PixEagle AI packages while preserving critical core runtime packages
# (numpy/opencv/torch stack) by default.
#
# Usage:
#   bash scripts/setup/install-ai-deps.sh
#   bash scripts/setup/install-ai-deps.sh --allow-core-upgrades
# ============================================================================

set -euo pipefail

TOTAL_STEPS=4

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
VENV_PYTHON="$PIXEAGLE_DIR/venv/bin/python"
VENV_PIP="$PIXEAGLE_DIR/venv/bin/pip"

ALLOW_CORE_UPGRADES=false
CONSTRAINTS_FILE=""

fix_line_endings() {
    local file="$1"
    if [[ -f "$file" ]] && grep -q $'\r' "$file" 2>/dev/null; then
        sed -i.bak 's/\r$//' "$file" 2>/dev/null || true
        rm -f "${file}.bak" 2>/dev/null || true
    fi
}

fix_line_endings "$SCRIPTS_DIR/lib/common.sh"
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
    CHECK="[OK]"; CROSS="[X]"; WARN="[!]"; INFO="[i]"
    log_info() { echo -e "   ${CYAN}[*]${NC} $1"; }
    log_success() { echo -e "   ${GREEN}${CHECK}${NC} $1"; }
    log_warn() { echo -e "   ${YELLOW}${WARN}${NC} $1"; }
    log_error() { echo -e "   ${RED}${CROSS}${NC} $1"; }
    log_step() { echo -e "\n${CYAN}[${1}/${TOTAL_STEPS}]${NC} $2"; }
    log_detail() { echo -e "      ${DIM}$1${NC}"; }
    display_pixeagle_banner() {
        echo -e "\n${CYAN}${BOLD}PixEagle${NC}\n"
    }
fi

cleanup() {
    if [[ -n "${CONSTRAINTS_FILE:-}" && -f "${CONSTRAINTS_FILE:-}" ]]; then
        rm -f "$CONSTRAINTS_FILE"
    fi
}
trap cleanup EXIT

show_help() {
    cat <<'USAGE'
Usage: bash scripts/setup/install-ai-deps.sh [OPTIONS]

Install AI dependencies used by SmartTracker and model tooling:
  - ultralytics
  - lap
  - ncnn
  - pnnx (recommended for NCNN export)

Options:
  --allow-core-upgrades   Allow pip to upgrade numpy/opencv/torch stack
  --help, -h              Show this help
USAGE
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --allow-core-upgrades)
                ALLOW_CORE_UPGRADES=true
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
        shift
    done
}

check_prereqs() {
    log_step 1 "Checking environment"

    [[ -x "$VENV_PIP" ]] || { log_error "Missing venv pip: $VENV_PIP"; exit 1; }
    [[ -x "$VENV_PYTHON" ]] || { log_error "Missing venv python: $VENV_PYTHON"; exit 1; }

    log_success "Using venv: $PIXEAGLE_DIR/venv"
}

build_constraints() {
    log_step 2 "Preparing dependency constraints"

    if [[ "$ALLOW_CORE_UPGRADES" == "true" ]]; then
        log_warn "Core package upgrades allowed (--allow-core-upgrades)"
        return 0
    fi

    CONSTRAINTS_FILE="$(mktemp)"

    "$VENV_PYTHON" - "$CONSTRAINTS_FILE" <<'PY'
import importlib.metadata as md
import sys

target = sys.argv[1]
protected = [
    "numpy",
    "opencv-python",
    "opencv-contrib-python",
    "torch",
    "torchvision",
    "torchaudio",
]

lines = []
for name in protected:
    try:
        version = md.version(name)
    except md.PackageNotFoundError:
        continue
    lines.append(f"{name}=={version}")

with open(target, "w", encoding="utf-8") as f:
    if lines:
        f.write("\n".join(lines) + "\n")
PY

    if [[ -s "$CONSTRAINTS_FILE" ]]; then
        log_success "Constraint lockfile generated"
        log_detail "Protected packages:"
        while IFS= read -r line; do
            [[ -n "$line" ]] && log_detail "- $line"
        done < "$CONSTRAINTS_FILE"
    else
        log_warn "No protected packages detected in current venv"
        rm -f "$CONSTRAINTS_FILE"
        CONSTRAINTS_FILE=""
    fi
}

install_ai_packages() {
    log_step 3 "Installing AI packages"

    local cmd=("$VENV_PIP" install --prefer-binary ultralytics lap ncnn)
    if [[ -n "$CONSTRAINTS_FILE" ]]; then
        cmd=("$VENV_PIP" install --prefer-binary -c "$CONSTRAINTS_FILE" ultralytics lap ncnn)
    fi

    log_info "Running pip install for ultralytics/lap/ncnn"
    "${cmd[@]}"

    # pnnx is used by Ultralytics NCNN export. Keep it best-effort so
    # SmartTracker runtime remains available even if pnnx wheel is unavailable.
    local pnnx_cmd=("$VENV_PIP" install --prefer-binary pnnx)
    if [[ -n "$CONSTRAINTS_FILE" ]]; then
        pnnx_cmd=("$VENV_PIP" install --prefer-binary -c "$CONSTRAINTS_FILE" pnnx)
    fi
    log_info "Installing optional NCNN exporter dependency (pnnx)"
    if "${pnnx_cmd[@]}"; then
        log_success "pnnx install OK"
    else
        log_warn "pnnx install failed (NCNN auto-export may be unavailable until fixed manually)"
    fi

    log_success "AI packages installation command completed"
}

verify_ai_runtime() {
    log_step 4 "Verifying imports"

    local payload
    payload="$("$VENV_PYTHON" <<'PY'
import json

status = {
    "ultralytics": False,
    "lap": False,
    "ncnn": False,
    "pnnx": False,
    "error": None,
}

try:
    from ultralytics import YOLO  # noqa: F401
    status["ultralytics"] = True
except Exception as e:
    status["error"] = f"ultralytics import failed: {e}"

try:
    import lap  # noqa: F401
    status["lap"] = True
except Exception as e:
    if not status["error"]:
        status["error"] = f"lap import failed: {e}"

try:
    import ncnn  # noqa: F401
    status["ncnn"] = True
except Exception:
    status["ncnn"] = False

try:
    import pnnx  # noqa: F401
    status["pnnx"] = True
except Exception:
    status["pnnx"] = False

print(json.dumps(status))
PY
)"

    local parsed
    parsed="$(python3 - "$payload" <<'PY'
import json
import shlex
import sys

data = json.loads(sys.argv[1])
ok = data.get("ultralytics") and data.get("lap")

print(f"OK={1 if ok else 0}")
print(f"ULTRA={1 if data.get('ultralytics') else 0}")
print(f"LAP={1 if data.get('lap') else 0}")
print(f"NCNN={1 if data.get('ncnn') else 0}")
print(f"PNNX={1 if data.get('pnnx') else 0}")
print(f"ERR={shlex.quote(data.get('error') or '')}")
PY
)"
    eval "$parsed"

    [[ "$ULTRA" -eq 1 ]] && log_success "ultralytics import OK" || log_warn "ultralytics import failed"
    [[ "$LAP" -eq 1 ]] && log_success "lap import OK" || log_warn "lap import failed"
    [[ "$NCNN" -eq 1 ]] && log_success "ncnn import OK" || log_warn "ncnn import failed (optional)"
    [[ "$PNNX" -eq 1 ]] && log_success "pnnx import OK" || log_warn "pnnx import failed (NCNN auto-export optional)"

    if [[ "$OK" -ne 1 ]]; then
        log_error "AI verification failed: ${ERR:-unknown}"
        return 1
    fi

    log_success "AI runtime verification passed"
    return 0
}

main() {
    parse_args "$@"
    display_pixeagle_banner "AI Dependency Setup" "Safe installation for ultralytics/lap/ncnn (+ optional pnnx)"

    check_prereqs
    build_constraints
    install_ai_packages
    verify_ai_runtime

    echo ""
    log_success "AI dependencies are ready"
}

main "$@"

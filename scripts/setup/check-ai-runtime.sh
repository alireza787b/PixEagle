#!/bin/bash

# ============================================================================
# scripts/setup/check-ai-runtime.sh - PixEagle AI Runtime Diagnostics
# ============================================================================
# Provides a deterministic snapshot of local AI/runtime readiness:
#   - torch/torchvision/torchaudio import and versions
#   - CUDA / MPS availability
#   - ultralytics / lap / ncnn / pnnx import health
#   - SmartTracker config intent (GPU/CPU + fallback)
#   - Model path existence checks
#
# Usage:
#   bash scripts/setup/check-ai-runtime.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
VENV_PYTHON="$PIXEAGLE_DIR/venv/bin/python"
CONFIG_PATH="$PIXEAGLE_DIR/configs/config.yaml"
DEFAULT_CONFIG_PATH="$PIXEAGLE_DIR/configs/config_default.yaml"

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
    display_pixeagle_banner() { echo -e "\n${CYAN}${BOLD}PixEagle${NC}\n"; }
fi

if [[ ! -f "$VENV_PYTHON" ]]; then
    log_error "Virtual environment Python not found: $VENV_PYTHON"
    log_info "Run: make init"
    exit 1
fi

display_pixeagle_banner "AI Runtime Check" "SmartTracker backend + model readiness"
log_info "Project: $PIXEAGLE_DIR"
log_info "Python:  $VENV_PYTHON"

"$VENV_PYTHON" - "$PIXEAGLE_DIR" "$CONFIG_PATH" "$DEFAULT_CONFIG_PATH" <<'PY'
import importlib
import importlib.util
import json
import sys
from pathlib import Path


root = Path(sys.argv[1])
config_path = Path(sys.argv[2])
default_config_path = Path(sys.argv[3])


def mod_status(name: str):
    status = {
        "name": name,
        "installed": False,
        "import_ok": False,
        "version": None,
        "error": None,
    }
    if importlib.util.find_spec(name) is None:
        return status
    status["installed"] = True
    try:
        module = importlib.import_module(name)
        status["import_ok"] = True
        status["version"] = getattr(module, "__version__", None)
    except Exception as exc:  # pragma: no cover - runtime diagnostics only
        status["error"] = str(exc)
    return status


def load_yaml(path: Path):
    if not path.exists():
        return None, f"not found: {path}"
    if importlib.util.find_spec("yaml") is None:
        return None, "PyYAML not installed in venv"
    try:
        import yaml  # type: ignore

        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}, None
    except Exception as exc:  # pragma: no cover - runtime diagnostics only
        return None, str(exc)


def resolve_path(path_value: str):
    p = Path(path_value)
    if p.is_absolute():
        return p
    return root / p


def ncnn_dir_ready(path_obj: Path):
    if not path_obj.is_dir():
        return False
    has_param = any(path_obj.glob("*.param"))
    has_bin = any(path_obj.glob("*.bin"))
    return has_param and has_bin


torch_status = mod_status("torch")
torchvision_status = mod_status("torchvision")
torchaudio_status = mod_status("torchaudio")
ultralytics_status = mod_status("ultralytics")
lap_status = mod_status("lap")
ncnn_status = mod_status("ncnn")
pnnx_status = mod_status("pnnx")

torch_details = {
    "cuda_built": None,
    "cuda_available": False,
    "cuda_tensor_ok": False,
    "cuda_device": None,
    "mps_available": False,
}
if torch_status["import_ok"]:
    import torch  # type: ignore

    torch_details["cuda_built"] = getattr(getattr(torch, "version", None), "cuda", None)
    try:
        torch_details["cuda_available"] = bool(torch.cuda.is_available())
    except Exception:
        torch_details["cuda_available"] = False
    if torch_details["cuda_available"]:
        try:
            x = torch.rand((2, 2), device="cuda")
            torch_details["cuda_tensor_ok"] = bool(getattr(x, "is_cuda", False))
            torch_details["cuda_device"] = torch.cuda.get_device_name(0)
        except Exception:
            torch_details["cuda_tensor_ok"] = False
    try:
        mps_backend = getattr(torch.backends, "mps", None)
        if mps_backend is not None:
            torch_details["mps_available"] = bool(mps_backend.is_available())
    except Exception:
        torch_details["mps_available"] = False

active_config_path = config_path if config_path.exists() else default_config_path
cfg, cfg_error = load_yaml(active_config_path)
smart_cfg = {}
if isinstance(cfg, dict):
    smart_cfg = cfg.get("SmartTracker") or {}

use_gpu = bool(smart_cfg.get("SMART_TRACKER_USE_GPU", True))
fallback_to_cpu = bool(smart_cfg.get("SMART_TRACKER_FALLBACK_TO_CPU", True))
gpu_model = str(smart_cfg.get("SMART_TRACKER_GPU_MODEL_PATH", "yolo/yolo26n.pt"))
cpu_model = str(smart_cfg.get("SMART_TRACKER_CPU_MODEL_PATH", "yolo/yolo26n_ncnn_model"))

gpu_model_path = resolve_path(gpu_model)
cpu_model_path = resolve_path(cpu_model)

gpu_model_exists = gpu_model_path.exists()
cpu_model_exists = cpu_model_path.exists()
cpu_model_ncnn_ready = ncnn_dir_ready(cpu_model_path) if cpu_model_path.is_dir() else False

if use_gpu:
    if torch_details["cuda_available"] and torch_details["cuda_tensor_ok"]:
        expected_runtime = "cuda"
    elif fallback_to_cpu:
        expected_runtime = "cpu_fallback"
    else:
        expected_runtime = "gpu_required"
else:
    expected_runtime = "cpu"

cpu_backend_hint = "cpu_ncnn" if cpu_model_ncnn_ready else "cpu_torch_or_other"

payload = {
    "python": sys.version.split()[0],
    "active_config": str(active_config_path),
    "config_error": cfg_error,
    "modules": {
        "torch": torch_status,
        "torchvision": torchvision_status,
        "torchaudio": torchaudio_status,
        "ultralytics": ultralytics_status,
        "lap": lap_status,
        "ncnn": ncnn_status,
        "pnnx": pnnx_status,
    },
    "torch_runtime": torch_details,
    "smart_tracker": {
        "use_gpu": use_gpu,
        "fallback_to_cpu": fallback_to_cpu,
        "gpu_model_path": gpu_model,
        "cpu_model_path": cpu_model,
        "gpu_model_exists": gpu_model_exists,
        "cpu_model_exists": cpu_model_exists,
        "cpu_model_ncnn_ready": cpu_model_ncnn_ready,
        "expected_runtime": expected_runtime,
        "cpu_backend_hint": cpu_backend_hint,
    },
}


def status_line(name: str, status: dict):
    if not status["installed"]:
        return f"  - {name:<12}: NOT INSTALLED"
    if status["import_ok"]:
        version = status["version"] or "unknown"
        return f"  - {name:<12}: OK ({version})"
    return f"  - {name:<12}: IMPORT FAILED ({status['error']})"


print("")
print("Module checks:")
print(status_line("torch", torch_status))
print(status_line("torchvision", torchvision_status))
print(status_line("torchaudio", torchaudio_status))
print(status_line("ultralytics", ultralytics_status))
print(status_line("lap", lap_status))
print(status_line("ncnn", ncnn_status))
print(status_line("pnnx", pnnx_status))
print("")
print("Acceleration:")
print(f"  - torch CUDA build : {torch_details['cuda_built'] or 'none'}")
print(f"  - CUDA available   : {torch_details['cuda_available']}")
print(f"  - CUDA tensor test : {torch_details['cuda_tensor_ok']}")
print(f"  - CUDA device      : {torch_details['cuda_device'] or 'n/a'}")
print(f"  - MPS available    : {torch_details['mps_available']}")
print("")
print("SmartTracker config:")
print(f"  - Config file      : {active_config_path}")
print(f"  - USE_GPU          : {use_gpu}")
print(f"  - FALLBACK_TO_CPU  : {fallback_to_cpu}")
print(f"  - GPU model path   : {gpu_model} (exists={gpu_model_exists})")
print(f"  - CPU model path   : {cpu_model} (exists={cpu_model_exists}, ncnn_ready={cpu_model_ncnn_ready})")
print(f"  - Expected runtime : {expected_runtime} ({cpu_backend_hint})")
if cfg_error:
    print(f"  - Config warning   : {cfg_error}")
print("")
print("JSON:")
print(json.dumps(payload, indent=2))
PY

echo ""
log_success "AI runtime check finished"

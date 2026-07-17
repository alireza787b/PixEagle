#!/bin/bash

# ============================================================================
# scripts/setup/check-ai-runtime.sh - PixEagle AI Runtime Diagnostics
# ============================================================================
# Provides a deterministic snapshot of local AI/runtime readiness:
#   - torch/torchvision/torchaudio import and versions
#   - CUDA / MPS availability
#   - ultralytics / lap / ncnn / pnnx / dlib import health
#   - OpenCV version, contrib tracker APIs, and GStreamer support
#   - SmartTracker config intent (GPU/CPU + fallback)
#   - bounded provenance-verified model load and deterministic first inference
#
# This check does not claim tracking readiness. The probe does not call
# Ultralytics model.track() because this slice has no enforceable offline/no-
# implicit-artifact contract for that upstream path.
#
# Usage:
#   bash scripts/setup/check-ai-runtime.sh [--json] [--require-smart-tracker]
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
ORIGINAL_ARGS=("$@")
CONFIG_PATH="$PIXEAGLE_DIR/configs/config.yaml"
DEFAULT_CONFIG_PATH="$PIXEAGLE_DIR/configs/config_default.yaml"
OUTPUT_JSON=false
REQUIRE_SMART_TRACKER=false
REPORT_JSON=""

show_help() {
    cat <<'USAGE'
Usage: bash scripts/setup/check-ai-runtime.sh [OPTIONS]

Options:
  --json                    Print only the machine-readable readiness payload
  --report-json <path>      Atomically write the readiness payload to a file
  --require-smart-tracker   Exit nonzero unless dependencies and a configured
                            trusted local model complete deterministic first
                            inference; this does not prove tracking readiness
  --help, -h                Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)
            OUTPUT_JSON=true
            ;;
        --report-json)
            shift
            [[ $# -gt 0 ]] || { echo "Missing value for --report-json" >&2; exit 2; }
            REPORT_JSON="$1"
            ;;
        --require-smart-tracker)
            REQUIRE_SMART_TRACKER=true
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            show_help >&2
            exit 2
            ;;
    esac
    shift
done

require_unix_line_endings() {
    local file="$1"
    if [[ -f "$file" ]] && grep -q $'\r' "$file" 2>/dev/null; then
        echo "Refusing to rewrite tracked helper with CRLF line endings: $file" >&2
        echo "Normalize the checkout line endings, then rerun this diagnostic." >&2
        exit 2
    fi
}

require_unix_line_endings "$SCRIPTS_DIR/lib/common.sh"
# shellcheck source=/dev/null
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
    CHECK="[OK]"; CROSS="[X]"; WARN="[!]"
    log_info() { echo -e "   ${CYAN}[*]${NC} $1"; }
    log_success() { echo -e "   ${GREEN}${CHECK}${NC} $1"; }
    log_warn() { echo -e "   ${YELLOW}${WARN}${NC} $1"; }
    log_error() { echo -e "   ${RED}${CROSS}${NC} $1"; }
    display_pixeagle_banner() { echo -e "\n${CYAN}${BOLD}PixEagle${NC}\n"; }
fi
# shellcheck source=scripts/lib/setup_lock.sh
if ! source "$SCRIPTS_DIR/lib/setup_lock.sh" 2>/dev/null; then
    echo "Error: Could not source the required environment lock helper" >&2
    exit 1
fi

if declare -F resolve_pixeagle_venv_dir >/dev/null 2>&1; then
    VENV_DIR="$(resolve_pixeagle_venv_dir "$PIXEAGLE_DIR")"
else
    VENV_DIR="${PIXEAGLE_VENV_DIR:-$PIXEAGLE_DIR/venv}"
fi
VENV_PYTHON="$VENV_DIR/bin/python"

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    if pixeagle_setup_lock_context_present; then
        pixeagle_acquire_setup_lock "$VENV_DIR" "AI runtime verification" 30 || exit 1
    elif pixeagle_shared_setup_lock_context_present; then
        pixeagle_validate_shared_setup_lock_context "$VENV_DIR" || exit 1
    else
        if pixeagle_run_with_shared_setup_lock \
            "$VENV_DIR" "AI runtime verification" 30 \
            bash "${BASH_SOURCE[0]}" "${ORIGINAL_ARGS[@]}"; then
            exit 0
        else
            exit $?
        fi
    fi
fi

if [[ ! -f "$VENV_PYTHON" ]]; then
    log_error "Virtual environment Python not found: $VENV_PYTHON"
    log_info "Run: make init"
    exit 1
fi

if [[ "$OUTPUT_JSON" != "true" ]]; then
    display_pixeagle_banner "AI Runtime Check" "SmartTracker local first-inference check"
    log_info "Project: $PIXEAGLE_DIR"
    log_info "Python:  $VENV_PYTHON"
fi

"$VENV_PYTHON" - "$PIXEAGLE_DIR" "$CONFIG_PATH" "$DEFAULT_CONFIG_PATH" \
    "$OUTPUT_JSON" "$REPORT_JSON" "$REQUIRE_SMART_TRACKER" <<'PY'
import importlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


root = Path(sys.argv[1])
config_path = Path(sys.argv[2])
default_config_path = Path(sys.argv[3])
output_json = sys.argv[4].lower() == "true"
report_json = sys.argv[5]
require_smart_tracker = sys.argv[6].lower() == "true"
sys.path.insert(0, str(root / "scripts" / "setup"))

from ai_runtime_probe import probe_smart_tracker_model


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
dlib_status = mod_status("dlib")
cv2_status = mod_status("cv2")

opencv_details = {
    "version": None,
    "gstreamer": None,
    "ffmpeg": None,
    "tracker_csrt": False,
    "tracker_kcf": False,
    "legacy_tracker_csrt": False,
    "legacy_tracker_kcf": False,
}
if cv2_status["import_ok"]:
    import cv2  # type: ignore

    opencv_details["version"] = getattr(cv2, "__version__", None)
    try:
        build_info = cv2.getBuildInformation()
    except Exception:
        build_info = ""

    def build_flag(label: str):
        if not build_info:
            return None
        marker = f"{label}:"
        if marker not in build_info:
            return None
        value = build_info.split(marker, 1)[1].splitlines()[0].strip()
        return value

    opencv_details["gstreamer"] = build_flag("GStreamer")
    opencv_details["ffmpeg"] = build_flag("FFMPEG")
    opencv_details["tracker_csrt"] = hasattr(cv2, "TrackerCSRT_create")
    opencv_details["tracker_kcf"] = hasattr(cv2, "TrackerKCF_create")
    legacy = getattr(cv2, "legacy", None)
    if legacy is not None:
        opencv_details["legacy_tracker_csrt"] = hasattr(legacy, "TrackerCSRT_create")
        opencv_details["legacy_tracker_kcf"] = hasattr(legacy, "TrackerKCF_create")

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
gpu_model = str(smart_cfg.get("SMART_TRACKER_GPU_MODEL_PATH", "models/yolo26n.pt"))
cpu_model = str(smart_cfg.get("SMART_TRACKER_CPU_MODEL_PATH", "models/yolo26n_ncnn_model"))

gpu_model_path = resolve_path(gpu_model)
cpu_model_path = resolve_path(cpu_model)

gpu_model_exists = gpu_model_path.exists()
cpu_model_exists = cpu_model_path.exists()
cpu_model_ncnn_ready = ncnn_dir_ready(cpu_model_path) if cpu_model_path.is_dir() else False
gpu_model_file_ready = gpu_model_path.is_file()
cpu_model_file_ready = cpu_model_path.is_file()

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
required_modules_ready = all(
    status["import_ok"]
    for status in (torch_status, ultralytics_status, lap_status, cv2_status)
)
model_probe = (
    probe_smart_tracker_model(root, smart_cfg, timeout_seconds=60.0)
    if not cfg_error
    else {
        "attempted": False,
        "candidate_available": False,
        "candidate_paths": [],
        "load_ready": False,
        "provenance_ready": False,
        "model_provenance": None,
        "inference_attempted": False,
        "first_inference_ready": False,
        "inference": None,
        "tracking_probe": {
            "attempted": False,
            "ready": None,
            "reason": "not_probed_no_offline_side_effect_contract",
        },
        "task": None,
        "runtime": None,
        "reason": "config_unavailable",
        "error": cfg_error,
        "timed_out": False,
    }
)
model_candidate_ready = bool(model_probe["candidate_available"])
model_load_ready = bool(model_probe["load_ready"])
model_provenance_ready = bool(model_probe["provenance_ready"])
first_inference_ready = bool(model_probe["first_inference_ready"])
configured_inference_ready = bool(
    required_modules_ready
    and model_provenance_ready
    and first_inference_ready
    and not cfg_error
)

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
        "dlib": dlib_status,
        "cv2": cv2_status,
    },
    "opencv": opencv_details,
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
    "model_probe": model_probe,
    "readiness": {
        "required_modules_ready": required_modules_ready,
        "model_candidate_ready": model_candidate_ready,
        "model_load_ready": model_load_ready,
        "model_provenance_ready": model_provenance_ready,
        "first_inference_ready": first_inference_ready,
        "configured_inference_ready": configured_inference_ready,
        "tracking_ready": model_probe["tracking_probe"]["ready"],
        "claim": "configured_local_model_first_inference",
        "reason": (
            "first_inference_succeeded"
            if configured_inference_ready
            else "config_unavailable"
            if cfg_error
            else "required_module_unavailable"
            if not required_modules_ready
            else model_probe["reason"]
        ),
    },
}


def status_line(name: str, status: dict):
    if not status["installed"]:
        return f"  - {name:<12}: NOT INSTALLED"
    if status["import_ok"]:
        version = status["version"] or "unknown"
        return f"  - {name:<12}: OK ({version})"
    return f"  - {name:<12}: IMPORT FAILED ({status['error']})"


encoded = json.dumps(payload, indent=2)

if report_json:
    destination = Path(report_json).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(encoded + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, destination)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(temp_name).unlink(missing_ok=True)
        raise

if output_json:
    print(encoded)
else:
    print("")
    print("Module checks:")
    print(status_line("torch", torch_status))
    print(status_line("torchvision", torchvision_status))
    print(status_line("torchaudio", torchaudio_status))
    print(status_line("ultralytics", ultralytics_status))
    print(status_line("lap", lap_status))
    print(status_line("ncnn", ncnn_status))
    print(status_line("pnnx", pnnx_status))
    print(status_line("dlib", dlib_status))
    print(status_line("cv2", cv2_status))
    print("")
    print("Acceleration:")
    print(f"  - torch CUDA build : {torch_details['cuda_built'] or 'none'}")
    print(f"  - CUDA available   : {torch_details['cuda_available']}")
    print(f"  - CUDA tensor test : {torch_details['cuda_tensor_ok']}")
    print(f"  - CUDA device      : {torch_details['cuda_device'] or 'n/a'}")
    print(f"  - MPS available    : {torch_details['mps_available']}")
    print("")
    print("OpenCV:")
    print(f"  - Version          : {opencv_details['version'] or 'n/a'}")
    print(f"  - GStreamer        : {opencv_details['gstreamer'] or 'n/a'}")
    print(f"  - FFMPEG           : {opencv_details['ffmpeg'] or 'n/a'}")
    print(f"  - Tracker CSRT API : {opencv_details['tracker_csrt'] or opencv_details['legacy_tracker_csrt']}")
    print(f"  - Tracker KCF API  : {opencv_details['tracker_kcf'] or opencv_details['legacy_tracker_kcf']}")
    print("")
    print("SmartTracker config:")
    print(f"  - Config file      : {active_config_path}")
    print(f"  - USE_GPU          : {use_gpu}")
    print(f"  - FALLBACK_TO_CPU  : {fallback_to_cpu}")
    print(f"  - GPU model path   : {gpu_model} (exists={gpu_model_exists})")
    print(f"  - CPU model path   : {cpu_model} (exists={cpu_model_exists}, ncnn_ready={cpu_model_ncnn_ready})")
    print(f"  - Expected runtime : {expected_runtime} ({cpu_backend_hint})")
    print(f"  - Probe result     : {model_probe['reason']} (task={model_probe['task'] or 'n/a'})")
    print(f"  - Model loaded     : {model_load_ready}")
    print(f"  - Provenance       : {model_provenance_ready}")
    if model_probe.get("model_provenance"):
        print(f"  - Artifact SHA-256 : {model_probe['model_provenance'].get('sha256', 'n/a')}")
    print(f"  - First inference  : {first_inference_ready}")
    print("  - Tracking probe   : not run (offline/no-implicit-artifact contract unavailable)")
    if model_probe.get("error"):
        print(f"  - Probe error      : {model_probe['error']}")
    print(f"  - Inference gate   : {configured_inference_ready} ({payload['readiness']['reason']})")
    if cfg_error:
        print(f"  - Config warning   : {cfg_error}")
    print("")
    print("JSON:")
    print(encoded)

if require_smart_tracker and not configured_inference_ready:
    raise SystemExit(2)
PY

if [[ "$OUTPUT_JSON" != "true" ]]; then
    echo ""
    log_success "AI runtime check finished"
fi

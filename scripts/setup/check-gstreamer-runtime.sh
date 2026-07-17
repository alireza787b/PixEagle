#!/usr/bin/env bash

# Verify the shared GStreamer prerequisites used by OpenCV capture pipelines
# and PixEagle's H.264/RTP/UDP output to QGroundControl.

set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"

if [[ -f "$SCRIPTS_DIR/lib/common.sh" ]]; then
    # shellcheck source=/dev/null
    source "$SCRIPTS_DIR/lib/common.sh"
fi

if declare -F resolve_pixeagle_venv_python >/dev/null 2>&1; then
    VENV_PYTHON="$(resolve_pixeagle_venv_python "$PIXEAGLE_DIR")"
else
    VENV_PYTHON="${PIXEAGLE_VENV_DIR:-$PIXEAGLE_DIR/venv}/bin/python"
fi

failures=0

pass() { printf '[OK]   %s\n' "$1"; }
fail() { printf '[FAIL] %s\n' "$1"; failures=$((failures + 1)); }
info() { printf '[INFO] %s\n' "$1"; }

printf 'PixEagle GStreamer runtime check\n'
printf 'Python: %s\n\n' "$VENV_PYTHON"

if [[ ! -x "$VENV_PYTHON" ]]; then
    fail "PixEagle virtual-environment Python was not found"
    info "Run make init first, or set PIXEAGLE_VENV_DIR"
    exit 1
fi

opencv_report="$($VENV_PYTHON - <<'PY'
try:
    import cv2
except Exception as exc:
    print(f"IMPORT_ERROR:{type(exc).__name__}")
    raise SystemExit(0)

flag = "UNKNOWN"
for line in cv2.getBuildInformation().splitlines():
    if line.strip().startswith("GStreamer:"):
        value = line.split(":", 1)[1].strip().upper()
        flag = "YES" if value.startswith("YES") else "NO"
        break
print(f"VERSION:{cv2.__version__}")
print(f"GSTREAMER:{flag}")
PY
)"

opencv_version="$(printf '%s\n' "$opencv_report" | sed -n 's/^VERSION://p')"
opencv_gstreamer="$(printf '%s\n' "$opencv_report" | sed -n 's/^GSTREAMER://p')"
opencv_error="$(printf '%s\n' "$opencv_report" | sed -n 's/^IMPORT_ERROR://p')"

if [[ -n "$opencv_error" ]]; then
    fail "OpenCV import failed ($opencv_error)"
elif [[ "$opencv_gstreamer" == "YES" ]]; then
    pass "OpenCV ${opencv_version:-unknown} reports GStreamer: YES"
else
    fail "OpenCV ${opencv_version:-unknown} does not report GStreamer: YES"
    info "Build the optional backend with: bash scripts/setup/build-opencv.sh"
fi

gst_inspect="$(command -v gst-inspect-1.0 2>/dev/null || true)"
if [[ -z "$gst_inspect" ]]; then
    fail "gst-inspect-1.0 is unavailable"
else
    pass "GStreamer plugin inspector: $gst_inspect"
fi

required_elements=(appsrc videoconvert x264enc rtph264pay udpsink)
if [[ -n "$gst_inspect" ]]; then
    for element in "${required_elements[@]}"; do
        if "$gst_inspect" "$element" >/dev/null 2>&1; then
            pass "Required QGC UDP element: $element"
        else
            fail "Missing required QGC UDP element: $element"
        fi
    done
fi

config_report="$(
    cd "$PIXEAGLE_DIR" || exit 1
    PYTHONPATH="$PIXEAGLE_DIR/src" "$VENV_PYTHON" - <<'PY'
try:
    from classes.parameters import Parameters
except Exception as exc:
    print(f"CONFIG_ERROR:{type(exc).__name__}")
    raise SystemExit(0)

print(f"HARDWARE:{str(bool(getattr(Parameters, 'ENABLE_HARDWARE_ENCODING', False))).lower()}")
PY
)"
hardware_enabled="$(printf '%s\n' "$config_report" | sed -n 's/^HARDWARE://p')"
config_error="$(printf '%s\n' "$config_report" | sed -n 's/^CONFIG_ERROR://p')"

if [[ -n "$config_error" ]]; then
    fail "Could not resolve the effective PixEagle GStreamer configuration ($config_error)"
    hardware_enabled="false"
elif [[ "$hardware_enabled" == "true" ]]; then
    info "Effective config enables supported hardware-encoder probing"
else
    info "Effective config selects the x264enc software path"
fi

selected_encoder="x264enc"
if [[ "$hardware_enabled" == "true" && -n "$gst_inspect" ]]; then
    if "$gst_inspect" nvh264enc >/dev/null 2>&1; then
        selected_encoder="nvh264enc"
    elif "$gst_inspect" vaapih264enc >/dev/null 2>&1; then
        selected_encoder="vaapih264enc"
    else
        info "No supported hardware encoder was discovered; runtime will fall back to x264enc"
    fi
fi

if [[ -n "$gst_inspect" ]] && "$gst_inspect" "$selected_encoder" >/dev/null 2>&1; then
    pass "Effective H.264 encoder path: $selected_encoder"
else
    fail "Effective H.264 encoder is unavailable: $selected_encoder"
fi

if [[ "$selected_encoder" != "x264enc" && -n "$gst_inspect" ]]; then
    if "$gst_inspect" h264parse >/dev/null 2>&1; then
        pass "Required hardware-encoder parser: h264parse"
    else
        fail "Missing h264parse required by the selected hardware-encoder path"
    fi
fi

if [[ -n "$gst_inspect" ]] && "$gst_inspect" nvv4l2h264enc >/dev/null 2>&1; then
    info "Jetson nvv4l2h264enc is installed but is not yet auto-selected by PixEagle"
fi
if [[ -n "$gst_inspect" ]] && "$gst_inspect" v4l2h264enc >/dev/null 2>&1; then
    info "v4l2h264enc is installed but is not yet auto-selected by PixEagle"
fi

printf '\n'
if [[ $failures -eq 0 ]]; then
    pass "Baseline OpenCV/GStreamer and QGC H.264/RTP/UDP prerequisites are ready"
    info "This capability check does not prove camera ingest or receiver playback"
    exit 0
fi

printf '[FAIL] %s prerequisite check(s) failed\n' "$failures"
info "HTTP MJPEG/WebSocket dashboard media can still work when only GStreamer is unavailable"
exit 1

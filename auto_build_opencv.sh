#!/usr/bin/env bash
# =============================================================================
# Project:      PixEagle
# Script:       auto_build_opencv.sh
# Description:  Automates building OpenCV v4.9.0 with GStreamer, Qt, and OpenGL
# Author:       Alireza Ghaderi <you@example.com>
# Date:         2025-05-01
# Version:      1.1.1
# Usage:        $(basename "$0") [-h|--help] [-v|--version]
# Prereqs:      Debian-based Linux; ≥2 GB free RAM; Git; Python 3; pkg-config
# License:      MIT License (see LICENSE file)
# =============================================================================

set -euo pipefail  # fail on error, undefined var, or failed pipe :contentReference[oaicite:2]{index=2}

###--------------------------------------------------------------------------###
###                          Utility Functions                              ###
###--------------------------------------------------------------------------###

print_info() {
    # print_info: standardized informational messages
    echo -e "\n[INFO] $1"
}

print_error() {
    # print_error: standardized error + exit
    echo -e "\n[ERROR] $1" >&2
    exit 1
}

print_usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  -h, --help      Show this help message
  -v, --version   Show script version
EOF
}

VERSION="1.1.1"  # bump when changes affect behavior :contentReference[oaicite:3]{index=3}

###--------------------------------------------------------------------------###
###                     Parse Command-Line Flags                            ###
###--------------------------------------------------------------------------###

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            print_usage
            exit 0
            ;;
        -v|--version)
            echo "$(basename "$0") version $VERSION"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            ;;
    esac
done

###--------------------------------------------------------------------------###
###               1. Install System Dependencies                            ###
###--------------------------------------------------------------------------###

print_info "Step 1: Updating system and installing dependencies"
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y build-essential cmake git pkg-config \
    libgtk2.0-dev \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-tools gstreamer1.0-libav gstreamer1.0-gl \
    gstreamer1.0-gtk3 gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly

###--------------------------------------------------------------------------###
###                    2. GStreamer Environment                             ###
###--------------------------------------------------------------------------###

print_info "Step 2: Configuring GStreamer environment"
# Ensure pkg-config finds GStreamer .pc files
export PKG_CONFIG_PATH=/usr/lib/pkgconfig
# Tell GStreamer where its plugins live
export GST_PLUGIN_PATH=/usr/lib/gstreamer-1.0

###--------------------------------------------------------------------------###
###                  3. Clone/OpenCV & Contrib Repos                        ###
###--------------------------------------------------------------------------###

PIX_DIR="$HOME/PixEagle"
OPENCV_VERSION="4.9.0"

print_info "Step 3: Preparing project directory at $PIX_DIR"
mkdir -p "$PIX_DIR"
cd "$PIX_DIR"

# TODO: allow overriding OPENCV_VERSION via CLI
for repo in opencv opencv_contrib; do
    DIR="$PIX_DIR/$repo"
    URL="https://github.com/opencv/$repo.git"
    if [[ ! -d "$DIR" ]]; then
        print_info "Cloning $repo..."
        git clone "$URL" "$DIR"
    else
        print_info "Fetching updates for $repo..."
        git -C "$DIR" fetch --all
    fi
    git -C "$DIR" checkout "$OPENCV_VERSION"
done

###--------------------------------------------------------------------------###
###                   4. Python Virtualenv Setup                             ###
###--------------------------------------------------------------------------###

VENV_DIR="$PIX_DIR/venv"
print_info "Step 4: Setting up Python virtualenv at $VENV_DIR"
python3 -m venv "$VENV_DIR"  # includes pip by default
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

print_info "Uninstalling any existing OpenCV pip packages"
pip uninstall -y opencv-python opencv-contrib-python \
    || echo "[INFO] No existing OpenCV pip packages found."

###--------------------------------------------------------------------------###
###                         5. Build Directory                               ###
###--------------------------------------------------------------------------###

print_info "Step 5: Creating build directory"
cd "$PIX_DIR/opencv"
rm -rf build
mkdir build && cd build

###--------------------------------------------------------------------------###
###                       6. CMake Configuration                             ###
###--------------------------------------------------------------------------###

print_info "Step 6: Configuring build with CMake"
cmake .. \
    -D CMAKE_BUILD_TYPE=Release \
    -D CMAKE_INSTALL_PREFIX="$VENV_DIR" \
    -D OPENCV_EXTRA_MODULES_PATH="$PIX_DIR/opencv_contrib/modules" \
    -D WITH_GSTREAMER=ON \
    -D WITH_QT=ON \
    -D WITH_OPENGL=ON \
    -D BUILD_EXAMPLES=ON \
    -D Python3_FIND_REGISTRY=NEVER \
    -D Python3_FIND_IMPLEMENTATIONS=CPython \
    -D Python3_FIND_STRATEGY=LOCATION

###--------------------------------------------------------------------------###
###                      7. Compile & Install                                ###
###--------------------------------------------------------------------------###

print_info "Step 7: Compiling OpenCV (all CPU cores)"
make -j"$(nproc)"

print_info "Step 8: Installing into virtualenv"
make install

###--------------------------------------------------------------------------###
###               8. Verify GStreamer Support & Finalize                     ###
###--------------------------------------------------------------------------###

print_info "Step 9: Verifying GStreamer support in cv2 build output"
# Capture build info in a variable to avoid here-doc mismatch :contentReference[oaicite:4]{index=4}
BUILD_INFO=$(python - <<'EOF'
import cv2
print(cv2.getBuildInformation())
EOF
) 2>/dev/null

if echo "$BUILD_INFO" | grep -q "GStreamer:.*YES"; then
    print_info "GStreamer support ENABLED in OpenCV build"
else
    print_error "GStreamer support NOT enabled—please inspect CMake logs"
fi

# Final success message
print_info "SUCCESS: OpenCV $OPENCV_VERSION built with GStreamer, Qt, OpenGL, and installed into venv at $VENV_DIR."

exit 0

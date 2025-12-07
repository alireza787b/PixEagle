#!/bin/bash
# install_opencv_gstreamer.sh
# Professional OpenCV build script with full GStreamer, FFMPEG, and GTK support
# for Raspberry Pi virtual environment installation.
#
# Features enabled:
#   - GStreamer (RTSP streaming, hardware acceleration)
#   - FFMPEG (codec fallback, broad format support)
#   - GTK3 (GUI support for non-headless systems)
#   - V4L2 (USB camera support)
#   - OpenGL (GPU acceleration)
#   - Python3 bindings (installed to venv)
#
# Usage:
#   1. Activate your virtual environment:
#      source ~/PixEagle/venv/bin/activate
#   2. Run this script:
#      bash ~/PixEagle/src/tools/install_opencv_gstreamer.sh
#
# Author: Alireza Ghaderi
# Date: Feb 2025
# Updated: Dec 2025

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}==================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}==================================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

check_error() {
    if [ $? -ne 0 ]; then
        print_error "ERROR during: $1"
        exit 1
    fi
}

# Configuration
OPENCV_VERSION="4.9.0"
BASE_DIR="$HOME/PixEagle"
OPENCV_DIR="$BASE_DIR/opencv"
OPENCV_CONTRIB_DIR="$BASE_DIR/opencv_contrib"

print_header "OpenCV $OPENCV_VERSION Installation with Full Video Support"

# =============================================================================
# Step 1: Verify Virtual Environment
# =============================================================================
echo ""
echo "Step 1/10: Verifying virtual environment..."

if [ -z "$VIRTUAL_ENV" ]; then
    print_error "No virtual environment detected!"
    echo "Please activate your virtual environment first:"
    echo "  source ~/PixEagle/venv/bin/activate"
    exit 1
fi

print_success "Virtual environment: $VIRTUAL_ENV"

# =============================================================================
# Step 2: Determine Python Configuration
# =============================================================================
echo ""
echo "Step 2/10: Detecting Python configuration..."

PYTHON_EXECUTABLE=$(which python)
PYTHON_VERSION=$($PYTHON_EXECUTABLE --version 2>&1)
PYTHON_INCLUDE_DIR=$($PYTHON_EXECUTABLE -c "from sysconfig import get_paths; print(get_paths()['include'])")
PYTHON_PACKAGES_PATH=$($PYTHON_EXECUTABLE -c "from sysconfig import get_paths; print(get_paths()['purelib'])")

echo "  Python executable: $PYTHON_EXECUTABLE"
echo "  Python version: $PYTHON_VERSION"
echo "  Include directory: $PYTHON_INCLUDE_DIR"
echo "  Packages path: $PYTHON_PACKAGES_PATH"

# Verify numpy is installed (required for cv2 Python bindings)
if ! $PYTHON_EXECUTABLE -c "import numpy" 2>/dev/null; then
    print_warning "NumPy not found. Installing..."
    pip install numpy
    check_error "NumPy installation"
fi
print_success "NumPy available"

# =============================================================================
# Step 3: Update System
# =============================================================================
echo ""
echo "Step 3/10: Updating system packages..."

sudo apt-get update
check_error "apt-get update"

# Optional: upgrade (can be slow, uncomment if needed)
# sudo apt-get upgrade -y

# =============================================================================
# Step 4: Install Build Dependencies
# =============================================================================
echo ""
echo "Step 4/10: Installing build dependencies..."

sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    pkg-config \
    ninja-build
check_error "Build tools installation"
print_success "Build tools installed"

# =============================================================================
# Step 5: Install GStreamer (Full Stack for RTSP)
# =============================================================================
echo ""
echo "Step 5/10: Installing GStreamer with RTSP support..."

sudo apt-get install -y \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-gl \
    gstreamer1.0-gtk3 \
    gstreamer1.0-rtsp \
    libgstrtspserver-1.0-dev
check_error "GStreamer installation"
print_success "GStreamer installed"

# Verify GStreamer RTSP plugin
if gst-inspect-1.0 rtspsrc > /dev/null 2>&1; then
    print_success "GStreamer rtspsrc plugin verified"
else
    print_warning "GStreamer rtspsrc not found - RTSP may not work"
fi

# =============================================================================
# Step 6: Install FFMPEG Development Libraries
# =============================================================================
echo ""
echo "Step 6/10: Installing FFMPEG libraries..."

sudo apt-get install -y \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libavfilter-dev \
    libpostproc-dev
check_error "FFMPEG installation"
print_success "FFMPEG libraries installed"

# =============================================================================
# Step 7: Install GUI and Image Libraries
# =============================================================================
echo ""
echo "Step 7/10: Installing GUI and image libraries..."

sudo apt-get install -y \
    libgtk-3-dev \
    libgtk2.0-dev \
    libcanberra-gtk3-module \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libwebp-dev \
    libopenexr-dev \
    libv4l-dev \
    v4l-utils \
    libdc1394-dev \
    libtbb-dev \
    libeigen3-dev \
    liblapack-dev \
    libopenblas-dev
check_error "GUI and image libraries installation"
print_success "GUI and image libraries installed"

# =============================================================================
# Step 8: Clone/Update OpenCV Repositories
# =============================================================================
echo ""
echo "Step 8/10: Setting up OpenCV source code..."

# Clone or update OpenCV
if [ ! -d "$OPENCV_DIR" ]; then
    echo "  Cloning OpenCV repository..."
    git clone --depth 1 --branch $OPENCV_VERSION https://github.com/opencv/opencv.git "$OPENCV_DIR"
    check_error "OpenCV clone"
else
    echo "  OpenCV repository exists, checking out version $OPENCV_VERSION..."
    cd "$OPENCV_DIR"
    git fetch --depth 1 origin tag $OPENCV_VERSION
    git checkout $OPENCV_VERSION
fi
print_success "OpenCV $OPENCV_VERSION ready"

# Clone or update OpenCV Contrib
if [ ! -d "$OPENCV_CONTRIB_DIR" ]; then
    echo "  Cloning OpenCV Contrib repository..."
    git clone --depth 1 --branch $OPENCV_VERSION https://github.com/opencv/opencv_contrib.git "$OPENCV_CONTRIB_DIR"
    check_error "OpenCV Contrib clone"
else
    echo "  OpenCV Contrib repository exists, checking out version $OPENCV_VERSION..."
    cd "$OPENCV_CONTRIB_DIR"
    git fetch --depth 1 origin tag $OPENCV_VERSION
    git checkout $OPENCV_VERSION
fi
print_success "OpenCV Contrib $OPENCV_VERSION ready"

# =============================================================================
# Step 9: Configure and Build OpenCV
# =============================================================================
echo ""
echo "Step 9/10: Configuring and building OpenCV (this takes 30-60 minutes)..."

BUILD_DIR="$OPENCV_DIR/build"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

echo "  Running CMake configuration..."
cmake -G Ninja \
    -D CMAKE_BUILD_TYPE=Release \
    -D CMAKE_INSTALL_PREFIX="$VIRTUAL_ENV" \
    -D OPENCV_EXTRA_MODULES_PATH="$OPENCV_CONTRIB_DIR/modules" \
    \
    -D WITH_GSTREAMER=ON \
    -D WITH_FFMPEG=ON \
    -D WITH_GTK=ON \
    -D WITH_GTK_2_X=OFF \
    -D WITH_V4L=ON \
    -D WITH_LIBV4L=ON \
    -D WITH_OPENGL=ON \
    -D WITH_TBB=ON \
    -D WITH_EIGEN=ON \
    -D WITH_LAPACK=ON \
    \
    -D BUILD_opencv_python3=ON \
    -D PYTHON3_EXECUTABLE="$PYTHON_EXECUTABLE" \
    -D PYTHON3_INCLUDE_DIR="$PYTHON_INCLUDE_DIR" \
    -D PYTHON3_PACKAGES_PATH="$PYTHON_PACKAGES_PATH" \
    -D OPENCV_PYTHON3_INSTALL_PATH="$PYTHON_PACKAGES_PATH" \
    \
    -D BUILD_EXAMPLES=OFF \
    -D BUILD_TESTS=OFF \
    -D BUILD_PERF_TESTS=OFF \
    -D BUILD_DOCS=OFF \
    -D INSTALL_C_EXAMPLES=OFF \
    -D INSTALL_PYTHON_EXAMPLES=OFF \
    \
    -D OPENCV_GENERATE_PKGCONFIG=ON \
    -D OPENCV_ENABLE_NONFREE=ON \
    .. 2>&1 | tee cmake_output.log

check_error "CMake configuration"
print_success "CMake configuration complete"

# Show key configuration from CMake output
echo ""
echo "  Key build configuration:"
grep -E "GStreamer:|FFMPEG:|GTK\+:|V4L/V4L2:|Python 3:" cmake_output.log | head -10 || true

echo ""
echo "  Building with $(nproc) cores..."
ninja -j$(nproc)
check_error "OpenCV build"
print_success "OpenCV build complete"

# =============================================================================
# Step 10: Install and Verify
# =============================================================================
echo ""
echo "Step 10/10: Installing and verifying..."

cmake --install .
check_error "OpenCV installation"

# Update linker cache
sudo ldconfig

print_success "OpenCV installed to $VIRTUAL_ENV"

# =============================================================================
# Verification
# =============================================================================
print_header "Verifying Installation"

echo ""
echo "Checking OpenCV Python import..."
if $PYTHON_EXECUTABLE -c "import cv2; print(f'OpenCV version: {cv2.__version__}')" 2>/dev/null; then
    print_success "OpenCV Python bindings work"
else
    print_error "OpenCV Python import failed!"
    echo "Check if cv2*.so exists in: $PYTHON_PACKAGES_PATH"
    ls -la "$PYTHON_PACKAGES_PATH"/cv2* 2>/dev/null || echo "No cv2 files found"
    exit 1
fi

echo ""
echo "Checking video backend support..."
$PYTHON_EXECUTABLE << 'EOF'
import cv2

build_info = cv2.getBuildInformation()

# Check key features
features = {
    'GStreamer': 'GStreamer:                   YES' in build_info,
    'FFMPEG': 'FFMPEG:                      YES' in build_info,
    'GTK+': 'GTK+:                        YES' in build_info or 'GTK+' in build_info and 'YES' in build_info.split('GTK+')[1][:50],
    'V4L/V4L2': 'V4L/V4L2:                    YES' in build_info,
}

print("\nVideo Backend Status:")
print("-" * 40)
for feature, enabled in features.items():
    status = "✓ YES" if enabled else "✗ NO"
    print(f"  {feature:15} {status}")

# Count enabled features
enabled_count = sum(features.values())
print("-" * 40)
print(f"  {enabled_count}/4 backends enabled")

if not features['GStreamer']:
    print("\n⚠ WARNING: GStreamer not enabled - RTSP streaming may not work!")
EOF

echo ""
print_header "Installation Complete!"
echo ""
echo "To verify full build info, run:"
echo "  python -c \"import cv2; print(cv2.getBuildInformation())\""
echo ""
echo "To test RTSP streaming:"
echo "  python -c \"import cv2; cap = cv2.VideoCapture('rtspsrc location=rtsp://IP:554/stream ! decodebin ! videoconvert ! appsink', cv2.CAP_GSTREAMER); print('OK' if cap.isOpened() else 'FAIL')\""
echo ""

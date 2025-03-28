#!/bin/bash
# auto_build_opencv.sh
# This script automates building OpenCV with GStreamer support for the PixEagle project.
# It installs necessary dependencies, sets environment variables, clones the required repositories,
# activates a Python virtual environment, builds OpenCV using CMake, and verifies that GStreamer is enabled.
# Author: Your Name | Date: August 2024

set -e  # Exit immediately if a command exits with a non-zero status

#############################
# Utility Functions
#############################

# Print info messages with step numbering
print_info() {
    echo -e "\n[INFO] $1\n"
}

# Print error messages and exit
print_error() {
    echo -e "\n[ERROR] $1\n"
    exit 1
}

#############################
# 1. Update System and Install Dependencies
#############################

print_info "Step 1: Updating system and installing dependencies"
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y build-essential cmake git pkg-config libgtk2.0-dev
sudo apt-get install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
                        gstreamer1.0-tools gstreamer1.0-libav gstreamer1.0-gl \
                        gstreamer1.0-gtk3 gstreamer1.0-plugins-good \
                        gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly

#############################
# 2. Set Environment Variables for GStreamer
#############################

print_info "Step 2: Setting environment variables"
export PKG_CONFIG_PATH=/usr/lib/pkgconfig
export GST_PLUGIN_PATH=/usr/lib/gstreamer-1.0

#############################
# 3. Create Project Directory and Clone Repositories
#############################

PIX_DIR="$HOME/PixEagle"
OPENCV_DIR="$PIX_DIR/opencv"
OPENCV_CONTRIB_DIR="$PIX_DIR/opencv_contrib"
OPENCV_VERSION="4.9.0"

print_info "Step 3: Setting up project directory at $PIX_DIR"
mkdir -p "$PIX_DIR"
cd "$PIX_DIR"

# Clone or update OpenCV repository
if [ ! -d "$OPENCV_DIR" ]; then
    print_info "Cloning OpenCV repository..."
    git clone https://github.com/opencv/opencv.git
else
    print_info "OpenCV repository already exists. Skipping clone."
fi

# Checkout the specified version for OpenCV
cd "$OPENCV_DIR"
git fetch --all
git checkout "$OPENCV_VERSION"

# Clone or update OpenCV Contrib repository
cd "$PIX_DIR"
if [ ! -d "$OPENCV_CONTRIB_DIR" ]; then
    print_info "Cloning OpenCV Contrib repository..."
    git clone https://github.com/opencv/opencv_contrib.git
else
    print_info "OpenCV Contrib repository already exists. Skipping clone."
fi

cd "$OPENCV_CONTRIB_DIR"
git fetch --all
git checkout "$OPENCV_VERSION"

#############################
# 4. Activate Python Virtual Environment and Remove Existing OpenCV Installations
#############################

VENV_DIR="$PIX_DIR/venv"

print_info "Step 4: Activating Python virtual environment"
if [ -d "$VENV_DIR" ]; then
    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"
else
    print_error "Virtual environment not found at $VENV_DIR. Please create one before running this script."
fi

print_info "Removing any pre-installed OpenCV packages from the virtual environment"
pip uninstall -y opencv-python opencv-contrib-python || echo "[INFO] No previous OpenCV packages found."

#############################
# 5. Create Build Directory
#############################

print_info "Step 5: Preparing the build directory"
cd "$OPENCV_DIR"
if [ -d "build" ]; then
    print_info "Removing previous build directory..."
    rm -rf build
fi
mkdir build && cd build

#############################
# 6. Configure the Build with CMake
#############################

print_info "Step 6: Configuring the build with CMake"
# Get Python paths dynamically from the activated virtual environment
PYTHON_EXECUTABLE=$(which python)
PYTHON_INCLUDE_DIR=$(python -c "from distutils.sysconfig import get_python_inc(); print(get_python_inc())")
PYTHON_PACKAGES_PATH=$(python -c "from distutils.sysconfig import get_python_lib(); print(get_python_lib())")

cmake -D CMAKE_BUILD_TYPE=Release \
      -D CMAKE_INSTALL_PREFIX="$VENV_DIR" \
      -D OPENCV_EXTRA_MODULES_PATH="$OPENCV_CONTRIB_DIR/modules" \
      -D WITH_GSTREAMER=ON \
      -D WITH_QT=ON \
      -D WITH_OPENGL=ON \
      -D BUILD_EXAMPLES=ON \
      -D PYTHON3_EXECUTABLE="$PYTHON_EXECUTABLE" \
      -D PYTHON3_INCLUDE_DIR="$PYTHON_INCLUDE_DIR" \
      -D PYTHON3_PACKAGES_PATH="$PYTHON_PACKAGES_PATH" \
      ..

#############################
# 7. Compile and Install OpenCV
#############################

print_info "Step 7: Compiling OpenCV (this may take a while)..."
make -j"$(nproc)"

print_info "Installing OpenCV into the virtual environment"
make install

#############################
# 8. Verify GStreamer Support in OpenCV Build
#############################

print_info "Step 8: Verifying OpenCV build information for GStreamer support"
BUILD_INFO=$(python -c "import cv2; print(cv2.getBuildInformation())")
echo "$BUILD_INFO" | grep "GStreamer: YES" > /dev/null && \
    print_info "Verification successful: GStreamer support is ENABLED in OpenCV" || \
    print_error "GStreamer support is NOT enabled in the OpenCV build. Please review the CMake configuration."

print_info "OpenCV build with GStreamer support is complete. Enjoy your PixEagle project!"

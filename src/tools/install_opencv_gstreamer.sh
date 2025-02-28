#!/bin/bash
# install_opencv_gstreamer.sh
# This script automates the process of building and installing OpenCV with GStreamer support
# into your Python virtual environment on a Raspberry Pi.
#
# It performs the following steps:
#   1. Verifies that the virtual environment is activated.
#   2. Checks the Python version and determines necessary paths.
#   3. Updates the system and installs dependencies.
#   4. Clones (or updates) the OpenCV and OpenCV Contrib repositories.
#   5. Creates a fresh build directory.
#   6. Configures the build with CMake.
#   7. Builds and installs OpenCV.
#   8. Updates the dynamic linker cache.
#
# Usage:
#   Ensure your virtual environment (~/PixEagle/venv) is activated, then run:
#       bash ~/PixEagle/src/tools/install_opencv_gstreamer.sh
#
# Author: Alireza Ghaderi
# Date: Feb 2025

# Exit immediately if a command exits with a non-zero status.
set -e

# Function to check for errors and exit with a message.
check_error() {
    if [ $? -ne 0 ]; then
        echo "ERROR during: $1"
        exit 1
    fi
}

echo "=================================================="
echo "Starting OpenCV with GStreamer installation..."
echo "=================================================="

# 1. Verify Virtual Environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "ERROR: No virtual environment detected."
    echo "Please activate your virtual environment at ~/PixEagle/venv and re-run this script."
    exit 1
fi

echo "Virtual environment detected: $VIRTUAL_ENV"

# 2. Determine Python Information
PYTHON_EXECUTABLE=$(which python)
echo "Using Python executable: $PYTHON_EXECUTABLE"
PYTHON_VERSION=$($PYTHON_EXECUTABLE --version 2>&1)
echo "Python version: $PYTHON_VERSION"

# Dynamically get Python include and packages directories.
PYTHON_INCLUDE_DIR=$($PYTHON_EXECUTABLE -c "from sysconfig import get_paths; print(get_paths()['include'])")
PYTHON_PACKAGES_PATH=$($PYTHON_EXECUTABLE -c "from sysconfig import get_paths; print(get_paths()['purelib'])")
echo "Python include directory: $PYTHON_INCLUDE_DIR"
echo "Python packages directory: $PYTHON_PACKAGES_PATH"

# 3. Update System and Install Dependencies
echo "Updating system and installing required packages..."
sudo apt-get update && sudo apt-get upgrade -y
check_error "System update/upgrade"

sudo apt-get install -y build-essential cmake git pkg-config \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev gstreamer1.0-tools \
    gstreamer1.0-libav gstreamer1.0-gl gstreamer1.0-gtk3 \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly
check_error "Installing dependencies"

# 4. Clone or Update OpenCV Repositories
OPENCV_VERSION="4.9.0"
BASE_DIR="$HOME/PixEagle"
OPENCV_DIR="$BASE_DIR/opencv"
OPENCV_CONTRIB_DIR="$BASE_DIR/opencv_contrib"

# Clone or update OpenCV repository.
if [ ! -d "$OPENCV_DIR" ]; then
    echo "Cloning OpenCV repository into $OPENCV_DIR..."
    git clone https://github.com/opencv/opencv.git "$OPENCV_DIR"
    check_error "Cloning OpenCV repository"
    cd "$OPENCV_DIR"
    git checkout $OPENCV_VERSION
else
    echo "OpenCV repository found at $OPENCV_DIR. Checking out version $OPENCV_VERSION..."
    cd "$OPENCV_DIR"
    git fetch
    git checkout $OPENCV_VERSION
fi

# Clone or update OpenCV Contrib repository.
if [ ! -d "$OPENCV_CONTRIB_DIR" ]; then
    echo "Cloning OpenCV Contrib repository into $OPENCV_CONTRIB_DIR..."
    git clone https://github.com/opencv/opencv_contrib.git "$OPENCV_CONTRIB_DIR"
    check_error "Cloning OpenCV Contrib repository"
    cd "$OPENCV_CONTRIB_DIR"
    git checkout $OPENCV_VERSION
else
    echo "OpenCV Contrib repository found at $OPENCV_CONTRIB_DIR. Checking out version $OPENCV_VERSION..."
    cd "$OPENCV_CONTRIB_DIR"
    git fetch
    git checkout $OPENCV_VERSION
fi

# 5. Create a Clean Build Directory
BUILD_DIR="$OPENCV_DIR/build"
echo "Creating clean build directory at $BUILD_DIR..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# 6. Configure the Build with CMake
echo "Configuring OpenCV build with CMake..."
cmake -D CMAKE_BUILD_TYPE=Release \
      -D CMAKE_INSTALL_PREFIX="$VIRTUAL_ENV" \
      -D OPENCV_EXTRA_MODULES_PATH="$OPENCV_CONTRIB_DIR/modules" \
      -D WITH_GSTREAMER=ON \
      -D WITH_QT=ON \
      -D WITH_OPENGL=ON \
      -D BUILD_EXAMPLES=ON \
      -D PYTHON3_EXECUTABLE="$PYTHON_EXECUTABLE" \
      -D PYTHON3_INCLUDE_DIR="$PYTHON_INCLUDE_DIR" \
      -D PYTHON3_PACKAGES_PATH="$PYTHON_PACKAGES_PATH" \
      ..
check_error "CMake configuration"

# 7. Build OpenCV
echo "Building OpenCV (this might take a while)..."
make -j$(nproc)
check_error "Building OpenCV"

# 8. Install OpenCV
echo "Installing OpenCV into the virtual environment..."
cmake --install .
check_error "Installing OpenCV"

# 9. Update the Dynamic Linker Cache
echo "Updating dynamic linker cache..."
sudo ldconfig

echo "=================================================="
echo "OpenCV with GStreamer installation complete!"
echo "To verify, run the following command:"
echo "$VIRTUAL_ENV/bin/python -c 'import cv2; print(cv2.getBuildInformation())'"
echo "=================================================="

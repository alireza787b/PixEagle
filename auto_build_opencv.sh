#!/usr/bin/env bash
set -euo pipefail

#############################
# Utility Functions
#############################

print_info()  { echo -e "\n[INFO]  $1"; }
print_error() { echo -e "\n[ERROR] $1"; exit 1; }

#############################
# 1. Install System Dependencies
#############################

print_info "Updating system and installing dependencies"
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y build-essential cmake git pkg-config \
     libgtk2.0-dev \
     libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
     gstreamer1.0-tools gstreamer1.0-libav gstreamer1.0-gl \
     gstreamer1.0-gtk3 gstreamer1.0-plugins-good \
     gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly

#############################
# 2. GStreamer Environment
#############################

print_info "Configuring GStreamer environment variables"
export PKG_CONFIG_PATH=/usr/lib/pkgconfig
export GST_PLUGIN_PATH=/usr/lib/gstreamer-1.0

#############################
# 3. Clone OpenCV Repos
#############################

PIX_DIR="$HOME/PixEagle"
OPENCV_VERSION="4.9.0"
print_info "Preparing project directory at $PIX_DIR"
mkdir -p "$PIX_DIR" && cd "$PIX_DIR"

for repo in opencv opencv_contrib; do
  DIR="$PIX_DIR/$repo"
  URL="https://github.com/opencv/$repo.git"
  if [ ! -d "$DIR" ]; then
    print_info "Cloning $repo..."
    git clone "$URL" "$DIR"
  else
    print_info "Updating $repo..."
    git -C "$DIR" fetch --all
  fi
  git -C "$DIR" checkout "$OPENCV_VERSION"
done

#############################
# 4. Python Virtualenv Setup
#############################

VENV_DIR="$PIX_DIR/venv"
print_info "Creating Python3 virtualenv at $VENV_DIR"
python3 -m venv "$VENV_DIR"  # ships with pip :contentReference[oaicite:5]{index=5}
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

print_info "Removing pre-installed OpenCV packages"
pip uninstall -y opencv-python opencv-contrib-python \
  || echo "[INFO] No existing OpenCV pip packages found."

#############################
# 5. Build Directory
#############################

print_info "Setting up build directory"
cd "$PIX_DIR/opencv"
rm -rf build && mkdir build && cd build

#############################
# 6. Configure with CMake
#############################

print_info "Configuring CMake build"
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
  -D Python3_FIND_STRATEGY=LOCATION  # uses FindPython3 :contentReference[oaicite:6]{index=6}

#############################
# 7. Compile & Install
#############################

print_info "Compiling OpenCV (using all CPU cores)"
make -j"$(nproc)"

print_info "Installing into virtualenv"
make install

#############################
# 8. Verify GStreamer Support
#############################

print_info "Checking GStreamer support in cv2 build info"
if python - <<'EOF' 2>/dev/null
import cv2; print(cv2.getBuildInformation())
EOF | grep -q "GStreamer:.*YES"; then
  print_info "GStreamer support ENABLED"
else
  print_error "GStreamer support NOT enabled—inspect CMake output"
fi

print_info "OpenCV build with GStreamer is complete!"

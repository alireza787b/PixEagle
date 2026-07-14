# Building OpenCV with GStreamer Support for PixEagle

> **Recommended (Linux)**: Use the automated script for a streamlined installation:
> ```bash
> bash scripts/setup/build-opencv.sh
> ```
> The manual instructions below are provided for users who need more control over the build process.

---

## Do I Need GStreamer?

**Most users do NOT need a custom OpenCV build.** The standard `pip install opencv-python` works
for all dashboard streaming (HTTP, WebSocket, WebRTC) and all tracking/detection features.

You only need OpenCV with GStreamer if you enable either of these in `configs/config.yaml`:

| Config Key | Section | Purpose | Needs GStreamer? |
|------------|---------|---------|-----------------|
| `USE_GSTREAMER: true` | `VideoSource:` | Read frames from cameras via GStreamer pipelines (RTSP, CSI, USB) | **Yes** |
| `ENABLE_GSTREAMER_STREAM: true` | `GStreamer:` | Send H.264/RTP/UDP video to QGroundControl | **Yes** |

If both are `false` (the defaults), skip this guide entirely.

### Platform Notes

- **Linux (Raspberry Pi, Jetson, Ubuntu)**: Run `bash scripts/setup/build-opencv.sh` — builds OpenCV 4.13 with GStreamer from source (~1-2 hours).
- **Windows**: See [Windows section](#windows) below. No automated build script yet.
- **macOS**: GStreamer builds are possible but rarely needed. Use Homebrew: `brew install gstreamer` then build from source.

---

## Linux: Automated Build (Recommended)

```bash
bash scripts/setup/build-opencv.sh
```

This builds OpenCV 4.13.0 with GStreamer and FFMPEG support. The default is a
headless companion build for Raspberry Pi, Jetson, and onboard Ubuntu. Set
`OPENCV_GUI=1` only when the target also needs OpenCV GTK/OpenGL display
windows:

```bash
OPENCV_GUI=1 bash scripts/setup/build-opencv.sh
```

The automated build:
- Checks disk space (10GB+) and available memory
- **Auto-creates temporary swap** on low-memory systems (Jetson Nano, RPi) — cleaned up after build
- Scales build parallelism to available RAM (2-2.5GB per job, CUDA-aware) to prevent OOM
- Auto-detects platform: Jetson (CUDA), Raspberry Pi (NEON), ARM, x86
- Installs all dependencies automatically
- Builds into the PixEagle virtual environment
- Verifies the imported module is OpenCV 4.13.0 from the selected PixEagle
  venv, instantiates CSRT/KCF contrib trackers, retains FFmpeg, reports
  `GStreamer: YES`, and confirms a submitted frame reaches a non-empty local
  `CAP_GSTREAMER` file sink
- Leaves the current working OpenCV installed while compiling and staging the
  complete installation under `/var/tmp`; before replacement it snapshots
  `cv2`, package metadata, wheel-owned `opencv*.libs`, venv OpenCV libraries,
  native include/CMake/pkg-config/share/tool roots, and every pre-existing
  destination in the generated install manifest; old native module files are
  removed before the staged layout is applied
- Restores all captured destinations automatically if installation,
  verification, or an interrupt fails; the backup is deleted only after all
  runtime checks pass, and an incomplete rollback preserves the recovery
  directory and prints its exact path
- Canonicalizes the selected venv and rejects site-packages, manifest targets,
  or existing destination ancestors that resolve outside it through symlinks
- Treats checked-in setup helpers as read-only inputs; it never rewrites
  `scripts/lib/common.sh` while starting
- Fails before the expensive compile when `pkg-config` cannot resolve
  GStreamer or the CMake summary does not report `GStreamer: YES`

Downloaded source/build trees are retained for diagnostics or a later rebuild.
`make clean` removes those generated trees when disk space is needed.

After the build, verify the complete PixEagle/QGC UDP prerequisite set:

```bash
make check-gstreamer-runtime
```

The script uses the same venv resolver as other setup helpers:
`PIXEAGLE_VENV_DIR` when set, then `.venv/`, then `venv/`. Fresh `make init`
creates `.venv/`; legacy `venv/` checkouts remain supported automatically.
It validates the effective configured encoder path, always checks the required
`x264enc` fallback, and checks `h264parse` when NVENC or VA-API is selected.

---

## Linux: Manual Build

### 1. Install GStreamer and Development Libraries

```bash
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y build-essential cmake git pkg-config libgtk2.0-dev \
                        libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
                        gstreamer1.0-tools gstreamer1.0-libav gstreamer1.0-gl \
                        gstreamer1.0-gtk3 gstreamer1.0-plugins-good \
                        gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly
```

### 2. Verify Package Discovery

```bash
pkg-config --modversion gstreamer-1.0
gst-inspect-1.0 appsrc
```

Do not hardcode `PKG_CONFIG_PATH` or `GST_PLUGIN_PATH` to one architecture.
Debian multiarch, Raspberry Pi OS, and Jetson install plugins in different
directories; `pkg-config` and GStreamer's normal registry are authoritative.

### 3. Download OpenCV and OpenCV Contrib Source Code

```bash
cd ~/PixEagle
git clone https://github.com/opencv/opencv.git
git clone https://github.com/opencv/opencv_contrib.git
cd opencv
git checkout 4.13.0
cd ../opencv_contrib
git checkout 4.13.0
```

### 4. Activate the venv Python environment

```bash
cd ~/PixEagle/
export PIXEAGLE_VENV_DIR="$PWD/venv"  # or "$PWD/.venv" for an existing .venv checkout
source "$PIXEAGLE_VENV_DIR/bin/activate"
```

If you have previously installed OpenCV using pip, uninstall it first:

```bash
pip uninstall opencv-python opencv-contrib-python
```

### 5. Create a Build Directory

```bash
cd ~/PixEagle/opencv
rm -rf build
mkdir build
cd build
```

### 6. Configure the Build with CMake

```bash
cmake -D CMAKE_BUILD_TYPE=Release \
      -D CMAKE_INSTALL_PREFIX="$PIXEAGLE_VENV_DIR" \
      -D OPENCV_EXTRA_MODULES_PATH=~/PixEagle/opencv_contrib/modules \
      -D WITH_GSTREAMER=ON \
      -D WITH_GTK=OFF \
      -D WITH_QT=OFF \
      -D WITH_OPENGL=OFF \
      -D BUILD_EXAMPLES=OFF \
      -D BUILD_TESTS=OFF \
      -D BUILD_PERF_TESTS=OFF \
      -D PYTHON3_EXECUTABLE=$(which python) \
      -D PYTHON3_INCLUDE_DIR=$(python -c "import sysconfig; print(sysconfig.get_path('include'))") \
      -D PYTHON3_LIBRARY=$(python -c "import os, sysconfig; print(os.path.join(sysconfig.get_config_var('LIBDIR'), sysconfig.get_config_var('LDLIBRARY')))") \
      ..
```

Those flags match the headless companion default. Enable GTK/OpenGL only for a
target that actually needs local OpenCV display windows.

### 7. Compile and Install

```bash
make -j$(nproc)
make install
```

### 8. Verify GStreamer Support

```bash
python -c "import cv2; print(cv2.getBuildInformation())" | grep GStreamer
```

You should see `GStreamer: YES`.

---

## Windows

The standard `pip install opencv-python` on Windows does **not** include GStreamer.
There are no official pre-built wheels with GStreamer support on any platform.

### Option A: Sensing-Dev PowerShell Installer (Easiest)

A community-maintained PowerShell script that builds OpenCV with GStreamer:

```powershell
# Download the installer
Invoke-WebRequest -Uri https://github.com/Sensing-Dev/sensing-dev-installer/releases/download/v25.01.02/opencv_python_installer.ps1 -OutFile opencv_python_installer.ps1

# Run it (builds OpenCV with GStreamer in your active Python environment)
powershell.exe -ExecutionPolicy Bypass -File .\opencv_python_installer.ps1
```

> **Warning**: This overwrites any existing `opencv-python` pip installation.

### Option B: Build from Source with CMake

1. Install [GStreamer runtime + development](https://gstreamer.freedesktop.org/download/) (both the runtime and dev MSI packages)
2. Install Visual Studio Build Tools with C++ workload
3. Clone and build:

```cmd
git clone https://github.com/opencv/opencv-python.git
cd opencv-python
set CMAKE_ARGS=-DWITH_GSTREAMER=ON
set ENABLE_CONTRIB=1
pip wheel --no-binary opencv-python .
pip install opencv_contrib_python-4.13.0-*.whl
```

### Option C: Skip GStreamer on Windows

If you only use the dashboard (HTTP/WebSocket/WebRTC streaming) and don't need:
- QGC video output (`ENABLE_GSTREAMER_STREAM`)
- GStreamer input capture (`USE_GSTREAMER`)

Then the standard pip install works perfectly:

```bash
pip install opencv-contrib-python>=4.10.0
```

All tracking, detection, OSD, and dashboard streaming features work without GStreamer.

---

## Troubleshooting

### OpenCV Installation Issues

If you encounter recursive import errors, remove existing OpenCV from your venv:

```bash
rm -rf "${PIXEAGLE_VENV_DIR:-$PWD/venv}"/lib/python*/site-packages/cv2
```

### Check OpenCV Build Information

```bash
python -c "import cv2; print(cv2.getBuildInformation())" | grep -E "GStreamer|Video I/O"
```

### GStreamer Pipeline Test

Test that GStreamer is working with a simple pipeline:

```bash
gst-launch-1.0 videotestsrc ! videoconvert ! autovideosink
```

### Global vs. Virtual Environment

Ensure you are using the correct Python interpreter (`python` in the virtual environment).
A custom-built OpenCV in the venv takes priority over any system-wide installation.

### Environment Variables

Make sure the environment variables are set correctly before building OpenCV.

---

By following these steps, you will ensure that OpenCV is built with GStreamer support, enabling
CSI camera input, RTSP streaming via GStreamer, and H.264/RTP output to QGroundControl.

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

This builds OpenCV 4.13.0 with GStreamer, Qt, OpenGL, and FFMPEG support. It:
- Checks disk space (10GB+) and available memory
- **Auto-creates temporary swap** on low-memory systems (Jetson Nano, RPi) — cleaned up after build
- Scales build parallelism to available RAM (1.5GB per job) to prevent OOM
- Auto-detects platform: Jetson (CUDA), Raspberry Pi (NEON), ARM, x86
- Installs all dependencies automatically
- Builds into the PixEagle virtual environment
- Verifies GStreamer support after build

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

### 2. Set Up Environment Variables

```bash
export PKG_CONFIG_PATH=/usr/lib/pkgconfig
export GST_PLUGIN_PATH=/usr/lib/gstreamer-1.0
```

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
source venv/bin/activate
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
      -D CMAKE_INSTALL_PREFIX=~/PixEagle/venv \
      -D OPENCV_EXTRA_MODULES_PATH=~/PixEagle/opencv_contrib/modules \
      -D WITH_GSTREAMER=ON \
      -D WITH_GTK=ON \
      -D WITH_QT=ON \
      -D WITH_OPENGL=ON \
      -D BUILD_EXAMPLES=ON \
      -D PYTHON3_EXECUTABLE=$(which python) \
      -D PYTHON3_INCLUDE_DIR=$(python -c "from distutils.sysconfig import get_python_inc; print(get_python_inc())") \
      -D PYTHON3_PACKAGES_PATH=$(python -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())") \
      ..
```

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
rm -rf ~/PixEagle/venv/lib/python*/site-packages/cv2
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

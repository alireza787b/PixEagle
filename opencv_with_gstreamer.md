# Building OpenCV with GStreamer Support for PixEagle

## Overview

This document provides detailed instructions on building OpenCV with GStreamer support to ensure compatibility with CSI cameras for the PixEagle project. Follow these steps if you encounter issues with CSI camera feeds.

### Date
December 2024

## Prerequisites

Before proceeding, ensure your system is up-to-date and necessary development tools are installed.

### 1. Update System and Install Development Tools

```bash
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y build-essential cmake git pkg-config
```

## Steps to Build OpenCV with GStreamer Support

### 2. Install GStreamer and Development Libraries

Install GStreamer and its plugins to handle various media formats:

```bash
sudo apt-get install -y libgstreamer1.0-dev \
                        libgstreamer-plugins-base1.0-dev \
                        gstreamer1.0-tools \
                        gstreamer1.0-libav \
                        gstreamer1.0-gl \
                        gstreamer1.0-gtk3 \
                        gstreamer1.0-plugins-good \
                        gstreamer1.0-plugins-bad \
                        gstreamer1.0-plugins-ugly
```

### 3. Set Up Environment Variables

Configure environment variables to ensure the system correctly locates GStreamer libraries:

```bash
echo 'export PKG_CONFIG_PATH=/usr/lib/pkgconfig' >> ~/.bashrc
echo 'export GST_PLUGIN_PATH=/usr/lib/gstreamer-1.0' >> ~/.bashrc
source ~/.bashrc
```

### 4. Download OpenCV and OpenCV Contrib Source Code

Clone the OpenCV and OpenCV Contrib repositories, ensuring both are at the same version for compatibility:

```bash
mkdir -p ~/PixEagle && cd ~/PixEagle
git clone https://github.com/opencv/opencv.git
git clone https://github.com/opencv/opencv_contrib.git
cd opencv
git checkout 4.9.0
cd ../opencv_contrib
git checkout 4.9.0
```

### 5. Create a Build Directory

Create a separate build directory within the OpenCV folder:

```bash
cd ~/PixEagle/opencv
mkdir build
cd build
```

### 6. Configure the Build with CMake

Configure the build to enable GStreamer support and specify the installation directory:

```bash
cmake -D CMAKE_BUILD_TYPE=Release \
      -D CMAKE_INSTALL_PREFIX=~/PixEagle/venv \
      -D OPENCV_EXTRA_MODULES_PATH=~/PixEagle/opencv_contrib/modules \
      -D WITH_GSTREAMER=ON \
      -D WITH_QT=ON \
      -D WITH_OPENGL=ON \
      -D BUILD_EXAMPLES=ON \
      -D PYTHON3_EXECUTABLE=$(which python3) \
      -D PYTHON3_INCLUDE_DIR=$(python3 -c "from distutils.sysconfig import get_python_inc()") \
      -D PYTHON3_PACKAGES_PATH=$(python3 -c "from distutils.sysconfig: get_python_lib()") \
      ..
```

### 7. Compile and Install

Compile and install OpenCV:

```bash
make -j$(nproc)
sudo make install
```

### 8. Update Library Cache

Ensure the system recognizes the newly installed libraries:

```bash
sudo ldconfig
```

### 9. Verify GStreamer Support

Confirm that OpenCV has GStreamer support enabled:

```bash
python3 -c "import cv2; print(cv2.getBuildInformation())"
```

In the output, look for the following line under the "Video I/O" section:

```
GStreamer:                   YES
```

## Additional Considerations

- **Virtual Environment**: If you're using a Python virtual environment, activate it before configuring the build to ensure the correct Python interpreter is used.

- **Dependencies**: Ensure all dependencies are satisfied to prevent build errors. Refer to the [OpenCV Linux Installation Guide](https://docs.opencv.org/4.x/d7/d9f/tutorial_linux_install.html) for detailed information.

- **Documentation and Examples**: If you require OpenCV documentation and examples, include the following flags during the CMake configuration:

  ```bash
  -D BUILD_DOCS=ON \
  -D BUILD_EXAMPLES=ON
  ```

- **Troubleshooting**: If you encounter issues during the build process, consult the [OpenCV Build Troubleshooting Guide](https://docs.opencv.org/4.x/d0/d3d/tutorial_general_install.html) for potential solutions.

By following these steps, you will build OpenCV with GStreamer support, ensuring compatibility with CSI cameras for the PixEagle project.
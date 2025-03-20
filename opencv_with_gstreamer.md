
# Building OpenCV with GStreamer Support for PixEagle

## Overview

This document provides detailed instructions on building OpenCV with GStreamer support to ensure compatibility with CSI cameras for the PixEagle project. Follow these steps if you encounter issues with CSI camera feeds.

### Date
August 2024

## Steps to Build OpenCV with GStreamer Support

### 1. Install GStreamer and Development Libraries

First, ensure that GStreamer and its development libraries are installed globally on your system:

```bash
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y build-essential cmake git pkg-config
sudo apt-get install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
                        gstreamer1.0-tools gstreamer1.0-libav gstreamer1.0-gl \
                        gstreamer1.0-gtk3 gstreamer1.0-plugins-good \
                        gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly
```

### 2. Set Up Environment Variables

Ensure the paths to the GStreamer libraries are set correctly:

```bash
export PKG_CONFIG_PATH=/usr/lib/pkgconfig
export GST_PLUGIN_PATH=/usr/lib/gstreamer-1.0
```

### 3. Download OpenCV and OpenCV Contrib Source Code

Clone the OpenCV and OpenCV Contrib repositories:

```bash
cd ~/PixEagle
git clone https://github.com/opencv/opencv.git
git clone https://github.com/opencv/opencv_contrib.git
cd opencv
git checkout 4.9.0
cd ../opencv_contrib
git checkout 4.9.0
```

### 4. Activate the venv Python environment

If you are using a venv (which I recommend doing), activate your python environment

```bash
cd ~/PixEagle/
source venv/bin/activate
```


### 5. Create a Build Directory

Create a build directory inside the OpenCV folder:

```bash
cd ~/PixEagle/opencv
mkdir build
cd build
```

### 6. Configure the Build with CMake

Configure the build to use GStreamer and point to the Python interpreter in your virtual environment:

```bash
cmake -D CMAKE_BUILD_TYPE=Release \
      -D CMAKE_INSTALL_PREFIX=~/PixEagle/venv \
      -D OPENCV_EXTRA_MODULES_PATH=~/PixEagle/opencv_contrib/modules \
      -D WITH_GSTREAMER=ON \
      -D WITH_QT=ON \
      -D WITH_OPENGL=ON \
      -D BUILD_EXAMPLES=ON \
      -D PYTHON3_EXECUTABLE=$(which python) \
      -D PYTHON3_INCLUDE_DIR=$(python -c "from distutils.sysconfig import get_python_inc; print(get_python_inc())") \
      -D PYTHON3_PACKAGES_PATH=$(python -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())") \
      ..
```

### 7. Compile and Install

Compile and install OpenCV:

```bash
make -j$(nproc)
make install
```

### 8. Verify GStreamer Support

Verify that GStreamer support is enabled in OpenCV:

```bash
python -c "import cv2; print(cv2.getBuildInformation())"
```

Look for `GStreamer: YES` in the output.

## Summary of Changes

- **Environment Variables**: `PKG_CONFIG_PATH` and `GST_PLUGIN_PATH` are set to ensure that the GStreamer libraries are correctly located.
- **CMake Configuration**: The `cmake` command includes flags to enable GStreamer, point to the Python interpreter in the virtual environment, and set up other necessary paths.

## Troubleshooting

- **Check OpenCV Build Information**: Use the provided Python command to verify if GStreamer is enabled.
- **Global vs. Virtual Environment**: Ensure you are using the correct Python interpreter (`python` in the virtual environment).
- **Environment Variables**: Make sure the environment variables are set correctly before building OpenCV.

By following these steps, you will ensure that OpenCV is rebuilt with GStreamer support in your virtual environment, allowing your application to access the CSI camera.

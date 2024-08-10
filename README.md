# PixEagle

## Overview

PixEagle is an all-in-one image processing, following, and tracking solution designed for the PX4 ecosystem (with potential expansion to ArduPilot). It leverages MAVSDK Python, OpenCV, and optional YOLO for precise object tracking and drone navigation. The project emphasizes modularity and extensibility, allowing users to implement their own tracking, detection, and segmentation algorithms. The system is modular, well-commented, and designed for easy integration of new algorithms. Additionally, PixEagle includes a beta web app GUI using React for real-time monitoring and control.
PixEagle comes with a full web-based React application that serves as the Ground Control Station (GCS). It provides a basic yet functional interface where you can view live camera feeds, tracker and follower data, and plots. The enhanced UI now supports drag-and-select target tracking and controlling the tracker.

## Latest Release

Watch the latest video showcasing PixEagle v1.0, demonstrating advanced features including precision landing and intelligent target tracking in a Software in the Loop Simulation with X-Plane 12 and [PX4XPlane](https://github.com/alireza787b/px4xplane):
[![PixEagle v1.0](https://github.com/user-attachments/assets/4acd965b-34c1-456e-be70-d4cc7f26eddb)](https://youtu.be/hw5MU0mPx2I)

## Getting Started

To set up the PixEagle project, follow these steps:

1. Clone the repository:
   ```bash
   git clone https://github.com/alireza787b/PixEagle.git
   ```
2. Navigate to the project directory:
   ```bash
   cd PixEagle
   ```
3. Set up a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```
4. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. (Optional) If you need PyTorch for YOLO detection, run the setup script:
   ```bash
   ./setup_pytorch.sh
   ```

### Running the Application

You can now easily run the PixEagle dashboard and main application using the provided bash scripts. These scripts simplify the process by handling the setup and execution steps automatically.

1. **Running the Main Python Application**:
   To run the main PixEagle Python application:
   ```bash
   ./run_main.sh
   ```
   This script will:
   - Activate the Python virtual environment located at `~/PixEagle/venv`.
   - Run the main Python script `src/main.py`.
   - You can customize the Python interpreter by editing the script or passing it as an argument:
     ```bash
     ./run_main.sh /path/to/python
     ```

2. **Running the Dashboard**:
   Install Node.js and npm for the dashboard application (if not already installed):
   ```bash
   # Follow instructions at https://nodejs.org/en/download/
   ```
   To run the PixEagle React dashboard:
   ```bash
   ./run_dashboard.sh
   ```
   This script will:
   - Navigate to the `~/PixEagle/dashboard` directory.
   - Install necessary npm packages.
   - Start the React server on the specified port (default: 3001).
   - You can change the port by passing it as an argument:
     ```bash
     ./run_dashboard.sh <Custom Port Number>
     ```

3. **Accessing the Dashboard**:
   After starting the dashboard, you can access it in your browser at:
   ```bash
   http://127.0.0.1:3001
   ```
   If you're accessing it from another device, replace `127.0.0.1` with your device's IP address.

### GStreamer and CSI Camera Support

PixEagle now supports GStreamer for video input and output. Several GStreamer test pipelines have been added, making it easy to directly send video feeds to QGroundControl (QGC) and other applications. The video source, including CSI camera input, can be configured in the `parameters.py` file.

**Important**: If you plan to use GStreamer or a CSI camera, you must ensure that OpenCV is built with GStreamer support. We recommend building OpenCV from source with the necessary configurations. A detailed guide is available [here](https://github.com/alireza787b/PixEagle/blob/main/opencv_with_gstreamer.md).

To verify your installation, you can run the following test script:
```bash
python src/test_Ver.py
```
This script will help you ensure that your environment is correctly set up with GStreamer and OpenCV.

### Parameter Customization

In the `parameters.py` file, you can customize various settings to suit your specific use case. This includes selecting your video source, setting descent parameters, and adjusting other important configurations such as PID gains and camera angles. The file is well-documented and easy to navigate.

#### Video Source Configuration

Select your video source (either from a video file, USB Camera, etc.). Note that not all methods are fully tested yet, but file and USB camera methods have been tested.

For PX4 real SITL implementation, you might need X-Plane or another simulation tool that can use the output video. There is a guide to using the PX4XPlane plugin and PixEagle SITL available [here](https://github.com/alireza787b/PixEagle/blob/main/Follow_Mode_Xplane_Guide.md).

#### Other Parameters

Ensure to check and adjust other parameters in the `parameters.py` file, such as PID gains, camera angles, and more, to optimize the system for your specific needs. The file is well-documented to assist you in making these customizations.

### Key Bindings

While in the video pop-up screen, you can use the following keys:
- `t`: Select target
- `c`: Cancel selection
- `y`: YOLO detection
- `f`: Start following offboard
- `d`: Try to re-detect target
- `q`: Quit

## Current Situation

Currently, the tracker with CSRT, detection with template matching, and connection to PX4 offboard using a simulated USB camera are working and tested.

### Known Issues

- The follower with a forward-looking camera and chase mode will be implemented soon.
- The main code will wait for any client receiving HTTP video feed to close before fully closing.
- Cannot start Offboard mode currently from the dashboard.

## Troubleshooting

If you encounter an ImportError related to `libGL.so.1`, install the OpenGL libraries with:
```bash
sudo apt-get update
sudo apt-get install -y libgl1-mesa-glx
```

This is often required for OpenCV's image and video display functionalities.

## Contribution Guidelines

We welcome contributions from developers, researchers, and enthusiasts in drone technology, AI, and robotics. You can contribute by checking out current issues, discussing your ideas, or submitting pull requests with new features or improvements.

## Project Status

PixEagle is under active development, focusing on leveraging PX4 for flight control, incorporating AI for smart decision-making, and utilizing advanced tracking for precise object interaction.

## Disclaimer

PixEagle has not yet been tested in real-world conditions. It has only been tested in SITL (Software In The Loop) simulations. Real-world testing can significantly differ and might lead to crashes or damage. Use it at your own risk, and the developers are not responsible for any damages or losses incurred during real-world testing.

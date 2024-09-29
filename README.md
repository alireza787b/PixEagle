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

5. Install and run MAVLink2REST:
   ```bash
   bash ~/PixEagle/src/tools/mavlink2rest/run_mavlink2rest.sh  # On Linux
   ```


6. (Optional) If you need PyTorch for YOLO detection, run the setup script:
   ```bash
   ./setup_pytorch.sh
   ```

### Running the PixEagle Application

To simplify the execution of the PixEagle system, including the MAVLink2REST service, the dashboard, and the main application, we’ve provided a single bash script that handles everything efficiently using `tmux`.

#### **Quick Start with Tmux:**

You can run the entire PixEagle application suite with a single command:

```bash
bash ~/PixEagle/run_pixeagle.sh
```

This script will:
- Automatically launch all necessary components (MAVLink2REST, Dashboard, Main Application) in separate `tmux` panes.
- Provide a split-screen view, allowing you to monitor all processes simultaneously.

**Navigating Tmux:**
- **Switch between panes:** `Ctrl+B`, then use the arrow keys (`←`, `→`, `↑`, `↓`).
- **Detach from session:** `Ctrl+B`, then `D`.
- **Reattach to session:** Run `tmux attach -t PixEagle` in your terminal.
- **Close a pane:** Type `exit` or press `Ctrl+D`.

**Customizing Execution:**
You can selectively run or skip components using flags, or by adjusting variables directly inside the script:
- `-m` to enable MAVLink2REST (enabled by default)
- `-d` to enable the Dashboard (enabled by default)
- `-p` to enable the Main Application (enabled by default)

For example, to run only the Dashboard and Main Application:
```bash
bash ~/PixEagle/run_pixeagle.sh -d -p
```

#### **Advanced Usage:**

For those who need more control or wish to run components separately, you can still execute each service individually using the following scripts:

1. **MAVLink2REST Service:**
   ```bash
   bash ~/PixEagle/src/tools/mavlink2rest/run_mavlink2rest.sh
   ```
   This script sets up and runs the MAVLink2REST service. You can customize its behavior by passing arguments for the MAVLink source and server IP/port.

2. **Main Python Application:**
   ```bash
   bash ~/PixEagle/run_main.sh
   ```
   This script activates the Python virtual environment and runs the main PixEagle application.

3. **Dashboard:**
   ```bash
   bash ~/PixEagle/run_dashboard.sh
   ```
   This script starts the React dashboard server, which you can access in your browser at `http://127.0.0.1:3001`.

#### **Accessing the Dashboard:**
Once the dashboard is running, access it in your browser at:
```bash
http://127.0.0.1:3001
```
If accessing from another device, replace `127.0.0.1` with the appropriate IP address, ensuring your firewall allows access to this port.

### Additional Notes:
- **Manual Setup:** If you prefer to set up the application manually, you can install npm packages with `npm install` and run the Python scripts directly with the `python` command. This approach is also recommended for Windows users, as bash scripts may not work out of the box on Windows systems.

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


# PixEagle

## Overview

PixEagle is an all-in-one image processing, following, and tracking solution designed for the PX4 ecosystem (with potential expansion to ArduPilot). It leverages MAVSDK Python, OpenCV, and optional YOLO for precise object tracking and drone navigation. The project emphasizes modularity and extensibility, allowing users to implement their own tracking, detection, and segmentation algorithms. The system is modular, well-commented, and designed for easy integration of new algorithms. Additionally, PixEagle includes a beta web app GUI using React for real-time monitoring and control.

## Latest Release

Watch the latest video showcasing PixEagle v1.0, demonstrating advanced features including precision landing and intelligent target tracking in a Software in the Loop Simulation with X-Plane 12 and [PX4XPlane](https://github.com/alireza787b/px4xplane):
[![PixEagle v1.0](https://github.com/user-attachments/assets/4acd965b-34c1-456e-be70-d4cc7f26eddb)](https://youtu.be/hw5MU0mPx2I)


## Key Components

### AppController

The AppController is essentially the manager and coordinator of the entire application flow. It oversees and orchestrates the main loops, streaming, following, tracking, and detection processes, ensuring smooth and efficient operation of the PixEagle system.

### Tracker

The `Tracker` class has been improved to allow for building custom tracker instances. It initializes and manages the tracking algorithm, processes video frames, and updates tracking data. It supports various tracking algorithms such as CSRT, KCF, and others. The tracker can also use a position estimator for enhanced accuracy.

### BaseTracker and Templates

The `BaseTracker` class provides a foundation for custom tracker implementations. Templates are provided for creating new tracking algorithms, allowing for easy extension and customization.

### Follower

The `Follower` class is designed for scenarios where a downward-looking camera follows a moving or stationary target. It uses PID control with gain scheduling to maintain accurate tracking even on a moving platform. The `Follower` class parameters are managed in the `Parameters` class.

### PX4Controller

The `PX4Controller` handles communication with MAVSDK and PX4 using MAVLink. It manages offboard control, allowing for precise drone navigation and control.

### FlaskHandler

The `FlaskHandler` sends telemetry and tracker data via HTTP to any Ground Control Station (GCS) and the PixEagle dashboard. Details on the URIs, ports, and syntax can be found in the `Parameters` class.

### TelemetryData

The `TelemetryData` class is responsible for packing data for the `FlaskHandler`, ensuring efficient and organized data transmission.

### Detector and DetectorInterface

Defines the base structure and interface for object detection modules, allowing for extensibility and integration of different detection algorithms.

### FeatureMatchingDetector

Specializes in detecting objects based on feature matching, enhancing the application's ability to recognize objects in various conditions.

### Parameters

Stores and manages all configuration settings, including detection parameters, video source configurations, and PID gains for the `Follower`.

### Segmentor

Implements advanced segmentation algorithms to improve object detection and tracking in complex scenes.

### TemplateMatcher

Utilizes template matching techniques for object detection, offering a straightforward method for recognizing objects based on stored templates.

### VideoHandler

Handles video inputs from various sources, including files and cameras, ensuring flexible input options for processing and analysis.

### Dashboard (React App)

A full web-based React application serves as the Ground Control Station (GCS). It provides a basic yet functional interface where you can view live camera feeds, tracker and follower data, and plots. Future updates will include additional features such as the ability to send commands and more interactive capabilities.

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
6. Execute the main application:
   ```bash
   python src/main.py
   ```
If you prefer, you can still use the global Python environment instead of a virtual environment.


7. Install Node.js and npm for the dashboard application (if not already installed):
   ```bash
   # Follow instructions at https://nodejs.org/en/download/
   ```
8. Navigate to the dashboard directory and install dependencies:
   ```bash
   cd dashboard
   npm install
   ```
9. Start the dashboard application:
   ```bash
   npm start
   ```

Access the dashboard in your browser at `http://127.0.0.1:3000`



### Parameter Customization

In the `parameters.py` file, you can customize various settings to suit your specific use case. This includes selecting your video source, setting descent parameters, and adjusting other important configurations such as PID gains and camera angles. The file is well-documented and easy to navigate.

#### Video Source Configuration

Select your video source (either from a video file, USB Camera, etc.). Note that not all methods are fully tested yet, but file and USB camera methods have been tested.

For PX4 real SITL implementation, you might need X-Plane or another simulation tool that can use the output video. There is a guide to using the PX4XPlane plugin and PixEagle SITL available [here](https://github.com/alireza787b/PixEagle/blob/main/Follow_Mode_Xplane_Guide.md).

#### Descent Parameters

You can define the altitude descent parameters in the `parameters.py` file. By default, these parameters might be set to prevent descending or to stop descending at 20 meters. Make sure to set these accordingly:

```python
# Minimum descent height in meters.
# The drone will not descend below this altitude during operations.
MIN_DESCENT_HEIGHT = 20  # meters

# Maximum rate of descent in meters per second.
# Limits the vertical speed to prevent rapid altitude loss.
MAX_RATE_OF_DESCENT = 0.5  # meters per second
```
#### Other Parameters
Ensure to check and adjust other parameters in the parameters.py file, such as PID gains, camera angles, and more, to optimize the system for your specific needs. The file is well-documented to assist you in making these customizations.

### Key Bindings

While in the video pop-up screen, you can use the following keys:
- `t`: Select target
- `c`: Cancel selection
- `y`: YOLO detection
- `f`: Start following offboard
- `d`: Try to re-detect target
- `q`: Quite

## Current Situation

Currently, the tracker with CSRT, detection with template matching, and connection to PX4 offboard using a simulated USB camera are working and tested.

### Known Issues

- In the React UI, video overlay on the scope plot makes the telemetry update stop.
- Unable to draw the bounding box around the target from the React app yet.
- The follower with a forward-looking camera and chase mode will be implemented soon.

## Troubleshooting

If you encounter an ImportError related to libGL.so.1, install the OpenGL libraries with:
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


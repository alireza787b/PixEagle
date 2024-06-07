
# Integration Guide for Follow Mode Tracker Test with X-Plane and SITL

## Overview
This guide details the steps to integrate MAVLink, SITL (Software in the Loop), X-Plane, and OpenCV for the follow mode tracker tests. This setup involves running SITL on Linux (WSF) and X-Plane on Windows, with video streaming through SparkoCam into OpenCV.

## Prerequisites
- Windows 10 or later with WSL installed.
- X-Plane installed on Windows.
- MAVLink Router installed on WSL.
- MAVSDK Server manually installed and run on Windows. Download the MAVSDK Server binary appropriate for Windows from the MAVSDK official repository. Later, the process of starting the server will be automated.
- SparkoCam installed on Windows to stream X-Plane output to a virtual webcam.
- OpenCV setup in Windows to process the virtual webcam video.
- PX4 simulation integration with X-Plane using [PX4XPlane](https://github.com/alireza787b/px4xplane).

## Configuration Steps

### Step 1: MAVLink Router Configuration on WSL
Route MAVLink messages between your SITL environment on Linux and your development environment on Windows:

```bash
mavlink-routerd -e 172.21.144.1:14540 -e 172.21.144.1:14550 0.0.0.0:14550
```

### Step 2: MAVSDK Server Setup on Windows
Manually run MAVSDK Server to interface with the MAVLink stream:

```cmd
.\mavsdk_server_bin.exe
```
#### Step 3: Setting System Parameters
Modify the parameters in the `parameters.py` file within the `src` folder:

```python
SYSTEM_ADDRESS = "udp://172.21.148.30:14540"  # Modify this with your own WSL IP if different.
EXTERNAL_MAVSDK_SERVER = True  # Enable this option to use an external MAVSDK server.
```
### Step 4: Configuration of X-Plane, SparkoCam, and OpenCV

#### **X-Plane Setup**
- Start by opening **X-Plane** on your Windows system and loading a supported aircraft, such as the ehang184.
- Ensure that the **PX4XPlane** plugin is installed. Navigate to the plugin menu within X-Plane to select the correct airframe configuration.

#### **SparkoCam Configuration**
- Launch **SparkoCam** and configure it to capture the entire screen output from X-Plane. This setup is essential as it creates a virtual webcam, enabling the video stream to be processed as if it were coming directly from a camera.
- Adjust SparkoCam settings to ensure it streams the entire screen effectively, simulating a top-down camera view that will be used for image processing.

#### **OpenCV Setup**
- Configure **OpenCV** to receive the video input from SparkoCam’s virtual webcam. This will allow OpenCV to process and analyze the video stream for the follow mode tracking and other computer vision tasks.

### Step 5: System Integration and Execution

#### **Running PX4 SITL and PX4XPlane on WSL**
- In WSL, follow the documentation for **PX4XPlane** to set up and run the necessary scripts or commands, ensuring they are adjusted for your own Windows IP settings.

#### **MAVLink Router Configuration**
- Make sure the MAVLink Router is running as previously set up to facilitate the communication between PX4 SITL on WSL and the simulation on Windows. The commands you use will bridge the necessary MAVLink data across the systems.

#### **Connecting to QGroundControl (QGC)**
- Launch **QGroundControl (QGC)** on Windows, connecting to the MAVLink Router streams available on ports 14550 and optionally on 18570, to receive telemetry and control data.

#### **Video Source and Camera Configuration in PixEagle**
- Within your PixEagle project, ensure the video source and camera settings are correctly configured in the `parameters.py` file:
    ```python
    VIDEO_SOURCE = "USB_CAMERA"  # Options include "VIDEO_FILE", "USB_CAMERA", "RTSP_STREAM", "UDP_STREAM", "HTTP_STREAM".
    CAMERA_INDEX = 1  # Index for USB Camera, adjust based on your system setup.
    ```

#### **Running the Follow Mode Tracker**
- Execute `main.py` from the PixEagle folder on your Windows environment. Follow the interactive prompts to select an object ('t' key) and start the follower mode ('f' key).
- During the test, you may need to adjust the PID gains and settings through the PixEagle interface to optimize the control and tracking behavior.

### Step 6: Performance Monitoring and Adjustment

- Regularly check the **system's performance and connectivity**. Use network analysis tools like **Wireshark** to monitor the data flow and troubleshoot any potential issues.
- Ensure that all applications are correctly synchronized and that the video stream is stable and provides the required visual data for processing.


## Additional Tips
- **Performance Monitoring**: Keep an eye on the system for the resource-intensive nature of video processing and network communication.
- **Security Measures**: Secure your network configurations to prevent unauthorized access.

## Conclusion
This setup enables realistic flight dynamics simulation in X-Plane, which can be manipulated and monitored via SITL and MAVLink, along with video stream processing using OpenCV for computer vision tasks.

---

*Document last updated: 7 June 2024*

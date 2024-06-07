
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
Ensure the system address and other parameters are configured in the `parameters.py` file in the `src` folder.

### Step 3: OpenCV and SparkoCam Configuration for X-Plane Video
- **X-Plane**: Operates on Windows connected to the flight simulation.
- **SparkoCam**: Captures the X-Plane screen output and creates a virtual webcam.
- **OpenCV**: Utilizes the video from SparkoCam for processing.

### Step 4: Integration and Execution
Ensure all applications are configured correctly:
- Use scripts for starting network bridging applications.
- Check connectivity and performance regularly.
- Monitor the setup with network analysis tools like Wireshark.

## Additional Tips
- **Performance Monitoring**: Keep an eye on the system for the resource-intensive nature of video processing and network communication.
- **Security Measures**: Secure your network configurations to prevent unauthorized access.

## Conclusion
This setup enables realistic flight dynamics simulation in X-Plane, which can be manipulated and monitored via SITL and MAVLink, along with video stream processing using OpenCV for computer vision tasks.

---

*Document last updated: 7 June 2024*

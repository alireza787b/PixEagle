# PixEagle

## Overview

PixEagle is an all-in-one image processing, following, and tracking solution designed for the PX4 ecosystem, with potential expansion to ArduPilot. It leverages **MAVSDK Python**, **OpenCV**, and optional **YOLO** for precise object tracking and drone navigation. The project emphasizes **modularity** and **extensibility**, allowing users to implement their own tracking, detection, and segmentation algorithms. Additionally, PixEagle includes a **web-based React application** that serves as a Ground Control Station (GCS), providing real-time monitoring and control with enhanced features like drag-and-select target tracking.

With PixEagle 2, we've introduced a suite of advanced features to elevate your drone's capabilities, making it more robust, user-friendly, and versatile for various aerial robotics applications.

## Latest Release

### 🎉 **PixEagle 2 - Enhanced Tracking, Modular Design & Advanced Features** 🚁✨

Watch our latest demo video showcasing **PixEagle 2**, where we demonstrate its advanced tracking functionalities, various following modes, and seamless integration with real hardware like the Raspberry Pi 5. This release brings significant improvements in tracker robustness, user experience, and operational efficiency.

[![PixEagle 2 Demo Video](https://img.youtube.com/vi/vJn27WEXQJw/0.jpg)](https://www.youtube.com/watch?v=vJn27WEXQJw)


### 📺 **Watch the PixEagle 2.0 Demo Video:**
[Your PX4 Drone Can See, Track & Follow! Give Eagle Eyes to your Drone with PixEagle 2.0](https://www.youtube.com/watch?v=vJn27WEXQJw)

### 🌟 **New Features in PixEagle 2.0:**

- **🚀 Improved Tracker Robustness:**
  - Enhanced algorithms for more reliable tracking in diverse environments.
  - **Redetection & Tracker Failure Compensation (Beta):** Automatically recovers tracking in case of failures, ensuring continuous operation.

- **🎨 Enhanced Visuals & User Experience:**
  - Sleeker user interfaces for a more intuitive and seamless user journey.
  - Easier operation features to streamline your workflow.

- **🌐 Full-Featured Web-Based Dashboard:**
  - Accessible from anywhere, providing comprehensive control and monitoring.
  - Optimized to work efficiently on companion computers, enhancing flexibility.

- **⚙️ Optimization for Companion Computers:**
  - Efficient performance on various companion computer setups.

- **🛠️ Fully Modular Design:**
  - Easily add your own trackers using the base tracker abstract method implementation.
  - **Customizable:** Tailor PixEagle 2.0 to fit your specific project needs with its all-in-one, modular design.

- **🔄 Multiple Following Modes:**
  - **Ground View Mode**
  - **Constant Distance**
  - **Constant Position**
  - **Chase Mode (Dogfight)**

- **🔗 Integration with MAVSDK & Mavlink2REST:**
  - Seamless communication and control integration for enhanced drone management.

- **📷 Support for CSI Cameras:**
  - Requires manual GStreamer build for optimal performance.

- **📡 Streaming Enhancements:**
  - **Stream to QGC Over UDP:** Real-time data streaming for enhanced control and monitoring.
  - **WebSocket & HTTP Streaming:** Improved WebSocket performance with reduced latency, ensuring smooth data transmission.

- **🛡️ Failsafe Handling Implementations:**
  - Enhanced safety measures for reliable drone operations in unforeseen scenarios.



## Getting Started

### Prerequisites

Before setting up PixEagle, ensure that your system meets the following requirements:

- **Operating System:** Linux (recommended). Windows is supported but only recommended for X-Plane SITL tests. (see [Integration Guide for Follow Mode Tracker Test with X-Plane and SITL
](https://github.com/alireza787b/PixEagle/blob/smart-param/Follow_Mode_Xplane_Guide.md)).
- **Python:** Version 3.9 or higher.
- **Python Virtual Environment:** `venv` module.
- **Python Packages:** As listed in `requirements.txt`.
- **Additional Tools:** `tmux`, `lsof` for better control and management.

#### Install Prerequisites on Linux

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip tmux lsof 
sudo apt install -y python3-gi gir1.2-gstreamer-1.0 gstreamer1.0-tools gstreamer1.0-plugins-base 
```

### Installation

1. **Clone the Repository:**

    ```bash
    cd ~
    git clone https://github.com/alireza787b/PixEagle.git
    ```

2. **Navigate to the Project Directory:**

    ```bash
    cd ~/PixEagle
    ```

3. **Initialize the Project:**

    Run the initialization script to set up the virtual environment, install dependencies, and handle configurations:

    ```bash
    bash init_pixeagle.sh
    ```

    **Note:** If you prefer manual setup, you can create a virtual environment, creating configs and env files and install the requirements manually.


4. **Install Node.js and npm:**

    PixEagle's dashboard requires Node.js and npm. Install them by following the instructions for your operating system on the [official Node.js website](https://nodejs.org/en/download/package-manager/).

    **Note:** Using package managers like `apt` may install outdated versions. It's recommended to use the official installation methods.

### Configuration

1. **Update Application Configuration:**

    Edit the main application configuration file to suit your setup:

    ```bash
    nano configs/config.yaml
    ```

    Adjust settings such as video source, PID gains, camera angles, and other parameters.

2. **Update Dashboard Configuration:**

    Edit the dashboard's environment variables:

    ```bash
    nano dashboard/.env
    ```

    Update server IP addresses, ports, and other relevant settings to match your system.


### PX4 Integration

To integrate PixEagle with PX4 for flight control, you need to set up MAVLink communication and ensure all necessary components are installed and configured correctly.

#### Installing MAVLink Router and MAVLink2REST

1. **Install MAVLink Router:**
     On systems like Raspberry Pi or Jetson, you can use the `mavlink-anywhere` auto-start daemon to automatically route serial connections (e.g., `/dev/ttyS0` or `/dev/ttyAMA0` or `/dev/ttyTHS1`) to UDP endpoints (e.g., `127.0.0.1:14550`, `127.0.0.1:14540`, `127.0.0.1:14569`) using the following command:
    Navigate to your home directory and clone the `mavlink-anywhere` repository:

    ```bash
    cd ~
    git clone https://github.com/alireza787b/mavlink-anywhere.git
    cd mavlink-anywhere
    bash install_mavlink_router.sh
    ```
    Once installed you can either run mavlink-router manually each time or set it as a system daemon and start automatically (recommended)
    ```bash
    bash ~/mavlink-anywhere/configure_mavlink_router.sh
    ```
    As an MAVLink input stream, you should specify your mavlink source. On Raspberry Pi, if you using Serial hardware on GPIO its either `/dev/ttyAMA0` or `/dev/ttyS0`. you can double check with the command `ls /dev/tty*`.
    As output  you can enter as many endpoints as you need. eg. `127.0.0.1:14540 127.0.0.1:14550 127.0.0.1:14569`. You can add extra GCS endpoints here.
   
   - **Manual MAVLink Router Commands:**

  You can manually run `mavlink-router` commands as needed. For example, in SITL mode, depending on where SITL and PixEagle are running, you might use:

  ```bash
  mavlink-routerd -e 172.21.144.1:14540 -e 172.21.144.1:14550 -e 172.21.144.1:14569 -e 127.0.0.1:14569 0.0.0.0:14550
  ```

  Adjust the IP addresses and ports based on your network configuration.
  
3. **Install and Run MAVLink2REST:**

    ```bash
    bash ~/PixEagle/src/tools/mavlink2rest/run_mavlink2rest.sh
    ```

    This script will install and start `mavlink2rest` on port `14569` by default.

#### Ensuring MAVSDK Server Binary is Present

PixEagle requires the `mavsdk_server_bin` binary for full functionality. This binary is essential for MAVSDK integration with PX4.

1. **Check for `mavsdk_server_bin`:**

    The `mavsdk_server_bin` should be located in the project root directory (`~/PixEagle`). It should be compatible with your hardware architecture. 

2. **Download `mavsdk_server_bin`:**

    If `mavsdk_server_bin` is not present, you have two options:

    - **Manual Download:**

        Download the MAVSDK Server binary from the [MAVSDK Releases](https://github.com/mavlink/MAVSDK/releases/) page. After downloading, rename the binary to `mavsdk_server_bin` and place it in the project root directory (`~/PixEagle`).

    - **Automatic Download via Script:**

        When you run the PixEagle system using the `run_pixeagle.sh` script, if the `mavsdk_server_bin` is not found, the script will prompt you to automatically download and install it. Follow the on-screen instructions to complete the installation.
    ```bash
    bash ~/PixEagle/src/tools/src/tools/download_mavsdk_server.sh
    ```


### Running PixEagle

You can run the entire PixEagle application suite with a single command:

```bash
bash run_pixeagle.sh
```

This script will:

- Automatically launch all necessary components (MAVLink2REST, Dashboard, Main Application, MAVSDK Server) in separate `tmux` windows or split panes.
- Check and free up default ports (`8088`, `5077`, `3001`) before starting.
- Ensure that the `mavsdk_server_bin` is present. If not, it will prompt you to automatically download it or guide you to download it manually.
- Provide a split-screen view for monitoring all processes simultaneously.

**Navigating Tmux:**

- **Switch between windows:** `Ctrl+B`, then number keys (`1`, `2`, `3`, `4`).
- **Switch between panes:** `Ctrl+B`, then arrow keys (`←`, `→`, `↑`, `↓`).
- **Detach from session:** `Ctrl+B`, then `D`.
- **Reattach to session:** `tmux attach -t PixEagle`.
- **Close a pane/window:** Type `exit` or press `Ctrl+D`.

**Customizing Execution:**

You can selectively run or skip components using flags:

- `-m` : Do **NOT** run MAVLink2REST.
- `-d` : Do **NOT** run Dashboard.
- `-p` : Do **NOT** run Main Python Application.
- `-k` : Do **NOT** run MAVSDK Server.



**Note:** instead of running `run_pixeagle.sh`, you can also run components separately using the provided scripts:

- **Run Dashboard Only:**

    ```bash
    bash ~/PixEagle/run_dashboard.sh
    ```

- **Run MAVLink2REST Only:**

    ```bash
    bash ~/PixEagle/src/tools/mavlink2rest/run_mavlink2rest.sh
    ```

### Accessing the Dashboard

Once the dashboard is running, access it in your browser at:

```
http://127.0.0.1:3001
```

If accessing from another device, replace `127.0.0.1` with your machine's IP address. Ensure your firewall allows access to this port.

### GStreamer and CSI Camera Support

PixEagle supports GStreamer for video input and output, including CSI camera input. Configure your video source in `configs/config.yaml`.

**Note:** If you plan to use GStreamer or a CSI camera, ensure that OpenCV is built with GStreamer support. You need to build OpenCV from the source with the necessary configurations. A detailed guide is available [here](https://github.com/alireza787b/PixEagle/blob/main/opencv_with_gstreamer.md).

To verify your installation:

```bash
python src/test_Ver.py
```

### Key Bindings

While in the video window, you can use the following keys:

- `t`: Select target
- `c`: Cancel selection
- `y`: YOLO detection
- `f`: Start following (offboard mode)
- `d`: Try to re-detect target
- `q`: Quit

## Windows Setup

PixEagle is supported on Windows, but you may need to handle some steps manually as bash scripts may not work out of the box. In Windows, you should manually run:

- **Main Python Application:**

    ```bash
    python src/main.py
    ```

- **Dashboard:**

    Navigate to the dashboard directory, install dependencies, and start the dashboard:

    ```bash
    cd dashboard
    npm install
    npm start
    ```

- **MAVLink2REST and MAVLink Router:**

    You may need to run these on WSL (Windows Subsystem for Linux) or adapt the commands accordingly.

For detailed instructions on setting up PixEagle with X-Plane on Windows and SITL on WSL with PX4XPlane, refer to the [Follow Mode X-Plane Guide](https://github.com/alireza787b/PixEagle/blob/main/Follow_Mode_Xplane_Guide.md).

## PX4 Integration

To integrate PixEagle with PX4 for flight control, you need to set up MAVLink communication.

### Installing MAVLink Router and MAVLink2REST

1. **Install MAVLink Router:**

    Navigate to your home directory and clone the `mavlink-anywhere` repository:

    ```bash
    cd ~
    git clone https://github.com/alireza787b/mavlink-anywhere.git
    cd mavlink-anywhere
    bash install_mavlink_router.sh
    ```

    This will install `mavlink-router`, which is essential for routing MAVLink messages.

2. **Install and Run MAVLink2REST:**

    ```bash
    bash ~/PixEagle/src/tools/mavlink2rest/run_mavlink2rest.sh
    ```

    This script will install and start `mavlink2rest` on port `14569` by default.

### Setting Up MAVLink Routing

- **Using mavlink-anywhere Auto-Start Daemon:**

  On systems like Raspberry Pi or Jetson, you can use the `mavlink-anywhere` auto-start daemon to automatically route serial connections (e.g., `/dev/ttyS0` or `/dev/ttyTHS1`) to UDP endpoints.

- **Manual MAVLink Router Commands:**

  You can manually run `mavlink-router` commands as needed. For example, in SITL mode, depending on where SITL and PixEagle are running, you might use:

  ```bash
  mavlink-routerd -e 172.21.144.1:14540 -e 172.21.144.1:14550 -e 172.21.144.1:14569 -e 127.0.0.1:14569 0.0.0.0:14550
  ```

  Adjust the IP addresses and ports based on your network configuration.

## Running PixEagle

You can run the entire PixEagle application suite with a single command:

```bash
./run_pixeagle.sh
```

This script will:

- Automatically launch all necessary components (MAVLink2REST, Dashboard, Main Application) in separate `tmux` windows.
- Check and free up default ports (`8088`, `5077`, `3001`) before starting.
- Provide a split-screen view for monitoring all processes simultaneously.

**Navigating Tmux:**

- **Switch between windows:** `Ctrl+B`, then number keys (`1`, `2`, `3`).
- **Switch between panes:** `Ctrl+B`, then arrow keys (`←`, `→`, `↑`, `↓`).
- **Detach from session:** `Ctrl+B`, then `D`.
- **Reattach to session:** `tmux attach -t PixEagle`.
- **Close a pane/window:** Type `exit` or press `Ctrl+D`.

**Customizing Execution:**

You can selectively run or skip components using flags:

- `-m` : Do **NOT** run MAVLink2REST.
- `-d` : Do **NOT** run Dashboard.
- `-p` : Do **NOT** run Main Python Application.

For example, to run only the Dashboard and Main Application:

```bash
./run_pixeagle.sh -m
```

**Note:** After running `run_pixeagle.sh`, you can also run components separately using the provided scripts:

- **Run Dashboard Only:**

    ```bash
    ./run_dashboard.sh
    ```

- **Run MAVLink2REST Only:**

    ```bash
    bash ~/PixEagle/src/tools/mavlink2rest/run_mavlink2rest.sh
    ```

### Manual Execution

If you prefer to run components separately:

1. **MAVLink2REST Service:**

    ```bash
    bash ~/PixEagle/src/tools/mavlink2rest/run_mavlink2rest.sh
    ```

2. **Main Python Application:**

    ```bash
    source venv/bin/activate
    python src/main.py
    ```

3. **Dashboard:**

    ```bash
    cd dashboard
    npm install
    npm start
    ```

## Accessing the Dashboard

Once the dashboard is running, access it in your browser at:

```
http://127.0.0.1:3001
```

If accessing from another device, replace `127.0.0.1` with your machine's IP address. Ensure your firewall allows access to this port.

## GStreamer and CSI Camera Support

PixEagle supports GStreamer for video input and output, including CSI camera input. Configure your video source in `configs/config.yaml`.

**Note:** If you plan to use GStreamer or a CSI camera, ensure that OpenCV is built with GStreamer support. Build OpenCV from source with the necessary configurations. A detailed guide is available [here](https://github.com/alireza787b/PixEagle/blob/main/opencv_with_gstreamer.md).

To verify your installation:

```bash
python src/test_Ver.py
```

## Key Bindings

While in the video window, you can use the following keys:

- `t`: Select target
- `c`: Cancel selection
- `y`: YOLO detection
- `f`: Start following (offboard mode)
- `d`: Try to re-detect target
- `q`: Quit

### 📚 **Additional Resources:**

- **📁 PixEagle GitHub Repository:**  
  [https://github.com/alireza787b/PixEagle](https://github.com/alireza787b/PixEagle)
  
- **📄 X-Plane SITL Instructions:**  
  [Follow Mode Xplane Guide](https://github.com/alireza787b/PixEagle/blob/smart-param/Follow_Mode_Xplane_Guide.md)
  
- **📂 PX4Xplane Repository:**  
  [https://github.com/alireza787b/px4xplane](https://github.com/alireza787b/px4xplane)
  
- **📺 PixEagle YouTube Playlist:**  
  [PixEagle Series](https://www.youtube.com/watch?v=nMThQLC7nBg&list=PLVZvZdBQdm_4oain9--ClKioiZrq64-Ky&index=1&t=0s)

### ⚠️ **Disclaimer:**

*PixEagle 2.0 is currently in an experimental stage and has not been tested in real-world scenarios. Use at your own risk. The developers are not responsible for any misuse or damages resulting from the use of this software.*

### 👍 **Stay Connected & Get Involved:**

- **🔔 Subscribe** to our [YouTube Channel](https://www.youtube.com/channel/YourChannelLink) for more updates and tutorials on PixEagle 2.0.
- **💬 Share** your thoughts and suggestions in the [issues](https://github.com/alireza787b/PixEagle/issues) section of our GitHub repository!
- **🔗 Join** our community by contributing on [GitHub](https://github.com/alireza787b/PixEagle).

### 📢 **Call to Action:**

Enjoyed PixEagle 2.0? **Star ⭐** the repository, **fork 🔀** it for your projects, and **contribute** to help us continue to innovate and improve PixEagle. Your support is invaluable!

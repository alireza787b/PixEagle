# PixEagle

## Overview

**PixEagle** is a powerful, modular image-processing and tracking suite for drones running the **PX4 autopilot** — with optional support for ArduPilot and integration-ready for custom systems. It combines **MAVSDK Python**, **OpenCV**, and **YOLO** object detection to deliver high-performance visual tracking and autonomous following.

With **PixEagle 3.0**, we’ve taken things to the next level — introducing a new GPU-accelerated **Smart Tracker**, seamless **YOLO integration**, a redesigned web-based GCS dashboard, and automatic model conversion tools. PixEagle is now more intelligent, flexible, and field-ready than ever before.

> Whether you're using a Raspberry Pi, Jetson, or x86 companion computer — PixEagle is built for real-time, on-board vision-based autonomy.

---

## 🚀 PixEagle – Demo

🎬 **Watch the PixEagle 2.0 Demo Video:**  

[![PixEagle 2 Demo Video](https://img.youtube.com/vi/vJn27WEXQJw/0.jpg)](https://www.youtube.com/watch?v=vJn27WEXQJw)


🎬 **Watch the PixEagle 3.0 Demo Video: (Soon...) **  
Your Drone Can Now Think — Smart Tracking with YOLO + PX4


---

### ✨ What's New in PixEagle 3.0

#### 🤖 Smart YOLO Tracker (New)

- Built-in **YOLO-powered tracking engine**, running in real-time
- **Supports any custom YOLO model** — auto-detection with bounding box or click-to-track
- **Works alongside classic trackers** (e.g. CSRT) for hybrid tracking scenarios
- **User-friendly switching between Classic / Smart modes** via updated Dashboard

#### ⚡ CUDA / GPU Acceleration (New)

- Enable **GPU support with a single config switch**
- Automatically falls back to CPU if needed
- Works seamlessly on Jetson, NVIDIA GPUs, or CPU-only setups

#### 📊 Dashboard Revamp (Improved UI/UX)

- Clean toggle UI for Smart vs Classic Mode
- Visual mode indicators and status feedback
- Fully responsive layout for GCS use in the field

#### 📦 Easy YOLO Model Management

- New `add_yolo_model.py` utility to:
  - Download YOLO models from Ultralytics
  - Auto-convert and register them for GPU/CPU usage

#### 🎯 Performance, Bug Fixes & Reliability

- Better tracker fallback and recovery logic
- Updated GStreamer streaming support
- Added support for **RTSP** camera feeds
- Improved logging, error handling, and startup detection

---


## 🚀 Getting Started with PixEagle 3.0

### 🔧 Prerequisites

Make sure your system meets the following requirements before installing PixEagle:

- **Operating System:**  
  - Linux (🟢 Recommended for all use cases)  
  - Windows (🟡 Supported only for simulation/SITL testing via X-Plane + WSL)  
    → [X-Plane SITL Guide](https://github.com/alireza787b/PixEagle/blob/smart-param/Follow_Mode_Xplane_Guide.md)

- **Python:** 3.9 or higher  
- **Virtual Environment Tool:** `venv`  
- **Python Packages:** Listed in `requirements.txt`  
- **Node.js & npm:** Required for the Dashboard UI  
- **Other Tools:** `tmux`, `lsof`, `curl` (for automatic setups)

#### 📦 Install Prerequisites (Linux)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip tmux lsof curl
```

---

### 📥 Installation

1. **Clone the Repository:**

```bash
cd ~
git clone https://github.com/alireza787b/PixEagle.git
cd PixEagle
```

2. **Initialize the Project (Recommended):**

```bash
bash init_pixeagle.sh
```

This script will:

- Create a Python virtual environment
- Install all required Python packages
- Generate `config.yaml` and `.env` files if missing
- Download the required `mavsdk_server_bin` if not present
- Provide guidance for installing Node.js if not already installed

> 🧠 **Manual setup available** if preferred — just activate `venv`, install requirements, and create configs manually.

---

### 🧰 YOLO Model Setup (For Smart Tracker)

PixEagle 3.0 includes `add_yolo_model.py`, a utility to download and prepare YOLO models for use in the Smart Tracker (GPU or CPU compatible).

```bash
python src/tools/add_yolo_model.py
```

This will:

- Download a model (e.g. `yolo11s.pt`) from Ultralytics
- Export to ONNX
- Optionally optimize for GPU inference
- Register the model in `configs/config.yaml`

> 💡 Supports custom or fine-tuned YOLO models too!

---

### ⚙️ Configuration

#### 1. **Main Application Settings**

Open the configuration file to customize your setup:

```bash
nano configs/config.yaml
```

Edit values such as:

- Video input (webcam, RTSP, CSI, or test files)
- PID tuning
- Tracker options
- SmartTracker mode selection: GPU vs CPU, fallback behavior
- Camera field of view and orientation

#### 2. **Dashboard Environment**

Configure dashboard networking (API and streaming ports):

```bash
nano dashboard/.env
```

Make sure the backend IP/port matches the one used by your drone or dev machine.

> 🧪 Test your installation anytime with:
```bash
python src/test_Ver.py
```

## 🧩 PX4 Integration

PixEagle integrates with PX4 via MAVLink for real-time command and telemetry. Follow the steps below to set up MAVLink routing and required bridge components.

---

### 🔄 MAVLink Routing Setup

#### ✅ Option A: Auto Setup via `mavlink-anywhere` (Recommended for Pi/Jetson)

1. **Clone and Install:**

```bash
cd ~
git clone https://github.com/alireza787b/mavlink-anywhere.git
cd mavlink-anywhere
bash install_mavlink_router.sh
```

2. **Configure Serial & Endpoints:**

```bash
bash ~/mavlink-anywhere/configure_mavlink_router.sh
```

- Input: e.g., `/dev/ttyAMA0`, `/dev/ttyS0`, or `/dev/ttyTHS1`  
- Output: e.g., `127.0.0.1:14540`, `127.0.0.1:14550`, `127.0.0.1:14569`

> 🧠 You can run `ls /dev/tty*` to locate the right serial port.

---

#### 🛠️ Option B: Manual MAVLink Router Command

```bash
mavlink-routerd \
  -e 127.0.0.1:14540 \
  -e 127.0.0.1:14550 \
  -e 127.0.0.1:14569 \
  0.0.0.0:14550
```

Use IPs that match your SITL, companion, or GCS network setup.

---

### 🌐 MAVLink2REST (Telemetry Bridge)

1. **Start MAVLink2REST:**

```bash
bash ~/PixEagle/src/tools/mavlink2rest/run_mavlink2rest.sh
```

- Default port: `14569`
- Binaries are auto-installed, or you can build manually from source.

---

### 🧠 MAVSDK Server Binary (Required)

PixEagle uses `mavsdk_server_bin` for all MAVSDK functionality.

#### A. **Check for Binary:**

Make sure it's in the root directory:  
```bash
~/PixEagle/mavsdk_server_bin
```

#### B. **Install Automatically:**

The main startup script (`run_pixeagle.sh`) will prompt to install it if missing.

#### C. **Or Download Manually:**

```bash
bash ~/PixEagle/src/tools/download_mavsdk_server.sh
```

Or grab it from the [MAVSDK Releases](https://github.com/mavlink/MAVSDK/releases) page and rename it to `mavsdk_server_bin`.

---

## ▶️ Running PixEagle

Start the full PixEagle suite with a single command:

```bash
bash run_pixeagle.sh
```

### This will:

- ✅ Launch:
  - Main Python app (classic + smart tracking)
  - FastAPI backend
  - Web dashboard (React)
  - MAVSDK server
  - MAVLink2REST
- 🧼 Clean ports (`8088`, `5077`, `3001`) if in use
- ⚙️ Setup all tmux panes automatically

---

### 🪟 Tmux Controls

- **Switch panes/windows:**  
  `Ctrl + B`, then arrow keys or window number
- **Detach session:**  
  `Ctrl + B`, then `D`
- **Reattach session:**  
  ```bash
  tmux attach -t PixEagle
  ```

---

### 🎯 Advanced CLI Flags (Optional)

```bash
bash run_pixeagle.sh [-m] [-d] [-p] [-k]
```

- `-m`: Skip MAVLink2REST  
- `-d`: Skip Dashboard  
- `-p`: Skip Python main app  
- `-k`: Skip MAVSDK server  

---

### 🔗 Accessing the Web Dashboard

Once running, open in your browser:

```
http://localhost:3001
```

From a remote device, use the host's IP address instead of `localhost`. Ensure the firewall permits port `3001`.

---

## 🎥 GStreamer & CSI Camera Support

PixEagle supports RTSP, CSI, and GStreamer pipelines.

To enable, set the `VIDEO_SOURCE` in `configs/config.yaml`. Example:

```yaml
VIDEO_SOURCE: "gst-pipeline://nvarguscamerasrc ! video/x-raw(memory:NVMM), width=640, height=480, framerate=30/1 ! nvvidconv ! video/x-raw, format=BGRx ! videoconvert ! appsink"
```

> ⚠️ Ensure OpenCV is built with GStreamer support!  
> [GStreamer OpenCV Build Guide](https://github.com/alireza787b/PixEagle/blob/main/opencv_with_gstreamer.md)

Test camera and config:

```bash
python src/test_Ver.py
```

---

### ⌨️ Key Bindings (Video Window)

| Key | Action                        |
|-----|-------------------------------|
| `t` | Select ROI (Classic Tracker)  |
| `c` | Cancel Tracking               |
| `y` | Trigger YOLO Detection        |
| `f` | Start Following               |
| `d` | Redetect Lost Object          |
| `s` | Toggle Smart Tracker Mode     |
| `q` | Quit PixEagle Session         |

---

## 🪟 Windows Setup Notes

PixEagle is compatible with Windows for **SITL/X-Plane simulation only**. Use WSL for routing tools and terminal scripts.

Manual steps:

1. **Main App:**

```bash
python src/main.py
```

2. **Dashboard:**

```bash
cd dashboard
npm install
npm start
```

3. **MAVLink2REST:**

Use WSL or Linux machine. You may need to port-forward if testing across devices.

4. **Reference Guide:**  
[Follow Mode + X-Plane Guide](https://github.com/alireza787b/PixEagle/blob/main/Follow_Mode_Xplane_Guide.md)


## 🧩 Setting Up MAVLink Routing

To enable PixEagle to communicate with PX4, you must configure MAVLink routing. This setup includes configuring serial connections, as well as integrating MAVLink2REST for telemetry.

---

### ⚙️ Using `mavlink-anywhere` Auto-Start Daemon

For systems like Raspberry Pi or Jetson, the **mavlink-anywhere** auto-start daemon will automatically route serial connections (e.g., `/dev/ttyS0`, `/dev/ttyAMA0`, or `/dev/ttyTHS1`) to UDP endpoints (e.g., `127.0.0.1:14550`, `127.0.0.1:14540`, etc.).

#### Setup:

1. **Clone and Install the MAVLink Anywhere Router:**

```bash
cd ~
git clone https://github.com/alireza787b/mavlink-anywhere.git
cd mavlink-anywhere
bash install_mavlink_router.sh
```

2. **Configure Router for Serial & UDP Endpoints:**

```bash
bash ~/mavlink-anywhere/configure_mavlink_router.sh
```

- **Serial Source (Input):** Example: `/dev/ttyAMA0`, `/dev/ttyS0`
- **UDP Endpoints (Output):** Example: `127.0.0.1:14540 127.0.0.1:14550 127.0.0.1:14569`

> 🧠 To confirm serial ports, run `ls /dev/tty*` to check available ports.

---

### 🛠️ Manual MAVLink Router Commands (Optional)

Alternatively, you can run the `mavlink-router` manually using the following command:

```bash
mavlink-routerd -e 172.21.144.1:14540 -e 172.21.144.1:14550 -e 172.21.144.1:14569 -e 127.0.0.1:14569 0.0.0.0:14550
```

Adjust the **IP addresses** and **ports** to match your network setup. This is useful if you want more control over routing and don't use the auto-start daemon.

---

### 🌐 Installing and Running MAVLink2REST

MAVLink2REST is used for exposing MAVLink telemetry as REST APIs. It helps bridge communication between PixEagle and external applications.

1. **Run the Installation Script for MAVLink2REST:**

```bash
bash ~/PixEagle/src/tools/mavlink2rest/run_mavlink2rest.sh
```

This will install and start the MAVLink2REST service on port `14569` by default. If you encounter issues building it, pre-built binaries are available for download.

---

### 🧠 Ensuring `mavsdk_server_bin` is Present

PixEagle uses the `mavsdk_server_bin` binary to interface with MAVSDK for PX4 communication. If it's missing, follow these steps to ensure it is available.

1. **Check for the Binary in the Root Directory:**

   ```bash
   ~/PixEagle/mavsdk_server_bin
   ```

2. **Download `mavsdk_server_bin` Manually:**

   If the binary is missing, either download it directly from the [MAVSDK Releases](https://github.com/mavlink/MAVSDK/releases) page and place it in the root directory (`~/PixEagle`), or use the provided script:

```bash
bash ~/PixEagle/src/tools/download_mavsdk_server.sh
```

---

## ▶️ Running PixEagle

With everything set up, you can start PixEagle using the following command:

```bash
bash run_pixeagle.sh
```

This will:

- ✅ Launch all necessary components (MAVLink2REST, Dashboard, Main Application, MAVSDK Server) in separate `tmux` windows.
- 🧼 Ensure default ports (`8088`, `5077`, `3001`) are free before starting.
- ⚙️ Provide a split-screen view of all running processes.

---

### 🪟 Tmux Session Management

PixEagle runs all components within `tmux` sessions. Below are the useful `tmux` controls:

- **Switch Between Windows:** `Ctrl+B`, then the window number (`1`, `2`, `3`)
- **Switch Between Panes:** `Ctrl+B`, then arrow keys (`←`, `→`, `↑`, `↓`)
- **Detach from Session:** `Ctrl+B`, then `D`
- **Reattach to Session:** 

```bash
tmux attach -t PixEagle
```

- **Close a Pane/Window:** Type `exit` or `Ctrl+D`

---

### 🎯 Customize Execution (Flags)

You can selectively run or skip components by passing flags to the script:

```bash
bash run_pixeagle.sh [-m] [-d] [-p] [-k]
```

- `-m`: Skip MAVLink2REST
- `-d`: Skip Dashboard
- `-p`: Skip Main Python Application
- `-k`: Skip MAVSDK Server

> Example: Run only Dashboard and Main Application:

```bash
bash run_pixeagle.sh -m
```

---

### 🌐 Accessing the Dashboard

Once the dashboard is running, access it at:

```
http://127.0.0.1:3001
```

For remote access, replace `127.0.0.1` with your system's IP. Make sure your firewall allows access to port `3001`.

---

## 🎥 GStreamer & CSI Camera Support

PixEagle supports video input/output via **GStreamer** and **CSI cameras**.

1. **Configure Video Source in `config.yaml`:**

   Example pipeline for CSI cameras:

```yaml
VIDEO_SOURCE: "gst-pipeline://nvarguscamerasrc ! video/x-raw(memory:NVMM), width=640, height=480, framerate=30/1 ! nvvidconv ! video/x-raw, format=BGRx ! videoconvert ! appsink"
```

2. **Ensure OpenCV is Built with GStreamer Support:**

   Follow this [GStreamer OpenCV Build Guide](https://github.com/alireza787b/PixEagle/blob/main/opencv_with_gstreamer.md) to ensure OpenCV is properly built.

---

### 🧪 Verify Installation:

Test your setup with:

```bash
python src/test_Ver.py
```

---

### ⌨️ Key Bindings (During Video Window)

While in the video window, these key bindings are available:

| Key | Action                                |
|-----|---------------------------------------|
| `t` | Select target for tracking           |
| `c` | Cancel selection                     |
| `y` | Trigger YOLO detection               |
| `f` | Start following (offboard mode)      |
| `d` | Attempt to re-detect the target      |
| `q` | Quit PixEagle                        |

---

## 🪟 Windows Setup Notes

PixEagle is **supported on Windows** for **SITL/X-Plane only**. You’ll need to manually execute certain components as bash scripts won’t work out of the box.

1. **Main Application:**

```bash
python src/main.py
```

2. **Run Dashboard:**

```bash
cd dashboard
npm install
npm start
```

3. **MAVLink2REST & MAVLink Router:**

To run on Windows, use **WSL** (Windows Subsystem for Linux) or adapt the commands accordingly.

> 📄 **For detailed SITL/X-Plane setup on Windows**, refer to [Follow Mode + X-Plane Guide](https://github.com/alireza787b/PixEagle/blob/main/Follow_Mode_Xplane_Guide.md).


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

*PixEagle 3.0 is currently in an experimental stage and has not been tested in real-world scenarios. Use at your own risk. The developers are not responsible for any misuse or damages resulting from the use of this software.*

### 👍 **Stay Connected & Get Involved:**

- **🔔 Subscribe** to our [YouTube Channel](https://www.youtube.com/channel/YourChannelLink) for more updates and tutorials on PixEagle 2.0.
- **💬 Share** your thoughts and suggestions in the [issues](https://github.com/alireza787b/PixEagle/issues) section of our GitHub repository!
- **🔗 Join** our community by contributing on [GitHub](https://github.com/alireza787b/PixEagle).

### 📢 **Call to Action:**

Enjoyed PixEagle 3.0? **Star ⭐** the repository, **fork 🔀** it for your projects, and **contribute** to help us continue to innovate and improve PixEagle. Your support is invaluable!
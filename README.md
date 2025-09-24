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

#### 🏗️ Schema-Aware Architecture (New)

- **YAML-based configuration system** for trackers and followers
- **Add custom trackers** without modifying core code
- **Dynamic validation** and type-safe data structures
- **Extensible follower modes** with unified command processing
- 📚 [Complete Developer Guide](docs/Tracker_and_Follower_Schema_Developer_Guide.md)

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
- **Node.js & npm:** Required for the Dashboard UI. (Install from: https://nodejs.org/en/download)  
- **Other Tools:** `tmux`, `lsof`, `curl` (for automatic setups)

#### 📦 Install Prerequisites (Linux)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip tmux lsof curl git
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

Make sure you have all the prerequisites installed before running this script. (Nodejs, npm, python, etc.)
```bash
bash init_pixeagle.sh
```

This script will:

- Create a Python virtual environment  
- Install all required Python packages  
- Generate `config.yaml` and `.env` files if missing  
- Download the required `mavsdk_server_bin` if not present  
- Provide guidance for installing Node.js if not already installed  

> 🧠 **Manual setup available** if preferred — just activate the `venv`, install requirements, and create configs manually.

---

### ⚙️ Note for Smart Tracker & YOLO Users (GPU Support)

If you're planning to use **YOLO models with Smart Tracker**, especially with **GPU acceleration via CUDA**, you need to **manually install PyTorch** to match your hardware and CUDA version.

> ✅ As of now, **PyTorch 2.1.0** or newer (e.g. **2.5.1**) is recommended.

📌 Go to the [official PyTorch installation page](https://pytorch.org/get-started/locally/)  
Select your preferences (OS, package manager, Python version, CUDA version)  
Then follow the command it provides to install PyTorch manually **before** running the tracker.

Example (for CUDA 12.4, PyTorch 2.5.1 tested on NVidia 3080Ti):

```bash
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124
```

Example (for CUDA 12.4, PyTorch 2.5.1 tested on CPU):

```bash
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
```

> 🔧 The version of PyTorch installed automatically might not be optimized for your GPU. Installing it manually ensures **maximum performance** and **CUDA compatibility** based on your hardware instructions.



---

### 🧰 YOLO Model Setup (For Smart Tracker)

PixEagle 3.0 includes `add_yolo_model.py`, a utility to download and prepare YOLO models for use in the Smart Tracker (GPU or CPU compatible).

```bash
source venv/bin/activate
python add_yolo_model.py
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

#### 2. **Follower Mode Configuration**

PixEagle 3.0 features unified follower configurations for easy customization:

```yaml
# Example follower configurations in config_default.yaml

CONSTANT_POSITION:
  ENABLE_ALTITUDE_CONTROL: true
  MIN_DESCENT_HEIGHT: 3.0
  MAX_CLIMB_HEIGHT: 120.0
  CONTROL_UPDATE_RATE: 20.0

BODY_VELOCITY_CHASE:
  MAX_FORWARD_VELOCITY: 8.0
  LATERAL_GUIDANCE_MODE: coordinated_turn
  ALTITUDE_SAFETY_ENABLED: false
```

**Available Follower Modes:**
- **CONSTANT_POSITION** (11 params) - Position hold with altitude control
- **CONSTANT_DISTANCE** (14 params) - Fixed distance tracking
- **CHASE_FOLLOWER** (17 params) - High-speed pursuit with coordinated turns
- **GROUND_VIEW** (15 params) - Ground target tracking with gimbal compensation
- **BODY_VELOCITY_CHASE** (23 params) - Body velocity control with dual guidance modes

Each follower mode has dedicated parameters for control enablement, safety limits, performance tuning, and mode-specific features. All parameters include sensible defaults and comprehensive documentation.

#### 3. **Dashboard Environment**

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
##  Building Opencv
If you want to use GStreamer, you need to build opencv manually. You can use the step by step instruction [here](https://github.com/alireza787b/PixEagle/blob/main/opencv_with_gstreamer.md) or use (`auto_opencv_build.sh`) sciprt.

```bash
bash ~/PixEagle/auto_opencv_build.sh
```

---

## ▶️ Running PixEagle

**Main Workflow:** Start the complete PixEagle suite with a single command:

```bash
bash run_pixeagle.sh
```

This is the **recommended way** to run PixEagle - it automatically launches all components (Python app, React dashboard, MAVLink2REST, MAVSDK server) in optimized tmux sessions.

### ⚡ Performance Optimizations (New in 3.0)

The system now includes intelligent caching for faster startup:

- **Smart dependency management** - Only reinstalls npm packages when needed
- **Intelligent build caching** - Skips React rebuilds when no source changes detected
- **Performance reporting** - Shows cache hits and startup times
- **~80% faster startup** when no changes detected

### 🔧 Development & Advanced Options

**Development Mode:**
```bash
./run_pixeagle.sh --dev     # Development mode with hot-reload
./run_pixeagle.sh --rebuild # Force rebuild all components
./run_pixeagle.sh --dev --rebuild # Dev mode + force rebuild
```

**Individual component testing:**
```bash
./run_dashboard.sh          # Dashboard only (production + caching)
./run_dashboard.sh -d       # Dashboard only (development mode)
./run_dashboard.sh -f       # Force rebuild even if no changes
```

**Custom component selection:**
```bash
./run_pixeagle.sh -d        # Skip dashboard
./run_pixeagle.sh -p        # Skip Python app
./run_pixeagle.sh -s        # Separate tmux windows
./run_pixeagle.sh --help    # Show all available options
```

**Development Mode Features:**
- **Dashboard**: Hot-reload with live changes (npm start)
- **Backend**: Development environment variables and debug mode
- **Enhanced logging**: Unbuffered output and detailed error messages
- **Force rebuild**: Clean npm cache and fresh builds when needed

### This will:

- ✅ Launch:
  - Main Python app (classic + smart tracking)
  - FastAPI backend
  - Web dashboard (React)
  - MAVSDK server
  - MAVLink2REST
- 🧼 Clean ports (`8088`, `5077`, `3000`) if in use
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

## 🔧 Service Management (Auto-Start)

**For Production/Raspberry Pi:** Enable PixEagle to start automatically on boot with professional service management:

### 📦 Installation

```bash
# Install service management system
sudo bash install_service.sh
```

### 🚀 Service Commands

```bash
pixeagle-service start      # Start PixEagle immediately
pixeagle-service stop       # Stop PixEagle gracefully
pixeagle-service status     # Show detailed status & health
pixeagle-service restart    # Clean restart with reporting

# Auto-start setup (requires sudo)
sudo pixeagle-service enable    # Enable auto-start on boot
sudo pixeagle-service disable   # Disable auto-start

# Monitoring & Access
pixeagle-service logs       # Show service logs
pixeagle-service logs -f    # Follow logs in real-time
pixeagle-service attach     # Access tmux session
pixeagle-service help       # Detailed help
```

### ✨ Service Features

- **Automatic startup** on system boot (Raspberry Pi/Linux)
- **Intelligent user detection** - works with any user
- **Professional status reporting** with component health checks
- **Seamless tmux integration** - attach/detach without interruption
- **Robust error handling** and graceful shutdown
- **Performance monitoring** and comprehensive logging

**Quick Setup:**
```bash
# 1. Install service management
sudo bash install_service.sh

# 2. Test functionality
pixeagle-service status
pixeagle-service start

# 3. Enable auto-start
sudo pixeagle-service enable
```

---

### 🔗 Accessing the Web Dashboard

Once running, open in your browser:

```
http://localhost:3000
```

From a remote device, use the host's IP address instead of `localhost`. Ensure the firewall permits port `3000`.

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

## Windows Setup Notes

PixEagle is compatible with Windows for **SITL/X-Plane simulation**. Use WSL for routing tools and terminal scripts.

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
[Follow Mode + X-Plane setup on Windows Guide](https://github.com/alireza787b/PixEagle/blob/main/Follow_Mode_Xplane_Guide.md)




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

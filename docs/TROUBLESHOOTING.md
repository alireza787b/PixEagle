# Troubleshooting Guide

> Common issues and solutions for PixEagle

## Installation Issues

### Python Version Error

**Problem**: `Python 3.9+ required`

**Solution**:
```bash
# Check version
python3 --version

# Install newer Python (Ubuntu)
sudo apt install python3.11 python3.11-venv
```

### npm/Node.js Not Found

**Problem**: Dashboard fails to start, npm command not found

**Solution**:
```bash
# Reload nvm
source ~/.nvm/nvm.sh
nvm use 22

# Or reinstall
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
```

### Permission Denied on Scripts

**Solution**:
```bash
chmod +x scripts/*.sh scripts/**/*.sh
```

## Video Feed Issues

### Camera Not Detected

**Check available cameras**:
```bash
ls /dev/video*
v4l2-ctl --list-devices
```

**Update config.yaml**:
```yaml
VIDEO_SOURCE: 0  # or /dev/video0
```

### RTSP Stream Not Working

**Test stream**:
```bash
ffplay rtsp://your-stream-url
```

**Check network connectivity** and firewall settings.

### GStreamer Pipeline Errors

**Rebuild OpenCV with GStreamer**:
```bash
bash scripts/setup/build-opencv.sh
```

If you rebuilt OpenCV manually, `make init` will ask before replacing it:

`Overwrite custom OpenCV? [y/N]`

Choose **N** to preserve your GStreamer-enabled build.

## Dashboard Issues

### Dashboard Not Accessible

1. **Check if running**: `tmux attach -t pixeagle`
2. **Check port**: `lsof -i :3040`
3. **Firewall**: `sudo ufw allow 3040`

### API Connection Failed

1. **Check backend**: `lsof -i :5077`
2. **Verify config**: Dashboard auto-detects host from browser URL
3. **Check logs**: Look at Python app pane in tmux

### LAN Access Not Working

Dashboard uses `window.location.hostname` for auto-detection. Ensure:
- Both devices on same network
- Firewall allows ports 3040, 5077
- Use IP address, not localhost

## PX4/MAVLink Issues

### MAVSDK Connection Failed

1. **Check binary exists**: `ls bin/mavsdk_server_bin`
2. **Re-download**: `bash scripts/setup/download-binaries.sh --mavsdk`
3. **Check port**: MAVLink should be on 14540

### MAVLink2REST Not Responding

1. **Check binary**: `ls bin/mavlink2rest`
2. **Re-download**: `bash scripts/setup/download-binaries.sh --mavlink2rest`
3. **Check port 14569**

### No Telemetry Data

1. **Verify MAVLink routing**: `mavlink-routerd` running?
2. **Check endpoints**: 127.0.0.1:14540, 14550, 14569
3. **Verify connection**: QGroundControl can connect?

## SmartTracker Issues

### SmartTracker Says ultralytics/lap Not Installed After Full Init

**Problem**: You selected `Full` in `make init`, but SmartTracker still reports missing AI packages.

**Why it happens**:
- Core dependencies may install successfully while AI verification fails
- Init can roll back AI packages if verification fails (based on your prompt choice)
- Network/wheel availability can cause transient AI install failures

**Solution**:
```bash
bash scripts/setup/setup-pytorch.sh --mode auto
bash scripts/setup/install-ai-deps.sh
bash scripts/setup/check-ai-runtime.sh
```

If the runtime check reports healthy `torch/ultralytics/lap`, restart PixEagle and re-enable SmartTracker.
If NCNN auto-export on model upload fails, also verify `pnnx` is installed in the same venv.

### YOLO Model Not Loading

**Check model exists**:
```bash
ls yolo/*.pt
```

**Download model**:
```bash
python add_yolo_model.py --model_name yolo26n.pt
```

### GPU Not Detected

1. **Check driver/runtime**: `nvidia-smi` (or `tegrastats` on Jetson)
2. **Run diagnostic**: `bash scripts/setup/check-ai-runtime.sh`
3. **Reinstall via matrix installer**: `bash scripts/setup/setup-pytorch.sh --mode auto`
4. **Strict GPU validation** (optional): `bash scripts/setup/setup-pytorch.sh --mode gpu`

### Low FPS

1. **Use smaller model**: yolo26n vs yolo26s
2. **Enable GPU**: Set `SMART_TRACKER_USE_GPU: true`
3. **Lower resolution** in config

## Service Issues

### Service Won't Start

```bash
# Check status
pixeagle-service status

# Check logs
pixeagle-service logs -n 200

# Reinstall command wrapper
sudo bash scripts/service/install.sh

# (Re)enable boot auto-start
sudo pixeagle-service enable
```

### Tmux Session Lost

```bash
# List sessions
tmux ls

# Reattach
tmux attach -t pixeagle

# If no session, restart
pixeagle-service start
```

## Firewall & Network Issues

### Check Port Status

```bash
# Check which ports are in use
sudo lsof -i :3040   # Dashboard
sudo lsof -i :5077   # Backend
sudo lsof -i :5551   # WebSocket (video)
sudo lsof -i :8088   # MAVLink2REST
sudo lsof -i :14540  # MAVSDK
sudo lsof -i :14569  # MAVLink input
```

### Open Required Ports (Ubuntu/Raspbian)

```bash
# PixEagle core services
sudo ufw allow 3040/tcp   # Dashboard
sudo ufw allow 5077/tcp   # Backend API
sudo ufw allow 5551/tcp   # WebSocket (video)
sudo ufw allow 8088/tcp   # MAVLink2REST

# PX4/MAVLink (UDP)
sudo ufw allow 14540/udp  # MAVSDK
sudo ufw allow 14569/udp  # MAVLink2REST input
sudo ufw allow 14550/udp  # QGC (optional)

# Verify rules
sudo ufw status
```

### Port Reference

| Port | Service | Protocol | Required |
|------|---------|----------|----------|
| 3040 | Dashboard | TCP | Yes |
| 5077 | Backend API | TCP | Yes |
| 5551 | WebSocket (video) | TCP | Yes |
| 8088 | MAVLink2REST API | TCP | For telemetry |
| 14540 | MAVSDK | UDP | For PX4 |
| 14569 | MAVLink2REST input | UDP | For PX4 |
| 14550 | QGC | UDP | Optional |

## Windows-Specific Issues

### Python Not Found

**Problem**: `'python' is not recognized as an internal or external command`

**Solution**:
1. Install Python from [python.org](https://www.python.org/downloads/)
2. During installation, check **"Add Python to PATH"**
3. Restart Command Prompt

### Node.js Not Found

**Problem**: `'node' is not recognized...`

**Solution**:
1. Install Node.js from [nodejs.org](https://nodejs.org/en/download)
2. Restart Command Prompt

### Port Already In Use (Windows)

```cmd
# Find process using the port
netstat -ano | findstr :3040

# Kill the process (replace PID with actual number)
taskkill /PID 12345 /F
```

### Colors Not Displaying

**Problem**: ANSI color codes showing as text

**Solution**:
- Use Windows Terminal (recommended)
- Ensure Windows 10 version 1809 or later
- Colors are enabled automatically by the scripts

### Virtual Environment Issues (Windows)

**Problem**: venv activation fails

**Solution**:
```cmd
# Remove corrupted venv
rmdir /s /q venv

# Re-run init
scripts\init.bat
```

### npm Install Fails (Windows)

```cmd
cd dashboard
rmdir /s /q node_modules
del package-lock.json
npm install
```

### Port Status Check (Windows)

```cmd
netstat -ano | findstr "3040 5077 8088 5551"
```

> **Full Windows Guide**: [Windows Setup Documentation](WINDOWS_SETUP.md)

## Getting Help

- [GitHub Issues](https://github.com/alireza787b/PixEagle/issues)
- [Documentation Index](README.md)
- [Windows Setup Guide](WINDOWS_SETUP.md)
- [YouTube Tutorials](https://www.youtube.com/watch?v=nMThQLC7nBg&list=PLVZvZdBQdm_4oain9--ClKioiZrq64-Ky)

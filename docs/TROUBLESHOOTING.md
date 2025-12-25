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
chmod +x init_pixeagle.sh run_pixeagle.sh
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
bash auto_opencv_build.sh
```

## Dashboard Issues

### Dashboard Not Accessible

1. **Check if running**: `tmux attach -t PixEagle`
2. **Check port**: `lsof -i :3000`
3. **Firewall**: `sudo ufw allow 3000`

### API Connection Failed

1. **Check backend**: `lsof -i :5077`
2. **Verify config**: Dashboard auto-detects host from browser URL
3. **Check logs**: Look at Python app pane in tmux

### LAN Access Not Working

Dashboard uses `window.location.hostname` for auto-detection. Ensure:
- Both devices on same network
- Firewall allows ports 3000, 5077
- Use IP address, not localhost

## PX4/MAVLink Issues

### MAVSDK Connection Failed

1. **Check binary exists**: `ls mavsdk_server_bin`
2. **Re-download**: `bash src/tools/download_mavsdk_server.sh`
3. **Check port**: MAVLink should be on 14540

### MAVLink2REST Not Responding

1. **Check binary**: `ls mavlink2rest`
2. **Re-download**: `bash src/tools/download_mavlink2rest.sh`
3. **Check port 14569**

### No Telemetry Data

1. **Verify MAVLink routing**: `mavlink-routerd` running?
2. **Check endpoints**: 127.0.0.1:14540, 14550, 14569
3. **Verify connection**: QGroundControl can connect?

## SmartTracker Issues

### YOLO Model Not Loading

**Check model exists**:
```bash
ls yolo/*.pt
```

**Download model**:
```bash
python add_yolo_model.py --model_name yolo11n.pt
```

### GPU Not Detected

1. **Check CUDA**: `nvidia-smi`
2. **Check PyTorch**: `python -c "import torch; print(torch.cuda.is_available())"`
3. **Reinstall PyTorch** for your CUDA version

### Low FPS

1. **Use smaller model**: yolo11n vs yolo11s
2. **Enable GPU**: Set `SMART_TRACKER_USE_GPU: true`
3. **Lower resolution** in config

## Service Issues

### Service Won't Start

```bash
# Check status
pixeagle-service status

# Check logs
pixeagle-service logs

# Reinstall
sudo bash install_service.sh
```

### Tmux Session Lost

```bash
# List sessions
tmux ls

# Reattach
tmux attach -t PixEagle

# If no session, restart
bash run_pixeagle.sh
```

## Firewall & Network Issues

### Check Port Status

```bash
# Check which ports are in use
sudo lsof -i :3000   # Dashboard
sudo lsof -i :5077   # Backend
sudo lsof -i :8088   # MAVLink2REST
sudo lsof -i :14540  # MAVSDK
sudo lsof -i :14569  # MAVLink input
```

### Open Required Ports (Ubuntu)

```bash
# PixEagle core services
sudo ufw allow 3000/tcp   # Dashboard
sudo ufw allow 5077/tcp   # Backend API
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
| 3000 | Dashboard | TCP | Yes |
| 5077 | Backend API | TCP | Yes |
| 8088 | MAVLink2REST | TCP | For telemetry |
| 14540 | MAVSDK | UDP | For PX4 |
| 14569 | MAVLink input | UDP | For PX4 |
| 14550 | QGC | UDP | Optional |

## Getting Help

- [GitHub Issues](https://github.com/alireza787b/PixEagle/issues)
- [Documentation Index](README.md)
- [YouTube Tutorials](https://www.youtube.com/watch?v=nMThQLC7nBg&list=PLVZvZdBQdm_4oain9--ClKioiZrq64-Ky)

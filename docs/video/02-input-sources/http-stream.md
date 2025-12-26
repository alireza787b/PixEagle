# HTTP Stream Source

> HTTP/HTTPS video streaming for web cameras

## Overview

HTTP streaming supports MJPEG streams and other HTTP-based video sources. Higher latency than RTSP/UDP but works through firewalls and proxies.

## Configuration

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: HTTP_STREAM
  HTTP_URL: http://192.168.1.100:8080/video
  USE_GSTREAMER: false  # OpenCV usually works
```

## GStreamer Pipeline

When `USE_GSTREAMER: true`:

```
souphttpsrc location=http://192.168.1.100:8080/video
  ! decodebin
  ! videoconvert
  ! video/x-raw,format=BGR
  ! videoscale
  ! video/x-raw,width=640,height=480
  ! appsink drop=true sync=false
```

## Common URL Patterns

### MJPEG Streams

```yaml
# ESP32-CAM
HTTP_URL: http://192.168.1.100:81/stream

# IP Webcam (Android)
HTTP_URL: http://192.168.1.100:8080/video

# Motion
HTTP_URL: http://localhost:8081/
```

### HTTPS

```yaml
HTTP_URL: https://secure-camera.example.com/stream
```

## Use Cases

- Web cameras with HTTP output
- Security cameras with web interface
- Android IP Webcam app
- ESP32-CAM modules

## Troubleshooting

### Connection Refused

1. Verify URL in browser first
2. Check authentication requirements
3. Verify network connectivity

### High Latency

HTTP streams typically have 200-500ms latency. For lower latency, consider RTSP or UDP sources.

## Example: ESP32-CAM

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: HTTP_STREAM
  HTTP_URL: http://esp32-cam.local:81/stream
  USE_GSTREAMER: false
```

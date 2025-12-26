# Video System Architecture

> Core architecture, components, and design patterns

## Overview

The video architecture is designed around the `VideoHandler` class, which provides a unified interface for all video input sources with automatic backend selection, error recovery, and frame state management.

## Contents

| Document | Description |
|----------|-------------|
| [video-handler.md](video-handler.md) | VideoHandler class reference |
| [frame-state-management.md](frame-state-management.md) | Frame states and caching |
| [error-recovery.md](error-recovery.md) | Failure handling and reconnection |

## Component Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                           VideoHandler                                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────────┐  │
│  │ Capture Factory │   │ Frame Manager   │   │ Connection Health   │  │
│  │                 │   │                 │   │                     │  │
│  │ - VIDEO_FILE    │   │ - raw_frame     │   │ - failure_count     │  │
│  │ - USB_CAMERA    │   │ - osd_frame     │   │ - recovery_state    │  │
│  │ - RTSP_STREAM   │   │ - resized_raw   │   │ - frame_cache       │  │
│  │ - UDP_STREAM    │   │ - resized_osd   │   │ - timeout_tracking  │  │
│  │ - HTTP_STREAM   │   │ - frame_history │   │                     │  │
│  │ - CSI_CAMERA    │   │                 │   │                     │  │
│  │ - CUSTOM_GSTR   │   │                 │   │                     │  │
│  └────────┬────────┘   └────────┬────────┘   └──────────┬──────────┘  │
│           │                     │                       │              │
│           └──────────┬──────────┴───────────────────────┘              │
│                      │                                                  │
│                      ▼                                                  │
│           ┌─────────────────────┐                                      │
│           │  cv2.VideoCapture   │                                      │
│           │  (OpenCV/GStreamer) │                                      │
│           └─────────────────────┘                                      │
└────────────────────────────────────────────────────────────────────────┘
```

## Design Principles

### 1. Factory Pattern for Sources

The `VideoHandler` uses a factory pattern to create source-specific capture objects:

```python
handlers = {
    "VIDEO_FILE": self._create_video_file_capture,
    "USB_CAMERA": self._create_usb_camera_capture,
    "RTSP_STREAM": self._create_rtsp_capture,
    "UDP_STREAM": self._create_udp_capture,
    "HTTP_STREAM": self._create_http_capture,
    "CSI_CAMERA": self._create_csi_capture,
    "CUSTOM_GSTREAMER": self._create_custom_gstreamer_capture
}
```

### 2. Graceful Degradation

Multiple fallback strategies ensure video continues even with connection issues:

1. **Primary Pipeline** - Optimal performance
2. **Fallback Pipelines** - Reduced features, higher stability
3. **OpenCV Backend** - Universal compatibility
4. **Cached Frames** - Last-resort during recovery

### 3. Coordinate Consistency

All pipelines maintain consistent dimensions for accurate dashboard-to-frame coordinate mapping:

- `videoscale` element enforces target dimensions
- Dimensions validated against configuration
- Smart scaling in RTSP pipelines

### 4. Platform Awareness

Automatic optimization based on detected platform:

```python
self.platform = platform.system()  # Linux, Windows, Darwin
self.is_arm = platform.machine().startswith('arm') or platform.machine().startswith('aarch')
```

## Data Flow

```
1. Configuration
   │
   ▼
2. init_video_source()
   │
   ├──▶ _create_capture_object()
   │    │
   │    ├──▶ GStreamer Pipeline (if USE_GSTREAMER)
   │    │
   │    └──▶ OpenCV Backend (fallback)
   │
   ▼
3. get_frame()
   │
   ├──▶ Success: Update frame states
   │    │
   │    ├── current_raw_frame
   │    ├── frame_history
   │    └── _frame_cache
   │
   └──▶ Failure: _handle_frame_failure()
        │
        ├──▶ Below threshold: Return cached frame
        │
        └──▶ Above threshold: _attempt_recovery()
```

## Key Attributes

| Attribute | Type | Purpose |
|-----------|------|---------|
| `cap` | `cv2.VideoCapture` | Underlying capture object |
| `width`, `height` | `int` | Frame dimensions |
| `fps` | `float` | Frames per second |
| `current_raw_frame` | `np.ndarray` | Latest captured frame |
| `current_osd_frame` | `np.ndarray` | Frame with OSD overlays |
| `frame_history` | `deque` | Recent frame buffer |
| `_frame_cache` | `deque` | Recovery frame cache |
| `_consecutive_failures` | `int` | Failure counter |
| `_is_recovering` | `bool` | Recovery state flag |

## Thread Safety

The `VideoHandler` is designed for single-threaded use in the main application loop. Frame states are updated synchronously:

```python
# Main loop pattern
while running:
    frame = video_handler.get_frame()
    # Process frame
    video_handler.current_osd_frame = processed_frame
    video_handler.update_resized_frames(stream_width, stream_height)
```

## Integration Points

### With AppController

```python
self.video_handler = VideoHandler()
frame = self.video_handler.get_frame()
```

### With Trackers

```python
tracker = CSRTTracker(video_handler, detector, app_controller)
# Tracker uses video_handler.width, video_handler.height
```

### With Streaming

```python
# FastAPI uses resized frames
frame = video_handler.current_resized_osd_frame
```

## Performance Characteristics

| Metric | Typical Value | Notes |
|--------|---------------|-------|
| `get_frame()` | <1ms | GStreamer optimized |
| Frame buffer | 5 frames | Configurable |
| Recovery timeout | 5s | Before forced reconnect |
| Max failures | 10 | Before recovery attempt |

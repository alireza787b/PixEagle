# VideoHandler Class Reference

> Core video input handler with multi-source support

**Source File:** `src/classes/video_handler.py`

## Overview

The `VideoHandler` class provides a unified interface for video input from 7 different source types. It handles capture initialization, frame acquisition, error recovery, and connection health monitoring.

### Backend Selection Notes

- `VIDEO_FILE` and `USB_CAMERA` treat `USE_GSTREAMER` as a preference:
  - `false`: OpenCV backend.
  - `true`: try GStreamer first, then fallback to OpenCV when unavailable/failing.
- `CSI_CAMERA` and `CUSTOM_GSTREAMER` always use GStreamer.
- Health/info diagnostics report the active backend after fallback (`active_backend`).

## Class Definition

```python
class VideoHandler:
    """
    Handles video input from various sources with optimized capture methods.

    Supported video sources:
    - VIDEO_FILE: Video files (mp4, avi, etc.)
    - USB_CAMERA: USB webcams and cameras
    - RTSP_STREAM: RTSP network streams
    - UDP_STREAM: UDP network streams
    - HTTP_STREAM: HTTP/HTTPS streams
    - CSI_CAMERA: MIPI CSI cameras (Raspberry Pi, Jetson)
    - CUSTOM_GSTREAMER: Custom GStreamer pipeline
    """
```

## Constructor

```python
def __init__(self):
```

Initializes the video handler with configured source type. Automatically:
- Detects platform (Linux/Windows/ARM)
- Creates appropriate capture object
- Initializes frame states and buffers
- Sets up error recovery tracking

**Raises:**
- `ValueError` if video source cannot be opened after retries

## Attributes

### Video Properties

| Attribute | Type | Description |
|-----------|------|-------------|
| `cap` | `cv2.VideoCapture` | Underlying OpenCV capture |
| `width` | `int` | Frame width in pixels |
| `height` | `int` | Frame height in pixels |
| `fps` | `float` | Frames per second |
| `delay_frame` | `int` | Frame delay in milliseconds |

### Frame States

| Attribute | Type | Description |
|-----------|------|-------------|
| `current_raw_frame` | `np.ndarray` | Latest captured frame |
| `current_osd_frame` | `np.ndarray` | Frame with OSD overlays |
| `current_resized_raw_frame` | `np.ndarray` | Resized raw for streaming |
| `current_resized_osd_frame` | `np.ndarray` | Resized OSD for streaming |
| `frame_history` | `deque` | FIFO buffer of recent frames |

### Connection State

| Attribute | Type | Description |
|-----------|------|-------------|
| `_consecutive_failures` | `int` | Count of failed reads |
| `_max_consecutive_failures` | `int` | Threshold for recovery |
| `_last_successful_frame_time` | `float` | Timestamp of last good frame |
| `_connection_timeout` | `float` | Timeout before forced recovery |
| `_is_recovering` | `bool` | Currently recovering flag |
| `_recovery_attempts` | `int` | Number of recovery tries |
| `_frame_cache` | `deque` | Frames for fallback during recovery |

### Platform Detection

| Attribute | Type | Description |
|-----------|------|-------------|
| `platform` | `str` | OS name (Linux, Windows, Darwin) |
| `is_arm` | `bool` | Running on ARM architecture |

## Methods

### Initialization

#### `init_video_source(max_retries=5, retry_delay=1.0) -> int`

Initialize video source with retry logic.

**Parameters:**
- `max_retries`: Maximum connection attempts
- `retry_delay`: Delay between retries (seconds)

**Returns:** Frame delay in milliseconds

**Example:**
```python
handler = VideoHandler()
delay = handler.init_video_source(max_retries=3)
```

### Frame Acquisition

#### `get_frame() -> Optional[np.ndarray]`

Read current frame from video source.

**Returns:** BGR frame as numpy array, or None on failure

**Behavior:**
1. Attempts to read from capture
2. On success: updates `current_raw_frame`, appends to history
3. On failure: returns cached frame, triggers recovery if needed

**Example:**
```python
frame = handler.get_frame()
if frame is not None:
    # Process frame
    pass
```

#### `get_frame_fast() -> Optional[np.ndarray]`

Read frame with aggressive buffer clearing for low latency.

**Returns:** Latest frame with minimal buffering delay

**Behavior:**
- For GStreamer RTSP: Uses standard `get_frame()` (already optimized)
- For OpenCV: Clears buffer with `grab()` before `retrieve()`

**Example:**
```python
# For real-time tracking where latency matters
frame = handler.get_frame_fast()
```

#### `get_last_frames() -> list`

Get frame history buffer.

**Returns:** List of recent frames (oldest first)

### Frame Management

#### `update_resized_frames(width: int, height: int) -> None`

Resize current frames for streaming output.

**Parameters:**
- `width`: Target width
- `height`: Target height

**Example:**
```python
handler.update_resized_frames(640, 480)
# Now handler.current_resized_osd_frame is ready for streaming
```

#### `set_frame_size(width: int, height: int) -> bool`

Dynamically change capture resolution.

**Parameters:**
- `width`: New capture width
- `height`: New capture height

**Returns:** True if successful

#### `clear_frame_history() -> None`

Clear the frame history buffer.

### Connection Management

#### `reconnect() -> bool`

Attempt full reconnection to video source.

**Returns:** True if reconnection successful

**Example:**
```python
if not handler.cap.isOpened():
    success = handler.reconnect()
```

#### `release() -> None`

Release video capture resources.

**Example:**
```python
handler.release()  # Clean up on exit
```

### Health Monitoring

#### `get_connection_health() -> dict`

Get detailed connection health metrics.

**Returns:** Dictionary with health information

```python
{
    'status': 'healthy',  # healthy, degraded, recovering, failed
    'consecutive_failures': 0,
    'time_since_last_frame': 0.05,
    'is_recovering': False,
    'recovery_attempts': 0,
    'cached_frames_available': 5,
    'connection_open': True,
    'video_source_type': 'RTSP_STREAM',
    'use_gstreamer': True,
    'active_backend': 'GStreamer'
}
```

#### `get_video_info() -> Dict[str, Any]`

Get video capture information.

**Returns:** Dictionary with video properties

```python
{
    'width': 640,
    'height': 480,
    'fps': 30.0,
    'source_type': 'RTSP_STREAM',
    'backend': 'GSTREAMER'
}
```

#### `force_recovery() -> bool`

Force immediate recovery attempt.

**Returns:** True if recovery successful

#### `validate_coordinate_mapping() -> Dict[str, Any]`

Validate coordinate mapping for dashboard integration.

**Returns:** Mapping validation results

### Internal Methods

#### `_create_capture_object() -> cv2.VideoCapture`

Factory method that routes to source-specific creators.

#### `_handle_frame_failure() -> Optional[np.ndarray]`

Handle frame read failure with graceful degradation.

#### `_attempt_recovery() -> Optional[np.ndarray]`

Attempt connection recovery.

#### `_reset_failure_counters() -> None`

Reset all failure tracking counters.

#### `_get_cached_frame() -> Optional[np.ndarray]`

Get most recent cached frame for fallback.

## Usage Patterns

### Basic Usage

```python
from classes.video_handler import VideoHandler

# Initialize
handler = VideoHandler()

# Main loop
while True:
    frame = handler.get_frame()
    if frame is None:
        continue

    # Process frame
    processed = apply_osd(frame)
    handler.current_osd_frame = processed

    # Prepare for streaming
    handler.update_resized_frames(640, 480)

# Cleanup
handler.release()
```

### With Health Monitoring

```python
health = handler.get_connection_health()

if health['status'] == 'failed':
    logger.error("Video connection failed")
    handler.force_recovery()
elif health['status'] == 'degraded':
    logger.warning(f"Connection degraded: {health['consecutive_failures']} failures")
```

### Low-Latency Capture

```python
# For real-time tracking scenarios
while tracking:
    frame = handler.get_frame_fast()
    if frame is not None:
        result = tracker.update(frame)
```

## Configuration

The VideoHandler reads configuration from `Parameters`:

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: RTSP_STREAM
  CAPTURE_WIDTH: 640
  CAPTURE_HEIGHT: 480
  CAPTURE_FPS: 30
  USE_GSTREAMER: true
  STORE_LAST_FRAMES: 5

  # RTSP-specific
  RTSP_URL: rtsp://192.168.0.108:554/stream
  RTSP_PROTOCOL: tcp
  RTSP_LATENCY: 200
  RTSP_MAX_CONSECUTIVE_FAILURES: 10
  RTSP_CONNECTION_TIMEOUT: 5.0
  RTSP_MAX_RECOVERY_ATTEMPTS: 3
```

## Error Handling

The VideoHandler uses a multi-level error handling strategy:

1. **Frame-level**: Returns cached frame on single failure
2. **Connection-level**: Tracks consecutive failures
3. **Recovery-level**: Attempts reconnection after threshold
4. **Fallback-level**: Uses simpler pipelines if primary fails

See [Error Recovery](error-recovery.md) for detailed behavior.

# Frame State Management

> Managing frame lifecycle from capture to streaming

## Overview

PixEagle maintains multiple frame states to support different consumers (trackers, OSD, streaming) without redundant processing. This document explains the frame state system and caching strategies.

## Frame States

The `VideoHandler` maintains 4 primary frame states:

```
┌─────────────────────────────────────────────────────────────────┐
│                       FRAME STATES                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │  current_raw_frame  │──────▶│  current_osd_frame  │         │
│  │                     │       │                     │         │
│  │  Original capture   │       │  + OSD overlays     │         │
│  │  from video source  │       │  + Annotations      │         │
│  └──────────┬──────────┘       └──────────┬──────────┘         │
│             │                              │                    │
│             │  update_resized_frames()     │                    │
│             ▼                              ▼                    │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │ current_resized_    │       │ current_resized_    │         │
│  │ raw_frame           │       │ osd_frame           │         │
│  │                     │       │                     │         │
│  │  Scaled for         │       │  Scaled for         │         │
│  │  streaming          │       │  streaming + OSD    │         │
│  └─────────────────────┘       └─────────────────────┘         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### State Descriptions

| State | Purpose | Updated By | Used By |
|-------|---------|------------|---------|
| `current_raw_frame` | Unprocessed capture | `get_frame()` | Trackers, OSD |
| `current_osd_frame` | Frame with overlays | AppController | Streaming |
| `current_resized_raw_frame` | Scaled raw frame | `update_resized_frames()` | Raw streaming |
| `current_resized_osd_frame` | Scaled OSD frame | `update_resized_frames()` | Dashboard streaming |

## Frame Lifecycle

### 1. Capture Phase

```python
def get_frame(self) -> Optional[np.ndarray]:
    ret, frame = self.cap.read()

    if ret and frame is not None:
        # Update primary state
        self.current_raw_frame = frame

        # Add to history buffer
        self.frame_history.append(frame)

        # Cache for recovery
        self._frame_cache.append(frame.copy())

        return frame
```

### 2. Processing Phase

```python
# In AppController main loop
frame = self.video_handler.get_frame()

# Apply OSD overlays
frame_with_osd = self.osd_handler.draw_osd(frame)

# Store processed frame
self.video_handler.current_osd_frame = frame_with_osd
```

### 3. Resize Phase

```python
# Prepare for streaming
self.video_handler.update_resized_frames(
    Parameters.STREAM_WIDTH,    # e.g., 640
    Parameters.STREAM_HEIGHT    # e.g., 480
)
```

### 4. Streaming Phase

```python
# FastAPI selects appropriate frame
if Parameters.STREAM_PROCESSED_OSD:
    frame = self.video_handler.current_resized_osd_frame
else:
    frame = self.video_handler.current_resized_raw_frame
```

## Frame History Buffer

The frame history maintains recent frames for:
- Recovery fallback
- Motion analysis
- Debugging

### Configuration

```yaml
VideoSource:
  STORE_LAST_FRAMES: 5  # Number of frames to keep
```

### Implementation

```python
# In VideoHandler.__init__
self.frame_history = deque(maxlen=Parameters.STORE_LAST_FRAMES)

# Access history
recent_frames = handler.get_last_frames()  # Returns list
```

### Use Cases

1. **Recovery Fallback**: Return last good frame during connection issues
2. **Frame Interpolation**: Smooth motion during frame drops
3. **Debug Visualization**: Review recent capture history

## Frame Cache (Recovery)

Separate from history, the frame cache specifically supports connection recovery:

```python
# In VideoHandler.__init__
self._frame_cache = deque(maxlen=getattr(Parameters, 'RTSP_FRAME_CACHE_SIZE', 5))

# During failure
def _get_cached_frame(self) -> Optional[np.ndarray]:
    if self._frame_cache:
        return self._frame_cache[-1]  # Most recent
    return None
```

### Cache vs History

| Feature | frame_history | _frame_cache |
|---------|---------------|--------------|
| Purpose | General history | Recovery fallback |
| Access | Public | Internal |
| Size | STORE_LAST_FRAMES | RTSP_FRAME_CACHE_SIZE |
| Copies | References | Deep copies |

## Resizing Strategy

### update_resized_frames()

```python
def update_resized_frames(self, width: int, height: int) -> None:
    """Resize current frames for streaming output."""
    import cv2

    if self.current_raw_frame is not None:
        self.current_resized_raw_frame = cv2.resize(
            self.current_raw_frame,
            (width, height),
            interpolation=cv2.INTER_LINEAR
        )

    if self.current_osd_frame is not None:
        self.current_resized_osd_frame = cv2.resize(
            self.current_osd_frame,
            (width, height),
            interpolation=cv2.INTER_LINEAR
        )
```

### Interpolation Methods

| Method | Quality | Speed | Use Case |
|--------|---------|-------|----------|
| `INTER_NEAREST` | Low | Fastest | Real-time priority |
| `INTER_LINEAR` | Medium | Fast | Default streaming |
| `INTER_CUBIC` | High | Slow | Quality priority |
| `INTER_AREA` | High | Medium | Downscaling |

### Streaming Dimensions

```yaml
Streaming:
  STREAM_WIDTH: 640
  STREAM_HEIGHT: 480
  STREAM_FPS: 10
  STREAM_PROCESSED_OSD: true  # Use OSD or raw
```

## Memory Management

### Frame Memory Footprint

For a 640x480 BGR frame:
- Size: 640 × 480 × 3 = 921,600 bytes (~900 KB)
- 4 frame states = ~3.6 MB
- 5-frame history = ~4.5 MB
- Total: ~8-10 MB

### Optimization Tips

1. **Limit History Size**: Use minimum needed
   ```yaml
   STORE_LAST_FRAMES: 3  # Minimum for recovery
   ```

2. **Avoid Unnecessary Copies**: Frame history uses references
   ```python
   self.frame_history.append(frame)  # Reference
   self._frame_cache.append(frame.copy())  # Copy for safety
   ```

3. **Resize Early**: Stream at lower resolution
   ```yaml
   Streaming:
     STREAM_WIDTH: 480   # Lower than capture
     STREAM_HEIGHT: 360
   ```

## Thread Safety Considerations

Frame states are designed for single-threaded access:

```python
# CORRECT: Sequential in main loop
frame = handler.get_frame()
handler.current_osd_frame = process(frame)
handler.update_resized_frames(640, 480)

# INCORRECT: Concurrent access
# Thread 1: handler.get_frame()
# Thread 2: handler.current_osd_frame  # Race condition
```

### For Async Streaming

FastAPI streaming accesses frames asynchronously but:
- Only reads resized frames (no writes)
- Reads are atomic at numpy level
- Occasional stale frame is acceptable

## Validation

### validate_coordinate_mapping()

Ensures frame dimensions match expected configuration:

```python
def validate_coordinate_mapping(self) -> Dict[str, Any]:
    return {
        'capture_width': self.width,
        'capture_height': self.height,
        'expected_width': Parameters.CAPTURE_WIDTH,
        'expected_height': Parameters.CAPTURE_HEIGHT,
        'valid': (self.width == Parameters.CAPTURE_WIDTH and
                  self.height == Parameters.CAPTURE_HEIGHT),
        'stream_width': Parameters.STREAM_WIDTH,
        'stream_height': Parameters.STREAM_HEIGHT,
    }
```

This validation is critical for dashboard click-to-frame coordinate mapping.

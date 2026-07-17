# Video File Source

> Video file playback for testing and development

## Overview

Video file source is ideal for testing, development, and demos. It supports common video formats through OpenCV or GStreamer backends.

## Configuration

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: VIDEO_FILE
  VIDEO_FILE_PATH: resources/test_video.mp4
  VIDEO_FILE_EOF_POLICY: LOOP
  USE_GSTREAMER: false  # OpenCV usually sufficient
```

## Supported Formats

| Format | Extension | Notes |
|--------|-----------|-------|
| MP4 | .mp4 | H.264/H.265, most common |
| AVI | .avi | Legacy, good compatibility |
| MKV | .mkv | Flexible container |
| MOV | .mov | Apple QuickTime |
| WebM | .webm | VP8/VP9 |

## File Paths

```yaml
# Relative to project root
VIDEO_FILE_PATH: resources/test_video.mp4

# Absolute path
VIDEO_FILE_PATH: /home/user/videos/drone_footage.mp4

# Windows path
VIDEO_FILE_PATH: C:/Videos/test.mp4
```

## GStreamer Pipeline

When `USE_GSTREAMER: true`:

```
filesrc location=/path/to/video.mp4
  ! decodebin
  ! videoconvert
  ! video/x-raw,format=BGR
  ! videoscale
  ! video/x-raw,width=640,height=480
  ! appsink drop=true sync=false
```

## Use Cases

### Testing Tracker Algorithms

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: VIDEO_FILE
  VIDEO_FILE_PATH: resources/tracking_test.mp4
  CAPTURE_WIDTH: 640
  CAPTURE_HEIGHT: 480
```

### Consistent Benchmarking

Video files provide reproducible results:
- Same frames every time
- No network variability
- Controlled conditions

### Demo Mode

```yaml
# config.yaml for demos
VideoSource:
  VIDEO_SOURCE_TYPE: VIDEO_FILE
  VIDEO_FILE_PATH: resources/demo_flight.mp4
```

## Looping Behavior

`VIDEO_FILE_EOF_POLICY` is the single playback-boundary setting:

| Value | Behavior |
|-------|----------|
| `LOOP` | Return one cached, command-unusable boundary frame, rewind, then start a new playback epoch. This is the checked-in demo default. |
| `STOP` | Hold the last cached frame at EOF without reconnect or seek retries. |

Do not manipulate `video_handler.cap` from application or plugin code. The
handler owns seek/reopen fallback, epoch counters, and frame provenance.
When a backend cannot report frame count/position, PixEagle waits for three
consecutive empty reads before applying the configured EOF policy; a successful
read resets that bounded ambiguity counter.

Video-file frames can drive tracking, overlays, streaming, and deterministic
validation. They are always marked `replay_source` and are not authorized to
start or drive autonomous following. PX4/SITL validation must use the explicit
validation injection boundary rather than treating a replay as a live camera.

Playback state is available in video health/status as
`video_file_playback_state`, `video_file_playback_epoch`, and
`video_file_loop_count`.

## Frame Properties

```python
# Get video info
info = video_handler.get_video_info()
print(f"Duration: {info['frame_count'] / info['fps']:.1f}s")
print(f"Resolution: {info['width']}x{info['height']}")
print(f"FPS: {info['fps']}")
```

## Troubleshooting

### "Cannot open video file"

**Solutions:**
1. Check file exists: `ls -la resources/`
2. Check file permissions
3. Verify path is relative to project root

### "Could not decode frame"

**Cause:** Missing codec

**Solution:**
```bash
# Install codecs
sudo apt install libavcodec-extra

# Or use GStreamer
USE_GSTREAMER: true
```

### Wrong FPS

Some files report incorrect FPS. Override:

```yaml
DEFAULT_FPS: 30  # Fallback if detection fails
```

## Creating Test Videos

### From Screen Recording

```bash
ffmpeg -video_size 1920x1080 -framerate 30 -f x11grab -i :0.0 \
    -c:v libx264 -preset ultrafast -crf 28 output.mp4
```

### From Images

```bash
ffmpeg -framerate 30 -pattern_type glob -i '*.png' \
    -c:v libx264 -pix_fmt yuv420p output.mp4
```

### Resize Existing Video

```bash
ffmpeg -i input.mp4 -vf scale=640:480 -c:v libx264 output.mp4
```

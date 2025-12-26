# Custom GStreamer Source

> Advanced custom GStreamer pipelines

## Overview

For complete control over video capture, use a custom GStreamer pipeline. This allows advanced configurations not covered by built-in source types.

## Configuration

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: CUSTOM_GSTREAMER
  CUSTOM_PIPELINE: >
    videotestsrc pattern=ball
    ! video/x-raw,width=640,height=480,framerate=30/1
    ! videoconvert
    ! video/x-raw,format=BGR
    ! appsink drop=true sync=false
```

## Pipeline Requirements

Your pipeline **must** end with:

```
! video/x-raw,format=BGR ! appsink
```

OpenCV expects BGR format frames.

## Example Pipelines

### Test Pattern

```yaml
CUSTOM_PIPELINE: >
  videotestsrc pattern=smpte
  ! video/x-raw,width=640,height=480,framerate=30/1
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink
```

### Dual Camera Composite

```yaml
CUSTOM_PIPELINE: >
  compositor name=comp
    sink_0::xpos=0 sink_0::ypos=0
    sink_1::xpos=320 sink_1::ypos=0
  ! video/x-raw,width=640,height=240
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink
  v4l2src device=/dev/video0 ! video/x-raw,width=320,height=240 ! comp.sink_0
  v4l2src device=/dev/video2 ! video/x-raw,width=320,height=240 ! comp.sink_1
```

### Hardware Decode (VAAPI)

```yaml
CUSTOM_PIPELINE: >
  filesrc location=/path/to/video.mp4
  ! qtdemux
  ! h264parse
  ! vaapih264dec
  ! vaapipostproc
  ! video/x-raw,format=BGR
  ! appsink
```

### Network Source with Authentication

```yaml
CUSTOM_PIPELINE: >
  souphttpsrc location="http://user:pass@camera/stream"
  ! decodebin
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink
```

## Debugging Pipelines

### Test with gst-launch

```bash
# Replace appsink with autovideosink for testing
gst-launch-1.0 videotestsrc ! videoconvert ! autovideosink
```

### Check Element Availability

```bash
gst-inspect-1.0 nvarguscamerasrc
gst-inspect-1.0 vaapih264dec
```

## Common Elements

| Element | Purpose |
|---------|---------|
| `videotestsrc` | Test pattern generator |
| `v4l2src` | V4L2 camera source |
| `rtspsrc` | RTSP source |
| `udpsrc` | UDP source |
| `filesrc` | File source |
| `decodebin` | Auto decoder |
| `videoconvert` | Format conversion |
| `videoscale` | Resolution scaling |
| `appsink` | Application sink |

## Troubleshooting

### "Element not found"

Install required GStreamer plugins:
```bash
sudo apt install gstreamer1.0-plugins-{base,good,bad,ugly}
```

### "Could not link elements"

Check caps compatibility between elements. Use `videoconvert` between incompatible formats.

### Pipeline Syntax Errors

- Use `>` for multiline YAML
- Escape special characters
- Test with `gst-launch-1.0` first

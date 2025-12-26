# On-Screen Display (OSD)

> Overlay rendering system for video frames

## Overview

The OSD (On-Screen Display) system renders informational overlays on video frames, including telemetry data, tracking status, safety indicators, and custom annotations.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                      OSD Rendering Pipeline                     │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Raw Frame                 OSD Renderer              OSD Frame  │
│  ─────────                 ────────────              ─────────  │
│                                                                 │
│  ┌─────────┐    ┌────────────────────────────┐    ┌─────────┐  │
│  │ BGR     │───▶│  Layout Manager            │───▶│ BGR     │  │
│  │ Frame   │    │  ┌──────────────────────┐  │    │ Frame   │  │
│  └─────────┘    │  │ Top-Left:    Status  │  │    │ + OSD   │  │
│                 │  │ Top-Right:   Time    │  │    └─────────┘  │
│                 │  │ Bottom-Left: FPS     │  │                  │
│                 │  │ Center:      Target  │  │                  │
│                 │  └──────────────────────┘  │                  │
│                 └────────────────────────────┘                  │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

## Components

- [OSD Renderer](osd-renderer.md) - Main rendering pipeline
- [Text Rendering](text-rendering.md) - Text styles and formatting
- [Layout Manager](layout-manager.md) - Anchor-based positioning

## Quick Start

### Enable OSD

```yaml
OSD:
  ENABLE: true
  SHOW_FPS: true
  SHOW_TIMESTAMP: true
  SHOW_TRACKING_STATUS: true
  SHOW_SAFETY_STATUS: true
```

### Basic Usage

```python
from classes.osd_renderer import OSDRenderer

# Initialize
osd = OSDRenderer(width=640, height=480)

# Render OSD on frame
osd_frame = osd.render(raw_frame, telemetry_data)
```

## OSD Elements

### Standard Elements

| Element | Position | Description |
|---------|----------|-------------|
| FPS Counter | Top-Left | Current frame rate |
| Timestamp | Top-Right | Current time |
| Mode | Bottom-Left | Operation mode |
| Tracking | Center | Target bounding box |
| Telemetry | Bottom | GPS, altitude, etc. |
| Safety | Top-Center | Safety status badge |

### Element Visibility

```yaml
OSD:
  Elements:
    FPS: true
    TIMESTAMP: true
    MODE: true
    TRACKING_BOX: true
    TELEMETRY_BAR: false
    SAFETY_INDICATOR: true
```

## Rendering Modes

### Minimal

```yaml
OSD:
  MODE: minimal
  # Shows: FPS, timestamp only
```

### Standard

```yaml
OSD:
  MODE: standard
  # Shows: All status elements
```

### Debug

```yaml
OSD:
  MODE: debug
  # Shows: All elements + technical details
```

## Color Scheme

### Default Colors

| Element | Color (BGR) | Hex |
|---------|-------------|-----|
| Text | (255, 255, 255) | #FFFFFF |
| Background | (0, 0, 0) | #000000 |
| Success | (0, 255, 0) | #00FF00 |
| Warning | (0, 255, 255) | #FFFF00 |
| Error | (0, 0, 255) | #FF0000 |
| Tracking | (0, 255, 255) | #00FFFF |

### Custom Colors

```yaml
OSD:
  Colors:
    TEXT: [255, 255, 255]
    BACKGROUND: [0, 0, 0]
    TRACKING_BOX: [0, 255, 255]
    SAFETY_OK: [0, 255, 0]
    SAFETY_WARN: [0, 165, 255]
    SAFETY_CRITICAL: [0, 0, 255]
```

## Frame States

OSD maintains multiple frame versions:

```python
# VideoHandler frame states
video_handler.current_raw_frame      # Original frame
video_handler.current_osd_frame      # Frame with OSD overlay
video_handler.current_resized_raw_frame    # Scaled raw
video_handler.current_resized_osd_frame    # Scaled OSD
```

## Performance

### Rendering Cost

| Resolution | Element Count | Render Time |
|------------|---------------|-------------|
| 640x480 | 5 | ~2ms |
| 1280x720 | 5 | ~3ms |
| 1920x1080 | 5 | ~5ms |

### Optimization Tips

1. **Minimize text updates**: Cache static text
2. **Use simpler fonts**: `cv2.FONT_HERSHEY_SIMPLEX`
3. **Batch rendering**: Group draw calls
4. **Skip unchanged elements**: Track dirty state

## Example: Custom OSD Element

```python
class CustomOSDElement:
    def __init__(self, position='top-left'):
        self.position = position
        self.text = ""

    def update(self, data):
        self.text = f"Custom: {data['value']}"

    def render(self, frame, layout):
        x, y = layout.get_position(self.position)
        cv2.putText(
            frame,
            self.text,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1
        )
        return frame
```

# OSD Renderer

> Main rendering pipeline for on-screen display

## Overview

The `OSDRenderer` class manages the complete OSD rendering pipeline, coordinating layout, text rendering, and element composition.

## Class Reference

### OSDRenderer

```python
class OSDRenderer:
    """
    Renders on-screen display overlays on video frames.

    Attributes:
        width: Frame width in pixels
        height: Frame height in pixels
        layout: LayoutManager instance
        text_renderer: OSDTextRenderer instance
        elements: List of OSD elements to render
    """

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        config: dict = None
    ):
        """
        Initialize OSD renderer.

        Args:
            width: Frame width
            height: Frame height
            config: OSD configuration dictionary
        """
        pass

    def render(
        self,
        frame: np.ndarray,
        data: dict = None
    ) -> np.ndarray:
        """
        Render OSD on frame.

        Args:
            frame: Input BGR frame
            data: Telemetry and status data

        Returns:
            Frame with OSD overlay
        """
        pass

    def add_element(self, element: OSDElement) -> None:
        """Add custom OSD element."""
        pass

    def remove_element(self, element_id: str) -> None:
        """Remove OSD element by ID."""
        pass

    def set_visibility(self, element_id: str, visible: bool) -> None:
        """Toggle element visibility."""
        pass
```

## Rendering Pipeline

```
┌────────────────────────────────────────────────────────────────┐
│                     Render Pipeline                             │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Copy Input     2. Layout        3. Render         4. Output │
│  ─────────────     ────────         ────────          ──────── │
│                                                                 │
│  ┌─────────┐    ┌──────────┐    ┌──────────────┐    ┌────────┐ │
│  │ frame   │───▶│ compute  │───▶│ for element: │───▶│ osd    │ │
│  │ .copy() │    │ positions│    │   draw()     │    │ frame  │ │
│  └─────────┘    └──────────┘    └──────────────┘    └────────┘ │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

## Implementation

```python
import cv2
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod

@dataclass
class OSDElement:
    """Base OSD element."""
    id: str
    position: str  # 'top-left', 'top-right', 'bottom-left', etc.
    visible: bool = True
    priority: int = 0  # Render order (higher = later)

    @abstractmethod
    def render(self, frame: np.ndarray, layout: 'LayoutManager') -> np.ndarray:
        pass


class OSDRenderer:
    """Main OSD rendering controller."""

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        config: Optional[dict] = None
    ):
        self.width = width
        self.height = height
        self.config = config or {}

        # Sub-components
        self.layout = LayoutManager(width, height)
        self.text_renderer = OSDTextRenderer()

        # Elements registry
        self._elements: Dict[str, OSDElement] = {}

        # Initialize standard elements
        self._init_standard_elements()

    def _init_standard_elements(self):
        """Initialize standard OSD elements."""
        if self.config.get('SHOW_FPS', True):
            self.add_element(FPSElement())

        if self.config.get('SHOW_TIMESTAMP', True):
            self.add_element(TimestampElement())

        if self.config.get('SHOW_TRACKING_STATUS', True):
            self.add_element(TrackingStatusElement())

        if self.config.get('SHOW_SAFETY_STATUS', True):
            self.add_element(SafetyStatusElement())

    def add_element(self, element: OSDElement):
        """Add element to renderer."""
        self._elements[element.id] = element

    def remove_element(self, element_id: str):
        """Remove element by ID."""
        if element_id in self._elements:
            del self._elements[element_id]

    def set_visibility(self, element_id: str, visible: bool):
        """Toggle element visibility."""
        if element_id in self._elements:
            self._elements[element_id].visible = visible

    def render(
        self,
        frame: np.ndarray,
        data: Optional[dict] = None
    ) -> np.ndarray:
        """
        Render all OSD elements on frame.

        Args:
            frame: Input BGR frame
            data: Telemetry/status data dictionary

        Returns:
            Frame with OSD overlay
        """
        # Work on copy
        osd_frame = frame.copy()

        # Update layout if frame size changed
        h, w = frame.shape[:2]
        if w != self.width or h != self.height:
            self.width = w
            self.height = h
            self.layout.update_dimensions(w, h)

        # Render elements by priority
        sorted_elements = sorted(
            self._elements.values(),
            key=lambda e: e.priority
        )

        for element in sorted_elements:
            if element.visible:
                try:
                    osd_frame = element.render(
                        osd_frame,
                        self.layout,
                        self.text_renderer,
                        data or {}
                    )
                except Exception as e:
                    print(f"OSD render error ({element.id}): {e}")

        return osd_frame

    def get_element_ids(self) -> List[str]:
        """Get list of registered element IDs."""
        return list(self._elements.keys())


class FPSElement(OSDElement):
    """FPS counter element."""

    def __init__(self):
        super().__init__(id='fps', position='top-left')
        self._frame_times = []
        self._fps = 0.0

    def render(
        self,
        frame: np.ndarray,
        layout: 'LayoutManager',
        text_renderer: 'OSDTextRenderer',
        data: dict
    ) -> np.ndarray:
        import time

        # Calculate FPS
        now = time.time()
        self._frame_times.append(now)

        # Keep last second
        self._frame_times = [
            t for t in self._frame_times
            if now - t < 1.0
        ]
        self._fps = len(self._frame_times)

        # Render
        text = f"FPS: {self._fps:.0f}"
        x, y = layout.get_anchor_position('top-left')

        return text_renderer.draw_text_with_background(
            frame, text, (x, y),
            font_scale=0.5,
            color=(255, 255, 255),
            bg_color=(0, 0, 0)
        )


class TimestampElement(OSDElement):
    """Timestamp element."""

    def __init__(self):
        super().__init__(id='timestamp', position='top-right')

    def render(
        self,
        frame: np.ndarray,
        layout: 'LayoutManager',
        text_renderer: 'OSDTextRenderer',
        data: dict
    ) -> np.ndarray:
        from datetime import datetime

        timestamp = datetime.now().strftime('%H:%M:%S')
        x, y = layout.get_anchor_position('top-right')

        # Adjust for text width
        text_width = len(timestamp) * 10
        x = x - text_width

        return text_renderer.draw_text_with_background(
            frame, timestamp, (x, y),
            font_scale=0.5,
            color=(255, 255, 255),
            bg_color=(0, 0, 0)
        )


class TrackingStatusElement(OSDElement):
    """Tracking status and bounding box."""

    def __init__(self):
        super().__init__(id='tracking', position='center', priority=10)

    def render(
        self,
        frame: np.ndarray,
        layout: 'LayoutManager',
        text_renderer: 'OSDTextRenderer',
        data: dict
    ) -> np.ndarray:
        tracker_data = data.get('tracker', {})

        if not tracker_data.get('is_tracking', False):
            return frame

        # Draw bounding box
        bbox = tracker_data.get('bbox')
        if bbox:
            x, y, w, h = map(int, bbox)
            cv2.rectangle(
                frame,
                (x, y),
                (x + w, y + h),
                (0, 255, 255),  # Cyan
                2
            )

            # Draw confidence
            confidence = tracker_data.get('confidence', 0)
            text = f"{confidence:.0%}"
            text_renderer.draw_text_with_background(
                frame, text, (x, y - 5),
                font_scale=0.4,
                color=(0, 255, 255),
                bg_color=(0, 0, 0)
            )

        return frame


class SafetyStatusElement(OSDElement):
    """Safety system status badge."""

    def __init__(self):
        super().__init__(id='safety', position='top-center', priority=5)

    def render(
        self,
        frame: np.ndarray,
        layout: 'LayoutManager',
        text_renderer: 'OSDTextRenderer',
        data: dict
    ) -> np.ndarray:
        safety_data = data.get('safety', {})
        status = safety_data.get('status', 'OK')

        # Color based on status
        colors = {
            'OK': (0, 255, 0),        # Green
            'WARNING': (0, 165, 255),  # Orange
            'CRITICAL': (0, 0, 255),   # Red
        }
        color = colors.get(status, (128, 128, 128))

        # Position
        x, y = layout.get_anchor_position('top-center')
        text = f"SAFETY: {status}"
        text_width = len(text) * 10
        x = x - text_width // 2

        return text_renderer.draw_text_with_background(
            frame, text, (x, y),
            font_scale=0.5,
            color=color,
            bg_color=(0, 0, 0)
        )
```

## Configuration

```yaml
OSD:
  ENABLE: true

  # Standard elements
  SHOW_FPS: true
  SHOW_TIMESTAMP: true
  SHOW_TRACKING_STATUS: true
  SHOW_SAFETY_STATUS: true
  SHOW_MODE: true
  SHOW_TELEMETRY: false

  # Appearance
  FONT_SCALE: 0.5
  FONT_THICKNESS: 1
  TEXT_COLOR: [255, 255, 255]
  BACKGROUND_COLOR: [0, 0, 0]
  BACKGROUND_OPACITY: 0.5

  # Layout
  MARGIN: 10
  PADDING: 5
```

## Extending OSD

### Custom Element

```python
class BatteryElement(OSDElement):
    """Battery status indicator."""

    def __init__(self):
        super().__init__(id='battery', position='bottom-right')

    def render(self, frame, layout, text_renderer, data):
        battery = data.get('telemetry', {}).get('battery', 100)

        # Color based on level
        if battery > 50:
            color = (0, 255, 0)
        elif battery > 20:
            color = (0, 165, 255)
        else:
            color = (0, 0, 255)

        text = f"BAT: {battery}%"
        x, y = layout.get_anchor_position('bottom-right')

        return text_renderer.draw_text_with_background(
            frame, text, (x - 80, y),
            font_scale=0.5,
            color=color
        )

# Add to renderer
osd.add_element(BatteryElement())
```

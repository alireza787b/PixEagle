# OSD Text Rendering

> Text styles and formatting for on-screen display

## Overview

The `OSDTextRenderer` handles all text rendering operations, providing consistent styling, background rendering, and multi-line support.

## Text Renderer Class

```python
import cv2
import numpy as np
from typing import Tuple, Optional, List

class OSDTextRenderer:
    """
    Text rendering utilities for OSD.

    Provides consistent text styling with background,
    shadow, and multi-line support.
    """

    # Font constants
    FONT_SIMPLE = cv2.FONT_HERSHEY_SIMPLEX
    FONT_PLAIN = cv2.FONT_HERSHEY_PLAIN
    FONT_DUPLEX = cv2.FONT_HERSHEY_DUPLEX
    FONT_COMPLEX = cv2.FONT_HERSHEY_COMPLEX
    FONT_MONO = cv2.FONT_HERSHEY_COMPLEX_SMALL

    def __init__(
        self,
        default_font: int = cv2.FONT_HERSHEY_SIMPLEX,
        default_scale: float = 0.5,
        default_thickness: int = 1
    ):
        """
        Initialize text renderer.

        Args:
            default_font: OpenCV font constant
            default_scale: Default font scale
            default_thickness: Default line thickness
        """
        self.default_font = default_font
        self.default_scale = default_scale
        self.default_thickness = default_thickness

    def draw_text(
        self,
        frame: np.ndarray,
        text: str,
        position: Tuple[int, int],
        font: int = None,
        font_scale: float = None,
        color: Tuple[int, int, int] = (255, 255, 255),
        thickness: int = None,
        line_type: int = cv2.LINE_AA
    ) -> np.ndarray:
        """
        Draw basic text on frame.

        Args:
            frame: Input frame
            text: Text to render
            position: (x, y) position
            font: OpenCV font
            font_scale: Scale factor
            color: BGR color tuple
            thickness: Line thickness
            line_type: Line type (antialiased)

        Returns:
            Frame with text
        """
        cv2.putText(
            frame,
            text,
            position,
            font or self.default_font,
            font_scale or self.default_scale,
            color,
            thickness or self.default_thickness,
            line_type
        )
        return frame

    def draw_text_with_background(
        self,
        frame: np.ndarray,
        text: str,
        position: Tuple[int, int],
        font: int = None,
        font_scale: float = None,
        color: Tuple[int, int, int] = (255, 255, 255),
        bg_color: Tuple[int, int, int] = (0, 0, 0),
        bg_opacity: float = 0.7,
        padding: int = 3,
        thickness: int = None
    ) -> np.ndarray:
        """
        Draw text with semi-transparent background.

        Args:
            frame: Input frame
            text: Text to render
            position: (x, y) position
            font: OpenCV font
            font_scale: Scale factor
            color: Text color (BGR)
            bg_color: Background color (BGR)
            bg_opacity: Background opacity (0-1)
            padding: Padding around text
            thickness: Line thickness

        Returns:
            Frame with text and background
        """
        font = font or self.default_font
        font_scale = font_scale or self.default_scale
        thickness = thickness or self.default_thickness

        # Calculate text size
        (text_w, text_h), baseline = cv2.getTextSize(
            text, font, font_scale, thickness
        )

        # Background rectangle coordinates
        x, y = position
        x1 = x - padding
        y1 = y - text_h - padding
        x2 = x + text_w + padding
        y2 = y + baseline + padding

        # Clip to frame bounds
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(frame.shape[1], x2)
        y2 = min(frame.shape[0], y2)

        # Draw semi-transparent background
        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), bg_color, -1)
        cv2.addWeighted(overlay, bg_opacity, frame, 1 - bg_opacity, 0, frame)

        # Draw text
        cv2.putText(
            frame, text, position,
            font, font_scale, color, thickness, cv2.LINE_AA
        )

        return frame

    def draw_text_with_shadow(
        self,
        frame: np.ndarray,
        text: str,
        position: Tuple[int, int],
        font: int = None,
        font_scale: float = None,
        color: Tuple[int, int, int] = (255, 255, 255),
        shadow_color: Tuple[int, int, int] = (0, 0, 0),
        shadow_offset: int = 2,
        thickness: int = None
    ) -> np.ndarray:
        """
        Draw text with drop shadow.

        Args:
            frame: Input frame
            text: Text to render
            position: (x, y) position
            font: OpenCV font
            font_scale: Scale factor
            color: Text color (BGR)
            shadow_color: Shadow color (BGR)
            shadow_offset: Shadow offset in pixels
            thickness: Line thickness

        Returns:
            Frame with shadowed text
        """
        font = font or self.default_font
        font_scale = font_scale or self.default_scale
        thickness = thickness or self.default_thickness

        x, y = position

        # Draw shadow
        cv2.putText(
            frame, text, (x + shadow_offset, y + shadow_offset),
            font, font_scale, shadow_color, thickness, cv2.LINE_AA
        )

        # Draw text
        cv2.putText(
            frame, text, (x, y),
            font, font_scale, color, thickness, cv2.LINE_AA
        )

        return frame

    def draw_text_with_outline(
        self,
        frame: np.ndarray,
        text: str,
        position: Tuple[int, int],
        font: int = None,
        font_scale: float = None,
        color: Tuple[int, int, int] = (255, 255, 255),
        outline_color: Tuple[int, int, int] = (0, 0, 0),
        outline_thickness: int = 2,
        thickness: int = None
    ) -> np.ndarray:
        """
        Draw text with outline for maximum readability.

        Args:
            frame: Input frame
            text: Text to render
            position: (x, y) position
            font: OpenCV font
            font_scale: Scale factor
            color: Text color (BGR)
            outline_color: Outline color (BGR)
            outline_thickness: Outline width
            thickness: Text thickness

        Returns:
            Frame with outlined text
        """
        font = font or self.default_font
        font_scale = font_scale or self.default_scale
        thickness = thickness or self.default_thickness

        # Draw outline
        cv2.putText(
            frame, text, position,
            font, font_scale, outline_color,
            thickness + outline_thickness, cv2.LINE_AA
        )

        # Draw text
        cv2.putText(
            frame, text, position,
            font, font_scale, color, thickness, cv2.LINE_AA
        )

        return frame

    def draw_multiline_text(
        self,
        frame: np.ndarray,
        lines: List[str],
        position: Tuple[int, int],
        font: int = None,
        font_scale: float = None,
        color: Tuple[int, int, int] = (255, 255, 255),
        line_spacing: float = 1.5,
        thickness: int = None
    ) -> np.ndarray:
        """
        Draw multiple lines of text.

        Args:
            frame: Input frame
            lines: List of text lines
            position: (x, y) starting position
            font: OpenCV font
            font_scale: Scale factor
            color: Text color (BGR)
            line_spacing: Line height multiplier
            thickness: Line thickness

        Returns:
            Frame with multiline text
        """
        font = font or self.default_font
        font_scale = font_scale or self.default_scale
        thickness = thickness or self.default_thickness

        x, y = position

        # Calculate line height
        (_, line_h), _ = cv2.getTextSize("Ay", font, font_scale, thickness)
        line_h = int(line_h * line_spacing)

        for i, line in enumerate(lines):
            line_y = y + (i * line_h)
            cv2.putText(
                frame, line, (x, line_y),
                font, font_scale, color, thickness, cv2.LINE_AA
            )

        return frame

    def get_text_size(
        self,
        text: str,
        font: int = None,
        font_scale: float = None,
        thickness: int = None
    ) -> Tuple[int, int, int]:
        """
        Get text dimensions.

        Args:
            text: Text to measure
            font: OpenCV font
            font_scale: Scale factor
            thickness: Line thickness

        Returns:
            Tuple of (width, height, baseline)
        """
        font = font or self.default_font
        font_scale = font_scale or self.default_scale
        thickness = thickness or self.default_thickness

        (w, h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
        return w, h, baseline
```

## Text Styles

### Style 1: Simple Text

```python
renderer.draw_text(frame, "Hello World", (10, 30))
```

### Style 2: Text with Background

```python
renderer.draw_text_with_background(
    frame, "Status: OK", (10, 30),
    color=(0, 255, 0),
    bg_color=(0, 0, 0),
    bg_opacity=0.7
)
```

### Style 3: Text with Shadow

```python
renderer.draw_text_with_shadow(
    frame, "Important!", (10, 30),
    color=(255, 255, 255),
    shadow_color=(0, 0, 0),
    shadow_offset=2
)
```

### Style 4: Text with Outline

```python
renderer.draw_text_with_outline(
    frame, "Critical", (10, 30),
    color=(0, 0, 255),
    outline_color=(255, 255, 255),
    outline_thickness=2
)
```

## Font Reference

| Font | Constant | Best For |
|------|----------|----------|
| Simplex | `FONT_HERSHEY_SIMPLEX` | General use |
| Plain | `FONT_HERSHEY_PLAIN` | Minimal display |
| Duplex | `FONT_HERSHEY_DUPLEX` | Bold text |
| Complex | `FONT_HERSHEY_COMPLEX` | Detailed text |
| Script | `FONT_HERSHEY_SCRIPT_SIMPLEX` | Decorative |

## Font Scale Guidelines

| Scale | Use Case |
|-------|----------|
| 0.3-0.4 | Fine print, dense info |
| 0.5-0.6 | Standard labels |
| 0.7-0.8 | Important status |
| 1.0+ | Headings, alerts |

## Performance Tips

1. **Cache text measurements**: Use `get_text_size()` once
2. **Minimize opacity blending**: `bg_opacity=1.0` is faster
3. **Use simpler fonts**: Simplex is fastest
4. **Batch similar draws**: Group by font/scale

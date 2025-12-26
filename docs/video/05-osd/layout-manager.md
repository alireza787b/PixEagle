# OSD Layout Manager

> Anchor-based positioning for OSD elements

## Overview

The `LayoutManager` handles OSD element positioning using anchor points, ensuring consistent layout across different frame sizes.

## Anchor System

```
┌─────────────────────────────────────────────────────────────────┐
│  top-left         top-center         top-right                  │
│     ●──────────────────●──────────────────●                     │
│     │                                     │                     │
│     │                                     │                     │
│     │                                     │                     │
│     │         ●                           │                     │
│     │       center                        │                     │
│     │                                     │                     │
│     │                                     │                     │
│     │                                     │                     │
│     ●──────────────────●──────────────────●                     │
│  bottom-left    bottom-center     bottom-right                  │
└─────────────────────────────────────────────────────────────────┘
```

## Layout Manager Class

```python
import numpy as np
from typing import Tuple, Dict, Optional
from dataclasses import dataclass
from enum import Enum

class Anchor(Enum):
    """Anchor point positions."""
    TOP_LEFT = 'top-left'
    TOP_CENTER = 'top-center'
    TOP_RIGHT = 'top-right'
    CENTER_LEFT = 'center-left'
    CENTER = 'center'
    CENTER_RIGHT = 'center-right'
    BOTTOM_LEFT = 'bottom-left'
    BOTTOM_CENTER = 'bottom-center'
    BOTTOM_RIGHT = 'bottom-right'


@dataclass
class Region:
    """Screen region with bounds."""
    x: int
    y: int
    width: int
    height: int


class LayoutManager:
    """
    Manages OSD element layout and positioning.

    Provides anchor-based positioning with margins,
    safe zones, and collision avoidance.
    """

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        margin: int = 10,
        padding: int = 5
    ):
        """
        Initialize layout manager.

        Args:
            width: Frame width
            height: Frame height
            margin: Edge margin in pixels
            padding: Element padding in pixels
        """
        self.width = width
        self.height = height
        self.margin = margin
        self.padding = padding

        # Track occupied regions
        self._occupied: Dict[str, Region] = {}

        # Calculate anchor positions
        self._anchors = self._calculate_anchors()

    def _calculate_anchors(self) -> Dict[str, Tuple[int, int]]:
        """Calculate anchor point positions."""
        m = self.margin
        w = self.width
        h = self.height
        cx = w // 2
        cy = h // 2

        return {
            'top-left': (m, m + 15),
            'top-center': (cx, m + 15),
            'top-right': (w - m, m + 15),
            'center-left': (m, cy),
            'center': (cx, cy),
            'center-right': (w - m, cy),
            'bottom-left': (m, h - m),
            'bottom-center': (cx, h - m),
            'bottom-right': (w - m, h - m),
        }

    def update_dimensions(self, width: int, height: int) -> None:
        """Update layout for new frame dimensions."""
        self.width = width
        self.height = height
        self._anchors = self._calculate_anchors()

    def get_anchor_position(self, anchor: str) -> Tuple[int, int]:
        """
        Get position for anchor point.

        Args:
            anchor: Anchor name ('top-left', 'center', etc.)

        Returns:
            (x, y) position tuple
        """
        return self._anchors.get(anchor, (0, 0))

    def get_position(
        self,
        anchor: str,
        offset: Tuple[int, int] = (0, 0)
    ) -> Tuple[int, int]:
        """
        Get position with offset.

        Args:
            anchor: Anchor name
            offset: (x, y) offset from anchor

        Returns:
            (x, y) position
        """
        x, y = self._anchors.get(anchor, (0, 0))
        return (x + offset[0], y + offset[1])

    def register_element(
        self,
        element_id: str,
        anchor: str,
        width: int,
        height: int
    ) -> Region:
        """
        Register element and get assigned region.

        Args:
            element_id: Unique element identifier
            anchor: Preferred anchor point
            width: Element width
            height: Element height

        Returns:
            Assigned region
        """
        x, y = self._anchors.get(anchor, (0, 0))

        # Adjust position based on anchor
        if 'right' in anchor:
            x = x - width
        elif 'center' in anchor and 'top' not in anchor and 'bottom' not in anchor:
            x = x - width // 2

        if 'bottom' in anchor:
            y = y - height
        elif 'center' in anchor:
            y = y - height // 2

        region = Region(x, y, width, height)
        self._occupied[element_id] = region
        return region

    def unregister_element(self, element_id: str) -> None:
        """Remove element from layout tracking."""
        if element_id in self._occupied:
            del self._occupied[element_id]

    def get_safe_zone(self) -> Region:
        """
        Get safe zone for content (avoiding margins).

        Returns:
            Safe zone region
        """
        return Region(
            x=self.margin,
            y=self.margin,
            width=self.width - 2 * self.margin,
            height=self.height - 2 * self.margin
        )

    def get_stacked_position(
        self,
        anchor: str,
        item_index: int,
        item_height: int,
        spacing: int = 5
    ) -> Tuple[int, int]:
        """
        Get position for stacked items (like list).

        Args:
            anchor: Base anchor point
            item_index: Index in stack (0-based)
            item_height: Height of each item
            spacing: Space between items

        Returns:
            (x, y) position for item
        """
        x, y = self._anchors.get(anchor, (0, 0))

        if 'top' in anchor:
            y = y + item_index * (item_height + spacing)
        elif 'bottom' in anchor:
            y = y - item_index * (item_height + spacing)

        return (x, y)

    def get_grid_position(
        self,
        row: int,
        col: int,
        cell_width: int,
        cell_height: int,
        origin: str = 'top-left'
    ) -> Tuple[int, int]:
        """
        Get position in grid layout.

        Args:
            row: Row index
            col: Column index
            cell_width: Grid cell width
            cell_height: Grid cell height
            origin: Grid origin anchor

        Returns:
            (x, y) position for cell
        """
        ox, oy = self._anchors.get(origin, (self.margin, self.margin))

        x = ox + col * cell_width
        y = oy + row * cell_height

        return (x, y)

    def clamp_to_frame(
        self,
        x: int,
        y: int,
        width: int = 0,
        height: int = 0
    ) -> Tuple[int, int]:
        """
        Clamp position to stay within frame bounds.

        Args:
            x: X position
            y: Y position
            width: Element width
            height: Element height

        Returns:
            Clamped (x, y) position
        """
        x = max(self.margin, min(x, self.width - width - self.margin))
        y = max(self.margin, min(y, self.height - height - self.margin))
        return (x, y)

    def get_all_anchors(self) -> Dict[str, Tuple[int, int]]:
        """Get all anchor positions."""
        return self._anchors.copy()
```

## Usage Examples

### Basic Positioning

```python
layout = LayoutManager(640, 480)

# Get anchor position
x, y = layout.get_anchor_position('top-left')
cv2.putText(frame, "FPS: 30", (x, y), ...)

# With offset
x, y = layout.get_position('top-left', offset=(0, 20))
cv2.putText(frame, "Mode: Track", (x, y), ...)
```

### Stacked Elements

```python
# Display multiple status lines
for i, status in enumerate(statuses):
    x, y = layout.get_stacked_position(
        'top-left',
        item_index=i,
        item_height=20
    )
    cv2.putText(frame, status, (x, y), ...)
```

### Grid Layout

```python
# 3x3 grid of icons
for row in range(3):
    for col in range(3):
        x, y = layout.get_grid_position(
            row, col,
            cell_width=50,
            cell_height=50
        )
        draw_icon(frame, icons[row][col], (x, y))
```

### Element Registration

```python
# Register element for collision tracking
region = layout.register_element(
    'telemetry',
    'bottom-left',
    width=200,
    height=100
)

# Draw element in region
cv2.rectangle(frame,
    (region.x, region.y),
    (region.x + region.width, region.y + region.height),
    (0, 0, 0), -1
)
```

## Configuration

```yaml
OSD:
  Layout:
    MARGIN: 10          # Edge margin
    PADDING: 5          # Element padding
    LINE_SPACING: 1.5   # Multiline text spacing
    STACK_SPACING: 5    # Stacked element gap
```

## Responsive Layout

```python
class ResponsiveLayout(LayoutManager):
    """Layout that adapts to frame size."""

    def __init__(self, width, height):
        super().__init__(width, height)

    def get_scaled_font(self) -> float:
        """Get font scale based on resolution."""
        base = 0.5
        if self.width >= 1920:
            return base * 1.5
        elif self.width >= 1280:
            return base * 1.2
        elif self.width <= 480:
            return base * 0.8
        return base

    def get_scaled_margin(self) -> int:
        """Get margin based on resolution."""
        return max(5, int(self.width * 0.015))
```

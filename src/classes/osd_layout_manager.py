"""
OSD Layout Manager Module
Manages adaptive positioning, safe zones, and collision detection for OSD elements.
Provides industry-standard layout systems with responsive design principles.

Features:
- Named anchor points (top-left, center, bottom-right, etc.)
- Safe zone margins (5% default, per aviation standards)
- Collision detection to prevent overlapping
- Responsive grid system (12-column layout)
- Resolution-independent positioning
"""

import logging
from typing import Tuple, Dict, List, Optional
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class Anchor(Enum):
    """Standard anchor points for OSD element positioning."""
    TOP_LEFT = "top-left"
    TOP_CENTER = "top-center"
    TOP_RIGHT = "top-right"
    CENTER_LEFT = "center-left"
    CENTER = "center"
    CENTER_RIGHT = "center-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_CENTER = "bottom-center"
    BOTTOM_RIGHT = "bottom-right"


@dataclass
class BoundingBox:
    """Represents a rectangular area on screen."""
    x: int
    y: int
    width: int
    height: int

    def intersects(self, other: 'BoundingBox') -> bool:
        """Check if this bounding box intersects with another."""
        return not (
            self.x + self.width < other.x or
            other.x + other.width < self.x or
            self.y + self.height < other.y or
            other.y + other.height < self.y
        )

    def contains_point(self, x: int, y: int) -> bool:
        """Check if a point is inside this bounding box."""
        return (self.x <= x <= self.x + self.width and
                self.y <= y <= self.y + self.height)


@dataclass
class OSDElement:
    """Represents an OSD element with position and size information."""
    name: str
    bbox: BoundingBox
    priority: int = 0  # Higher priority elements win in collision resolution
    enabled: bool = True


class OSDLayoutManager:
    """
    Manages OSD element positioning and layout with professional features.

    Provides adaptive positioning, safe zones, and collision detection to ensure
    clean, readable OSD layouts across different resolutions.
    """

    def __init__(
        self,
        frame_width: int,
        frame_height: int,
        safe_zone_margin: float = 5.0,
        grid_columns: int = 12
    ):
        """
        Initialize the layout manager.

        Args:
            frame_width: Width of the video frame in pixels
            frame_height: Height of the video frame in pixels
            safe_zone_margin: Margin from frame edges as percentage (default: 5%)
            grid_columns: Number of columns in responsive grid (default: 12)
        """
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.safe_zone_margin = safe_zone_margin
        self.grid_columns = grid_columns

        # Calculate safe zone boundaries
        self.safe_margin_x = int(frame_width * safe_zone_margin / 100)
        self.safe_margin_y = int(frame_height * safe_zone_margin / 100)

        # Calculate usable area
        self.usable_width = frame_width - (2 * self.safe_margin_x)
        self.usable_height = frame_height - (2 * self.safe_margin_y)

        # Track placed elements for collision detection
        self.placed_elements: List[OSDElement] = []

        logger.info(
            f"OSDLayoutManager initialized: {frame_width}x{frame_height}, "
            f"safe_zone={safe_zone_margin}%, margins=({self.safe_margin_x}px, {self.safe_margin_y}px)"
        )

    def get_anchor_position(
        self,
        anchor: Anchor,
        text_width: int = 0,
        text_height: int = 0
    ) -> Tuple[int, int]:
        """
        Get pixel coordinates for a named anchor point.

        Args:
            anchor: Anchor point enum
            text_width: Width of text to position (for alignment)
            text_height: Height of text to position (for alignment)

        Returns:
            (x, y) pixel coordinates
        """
        # Calculate base anchor positions within safe zones
        positions = {
            Anchor.TOP_LEFT: (
                self.safe_margin_x,
                self.safe_margin_y
            ),
            Anchor.TOP_CENTER: (
                (self.frame_width - text_width) // 2,
                self.safe_margin_y
            ),
            Anchor.TOP_RIGHT: (
                self.frame_width - self.safe_margin_x - text_width,
                self.safe_margin_y
            ),
            Anchor.CENTER_LEFT: (
                self.safe_margin_x,
                (self.frame_height - text_height) // 2
            ),
            Anchor.CENTER: (
                (self.frame_width - text_width) // 2,
                (self.frame_height - text_height) // 2
            ),
            Anchor.CENTER_RIGHT: (
                self.frame_width - self.safe_margin_x - text_width,
                (self.frame_height - text_height) // 2
            ),
            Anchor.BOTTOM_LEFT: (
                self.safe_margin_x,
                self.frame_height - self.safe_margin_y - text_height
            ),
            Anchor.BOTTOM_CENTER: (
                (self.frame_width - text_width) // 2,
                self.frame_height - self.safe_margin_y - text_height
            ),
            Anchor.BOTTOM_RIGHT: (
                self.frame_width - self.safe_margin_x - text_width,
                self.frame_height - self.safe_margin_y - text_height
            ),
        }

        return positions.get(anchor, positions[Anchor.TOP_LEFT])

    def calculate_position(
        self,
        anchor: Optional[Anchor] = None,
        offset: Tuple[int, int] = (0, 0),
        percentage_pos: Optional[Tuple[float, float]] = None,
        text_width: int = 0,
        text_height: int = 0
    ) -> Tuple[int, int]:
        """
        Calculate final position for an OSD element.

        Supports both anchor-based and percentage-based positioning for
        backward compatibility.

        Args:
            anchor: Named anchor point (preferred method)
            offset: (x, y) pixel offset from anchor
            percentage_pos: (x%, y%) position as percentages (legacy method)
            text_width: Width of text for alignment
            text_height: Height of text for alignment

        Returns:
            (x, y) pixel coordinates
        """
        if anchor is not None:
            # Modern anchor-based positioning
            base_x, base_y = self.get_anchor_position(anchor, text_width, text_height)
            return (base_x + offset[0], base_y + offset[1])

        elif percentage_pos is not None:
            # Legacy percentage-based positioning
            x_percent, y_percent = percentage_pos
            x = int(self.frame_width * x_percent / 100)
            y = int(self.frame_height * y_percent / 100)
            return (x + offset[0], y + offset[1])

        else:
            # Default to top-left if no positioning specified
            return (self.safe_margin_x + offset[0], self.safe_margin_y + offset[1])

    def apply_safe_zone_constraints(
        self,
        x: int,
        y: int,
        width: int,
        height: int
    ) -> Tuple[int, int]:
        """
        Ensure element stays within safe zones.

        Args:
            x: X coordinate
            y: Y coordinate
            width: Element width
            height: Element height

        Returns:
            Constrained (x, y) coordinates
        """
        # Clamp to safe zones
        x = max(self.safe_margin_x, min(x, self.frame_width - self.safe_margin_x - width))
        y = max(self.safe_margin_y, min(y, self.frame_height - self.safe_margin_y - height))

        return (x, y)

    def register_element(
        self,
        name: str,
        x: int,
        y: int,
        width: int,
        height: int,
        priority: int = 0
    ) -> OSDElement:
        """
        Register an OSD element for collision tracking.

        Args:
            name: Unique element name
            x: X coordinate
            y: Y coordinate
            width: Element width
            height: Element height
            priority: Priority for collision resolution (higher wins)

        Returns:
            Created OSDElement object
        """
        bbox = BoundingBox(x, y, width, height)
        element = OSDElement(name, bbox, priority)
        self.placed_elements.append(element)

        logger.debug(f"Registered element '{name}' at ({x}, {y}) size ({width}x{height})")
        return element

    def check_collision(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        exclude_names: Optional[List[str]] = None
    ) -> Optional[OSDElement]:
        """
        Check if a bounding box collides with any registered elements.

        Args:
            x: X coordinate
            y: Y coordinate
            width: Width
            height: Height
            exclude_names: List of element names to exclude from check

        Returns:
            Colliding element or None
        """
        test_bbox = BoundingBox(x, y, width, height)
        exclude_names = exclude_names or []

        for element in self.placed_elements:
            if element.name in exclude_names:
                continue

            if element.enabled and test_bbox.intersects(element.bbox):
                return element

        return None

    def find_free_position(
        self,
        preferred_anchor: Anchor,
        width: int,
        height: int,
        fallback_anchors: Optional[List[Anchor]] = None
    ) -> Optional[Tuple[int, int]]:
        """
        Find a collision-free position for an element.

        Tries preferred anchor first, then falls back to alternative anchors.

        Args:
            preferred_anchor: Preferred anchor point
            width: Element width
            height: Element height
            fallback_anchors: List of alternative anchors to try

        Returns:
            (x, y) coordinates or None if no free position found
        """
        # Try preferred anchor
        x, y = self.get_anchor_position(preferred_anchor, width, height)
        if self.check_collision(x, y, width, height) is None:
            return (x, y)

        # Try fallback anchors
        if fallback_anchors:
            for fallback in fallback_anchors:
                x, y = self.get_anchor_position(fallback, width, height)
                if self.check_collision(x, y, width, height) is None:
                    logger.debug(
                        f"Used fallback anchor {fallback.value} instead of {preferred_anchor.value}"
                    )
                    return (x, y)

        logger.warning(
            f"Could not find collision-free position for element "
            f"(anchor: {preferred_anchor.value}, size: {width}x{height})"
        )
        return None

    def clear_elements(self):
        """Clear all registered elements."""
        self.placed_elements.clear()
        logger.debug("Cleared all registered elements")

    def get_grid_position(
        self,
        column: int,
        row: int,
        column_span: int = 1,
        row_height: int = 30
    ) -> Tuple[int, int, int, int]:
        """
        Get position and size based on grid system.

        Args:
            column: Starting column (0 to grid_columns-1)
            row: Row number (0-indexed)
            column_span: Number of columns to span
            row_height: Height of each row in pixels

        Returns:
            (x, y, width, height) tuple
        """
        column_width = self.usable_width // self.grid_columns

        x = self.safe_margin_x + (column * column_width)
        y = self.safe_margin_y + (row * row_height)
        width = column_span * column_width
        height = row_height

        return (x, y, width, height)

    def update_frame_size(self, width: int, height: int):
        """
        Update frame dimensions and recalculate layout parameters.

        Args:
            width: New frame width
            height: New frame height
        """
        self.frame_width = width
        self.frame_height = height

        # Recalculate safe zones
        self.safe_margin_x = int(width * self.safe_zone_margin / 100)
        self.safe_margin_y = int(height * self.safe_zone_margin / 100)

        # Recalculate usable area
        self.usable_width = width - (2 * self.safe_margin_x)
        self.usable_height = height - (2 * self.safe_margin_y)

        # Clear placed elements as positions need recalculation
        self.clear_elements()

        logger.info(
            f"Frame size updated: {width}x{height}, "
            f"margins=({self.safe_margin_x}px, {self.safe_margin_y}px)"
        )

    def get_safe_zone_info(self) -> Dict[str, int]:
        """
        Get information about safe zone boundaries.

        Returns:
            Dictionary with safe zone measurements
        """
        return {
            'frame_width': self.frame_width,
            'frame_height': self.frame_height,
            'safe_margin_x': self.safe_margin_x,
            'safe_margin_y': self.safe_margin_y,
            'usable_width': self.usable_width,
            'usable_height': self.usable_height,
            'safe_zone_percentage': self.safe_zone_margin
        }

    def debug_draw_safe_zones(self, frame) -> any:
        """
        Draw safe zone boundaries on frame for debugging.

        Args:
            frame: OpenCV frame

        Returns:
            Frame with safe zones drawn
        """
        import cv2

        # Draw safe zone boundaries
        color = (0, 255, 255)  # Yellow
        thickness = 1

        # Draw rectangle for safe zone
        cv2.rectangle(
            frame,
            (self.safe_margin_x, self.safe_margin_y),
            (self.frame_width - self.safe_margin_x, self.frame_height - self.safe_margin_y),
            color,
            thickness
        )

        # Draw grid lines
        column_width = self.usable_width // self.grid_columns
        for i in range(1, self.grid_columns):
            x = self.safe_margin_x + (i * column_width)
            cv2.line(
                frame,
                (x, self.safe_margin_y),
                (x, self.frame_height - self.safe_margin_y),
                color,
                1
            )

        return frame

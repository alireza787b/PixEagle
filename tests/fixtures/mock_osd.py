# tests/fixtures/mock_osd.py
"""
Mock OSD (On-Screen Display) objects for testing OSD rendering system.

Provides mock implementations of OSDRenderer, OSDTextRenderer, and
OSDLayoutManager for isolated unit testing.
"""

import numpy as np
from typing import Tuple, Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from unittest.mock import MagicMock


class MockTextStyle(Enum):
    """Mock text rendering styles."""
    PLAIN = "plain"
    OUTLINED = "outlined"
    SHADOWED = "shadowed"
    PLATE = "plate"


class MockAnchor(Enum):
    """Mock anchor positions."""
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
class MockOSDElement:
    """Represents a rendered OSD element."""
    type: str
    text: Optional[str] = None
    position: Tuple[int, int] = (0, 0)
    anchor: str = "top-left"
    style: str = "plain"
    font_size: int = 16
    color: Tuple[int, int, int] = (255, 255, 255)
    background_color: Optional[Tuple[int, int, int]] = None
    visible: bool = True
    timestamp: float = field(default_factory=lambda: 0.0)


class MockOSDTextRenderer:
    """
    Mock OSD text renderer for testing.

    Tracks all rendered text for verification without actual rendering.
    """

    def __init__(self, width: int = 640, height: int = 480):
        """
        Initialize mock text renderer.

        Args:
            width: Frame width
            height: Frame height
        """
        self.width = width
        self.height = height
        self.rendered_texts: List[MockOSDElement] = []
        self.font_scale_base = 1.0
        self.default_font_size = 16
        self.default_color = (255, 255, 255)
        self.default_style = MockTextStyle.PLAIN

    def render_text(
        self,
        frame: np.ndarray,
        text: str,
        position: Tuple[int, int],
        font_size: int = 16,
        color: Tuple[int, int, int] = (255, 255, 255),
        style: str = "plain",
        background_color: Optional[Tuple[int, int, int]] = None,
        **kwargs
    ) -> np.ndarray:
        """
        Mock render text onto frame.

        Args:
            frame: Input frame (not modified)
            text: Text to render
            position: (x, y) position
            font_size: Font size in pixels
            color: BGR color tuple
            style: Text style (plain, outlined, shadowed, plate)
            background_color: Background color for plate style

        Returns:
            Unmodified frame (mock)
        """
        element = MockOSDElement(
            type="text",
            text=text,
            position=position,
            style=style,
            font_size=font_size,
            color=color,
            background_color=background_color,
        )
        self.rendered_texts.append(element)
        return frame

    def render_multiline_text(
        self,
        frame: np.ndarray,
        lines: List[str],
        position: Tuple[int, int],
        line_spacing: float = 1.5,
        **kwargs
    ) -> np.ndarray:
        """
        Mock render multiple lines of text.

        Args:
            frame: Input frame
            lines: List of text lines
            position: Starting position
            line_spacing: Line spacing multiplier

        Returns:
            Unmodified frame
        """
        y_offset = 0
        for line in lines:
            pos = (position[0], position[1] + y_offset)
            self.render_text(frame, line, pos, **kwargs)
            y_offset += int(kwargs.get('font_size', 16) * line_spacing)
        return frame

    def get_text_size(
        self,
        text: str,
        font_size: int = 16,
        **kwargs
    ) -> Tuple[int, int]:
        """
        Get text bounding box size.

        Args:
            text: Text to measure
            font_size: Font size

        Returns:
            (width, height) tuple
        """
        # Approximate: 0.6 * font_size per character width
        width = int(len(text) * font_size * 0.6)
        height = int(font_size * 1.2)
        return (width, height)

    def clear_rendered(self) -> None:
        """Clear rendered text history."""
        self.rendered_texts.clear()

    def get_rendered_count(self) -> int:
        """Get count of rendered texts."""
        return len(self.rendered_texts)

    def get_rendered_by_text(self, text: str) -> List[MockOSDElement]:
        """Get all rendered elements matching text."""
        return [e for e in self.rendered_texts if e.text == text]


class MockOSDLayoutManager:
    """
    Mock OSD layout manager for testing element positioning.

    Handles anchor-based positioning and layout calculations.
    """

    def __init__(self, width: int = 640, height: int = 480):
        """
        Initialize mock layout manager.

        Args:
            width: Frame width
            height: Frame height
        """
        self.width = width
        self.height = height
        self.margin = 10
        self.safe_zone = 20
        self.elements: Dict[str, Dict] = {}
        self.layout_updates: List[Dict] = []

    def register_element(self, name: str, config: Dict) -> None:
        """
        Register OSD element.

        Args:
            name: Element identifier
            config: Element configuration dict
        """
        self.elements[name] = config

    def unregister_element(self, name: str) -> None:
        """Unregister OSD element."""
        self.elements.pop(name, None)

    def get_position(
        self,
        anchor: str,
        offset: Tuple[int, int] = (0, 0),
        element_size: Tuple[int, int] = (0, 0)
    ) -> Tuple[int, int]:
        """
        Calculate position from anchor.

        Args:
            anchor: Anchor name (e.g., 'top-left', 'center')
            offset: (x, y) offset from anchor
            element_size: (width, height) for alignment

        Returns:
            (x, y) position tuple
        """
        anchor_positions = {
            "top-left": (self.margin, self.margin),
            "top-center": (self.width // 2, self.margin),
            "top-right": (self.width - self.margin, self.margin),
            "center-left": (self.margin, self.height // 2),
            "center": (self.width // 2, self.height // 2),
            "center-right": (self.width - self.margin, self.height // 2),
            "bottom-left": (self.margin, self.height - self.margin),
            "bottom-center": (self.width // 2, self.height - self.margin),
            "bottom-right": (self.width - self.margin, self.height - self.margin),
        }

        base = anchor_positions.get(anchor, (0, 0))

        # Adjust for element size on right/bottom anchors
        x, y = base
        if "right" in anchor:
            x -= element_size[0]
        if "bottom" in anchor:
            y -= element_size[1]
        if "center" in anchor and "left" not in anchor and "right" not in anchor:
            x -= element_size[0] // 2
        if anchor == "center" or "center" in anchor.split("-")[0]:
            y -= element_size[1] // 2

        return (x + offset[0], y + offset[1])

    def update_layout(self, new_width: int, new_height: int) -> None:
        """
        Update layout dimensions.

        Args:
            new_width: New frame width
            new_height: New frame height
        """
        self.layout_updates.append({
            'old': (self.width, self.height),
            'new': (new_width, new_height),
        })
        self.width = new_width
        self.height = new_height

    def get_safe_area(self) -> Tuple[int, int, int, int]:
        """
        Get safe rendering area.

        Returns:
            (x, y, width, height) of safe area
        """
        return (
            self.safe_zone,
            self.safe_zone,
            self.width - 2 * self.safe_zone,
            self.height - 2 * self.safe_zone,
        )

    def is_position_visible(self, position: Tuple[int, int]) -> bool:
        """Check if position is within visible area."""
        x, y = position
        return 0 <= x < self.width and 0 <= y < self.height


class MockOSDRenderer:
    """
    Mock OSD renderer for testing.

    Combines text rendering and layout management with element tracking.
    """

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        enabled: bool = True
    ):
        """
        Initialize mock OSD renderer.

        Args:
            width: Frame width
            height: Frame height
            enabled: Whether OSD is enabled
        """
        self.width = width
        self.height = height
        self.osd_enabled = enabled
        self.performance_mode = "balanced"

        # Sub-components
        self.text_renderer = MockOSDTextRenderer(width, height)
        self.layout_manager = MockOSDLayoutManager(width, height)

        # Element registry
        self.registered_elements: Dict[str, Dict] = {}
        self.visible_elements: List[str] = []

        # Render tracking
        self.render_calls = 0
        self.last_render_time = 0.0
        self.rendered_frames: List[np.ndarray] = []

        # Preset system
        self.current_preset = "default"
        self.available_presets = ["minimal", "professional", "full_telemetry"]

    def render(self, frame: np.ndarray) -> np.ndarray:
        """
        Render OSD onto frame.

        Args:
            frame: Input BGR frame

        Returns:
            Frame with OSD (mock returns copy)
        """
        self.render_calls += 1

        if not self.osd_enabled:
            return frame.copy()

        output = frame.copy()
        self.rendered_frames.append(output)
        return output

    def draw_osd(self, frame: np.ndarray) -> np.ndarray:
        """Alias for render method."""
        return self.render(frame)

    def render_element(
        self,
        frame: np.ndarray,
        element_name: str,
        **kwargs
    ) -> np.ndarray:
        """
        Render specific element.

        Args:
            frame: Input frame
            element_name: Name of element to render
            **kwargs: Override element configuration

        Returns:
            Frame with element rendered
        """
        if element_name not in self.registered_elements:
            return frame

        config = {**self.registered_elements[element_name], **kwargs}
        position = self.layout_manager.get_position(
            config.get('anchor', 'top-left'),
            config.get('offset', (0, 0)),
        )

        if 'text' in config:
            return self.text_renderer.render_text(
                frame,
                config['text'],
                position,
                **config
            )

        return frame

    def register_element(self, name: str, config: Dict) -> None:
        """Register OSD element."""
        self.registered_elements[name] = config
        self.layout_manager.register_element(name, config)

    def show_element(self, name: str) -> None:
        """Show registered element."""
        if name not in self.visible_elements:
            self.visible_elements.append(name)

    def hide_element(self, name: str) -> None:
        """Hide registered element."""
        if name in self.visible_elements:
            self.visible_elements.remove(name)

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable OSD."""
        self.osd_enabled = enabled

    def set_performance_mode(self, mode: str) -> None:
        """
        Set performance mode.

        Args:
            mode: 'fast', 'balanced', or 'quality'
        """
        self.performance_mode = mode

    def load_preset(self, preset_name: str) -> bool:
        """
        Load OSD preset.

        Args:
            preset_name: Name of preset to load

        Returns:
            True if preset loaded
        """
        if preset_name in self.available_presets:
            self.current_preset = preset_name
            return True
        return False

    def get_element_config(self, name: str) -> Optional[Dict]:
        """Get element configuration."""
        return self.registered_elements.get(name)

    def update_dimensions(self, width: int, height: int) -> None:
        """Update renderer dimensions."""
        self.width = width
        self.height = height
        self.text_renderer.width = width
        self.text_renderer.height = height
        self.layout_manager.update_layout(width, height)


class MockOSDHandler:
    """
    Mock legacy OSD handler for backward compatibility testing.

    Simulates the older OSD interface.
    """

    def __init__(self, enabled: bool = True):
        """
        Initialize mock OSD handler.

        Args:
            enabled: Whether OSD is enabled
        """
        self.enabled = enabled
        self.elements_drawn: List[str] = []
        self.draw_calls = 0

    def draw_osd(self, frame: np.ndarray) -> np.ndarray:
        """
        Draw OSD on frame.

        Args:
            frame: Input frame

        Returns:
            Frame with OSD
        """
        self.draw_calls += 1
        if not self.enabled:
            return frame

        self.elements_drawn.append("frame")
        return frame.copy()

    def draw_crosshair(self, frame: np.ndarray) -> np.ndarray:
        """Draw crosshair element."""
        self.elements_drawn.append("crosshair")
        return frame

    def draw_timestamp(self, frame: np.ndarray) -> np.ndarray:
        """Draw timestamp element."""
        self.elements_drawn.append("timestamp")
        return frame

    def draw_telemetry(self, frame: np.ndarray, data: Dict) -> np.ndarray:
        """Draw telemetry data."""
        self.elements_drawn.append("telemetry")
        return frame


# Factory functions

def create_mock_osd_renderer(
    width: int = 640,
    height: int = 480,
    enabled: bool = True
) -> MockOSDRenderer:
    """
    Create configured mock OSD renderer.

    Args:
        width: Frame width
        height: Frame height
        enabled: Whether OSD is enabled

    Returns:
        Configured MockOSDRenderer
    """
    return MockOSDRenderer(width, height, enabled)


def create_mock_text_renderer(
    width: int = 640,
    height: int = 480
) -> MockOSDTextRenderer:
    """Create mock text renderer."""
    return MockOSDTextRenderer(width, height)


def create_mock_layout_manager(
    width: int = 640,
    height: int = 480
) -> MockOSDLayoutManager:
    """Create mock layout manager."""
    return MockOSDLayoutManager(width, height)


def create_osd_renderer_with_elements(
    elements: Dict[str, Dict]
) -> MockOSDRenderer:
    """
    Create OSD renderer with pre-registered elements.

    Args:
        elements: Dictionary of element configurations

    Returns:
        Configured MockOSDRenderer with elements
    """
    renderer = MockOSDRenderer()
    for name, config in elements.items():
        renderer.register_element(name, config)
    return renderer


def create_test_osd_config() -> Dict[str, Any]:
    """
    Create standard test OSD configuration.

    Returns:
        OSD configuration dictionary
    """
    return {
        'enabled': True,
        'performance_mode': 'balanced',
        'elements': {
            'timestamp': {
                'anchor': 'top-left',
                'offset': (10, 10),
                'style': 'outlined',
                'font_size': 16,
            },
            'crosshair': {
                'anchor': 'center',
                'offset': (0, 0),
                'color': (0, 255, 0),
            },
            'telemetry': {
                'anchor': 'bottom-left',
                'offset': (10, -10),
                'style': 'plate',
                'font_size': 14,
            },
        },
    }

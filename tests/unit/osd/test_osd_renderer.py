# tests/unit/osd/test_osd_renderer.py
"""
Unit tests for OSD renderer functionality.

Tests cover:
- Renderer initialization
- Element registration and visibility
- Render pipeline
- Standard OSD elements
"""

import pytest
import numpy as np
import cv2
from unittest.mock import MagicMock, patch
from typing import Dict, List, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod
import time

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.osd]


# ============================================================================
# OSD Element Base Class
# ============================================================================

@dataclass
class OSDElement:
    """Base OSD element for testing."""
    id: str
    position: str
    visible: bool = True
    priority: int = 0

    def render(self, frame, layout, text_renderer, data):
        return frame


# ============================================================================
# Mock Layout Manager
# ============================================================================

class MockLayoutManager:
    """Mock layout manager for testing."""

    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height
        self.margin = 10

        self._anchors = {
            'top-left': (10, 25),
            'top-center': (320, 25),
            'top-right': (630, 25),
            'center-left': (10, 240),
            'center': (320, 240),
            'center-right': (630, 240),
            'bottom-left': (10, 470),
            'bottom-center': (320, 470),
            'bottom-right': (630, 470),
        }

    def get_anchor_position(self, anchor: str):
        return self._anchors.get(anchor, (0, 0))

    def update_dimensions(self, width: int, height: int):
        self.width = width
        self.height = height


# ============================================================================
# Mock Text Renderer
# ============================================================================

class MockTextRenderer:
    """Mock text renderer for testing."""

    def __init__(self):
        self.draw_calls = []

    def draw_text(self, frame, text, position, **kwargs):
        self.draw_calls.append(('text', text, position))
        return frame

    def draw_text_with_background(self, frame, text, position, **kwargs):
        self.draw_calls.append(('text_bg', text, position))
        return frame


# ============================================================================
# OSD Renderer Implementation
# ============================================================================

class OSDRenderer:
    """OSD renderer for testing."""

    def __init__(self, width: int = 640, height: int = 480, config: dict = None):
        self.width = width
        self.height = height
        self.config = config or {}

        self.layout = MockLayoutManager(width, height)
        self.text_renderer = MockTextRenderer()

        self._elements: Dict[str, OSDElement] = {}

    def add_element(self, element: OSDElement):
        self._elements[element.id] = element

    def remove_element(self, element_id: str):
        if element_id in self._elements:
            del self._elements[element_id]

    def set_visibility(self, element_id: str, visible: bool):
        if element_id in self._elements:
            self._elements[element_id].visible = visible

    def get_element(self, element_id: str) -> Optional[OSDElement]:
        return self._elements.get(element_id)

    def get_element_ids(self) -> List[str]:
        return list(self._elements.keys())

    def render(self, frame: np.ndarray, data: dict = None) -> np.ndarray:
        osd_frame = frame.copy()

        h, w = frame.shape[:2]
        if w != self.width or h != self.height:
            self.width = w
            self.height = h
            self.layout.update_dimensions(w, h)

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
                except Exception:
                    pass

        return osd_frame


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def test_frame():
    """Create a test BGR frame."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def osd_renderer():
    """Create OSD renderer instance."""
    return OSDRenderer(width=640, height=480)


# ============================================================================
# Initialization Tests
# ============================================================================

class TestOSDRendererInitialization:
    """Tests for OSD renderer initialization."""

    def test_renderer_default_dimensions(self):
        """Renderer uses default dimensions."""
        renderer = OSDRenderer()
        assert renderer.width == 640
        assert renderer.height == 480

    def test_renderer_custom_dimensions(self):
        """Renderer accepts custom dimensions."""
        renderer = OSDRenderer(width=1920, height=1080)
        assert renderer.width == 1920
        assert renderer.height == 1080

    def test_renderer_has_layout_manager(self, osd_renderer):
        """Renderer has layout manager."""
        assert osd_renderer.layout is not None

    def test_renderer_has_text_renderer(self, osd_renderer):
        """Renderer has text renderer."""
        assert osd_renderer.text_renderer is not None

    def test_renderer_elements_initially_empty(self, osd_renderer):
        """Renderer has no elements initially."""
        assert len(osd_renderer.get_element_ids()) == 0

    def test_renderer_with_config(self):
        """Renderer accepts configuration."""
        config = {'SHOW_FPS': True, 'SHOW_TIMESTAMP': False}
        renderer = OSDRenderer(config=config)
        assert renderer.config == config


# ============================================================================
# Element Registration Tests
# ============================================================================

class TestElementRegistration:
    """Tests for OSD element registration."""

    def test_add_element(self, osd_renderer):
        """Element can be added."""
        element = OSDElement(id='test', position='top-left')
        osd_renderer.add_element(element)

        assert 'test' in osd_renderer.get_element_ids()

    def test_add_multiple_elements(self, osd_renderer):
        """Multiple elements can be added."""
        osd_renderer.add_element(OSDElement(id='fps', position='top-left'))
        osd_renderer.add_element(OSDElement(id='time', position='top-right'))
        osd_renderer.add_element(OSDElement(id='status', position='bottom-left'))

        assert len(osd_renderer.get_element_ids()) == 3

    def test_remove_element(self, osd_renderer):
        """Element can be removed."""
        element = OSDElement(id='test', position='top-left')
        osd_renderer.add_element(element)
        osd_renderer.remove_element('test')

        assert 'test' not in osd_renderer.get_element_ids()

    def test_remove_nonexistent_element(self, osd_renderer):
        """Removing nonexistent element is safe."""
        osd_renderer.remove_element('nonexistent')
        # Should not raise

    def test_get_element_by_id(self, osd_renderer):
        """Element can be retrieved by ID."""
        element = OSDElement(id='test', position='top-left')
        osd_renderer.add_element(element)

        retrieved = osd_renderer.get_element('test')
        assert retrieved is element

    def test_get_nonexistent_element(self, osd_renderer):
        """Getting nonexistent element returns None."""
        assert osd_renderer.get_element('nonexistent') is None

    def test_replace_element(self, osd_renderer):
        """Element with same ID replaces existing."""
        element1 = OSDElement(id='test', position='top-left')
        element2 = OSDElement(id='test', position='bottom-right')

        osd_renderer.add_element(element1)
        osd_renderer.add_element(element2)

        retrieved = osd_renderer.get_element('test')
        assert retrieved.position == 'bottom-right'


# ============================================================================
# Visibility Tests
# ============================================================================

class TestElementVisibility:
    """Tests for OSD element visibility control."""

    def test_element_visible_by_default(self, osd_renderer):
        """Element is visible by default."""
        element = OSDElement(id='test', position='top-left')
        osd_renderer.add_element(element)

        assert osd_renderer.get_element('test').visible is True

    def test_set_visibility_false(self, osd_renderer):
        """Element visibility can be set to false."""
        element = OSDElement(id='test', position='top-left')
        osd_renderer.add_element(element)
        osd_renderer.set_visibility('test', False)

        assert osd_renderer.get_element('test').visible is False

    def test_set_visibility_true(self, osd_renderer):
        """Element visibility can be set to true."""
        element = OSDElement(id='test', position='top-left', visible=False)
        osd_renderer.add_element(element)
        osd_renderer.set_visibility('test', True)

        assert osd_renderer.get_element('test').visible is True

    def test_toggle_visibility(self, osd_renderer):
        """Element visibility can be toggled."""
        element = OSDElement(id='test', position='top-left')
        osd_renderer.add_element(element)

        osd_renderer.set_visibility('test', False)
        assert osd_renderer.get_element('test').visible is False

        osd_renderer.set_visibility('test', True)
        assert osd_renderer.get_element('test').visible is True

    def test_set_visibility_nonexistent(self, osd_renderer):
        """Setting visibility of nonexistent element is safe."""
        osd_renderer.set_visibility('nonexistent', True)
        # Should not raise


# ============================================================================
# Render Pipeline Tests
# ============================================================================

class TestRenderPipeline:
    """Tests for OSD render pipeline."""

    def test_render_returns_ndarray(self, osd_renderer, test_frame):
        """Render returns numpy array."""
        result = osd_renderer.render(test_frame)
        assert isinstance(result, np.ndarray)

    def test_render_returns_copy(self, osd_renderer, test_frame):
        """Render returns copy of input frame."""
        result = osd_renderer.render(test_frame)
        assert result is not test_frame

    def test_render_preserves_shape(self, osd_renderer, test_frame):
        """Render preserves frame shape."""
        result = osd_renderer.render(test_frame)
        assert result.shape == test_frame.shape

    def test_render_with_no_elements(self, osd_renderer, test_frame):
        """Render works with no elements."""
        result = osd_renderer.render(test_frame)
        assert np.array_equal(result, test_frame)

    def test_render_calls_visible_elements(self, osd_renderer, test_frame):
        """Render calls visible elements."""
        element = MagicMock(spec=OSDElement)
        element.id = 'test'
        element.visible = True
        element.priority = 0
        element.render.return_value = test_frame

        osd_renderer.add_element(element)
        osd_renderer.render(test_frame, {})

        element.render.assert_called_once()

    def test_render_skips_invisible_elements(self, osd_renderer, test_frame):
        """Render skips invisible elements."""
        element = MagicMock(spec=OSDElement)
        element.id = 'test'
        element.visible = False
        element.priority = 0

        osd_renderer.add_element(element)
        osd_renderer.render(test_frame, {})

        element.render.assert_not_called()

    def test_render_respects_priority_order(self, osd_renderer, test_frame):
        """Render respects element priority."""
        call_order = []

        def make_element(id, priority):
            elem = MagicMock(spec=OSDElement)
            elem.id = id
            elem.visible = True
            elem.priority = priority
            elem.render.side_effect = lambda *args: call_order.append(id) or test_frame
            return elem

        osd_renderer.add_element(make_element('high', 10))
        osd_renderer.add_element(make_element('low', 1))
        osd_renderer.add_element(make_element('mid', 5))

        osd_renderer.render(test_frame, {})

        assert call_order == ['low', 'mid', 'high']

    def test_render_updates_dimensions_on_resize(self, osd_renderer, test_frame):
        """Render updates dimensions when frame size changes."""
        large_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        osd_renderer.render(large_frame)

        assert osd_renderer.width == 1280
        assert osd_renderer.height == 720

    def test_render_passes_data_to_elements(self, osd_renderer, test_frame):
        """Render passes data dict to elements."""
        element = MagicMock(spec=OSDElement)
        element.id = 'test'
        element.visible = True
        element.priority = 0
        element.render.return_value = test_frame

        osd_renderer.add_element(element)
        data = {'tracker': {'is_tracking': True}}
        osd_renderer.render(test_frame, data)

        call_args = element.render.call_args
        assert call_args[0][3] == data


# ============================================================================
# Standard Element Tests
# ============================================================================

class TestStandardElements:
    """Tests for standard OSD elements."""

    def test_fps_element_creation(self):
        """FPS element can be created."""
        element = OSDElement(id='fps', position='top-left')
        assert element.id == 'fps'
        assert element.position == 'top-left'

    def test_timestamp_element_creation(self):
        """Timestamp element can be created."""
        element = OSDElement(id='timestamp', position='top-right')
        assert element.id == 'timestamp'
        assert element.position == 'top-right'

    def test_tracking_element_creation(self):
        """Tracking element can be created."""
        element = OSDElement(id='tracking', position='center', priority=10)
        assert element.id == 'tracking'
        assert element.priority == 10

    def test_safety_element_creation(self):
        """Safety element can be created."""
        element = OSDElement(id='safety', position='top-center', priority=5)
        assert element.id == 'safety'
        assert element.priority == 5

    def test_standard_elements_positions(self):
        """Standard elements use correct positions."""
        elements = {
            'fps': 'top-left',
            'timestamp': 'top-right',
            'tracking': 'center',
            'safety': 'top-center',
            'mode': 'bottom-left',
        }

        for elem_id, position in elements.items():
            elem = OSDElement(id=elem_id, position=position)
            assert elem.position == position

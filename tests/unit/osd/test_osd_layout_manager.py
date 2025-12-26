# tests/unit/osd/test_osd_layout_manager.py
"""
Unit tests for OSD layout manager functionality.

Tests cover:
- Anchor position calculation
- Dimension updates
- Stacked positioning
- Grid positioning
- Safe zone calculation
- Frame clamping
"""

import pytest
import numpy as np
from typing import Tuple, Dict
from dataclasses import dataclass

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.osd]


# ============================================================================
# Region Dataclass
# ============================================================================

@dataclass
class Region:
    """Screen region with bounds."""
    x: int
    y: int
    width: int
    height: int


# ============================================================================
# Layout Manager Implementation
# ============================================================================

class LayoutManager:
    """Layout manager for testing."""

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        margin: int = 10,
        padding: int = 5
    ):
        self.width = width
        self.height = height
        self.margin = margin
        self.padding = padding

        self._occupied: Dict[str, Region] = {}
        self._anchors = self._calculate_anchors()

    def _calculate_anchors(self) -> Dict[str, Tuple[int, int]]:
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
        self.width = width
        self.height = height
        self._anchors = self._calculate_anchors()

    def get_anchor_position(self, anchor: str) -> Tuple[int, int]:
        return self._anchors.get(anchor, (0, 0))

    def get_position(
        self,
        anchor: str,
        offset: Tuple[int, int] = (0, 0)
    ) -> Tuple[int, int]:
        x, y = self._anchors.get(anchor, (0, 0))
        return (x + offset[0], y + offset[1])

    def register_element(
        self,
        element_id: str,
        anchor: str,
        width: int,
        height: int
    ) -> Region:
        x, y = self._anchors.get(anchor, (0, 0))

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
        if element_id in self._occupied:
            del self._occupied[element_id]

    def get_safe_zone(self) -> Region:
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
        x = max(self.margin, min(x, self.width - width - self.margin))
        y = max(self.margin, min(y, self.height - height - self.margin))
        return (x, y)

    def get_all_anchors(self) -> Dict[str, Tuple[int, int]]:
        return self._anchors.copy()


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def layout():
    """Create layout manager instance."""
    return LayoutManager(width=640, height=480)


# ============================================================================
# Anchor Position Tests
# ============================================================================

class TestAnchorPositions:
    """Tests for anchor position calculation."""

    def test_top_left_anchor(self, layout):
        """Top-left anchor position is correct."""
        x, y = layout.get_anchor_position('top-left')
        assert x == 10  # margin
        assert y == 25  # margin + 15

    def test_top_right_anchor(self, layout):
        """Top-right anchor position is correct."""
        x, y = layout.get_anchor_position('top-right')
        assert x == 630  # width - margin
        assert y == 25

    def test_top_center_anchor(self, layout):
        """Top-center anchor position is correct."""
        x, y = layout.get_anchor_position('top-center')
        assert x == 320  # width / 2
        assert y == 25

    def test_center_anchor(self, layout):
        """Center anchor position is correct."""
        x, y = layout.get_anchor_position('center')
        assert x == 320  # width / 2
        assert y == 240  # height / 2

    def test_bottom_left_anchor(self, layout):
        """Bottom-left anchor position is correct."""
        x, y = layout.get_anchor_position('bottom-left')
        assert x == 10
        assert y == 470  # height - margin

    def test_bottom_right_anchor(self, layout):
        """Bottom-right anchor position is correct."""
        x, y = layout.get_anchor_position('bottom-right')
        assert x == 630
        assert y == 470

    def test_unknown_anchor_returns_zero(self, layout):
        """Unknown anchor returns (0, 0)."""
        x, y = layout.get_anchor_position('unknown')
        assert x == 0
        assert y == 0

    def test_get_all_anchors(self, layout):
        """Get all anchor positions."""
        anchors = layout.get_all_anchors()
        assert len(anchors) == 9
        assert 'top-left' in anchors
        assert 'center' in anchors


# ============================================================================
# Dimension Update Tests
# ============================================================================

class TestDimensionUpdates:
    """Tests for dimension updates."""

    def test_update_dimensions(self, layout):
        """Dimensions are updated correctly."""
        layout.update_dimensions(1920, 1080)
        assert layout.width == 1920
        assert layout.height == 1080

    def test_anchors_recalculated_on_update(self, layout):
        """Anchors are recalculated on dimension change."""
        old_center = layout.get_anchor_position('center')
        layout.update_dimensions(1920, 1080)
        new_center = layout.get_anchor_position('center')

        assert old_center != new_center
        assert new_center == (960, 540)

    def test_top_right_updates_with_width(self, layout):
        """Top-right anchor updates with width change."""
        layout.update_dimensions(800, 600)
        x, y = layout.get_anchor_position('top-right')
        assert x == 790  # 800 - 10

    def test_bottom_updates_with_height(self, layout):
        """Bottom anchor updates with height change."""
        layout.update_dimensions(640, 720)
        _, y = layout.get_anchor_position('bottom-left')
        assert y == 710  # 720 - 10


# ============================================================================
# Position with Offset Tests
# ============================================================================

class TestPositionWithOffset:
    """Tests for position with offset."""

    def test_position_with_zero_offset(self, layout):
        """Position with zero offset equals anchor."""
        anchor = layout.get_anchor_position('top-left')
        position = layout.get_position('top-left', (0, 0))
        assert anchor == position

    def test_position_with_positive_offset(self, layout):
        """Position with positive offset moves right/down."""
        x, y = layout.get_position('top-left', (10, 20))
        assert x == 20  # 10 + 10
        assert y == 45  # 25 + 20

    def test_position_with_negative_offset(self, layout):
        """Position with negative offset moves left/up."""
        x, y = layout.get_position('center', (-50, -50))
        assert x == 270  # 320 - 50
        assert y == 190  # 240 - 50


# ============================================================================
# Element Registration Tests
# ============================================================================

class TestElementRegistration:
    """Tests for element registration."""

    def test_register_element_returns_region(self, layout):
        """Register element returns Region."""
        region = layout.register_element('test', 'top-left', 100, 50)
        assert isinstance(region, Region)

    def test_register_element_top_left(self, layout):
        """Element registered at top-left."""
        region = layout.register_element('test', 'top-left', 100, 50)
        assert region.x == 10
        assert region.y == 25

    def test_register_element_top_right_adjusts_x(self, layout):
        """Element registered at top-right adjusts x."""
        region = layout.register_element('test', 'top-right', 100, 50)
        # x should be adjusted left by width
        assert region.x == 530  # 630 - 100

    def test_register_element_center_adjusts_both(self, layout):
        """Element registered at center adjusts x and y."""
        region = layout.register_element('test', 'center', 100, 50)
        # Both x and y should be adjusted
        assert region.x == 270  # 320 - 50
        assert region.y == 215  # 240 - 25

    def test_unregister_element(self, layout):
        """Element can be unregistered."""
        layout.register_element('test', 'top-left', 100, 50)
        layout.unregister_element('test')
        assert 'test' not in layout._occupied


# ============================================================================
# Stacked Position Tests
# ============================================================================

class TestStackedPositions:
    """Tests for stacked element positioning."""

    def test_stacked_position_first_item(self, layout):
        """First stacked item at anchor position."""
        x, y = layout.get_stacked_position('top-left', 0, 20)
        anchor_x, anchor_y = layout.get_anchor_position('top-left')
        assert x == anchor_x
        assert y == anchor_y

    def test_stacked_position_top_moves_down(self, layout):
        """Top anchor items stack downward."""
        y0 = layout.get_stacked_position('top-left', 0, 20)[1]
        y1 = layout.get_stacked_position('top-left', 1, 20)[1]
        y2 = layout.get_stacked_position('top-left', 2, 20)[1]

        assert y1 > y0
        assert y2 > y1

    def test_stacked_position_bottom_moves_up(self, layout):
        """Bottom anchor items stack upward."""
        y0 = layout.get_stacked_position('bottom-left', 0, 20)[1]
        y1 = layout.get_stacked_position('bottom-left', 1, 20)[1]
        y2 = layout.get_stacked_position('bottom-left', 2, 20)[1]

        assert y1 < y0
        assert y2 < y1

    def test_stacked_position_with_spacing(self, layout):
        """Stacked items respect spacing."""
        y0 = layout.get_stacked_position('top-left', 0, 20, spacing=10)[1]
        y1 = layout.get_stacked_position('top-left', 1, 20, spacing=10)[1]

        assert y1 - y0 == 30  # 20 (height) + 10 (spacing)


# ============================================================================
# Grid Position Tests
# ============================================================================

class TestGridPositions:
    """Tests for grid-based positioning."""

    def test_grid_position_origin(self, layout):
        """Grid position at origin."""
        x, y = layout.get_grid_position(0, 0, 50, 50)
        anchor_x, anchor_y = layout.get_anchor_position('top-left')
        assert x == anchor_x
        assert y == anchor_y

    def test_grid_position_column(self, layout):
        """Grid position moves by column."""
        x0, _ = layout.get_grid_position(0, 0, 50, 50)
        x1, _ = layout.get_grid_position(0, 1, 50, 50)
        x2, _ = layout.get_grid_position(0, 2, 50, 50)

        assert x1 - x0 == 50
        assert x2 - x1 == 50

    def test_grid_position_row(self, layout):
        """Grid position moves by row."""
        _, y0 = layout.get_grid_position(0, 0, 50, 50)
        _, y1 = layout.get_grid_position(1, 0, 50, 50)
        _, y2 = layout.get_grid_position(2, 0, 50, 50)

        assert y1 - y0 == 50
        assert y2 - y1 == 50

    def test_grid_with_different_cell_sizes(self, layout):
        """Grid works with different cell sizes."""
        x, y = layout.get_grid_position(2, 3, 100, 75)
        anchor_x, anchor_y = layout.get_anchor_position('top-left')

        assert x == anchor_x + 3 * 100
        assert y == anchor_y + 2 * 75


# ============================================================================
# Safe Zone Tests
# ============================================================================

class TestSafeZone:
    """Tests for safe zone calculation."""

    def test_safe_zone_returns_region(self, layout):
        """Safe zone returns Region."""
        zone = layout.get_safe_zone()
        assert isinstance(zone, Region)

    def test_safe_zone_respects_margin(self, layout):
        """Safe zone respects margin."""
        zone = layout.get_safe_zone()
        assert zone.x == layout.margin
        assert zone.y == layout.margin

    def test_safe_zone_width(self, layout):
        """Safe zone width excludes margins."""
        zone = layout.get_safe_zone()
        assert zone.width == layout.width - 2 * layout.margin

    def test_safe_zone_height(self, layout):
        """Safe zone height excludes margins."""
        zone = layout.get_safe_zone()
        assert zone.height == layout.height - 2 * layout.margin


# ============================================================================
# Frame Clamping Tests
# ============================================================================

class TestFrameClamping:
    """Tests for clamping positions to frame bounds."""

    def test_clamp_position_inside_frame(self, layout):
        """Position inside frame is unchanged."""
        x, y = layout.clamp_to_frame(100, 100)
        assert x == 100
        assert y == 100

    def test_clamp_position_left_edge(self, layout):
        """Position clamped to left edge."""
        x, y = layout.clamp_to_frame(-50, 100)
        assert x == layout.margin

    def test_clamp_position_right_edge(self, layout):
        """Position clamped to right edge."""
        x, y = layout.clamp_to_frame(700, 100, width=50)
        assert x == layout.width - 50 - layout.margin

    def test_clamp_position_top_edge(self, layout):
        """Position clamped to top edge."""
        x, y = layout.clamp_to_frame(100, -50)
        assert y == layout.margin

    def test_clamp_position_bottom_edge(self, layout):
        """Position clamped to bottom edge."""
        x, y = layout.clamp_to_frame(100, 500, height=50)
        assert y == layout.height - 50 - layout.margin

    def test_clamp_with_element_size(self, layout):
        """Clamping considers element size."""
        x, y = layout.clamp_to_frame(620, 460, width=100, height=100)
        assert x == layout.width - 100 - layout.margin
        assert y == layout.height - 100 - layout.margin

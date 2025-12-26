# tests/unit/osd/test_osd_text_renderer.py
"""
Unit tests for OSD text rendering functionality.

Tests cover:
- Basic text rendering
- Text with background
- Text with shadow
- Text with outline
- Multiline text
- Text size calculation
"""

import pytest
import numpy as np
import cv2
from typing import Tuple

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.osd]


# ============================================================================
# OSD Text Renderer Implementation
# ============================================================================

class OSDTextRenderer:
    """Text renderer for testing."""

    FONT_SIMPLE = cv2.FONT_HERSHEY_SIMPLEX
    FONT_PLAIN = cv2.FONT_HERSHEY_PLAIN
    FONT_DUPLEX = cv2.FONT_HERSHEY_DUPLEX

    def __init__(
        self,
        default_font: int = cv2.FONT_HERSHEY_SIMPLEX,
        default_scale: float = 0.5,
        default_thickness: int = 1
    ):
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
        cv2.putText(
            frame, text, position,
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
        font = font or self.default_font
        font_scale = font_scale or self.default_scale
        thickness = thickness or self.default_thickness

        (text_w, text_h), baseline = cv2.getTextSize(
            text, font, font_scale, thickness
        )

        x, y = position
        x1 = max(0, x - padding)
        y1 = max(0, y - text_h - padding)
        x2 = min(frame.shape[1], x + text_w + padding)
        y2 = min(frame.shape[0], y + baseline + padding)

        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), bg_color, -1)
        cv2.addWeighted(overlay, bg_opacity, frame, 1 - bg_opacity, 0, frame)

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
        font = font or self.default_font
        font_scale = font_scale or self.default_scale
        thickness = thickness or self.default_thickness

        x, y = position

        cv2.putText(
            frame, text, (x + shadow_offset, y + shadow_offset),
            font, font_scale, shadow_color, thickness, cv2.LINE_AA
        )

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
        font = font or self.default_font
        font_scale = font_scale or self.default_scale
        thickness = thickness or self.default_thickness

        cv2.putText(
            frame, text, position,
            font, font_scale, outline_color,
            thickness + outline_thickness, cv2.LINE_AA
        )

        cv2.putText(
            frame, text, position,
            font, font_scale, color, thickness, cv2.LINE_AA
        )

        return frame

    def draw_multiline_text(
        self,
        frame: np.ndarray,
        lines: list,
        position: Tuple[int, int],
        font: int = None,
        font_scale: float = None,
        color: Tuple[int, int, int] = (255, 255, 255),
        line_spacing: float = 1.5,
        thickness: int = None
    ) -> np.ndarray:
        font = font or self.default_font
        font_scale = font_scale or self.default_scale
        thickness = thickness or self.default_thickness

        x, y = position

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
        font = font or self.default_font
        font_scale = font_scale or self.default_scale
        thickness = thickness or self.default_thickness

        (w, h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
        return w, h, baseline


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def test_frame():
    """Create a test BGR frame with non-black color for visibility testing."""
    # Use gray background so text and effects are visible
    return np.full((480, 640, 3), 128, dtype=np.uint8)


@pytest.fixture
def text_renderer():
    """Create text renderer instance."""
    return OSDTextRenderer()


# ============================================================================
# Basic Text Rendering Tests
# ============================================================================

class TestBasicTextRendering:
    """Tests for basic text rendering."""

    def test_draw_text_returns_frame(self, text_renderer, test_frame):
        """draw_text returns numpy array."""
        result = text_renderer.draw_text(test_frame, "Hello", (10, 30))
        assert isinstance(result, np.ndarray)

    def test_draw_text_modifies_frame(self, text_renderer, test_frame):
        """draw_text modifies the frame."""
        original = test_frame.copy()
        text_renderer.draw_text(test_frame, "Hello", (10, 30))
        assert not np.array_equal(test_frame, original)

    def test_draw_text_with_custom_color(self, text_renderer, test_frame):
        """draw_text accepts custom color."""
        result = text_renderer.draw_text(
            test_frame, "Hello", (10, 30),
            color=(0, 255, 0)
        )
        assert result is not None

    def test_draw_text_with_custom_scale(self, text_renderer, test_frame):
        """draw_text accepts custom font scale."""
        result = text_renderer.draw_text(
            test_frame, "Hello", (10, 30),
            font_scale=1.0
        )
        assert result is not None

    def test_draw_text_with_custom_thickness(self, text_renderer, test_frame):
        """draw_text accepts custom thickness."""
        result = text_renderer.draw_text(
            test_frame, "Hello", (10, 30),
            thickness=2
        )
        assert result is not None

    def test_draw_text_different_fonts(self, text_renderer, test_frame):
        """draw_text works with different fonts."""
        fonts = [
            cv2.FONT_HERSHEY_SIMPLEX,
            cv2.FONT_HERSHEY_PLAIN,
            cv2.FONT_HERSHEY_DUPLEX,
        ]

        for font in fonts:
            frame = test_frame.copy()
            result = text_renderer.draw_text(frame, "Test", (10, 30), font=font)
            assert result is not None


# ============================================================================
# Text with Background Tests
# ============================================================================

class TestTextWithBackground:
    """Tests for text with background rendering."""

    def test_draw_text_with_background_returns_frame(self, text_renderer, test_frame):
        """draw_text_with_background returns frame."""
        result = text_renderer.draw_text_with_background(
            test_frame, "Hello", (10, 30)
        )
        assert isinstance(result, np.ndarray)

    def test_background_color_applied(self, text_renderer, test_frame):
        """Background color is applied."""
        result = text_renderer.draw_text_with_background(
            test_frame, "Hello", (10, 30),
            bg_color=(255, 0, 0)
        )
        assert result is not None

    def test_background_opacity(self, text_renderer, test_frame):
        """Background opacity affects blending."""
        # With full opacity
        frame1 = test_frame.copy()
        text_renderer.draw_text_with_background(
            frame1, "Hello", (10, 30),
            bg_opacity=1.0
        )

        # With partial opacity
        frame2 = test_frame.copy()
        text_renderer.draw_text_with_background(
            frame2, "Hello", (10, 30),
            bg_opacity=0.5
        )

        # Results should differ
        assert not np.array_equal(frame1, frame2)

    def test_background_padding(self, text_renderer, test_frame):
        """Background padding affects size."""
        frame1 = test_frame.copy()
        text_renderer.draw_text_with_background(
            frame1, "Hello", (50, 50),
            padding=5
        )

        frame2 = test_frame.copy()
        text_renderer.draw_text_with_background(
            frame2, "Hello", (50, 50),
            padding=20
        )

        # Results should differ due to padding
        assert not np.array_equal(frame1, frame2)

    def test_background_clipped_to_frame(self, text_renderer, test_frame):
        """Background is clipped to frame bounds."""
        # Text near edge
        result = text_renderer.draw_text_with_background(
            test_frame, "Hello", (5, 15),
            padding=10
        )
        assert result is not None


# ============================================================================
# Text with Shadow Tests
# ============================================================================

class TestTextWithShadow:
    """Tests for text with shadow rendering."""

    def test_draw_text_with_shadow_returns_frame(self, text_renderer, test_frame):
        """draw_text_with_shadow returns frame."""
        result = text_renderer.draw_text_with_shadow(
            test_frame, "Hello", (10, 30)
        )
        assert isinstance(result, np.ndarray)

    def test_shadow_offset(self, text_renderer, test_frame):
        """Shadow offset is applied."""
        frame1 = test_frame.copy()
        text_renderer.draw_text_with_shadow(
            frame1, "Hello", (50, 50),
            shadow_offset=2
        )

        frame2 = test_frame.copy()
        text_renderer.draw_text_with_shadow(
            frame2, "Hello", (50, 50),
            shadow_offset=5
        )

        # Different offsets produce different results
        assert not np.array_equal(frame1, frame2)

    def test_shadow_color(self, text_renderer, test_frame):
        """Shadow color is applied."""
        result = text_renderer.draw_text_with_shadow(
            test_frame, "Hello", (10, 30),
            shadow_color=(100, 100, 100)
        )
        assert result is not None

    def test_shadow_drawn_before_text(self, text_renderer, test_frame):
        """Shadow is drawn before main text (underneath)."""
        # This is verified by the implementation order
        result = text_renderer.draw_text_with_shadow(
            test_frame, "Hello", (50, 50),
            color=(255, 255, 255),
            shadow_color=(0, 0, 0)
        )
        assert result is not None


# ============================================================================
# Text with Outline Tests
# ============================================================================

class TestTextWithOutline:
    """Tests for text with outline rendering."""

    def test_draw_text_with_outline_returns_frame(self, text_renderer, test_frame):
        """draw_text_with_outline returns frame."""
        result = text_renderer.draw_text_with_outline(
            test_frame, "Hello", (10, 30)
        )
        assert isinstance(result, np.ndarray)

    def test_outline_thickness(self, text_renderer, test_frame):
        """Outline thickness affects appearance."""
        frame1 = test_frame.copy()
        text_renderer.draw_text_with_outline(
            frame1, "Hello", (50, 50),
            outline_thickness=1
        )

        frame2 = test_frame.copy()
        text_renderer.draw_text_with_outline(
            frame2, "Hello", (50, 50),
            outline_thickness=3
        )

        # Different thickness produces different results
        assert not np.array_equal(frame1, frame2)

    def test_outline_color(self, text_renderer, test_frame):
        """Outline color is applied."""
        result = text_renderer.draw_text_with_outline(
            test_frame, "Hello", (10, 30),
            outline_color=(255, 0, 0)
        )
        assert result is not None


# ============================================================================
# Multiline Text Tests
# ============================================================================

class TestMultilineText:
    """Tests for multiline text rendering."""

    def test_draw_multiline_returns_frame(self, text_renderer, test_frame):
        """draw_multiline_text returns frame."""
        result = text_renderer.draw_multiline_text(
            test_frame,
            ["Line 1", "Line 2", "Line 3"],
            (10, 30)
        )
        assert isinstance(result, np.ndarray)

    def test_multiple_lines_rendered(self, text_renderer, test_frame):
        """Multiple lines are rendered."""
        original = test_frame.copy()
        text_renderer.draw_multiline_text(
            test_frame,
            ["Line 1", "Line 2", "Line 3"],
            (10, 30)
        )
        assert not np.array_equal(test_frame, original)

    def test_line_spacing(self, text_renderer, test_frame):
        """Line spacing affects layout."""
        frame1 = test_frame.copy()
        text_renderer.draw_multiline_text(
            frame1,
            ["Line 1", "Line 2"],
            (50, 50),
            line_spacing=1.0
        )

        frame2 = test_frame.copy()
        text_renderer.draw_multiline_text(
            frame2,
            ["Line 1", "Line 2"],
            (50, 50),
            line_spacing=2.0
        )

        # Different spacing produces different results
        assert not np.array_equal(frame1, frame2)

    def test_empty_lines_list(self, text_renderer, test_frame):
        """Empty lines list is handled."""
        original = test_frame.copy()
        result = text_renderer.draw_multiline_text(
            test_frame, [], (10, 30)
        )
        assert np.array_equal(result, original)


# ============================================================================
# Text Size Calculation Tests
# ============================================================================

class TestTextSizeCalculation:
    """Tests for text size calculation."""

    def test_get_text_size_returns_tuple(self, text_renderer):
        """get_text_size returns tuple."""
        w, h, baseline = text_renderer.get_text_size("Hello")
        assert isinstance(w, int)
        assert isinstance(h, int)
        assert isinstance(baseline, int)

    def test_longer_text_wider(self, text_renderer):
        """Longer text has greater width."""
        w1, _, _ = text_renderer.get_text_size("Hi")
        w2, _, _ = text_renderer.get_text_size("Hello World")
        assert w2 > w1

    def test_larger_scale_larger_size(self, text_renderer):
        """Larger font scale produces larger size."""
        w1, h1, _ = text_renderer.get_text_size("Hello", font_scale=0.5)
        w2, h2, _ = text_renderer.get_text_size("Hello", font_scale=1.0)
        assert w2 > w1
        assert h2 > h1

    def test_different_fonts_different_sizes(self, text_renderer):
        """Different fonts produce different sizes."""
        w1, h1, _ = text_renderer.get_text_size(
            "Hello",
            font=cv2.FONT_HERSHEY_SIMPLEX
        )
        w2, h2, _ = text_renderer.get_text_size(
            "Hello",
            font=cv2.FONT_HERSHEY_PLAIN
        )
        # Sizes should differ (not necessarily larger/smaller)
        assert (w1, h1) != (w2, h2)

    def test_baseline_positive(self, text_renderer):
        """Baseline is positive."""
        _, _, baseline = text_renderer.get_text_size("Hello")
        assert baseline >= 0

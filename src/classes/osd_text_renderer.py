"""
OSD Text Renderer Module
High-quality text rendering for professional drone OSD using PIL/Pillow.
Provides resolution-independent, anti-aliased text with professional effects.

Features:
- TrueType font support with fallback to OpenCV fonts
- Resolution-independent scaling
- Professional text effects (shadows, outlines, background plates)
- 4-8x better quality than cv2.putText()
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import logging
from pathlib import Path
from typing import Tuple, Optional, Union
from enum import Enum

logger = logging.getLogger(__name__)


class TextStyle(Enum):
    """Text rendering styles for OSD elements."""
    PLAIN = "plain"           # Simple text
    OUTLINED = "outlined"     # Text with black outline
    SHADOWED = "shadowed"     # Text with drop shadow
    PLATE = "plate"           # Text with background plate


class OSDTextRenderer:
    """
    High-quality text renderer for OSD overlays using PIL/Pillow.

    This class provides professional-grade text rendering that significantly
    improves upon OpenCV's basic putText() function.
    """

    def __init__(self, frame_width: int, frame_height: int, base_font_scale: float = 1.0):
        """
        Initialize the text renderer.

        Args:
            frame_width: Width of the video frame in pixels
            frame_height: Height of the video frame in pixels
            base_font_scale: Global font size multiplier (default: 1.0)
        """
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.base_font_scale = base_font_scale

        # Calculate base font size based on frame height
        # Professional sizing: 1/20th of frame height (~24px @ 480p, ~54px @ 1080p)
        self.base_font_size = int((frame_height / 20) * base_font_scale)

        # Font cache to avoid reloading fonts
        self.font_cache = {}

        # Load available fonts
        self.font_paths = self._discover_fonts()
        self.default_font_name = self._select_default_font()

        logger.info(f"OSDTextRenderer initialized: {frame_width}x{frame_height}, base_size={self.base_font_size}px")

    def _discover_fonts(self) -> dict:
        """
        Discover available TrueType fonts.

        Returns:
            Dictionary mapping font names to file paths
        """
        font_paths = {}

        # Check custom fonts directory (FIRST - takes priority over system fonts)
        custom_fonts_dir = Path("resources/fonts")
        if custom_fonts_dir.exists():
            for font_file in custom_fonts_dir.glob("*.ttf"):
                # Strip common suffixes to normalize font names
                font_name = font_file.stem.lower().replace("-regular", "").replace("_regular", "")
                font_paths[font_name] = str(font_file)
                logger.debug(f"Found custom font: {font_name} -> {font_file}")

        # Common system font paths
        system_font_locations = [
            Path("/usr/share/fonts/truetype"),  # Linux
            Path("/System/Library/Fonts"),      # macOS
            Path("C:/Windows/Fonts"),           # Windows
        ]

        # Common professional fonts for drones/aviation
        target_fonts = [
            "RobotoMono-Regular.ttf",
            "IBMPlexMono-Regular.ttf",
            "DejaVuSansMono.ttf",
            "LiberationMono-Regular.ttf",
            "CourierNew.ttf",
            "Consolas.ttf",
        ]

        for location in system_font_locations:
            if not location.exists():
                continue

            for target_font in target_fonts:
                for font_file in location.rglob(target_font):
                    font_name = font_file.stem.lower().replace("-regular", "")
                    if font_name not in font_paths:
                        font_paths[font_name] = str(font_file)
                    break  # Take first match

        logger.debug(f"Discovered {len(font_paths)} TrueType fonts")
        return font_paths

    def _select_default_font(self) -> str:
        """
        Select the best available default font.

        Returns:
            Font name to use as default
        """
        # Priority order for default font (prefer RobotoMono - most professional)
        preferred_fonts = [
            "robotomono",      # FIRST choice - most professional
            "roboto-mono",     # Alternative name
            "ibmplexmono",     # Second choice
            "dejavusansmono",
            "liberationmono",
            "consolas",
            "couriernew",
        ]

        for font_name in preferred_fonts:
            if font_name in self.font_paths:
                logger.info(f"Selected default font: {font_name}")
                return font_name

        # Fallback to any available font
        if self.font_paths:
            default = list(self.font_paths.keys())[0]
            logger.warning(f"Using fallback font: {default}")
            return default

        logger.warning("No TrueType fonts found, will use OpenCV fallback")
        return None

    def _get_font(self, font_size: int, font_name: Optional[str] = None) -> Optional[ImageFont.FreeTypeFont]:
        """
        Get or create a PIL font object.

        Args:
            font_size: Font size in pixels
            font_name: Font name (uses default if None)

        Returns:
            PIL Font object or None if unavailable
        """
        if font_name is None:
            font_name = self.default_font_name

        if font_name is None:
            return None

        # Check cache
        cache_key = f"{font_name}_{font_size}"
        if cache_key in self.font_cache:
            return self.font_cache[cache_key]

        # Load font
        try:
            font_path = self.font_paths.get(font_name)
            if font_path:
                font = ImageFont.truetype(font_path, font_size)
                self.font_cache[cache_key] = font
                return font
        except Exception as e:
            logger.error(f"Failed to load font {font_name}: {e}")

        return None

    def calculate_font_size(self, scale: float = 1.0) -> int:
        """
        Calculate actual font size based on scale factor.

        Args:
            scale: Scale multiplier relative to base size

        Returns:
            Font size in pixels
        """
        return max(int(self.base_font_size * scale), 8)  # Minimum 8px

    def render_text(
        self,
        frame: np.ndarray,
        text: str,
        position: Tuple[int, int],
        color: Tuple[int, int, int] = (220, 220, 220),
        font_scale: float = 1.0,
        style: TextStyle = TextStyle.OUTLINED,
        outline_thickness: int = 2,
        shadow_offset: Tuple[int, int] = (2, 2),
        shadow_opacity: float = 0.7,
        background_opacity: float = 0.6,
        background_padding: Tuple[int, int] = (8, 4),
        font_name: Optional[str] = None
    ) -> np.ndarray:
        """
        Render high-quality text on frame with professional effects.

        Args:
            frame: OpenCV frame (BGR format)
            text: Text to render
            position: (x, y) position in pixels
            color: Text color in BGR format
            font_scale: Font size multiplier
            style: Text rendering style
            outline_thickness: Outline thickness in pixels (for OUTLINED style)
            shadow_offset: (x, y) shadow offset in pixels (for SHADOWED style)
            shadow_opacity: Shadow opacity 0-1 (for SHADOWED style)
            background_opacity: Background plate opacity 0-1 (for PLATE style)
            background_padding: (horizontal, vertical) padding in pixels
            font_name: Font to use (None = default)

        Returns:
            Frame with text rendered
        """
        font_size = self.calculate_font_size(font_scale)
        font = self._get_font(font_size, font_name)

        if font is None:
            # Fallback to OpenCV putText
            return self._render_text_opencv(
                frame, text, position, color, font_scale,
                outline_thickness, shadow_offset, style
            )

        # Use PIL for high-quality rendering
        return self._render_text_pil(
            frame, text, position, color, font, style,
            outline_thickness, shadow_offset, shadow_opacity,
            background_opacity, background_padding
        )

    def _render_text_pil(
        self,
        frame: np.ndarray,
        text: str,
        position: Tuple[int, int],
        color: Tuple[int, int, int],
        font: ImageFont.FreeTypeFont,
        style: TextStyle,
        outline_thickness: int,
        shadow_offset: Tuple[int, int],
        shadow_opacity: float,
        background_opacity: float,
        background_padding: Tuple[int, int]
    ) -> np.ndarray:
        """Render text using PIL with professional effects."""

        # Convert BGR frame to RGB PIL Image
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)

        # Create drawing context
        draw = ImageDraw.Draw(pil_image, 'RGBA')

        # Get text bounding box
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x, y = position

        # Apply style-specific effects
        if style == TextStyle.PLATE:
            # Draw semi-transparent background plate
            plate_color = (20, 20, 20, int(255 * background_opacity))
            plate_box = [
                x - background_padding[0],
                y - background_padding[1],
                x + text_width + background_padding[0],
                y + text_height + background_padding[1]
            ]
            draw.rectangle(plate_box, fill=plate_color)

            # Draw text on plate
            text_color_rgba = (*reversed(color), 255)  # Convert BGR to RGB
            draw.text((x, y), text, font=font, fill=text_color_rgba)

        elif style == TextStyle.SHADOWED:
            # Draw shadow
            shadow_x = x + shadow_offset[0]
            shadow_y = y + shadow_offset[1]
            shadow_color = (0, 0, 0, int(255 * shadow_opacity))
            draw.text((shadow_x, shadow_y), text, font=font, fill=shadow_color)

            # Draw main text
            text_color_rgba = (*reversed(color), 255)
            draw.text((x, y), text, font=font, fill=text_color_rgba)

        elif style == TextStyle.OUTLINED:
            # Draw outline by rendering text multiple times with offset
            outline_color = (0, 0, 0, 255)
            for offset_x in range(-outline_thickness, outline_thickness + 1):
                for offset_y in range(-outline_thickness, outline_thickness + 1):
                    if offset_x != 0 or offset_y != 0:
                        draw.text(
                            (x + offset_x, y + offset_y),
                            text,
                            font=font,
                            fill=outline_color
                        )

            # Draw main text on top
            text_color_rgba = (*reversed(color), 255)
            draw.text((x, y), text, font=font, fill=text_color_rgba)

        else:  # PLAIN
            text_color_rgba = (*reversed(color), 255)
            draw.text((x, y), text, font=font, fill=text_color_rgba)

        # Convert back to OpenCV BGR
        frame_rgb_modified = np.array(pil_image)
        frame_bgr = cv2.cvtColor(frame_rgb_modified, cv2.COLOR_RGB2BGR)

        return frame_bgr

    def _render_text_opencv(
        self,
        frame: np.ndarray,
        text: str,
        position: Tuple[int, int],
        color: Tuple[int, int, int],
        font_scale: float,
        outline_thickness: int,
        shadow_offset: Tuple[int, int],
        style: TextStyle
    ) -> np.ndarray:
        """
        Fallback text rendering using OpenCV (when PIL fonts unavailable).
        """
        font = cv2.FONT_HERSHEY_SIMPLEX
        thickness = max(1, int(2 * font_scale))

        # Apply anti-aliasing
        line_type = cv2.LINE_AA

        x, y = position

        if style == TextStyle.SHADOWED:
            # Draw shadow
            shadow_x = x + shadow_offset[0]
            shadow_y = y + shadow_offset[1]
            cv2.putText(
                frame, text, (shadow_x, shadow_y),
                font, font_scale * 0.6, (0, 0, 0),
                thickness, line_type
            )

        elif style == TextStyle.OUTLINED:
            # Draw outline
            cv2.putText(
                frame, text, (x, y),
                font, font_scale * 0.6, (0, 0, 0),
                thickness + outline_thickness, line_type
            )

        # Draw main text
        cv2.putText(
            frame, text, (x, y),
            font, font_scale * 0.6, color,
            thickness, line_type
        )

        return frame

    def get_text_size(
        self,
        text: str,
        font_scale: float = 1.0,
        font_name: Optional[str] = None
    ) -> Tuple[int, int]:
        """
        Get the size of rendered text.

        Args:
            text: Text to measure
            font_scale: Font size multiplier
            font_name: Font to use (None = default)

        Returns:
            (width, height) tuple in pixels
        """
        font_size = self.calculate_font_size(font_scale)
        font = self._get_font(font_size, font_name)

        if font is None:
            # Fallback to OpenCV
            (width, height), _ = cv2.getTextSize(
                text,
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale * 0.6,
                2
            )
            return (width, height)

        # Use PIL to measure
        dummy_img = Image.new('RGB', (1, 1))
        draw = ImageDraw.Draw(dummy_img)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]

        return (width, height)

    def update_frame_size(self, width: int, height: int):
        """
        Update frame dimensions and recalculate base font size.

        Args:
            width: New frame width
            height: New frame height
        """
        self.frame_width = width
        self.frame_height = height
        self.base_font_size = int((height / 20) * self.base_font_scale)

        # Clear font cache to force regeneration with new sizes
        self.font_cache.clear()

        logger.info(f"Frame size updated: {width}x{height}, base_size={self.base_font_size}px")

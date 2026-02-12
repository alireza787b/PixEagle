"""
OSD Color System
================

Military-grade color palettes with runtime day/night/amber mode switching.

Design references:
- MIL-STD-411F alert hierarchy (WARNING/CAUTION/ADVISORY)
- MIL-STD-3009 NVIS compatibility (night mode)
- P-43 green phosphor (565nm) for day mode fatigue reduction

All colors are BGR tuples for direct OpenCV use.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

BGR = Tuple[int, int, int]


class ColorMode(Enum):
    DAY = "day"
    NIGHT = "night"
    AMBER = "amber"


# Palette definitions — BGR order for OpenCV
_PALETTES: Dict[ColorMode, Dict[str, BGR]] = {
    ColorMode.DAY: {
        "primary":       (0, 220, 100),     # Green phosphor (P-43 inspired)
        "secondary":     (160, 170, 160),    # Neutral grey
        "critical":      (50, 255, 80),      # Bright green — altitude, battery
        "warning":       (0, 180, 255),      # Amber — caution alerts
        "alert":         (60, 60, 255),      # Red — critical alerts
        "accent":        (200, 180, 60),     # Teal — mode labels
        "plate_bg":      (20, 22, 20),       # Near-black label background
        "crosshair":     (0, 200, 80),       # Subdued green
        "muted":         (120, 130, 120),    # Dim grey — tertiary info
    },
    ColorMode.NIGHT: {
        "primary":       (0, 140, 60),       # Dim green — NVIS safe
        "secondary":     (80, 85, 80),       # Very dim grey
        "critical":      (0, 160, 50),       # Dim bright green
        "warning":       (0, 100, 140),      # Dim amber
        "alert":         (40, 40, 160),      # Dim red
        "accent":        (120, 100, 30),     # Dim teal
        "plate_bg":      (10, 12, 10),       # Deep black
        "crosshair":     (0, 120, 40),       # Dim green
        "muted":         (50, 55, 50),       # Barely visible grey
    },
    ColorMode.AMBER: {
        "primary":       (50, 190, 240),     # Amber (A-10/Apache style)
        "secondary":     (100, 140, 160),    # Warm grey
        "critical":      (30, 210, 255),     # Bright amber
        "warning":       (0, 140, 200),      # Deep amber
        "alert":         (60, 60, 255),      # Red
        "accent":        (80, 200, 255),     # Light amber
        "plate_bg":      (15, 18, 22),       # Warm near-black
        "crosshair":     (40, 170, 220),     # Amber crosshair
        "muted":         (60, 100, 120),     # Dim warm grey
    },
}

# All valid color mode strings for API validation
VALID_COLOR_MODES = [m.value for m in ColorMode]


class OSDColorSystem:
    """Runtime color mode manager with palette lookup."""

    def __init__(self, mode: str = "day"):
        try:
            self._mode = ColorMode(mode)
        except ValueError:
            logger.warning(f"Invalid color mode '{mode}', defaulting to 'day'")
            self._mode = ColorMode.DAY

    # -- public interface --

    @property
    def mode(self) -> ColorMode:
        return self._mode

    @property
    def mode_name(self) -> str:
        return self._mode.value

    def set_mode(self, mode: str) -> bool:
        """Switch color mode. Returns True on success."""
        try:
            self._mode = ColorMode(mode)
            logger.info(f"OSD color mode switched to '{mode}'")
            return True
        except ValueError:
            logger.warning(f"Invalid color mode '{mode}'")
            return False

    def get(self, name: str) -> BGR:
        """Get a named color from the current palette."""
        palette = _PALETTES[self._mode]
        if name not in palette:
            logger.warning(f"Unknown color name '{name}', returning secondary")
            return palette["secondary"]
        return palette[name]

    def get_palette(self) -> Dict[str, BGR]:
        """Get the full current palette (copy)."""
        return dict(_PALETTES[self._mode])

    @staticmethod
    def available_modes() -> list:
        return VALID_COLOR_MODES

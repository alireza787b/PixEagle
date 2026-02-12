"""
OSD Mode Manager
================

Runtime OSD mode and color switching without application restart.

Coordinates preset loading, color mode switching, and pipeline cache
invalidation through a single entry point used by API, keyboard, and
dashboard controls.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .osd_colors import OSDColorSystem, VALID_COLOR_MODES

logger = logging.getLogger(__name__)

# Preset descriptions shown in API/dashboard
PRESET_DESCRIPTIONS: Dict[str, str] = {
    "minimal":        "Racing/FPV — only essential data (altitude + battery)",
    "professional":   "Default — balanced aviation-grade layout",
    "military":       "Tactical — MIL-STD inspired defense HUD",
    "full_telemetry": "Analysis — maximum telemetry density",
    "debug":          "Engineering — all fields + debug info",
}


class OSDModeManager:
    """
    Manages OSD preset switching and color mode at runtime.

    Designed as a thin coordinator — delegates actual rendering changes
    to the existing OSDRenderer (preset reload) and OSDPipeline (cache
    invalidation).  Avoids duplicating logic that already exists.
    """

    def __init__(self, app_controller: Any):
        self._app = app_controller
        self._presets_dir = Path("configs/osd_presets")

        # Color system
        from .parameters import Parameters
        initial_color = getattr(Parameters, "OSD_COLOR_MODE", "day")
        self.color_system = OSDColorSystem(initial_color)

        # Track current preset name
        self._current_preset: str = getattr(Parameters, "OSD_PRESET", "professional")

        logger.info(
            f"OSDModeManager initialized — preset='{self._current_preset}', "
            f"color_mode='{self.color_system.mode_name}'"
        )

    # ── Preset switching ────────────────────────────────────────────────

    @property
    def current_preset(self) -> str:
        return self._current_preset

    def switch_preset(self, preset_name: str) -> bool:
        """
        Hot-switch OSD preset.  Returns True on success.

        Reuses the same logic as the existing ``load_osd_preset`` API
        endpoint — constructs a new OSDRenderer and invalidates the
        pipeline cache.
        """
        preset_path = self._presets_dir / f"{preset_name}.yaml"
        if not preset_path.exists():
            logger.warning(f"Preset '{preset_name}' not found at {preset_path}")
            return False

        from .parameters import Parameters
        from .osd_renderer import OSDRenderer

        old = self._current_preset
        Parameters.OSD_PRESET = preset_name

        try:
            osd_handler = getattr(self._app, "osd_handler", None)
            if osd_handler is not None:
                osd_handler.renderer = OSDRenderer(self._app)

            pipeline = getattr(self._app, "osd_pipeline", None)
            if pipeline is not None:
                pipeline.invalidate_cache("preset_switch")

            self._current_preset = preset_name
            logger.info(f"OSD preset switched: '{old}' -> '{preset_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to switch preset to '{preset_name}': {e}")
            return False

    def cycle_preset(self) -> str:
        """Cycle to next preset. Returns the new preset name."""
        presets = self.available_presets()
        if not presets:
            return self._current_preset
        try:
            idx = presets.index(self._current_preset)
        except ValueError:
            idx = -1
        next_idx = (idx + 1) % len(presets)
        self.switch_preset(presets[next_idx])
        return self._current_preset

    def available_presets(self) -> List[str]:
        """List available preset names sorted with professional first."""
        if not self._presets_dir.exists():
            return []
        presets = [p.stem for p in self._presets_dir.glob("*.yaml")]
        presets.sort(key=lambda x: (x != "professional", x))
        return presets

    # ── Color mode ──────────────────────────────────────────────────────

    @property
    def color_mode(self) -> str:
        return self.color_system.mode_name

    def switch_color_mode(self, mode: str) -> bool:
        """Switch color mode and invalidate cache. Returns True on success."""
        if not self.color_system.set_mode(mode):
            return False

        pipeline = getattr(self._app, "osd_pipeline", None)
        if pipeline is not None:
            pipeline.invalidate_cache("color_mode_switch")

        return True

    def cycle_color_mode(self) -> str:
        """Cycle to next color mode. Returns the new mode name."""
        modes = VALID_COLOR_MODES
        try:
            idx = modes.index(self.color_system.mode_name)
        except ValueError:
            idx = -1
        next_idx = (idx + 1) % len(modes)
        self.switch_color_mode(modes[next_idx])
        return self.color_system.mode_name

    # ── Status ──────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Full status dict for API responses."""
        return {
            "current_preset": self._current_preset,
            "color_mode": self.color_system.mode_name,
            "available_presets": self.available_presets(),
            "available_color_modes": VALID_COLOR_MODES,
            "preset_descriptions": {
                k: v for k, v in PRESET_DESCRIPTIONS.items()
                if k in self.available_presets()
            },
        }

"""
OSD Handler Module - Backward Compatibility Layer
Provides drop-in replacement interface for legacy OSD system.
Delegates to new professional OSDRenderer while maintaining API compatibility.

MIGRATION NOTE:
This module wraps the new OSDRenderer system to ensure zero breaking changes.
All OSD rendering now uses:
    - High-quality PIL/Pillow text rendering (4-8x better than OpenCV)
    - Resolution-independent adaptive scaling
    - Professional text effects (outlines, shadows, background plates)
    - Safe zone management and collision detection

Legacy code using OSDHandler will work without modifications.
"""

import logging
from .osd_renderer import OSDRenderer
from .parameters import Parameters

logger = logging.getLogger(__name__)


class OSDHandler:
    """
    Legacy OSD Handler - Backward Compatibility Wrapper.

    This class maintains the original OSDHandler interface while delegating
    all rendering to the new professional OSDRenderer system.
    """

    def __init__(self, app_controller=None):
        """
        Initialize the OSDHandler with a reference to AppController.

        Args:
            app_controller: Reference to AppController instance
        """
        self.app_controller = app_controller
        self.mavlink_data_manager = self.app_controller.mavlink_data_manager if app_controller else None
        self.logger = logging.getLogger(__name__)

        # Initialize new professional renderer (loads config from preset files)
        self.renderer = OSDRenderer(app_controller)

        logger.info("OSDHandler initialized (using professional OSDRenderer backend)")

    def draw_osd(self, frame):
        """
        Draw all enabled OSD elements on the frame.

        This method is the main interface used by app_controller.py.
        Now delegates to the professional OSDRenderer system.

        Args:
            frame: Input frame (BGR format)

        Returns:
            Frame with OSD elements rendered
        """
        return self.renderer.render(frame)

    # ========================================================================
    # LEGACY METHODS - Maintained for potential compatibility
    # All functionality now delegated to OSDRenderer
    # ========================================================================

    def set_enabled(self, enabled: bool):
        """Enable or disable OSD rendering (delegates to renderer)."""
        self.renderer.set_enabled(enabled)

    def is_enabled(self) -> bool:
        """Check if OSD is enabled (delegates to renderer)."""
        return self.renderer.is_enabled()

    def get_performance_stats(self):
        """Get rendering performance statistics (delegates to renderer)."""
        return self.renderer.get_performance_stats()

    def render_overlay(self, frame_shape, layer_filter=None):
        """Render a transparent RGBA overlay for the requested layer."""
        return self.renderer.render_overlay(frame_shape, layer_filter=layer_filter)

    def compose_overlay(self, frame, overlay_rgba, method="cv2_alpha"):
        """Composite an RGBA overlay onto a BGR frame."""
        return self.renderer.composite_overlay_rgba(frame, overlay_rgba, method=method)

    def get_performance_mode(self) -> str:
        """Get current renderer performance mode."""
        return self.renderer.get_performance_mode()

    def set_performance_mode(self, mode: str) -> bool:
        """Set renderer performance mode."""
        return self.renderer.set_performance_mode(mode)

    def debug_draw_layout(self, frame):
        """Draw layout debug information (delegates to renderer)."""
        return self.renderer.debug_draw_layout(frame)

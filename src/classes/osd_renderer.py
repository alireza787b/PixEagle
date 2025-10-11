"""
OSD Renderer Module - Main Integration Layer
Professional OSD rendering system integrating text rendering and layout management.
Provides backward-compatible interface while enabling advanced features.

Architecture:
    OSDRenderer (main)
        ├── OSDTextRenderer (high-quality text)
        ├── OSDLayoutManager (adaptive positioning)
        └── Element Handlers (specialized renderers)

Usage:
    renderer = OSDRenderer(app_controller)
    frame = renderer.render(frame)  # Drop-in replacement for old system
"""

import cv2
import numpy as np
import time
import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from .osd_text_renderer import OSDTextRenderer, TextStyle
from .osd_layout_manager import OSDLayoutManager, Anchor
from .parameters import Parameters

logger = logging.getLogger(__name__)


class OSDRenderer:
    """
    Main OSD rendering system with professional text quality and adaptive layout.

    This class replaces the legacy OSDHandler while maintaining 100% backward
    compatibility with existing configurations.
    """

    def __init__(self, app_controller=None):
        """
        Initialize the OSD renderer.

        Args:
            app_controller: Reference to AppController for accessing system state
        """
        self.app_controller = app_controller
        self.mavlink_data_manager = app_controller.mavlink_data_manager if app_controller else None

        # Get OSD enable state from Parameters
        self.osd_enabled = Parameters.OSD_ENABLED

        # Load OSD configuration from preset file
        self.osd_config = self._load_preset_config()

        # Get global OSD settings with defaults from preset
        self.global_settings = self.osd_config.get('GLOBAL_SETTINGS', {})
        self.base_font_scale = self.global_settings.get('base_font_scale', 1.0)
        self.default_style = self.global_settings.get('text_style', 'outlined')
        self.outline_thickness = self.global_settings.get('outline_thickness', 2)
        self.shadow_offset = tuple(self.global_settings.get('shadow_offset', [2, 2]))
        self.shadow_opacity = self.global_settings.get('shadow_opacity', 0.5)
        self.background_opacity = self.global_settings.get('background_opacity', 0.7)
        self.safe_zone_margin = self.global_settings.get('safe_zone_margin', 5.0)

        # Get element configuration from preset
        self.osd_elements = self.osd_config.get('ELEMENTS', {})

        # Initialize with default frame size (will update on first render)
        self.frame_width = 640
        self.frame_height = 480

        # Initialize rendering engines
        self.text_renderer = None
        self.layout_manager = None
        self._initialize_renderers(self.frame_width, self.frame_height)

        # Style mapping
        self.style_map = {
            'plain': TextStyle.PLAIN,
            'outlined': TextStyle.OUTLINED,
            'shadowed': TextStyle.SHADOWED,
            'plate': TextStyle.PLATE
        }

        # Performance tracking
        self.last_render_time = 0
        self.render_count = 0

        preset_name = getattr(Parameters, 'OSD_PRESET', 'professional')
        logger.info(f"OSDRenderer initialized with preset '{preset_name}'")

    def _load_preset_config(self) -> Dict[str, Any]:
        """
        Load OSD configuration from preset file.

        Returns:
            Dictionary containing GLOBAL_SETTINGS and ELEMENTS
        """
        # Get preset name from Parameters
        preset_name = getattr(Parameters, 'OSD_PRESET', 'professional')

        # Construct preset file path
        preset_path = Path('configs') / 'osd_presets' / f'{preset_name}.yaml'

        # Load preset file
        try:
            with open(preset_path, 'r') as f:
                preset_config = yaml.safe_load(f)
                logger.info(f"Loaded OSD preset from: {preset_path}")
                return preset_config
        except FileNotFoundError:
            logger.error(f"OSD preset file not found: {preset_path}")
            logger.warning("Falling back to default minimal configuration")
            return self._get_fallback_config()
        except yaml.YAMLError as e:
            logger.error(f"Error parsing OSD preset YAML: {e}")
            logger.warning("Falling back to default minimal configuration")
            return self._get_fallback_config()

    def _get_fallback_config(self) -> Dict[str, Any]:
        """
        Get minimal fallback configuration if preset loading fails.

        Returns:
            Minimal OSD configuration
        """
        return {
            'GLOBAL_SETTINGS': {
                'base_font_scale': 1.0,
                'text_style': 'outlined',
                'outline_thickness': 2,
                'shadow_offset': [2, 2],
                'shadow_opacity': 0.5,
                'background_opacity': 0.7,
                'safe_zone_margin': 5.0
            },
            'ELEMENTS': {
                'name': {
                    'enabled': True,
                    'text': 'PixEagle',
                    'anchor': 'top-left',
                    'offset': [10, 10],
                    'font_scale': 0.7,
                    'color': [255, 255, 255],
                    'style': 'outlined'
                }
            }
        }

    def _initialize_renderers(self, width: int, height: int):
        """
        Initialize or reinitialize rendering engines with new dimensions.

        Args:
            width: Frame width
            height: Frame height
        """
        # Get performance mode from Parameters (defaults to "balanced")
        performance_mode = getattr(Parameters, 'OSD_PERFORMANCE_MODE', 'balanced')

        self.text_renderer = OSDTextRenderer(width, height, self.base_font_scale, performance_mode)
        self.layout_manager = OSDLayoutManager(width, height, self.safe_zone_margin)

        logger.debug(f"Rendering engines initialized for {width}x{height} (performance mode: {performance_mode})")

    def _check_frame_size_change(self, frame: np.ndarray) -> bool:
        """
        Check if frame size has changed and update renderers if needed.

        Args:
            frame: Current frame

        Returns:
            True if size changed
        """
        height, width = frame.shape[:2]

        if width != self.frame_width or height != self.frame_height:
            logger.info(f"Frame size changed: {self.frame_width}x{self.frame_height} → {width}x{height}")
            self.frame_width = width
            self.frame_height = height

            # Update renderers
            self.text_renderer.update_frame_size(width, height)
            self.layout_manager.update_frame_size(width, height)

            return True

        return False

    def render(self, frame: np.ndarray) -> np.ndarray:
        """
        Main rendering method - drop-in replacement for OSDHandler.draw_osd().

        Args:
            frame: Input frame (BGR format)

        Returns:
            Frame with OSD rendered
        """
        if not self.osd_enabled:
            return frame

        # Diagnostic logging on first frame
        if self.render_count == 0:
            logger.info(f"OSD render() called for first time. Elements loaded: {len(self.osd_elements)}, Element names: {list(self.osd_elements.keys())}")

        # Check for frame size changes
        self._check_frame_size_change(frame)

        # Clear layout manager's element tracking for this frame
        self.layout_manager.clear_elements()

        # Performance tracking
        start_time = time.time()

        # Initialize transparent overlay for this frame (optimized compositing)
        self.text_renderer.initialize_overlay(frame.shape)

        # Render each enabled element
        rendered_count = 0
        for element_name, config in self.osd_elements.items():
            if not isinstance(config, dict):
                logger.debug(f"Skipping non-dict element '{element_name}': {type(config)}")
                continue

            if config.get("enabled", False):
                try:
                    frame = self._render_element(frame, element_name, config)
                    rendered_count += 1
                    if self.render_count == 0:
                        logger.info(f"✓ Rendered OSD element: {element_name}")
                except Exception as e:
                    logger.error(f"Error rendering OSD element '{element_name}': {e}")
            else:
                if self.render_count == 0:
                    logger.info(f"✗ Element '{element_name}' not enabled: {config.get('enabled', 'key missing')}")

        if rendered_count == 0 and self.render_count == 0:
            logger.warning(f"No OSD elements rendered! Loaded {len(self.osd_elements)} elements from preset")

        # Composite overlay onto frame (ONCE per frame - major optimization!)
        frame = self.text_renderer.composite_overlay(frame)

        # Update performance metrics
        self.last_render_time = time.time() - start_time
        self.render_count += 1

        # Log performance periodically
        if self.render_count % 100 == 0:
            logger.debug(f"OSD render time: {self.last_render_time*1000:.2f}ms (avg over 100 frames)")

        return frame

    def _render_element(self, frame: np.ndarray, element_name: str, config: Dict[str, Any]) -> np.ndarray:
        """
        Render a single OSD element.

        Args:
            frame: Current frame
            element_name: Name of element to render
            config: Element configuration

        Returns:
            Frame with element rendered
        """
        # Route to specialized handlers
        handler_map = {
            "name": self._draw_name,
            "datetime": self._draw_datetime,
            "crosshair": self._draw_crosshair,
            "mavlink_data": self._draw_mavlink_data,
            "attitude_indicator": self._draw_attitude_indicator,
            "tracker_status": self._draw_tracker_status,
            "follower_status": self._draw_follower_status,
        }

        handler = handler_map.get(element_name)
        if handler:
            return handler(frame, config)
        else:
            logger.warning(f"No handler for OSD element: {element_name}")
            return frame

    def _get_text_style(self, config: Dict[str, Any]) -> TextStyle:
        """Get TextStyle enum from config string."""
        style_str = config.get('style', self.default_style).lower()
        return self.style_map.get(style_str, TextStyle.OUTLINED)

    def _calculate_position(self, config: Dict[str, Any], text: str = "", font_scale: float = 1.0) -> Tuple[int, int]:
        """
        Calculate position for an element using modern or legacy positioning.

        Args:
            config: Element configuration
            text: Text to render (for size calculation)
            font_scale: Font scale multiplier

        Returns:
            (x, y) pixel coordinates
        """
        # Get text size for alignment
        text_width, text_height = 0, 0
        if text:
            text_width, text_height = self.text_renderer.get_text_size(text, font_scale)

        # Check for modern anchor-based positioning
        if 'anchor' in config:
            anchor_str = config['anchor']
            try:
                anchor = Anchor(anchor_str)
                offset = tuple(config.get('offset', [0, 0]))
                return self.layout_manager.calculate_position(
                    anchor=anchor,
                    offset=offset,
                    text_width=text_width,
                    text_height=text_height
                )
            except ValueError:
                logger.warning(f"Invalid anchor: {anchor_str}, falling back to percentage positioning")

        # Legacy percentage-based positioning
        if 'position' in config:
            percentage_pos = tuple(config['position'])
            return self.layout_manager.calculate_position(
                percentage_pos=percentage_pos,
                text_width=text_width,
                text_height=text_height
            )

        # Default position
        return (self.layout_manager.safe_margin_x, self.layout_manager.safe_margin_y)

    def _draw_name(self, frame: np.ndarray, config: Dict[str, Any]) -> np.ndarray:
        """Draw system name/watermark."""
        text = config.get("text", "PixEagle")
        font_scale = config.get("font_scale", config.get("font_size", 0.7))
        color = tuple(config.get("color", [255, 255, 255]))
        style = self._get_text_style(config)

        x, y = self._calculate_position(config, text, font_scale)

        return self.text_renderer.render_text(
            frame, text, (x, y),
            color=color,
            font_scale=font_scale,
            style=style,
            outline_thickness=self.outline_thickness
        )

    def _draw_datetime(self, frame: np.ndarray, config: Dict[str, Any]) -> np.ndarray:
        """Draw current date and time."""
        datetime_str = time.strftime("%Y-%m-%d %H:%M:%S")
        font_scale = config.get("font_scale", config.get("font_size", 0.6))
        color = tuple(config.get("color", [255, 255, 255]))
        style = self._get_text_style(config)

        # Calculate position - anchor system handles text width automatically
        x, y = self._calculate_position(config, datetime_str, font_scale)

        return self.text_renderer.render_text(
            frame, datetime_str, (x, y),
            color=color,
            font_scale=font_scale,
            style=style,
            outline_thickness=self.outline_thickness
        )

    def _draw_crosshair(self, frame: np.ndarray, config: Dict[str, Any]) -> np.ndarray:
        """Draw center crosshair."""
        center_x = self.frame_width // 2
        center_y = self.frame_height // 2
        color = tuple(config.get("color", [0, 255, 0]))
        thickness = config.get("thickness", 2)
        length = config.get("length", 15)

        # Draw crosshair lines
        cv2.line(frame, (center_x - length, center_y), (center_x + length, center_y), color, thickness)
        cv2.line(frame, (center_x, center_y - length), (center_x, center_y + length), color, thickness)

        return frame

    def _draw_tracker_status(self, frame: np.ndarray, config: Dict[str, Any]) -> np.ndarray:
        """Draw tracker status indicator."""
        if not self.app_controller:
            return frame

        status = "Active" if self.app_controller.tracking_started else "Not Active"
        color = tuple([0, 255, 0] if self.app_controller.tracking_started else config.get("color", [255, 255, 0]))
        font_scale = config.get("font_scale", config.get("font_size", 0.4))
        style = self._get_text_style(config)

        text = f"Tracker: {status}"
        x, y = self._calculate_position(config, text, font_scale)

        return self.text_renderer.render_text(
            frame, text, (x, y),
            color=color,
            font_scale=font_scale,
            style=style,
            outline_thickness=self.outline_thickness
        )

    def _draw_follower_status(self, frame: np.ndarray, config: Dict[str, Any]) -> np.ndarray:
        """Draw follower status indicator."""
        if not self.app_controller:
            return frame

        status = "Active" if self.app_controller.following_active else "Not Active"
        color = tuple([0, 255, 0] if self.app_controller.following_active else config.get("color", [255, 255, 0]))
        font_scale = config.get("font_scale", config.get("font_size", 0.4))
        style = self._get_text_style(config)

        text = f"Follower: {status}"
        x, y = self._calculate_position(config, text, font_scale)

        return self.text_renderer.render_text(
            frame, text, (x, y),
            color=color,
            font_scale=font_scale,
            style=style,
            outline_thickness=self.outline_thickness
        )

    def _draw_mavlink_data(self, frame: np.ndarray, config: Dict[str, Any]) -> np.ndarray:
        """
        Draw MAVLink telemetry data fields.

        Supports rendering multiple individual MAVLink fields with custom positioning,
        colors, and formatting - just like the legacy OSD system.

        IMPORTANT: Always renders all fields, showing N/A placeholders when data is unavailable.
        """
        # Get fields configuration - this is a dict of field_name: field_config
        fields_config = config.get("fields", {})

        # Render each MAVLink field independently
        for field_name, field_config in fields_config.items():
            if not isinstance(field_config, dict):
                logger.warning(f"Invalid config for MAVLink field '{field_name}'")
                continue

            # Skip if field is explicitly disabled
            if field_config.get("enabled", True) is False:
                continue

            try:
                # Get raw value from MAVLink data manager (or None if unavailable)
                raw_value = None
                if Parameters.MAVLINK_ENABLED and self.mavlink_data_manager:
                    raw_value = self.mavlink_data_manager.get_data(field_name.lower())

                # Special handling for flight_path_angle
                if field_name == "flight_path_angle":
                    if raw_value == 0.0:
                        formatted_value = "Level"
                    else:
                        try:
                            formatted_value = f"{float(raw_value):.1f}"
                        except (ValueError, TypeError):
                            formatted_value = "N/A"
                else:
                    # Use standard formatting (handles None/N/A gracefully)
                    if raw_value is None:
                        raw_value = "N/A"
                    formatted_value = self._format_value(
                        field_name.replace("_", " ").title(),
                        raw_value
                    )

                # Get rendering configuration
                font_scale = field_config.get("font_size", field_config.get("font_scale", 0.4))
                color = tuple(field_config.get("color", [255, 255, 255]))
                style = self._get_text_style(field_config)

                # Build display text (field name + value)
                display_name = field_config.get("display_name", field_name.replace('_', ' ').title())
                text = f"{display_name}: {formatted_value}"

                # Calculate position (supports both anchor and legacy percentage positioning)
                x, y = self._calculate_position(field_config, text, font_scale)

                # Render the field
                frame = self.text_renderer.render_text(
                    frame, text, (x, y),
                    color=color,
                    font_scale=font_scale,
                    style=style,
                    outline_thickness=self.outline_thickness,
                    shadow_offset=self.shadow_offset,
                    shadow_opacity=self.shadow_opacity,
                    background_opacity=self.background_opacity
                )

            except Exception as e:
                logger.warning(f"Error rendering MAVLink field '{field_name}': {e}")
                continue

        return frame

    def _draw_attitude_indicator(self, frame: np.ndarray, config: Dict[str, Any]) -> np.ndarray:
        """
        Draw artificial horizon attitude indicator.

        Note: This is kept as OpenCV-based for performance (complex graphics).
        """
        # Safely retrieve roll and pitch
        roll = np.rad2deg(self._safe_get_float("roll"))
        pitch = np.rad2deg(self._safe_get_float("pitch"))

        # Get position (use legacy percentage for attitude indicator)
        position = config.get("position", [50, 50])
        center_x = int(self.frame_width * position[0] / 100)
        center_y = int(self.frame_height * position[1] / 100)

        # Get size
        size = config.get("size", [70, 70])
        size_x = int(self.frame_width * size[0] / 100)
        size_y = int(self.frame_height * size[1] / 100)

        # Colors
        horizon_color = tuple(config.get("horizon_color", [255, 255, 255]))
        grid_color = tuple(config.get("grid_color", [200, 200, 200]))
        thickness = config.get("thickness", 2)

        # Calculate horizon line position based on pitch
        horizon_y = center_y + int(pitch * size_y / 90)

        # Calculate rotation matrix for roll
        rotation_matrix = cv2.getRotationMatrix2D((center_x, center_y), -roll, 1)

        # Draw horizon line
        horizon_line = np.array([[center_x - size_x, horizon_y], [center_x + size_x, horizon_y]], dtype=np.float32)
        horizon_line = cv2.transform(np.array([horizon_line]), rotation_matrix)[0]
        pt1 = tuple(map(int, horizon_line[0]))
        pt2 = tuple(map(int, horizon_line[1]))
        cv2.line(frame, pt1, pt2, horizon_color, thickness)

        # Draw pitch lines
        for i in range(-90, 100, 10):
            tick_y = center_y + int(i * size_y / 90)
            tick_line = np.array([
                [center_x - size_x / 4, tick_y],
                [center_x + size_x / 4, tick_y]
            ], dtype=np.float32)
            tick_line = cv2.transform(np.array([tick_line]), rotation_matrix)[0]
            tick_pt1 = tuple(map(int, tick_line[0]))
            tick_pt2 = tuple(map(int, tick_line[1]))
            cv2.line(frame, tick_pt1, tick_pt2, grid_color, thickness)

        # Draw roll indicator arc
        cv2.ellipse(
            frame,
            (center_x, center_y),
            (int(size_x / 2), int(size_y / 2)),
            0, 0, 180,
            grid_color,
            thickness
        )

        return frame

    def _format_value(self, field: str, value: Any) -> str:
        """
        Format MAVLink values for display (same as original OSDHandler).

        Args:
            field: Field name
            value: Raw value

        Returns:
            Formatted string
        """
        if value == "N/A":
            return value

        try:
            if field in ["Airspeed", "Groundspeed", "Climb"]:
                return f"{float(value):.1f} m/s"
            elif field in ["Roll", "Pitch"]:
                value = np.rad2deg(float(value))
                return f"{int(value)}"
            elif field == "Heading":
                heading = float(value) % 360
                return f"{int(heading)}"
            elif field in ["Altitude Msl", "Altitude Agl"]:
                return f"{float(value):.1f} m" if "agl" in field.lower() else f"{int(float(value))} m"
            elif field == "Voltage":
                return f"{float(value):.1f} V"
            elif field in ["Latitude", "Longitude"]:
                return f"{float(value):.6f}"
            elif field in ["Hdop", "Vdop"]:
                return f"{float(value):.2f}"
            elif field in ["Satellites Visible", "Throttle"]:
                return f"{int(float(value))}"
            elif field == "Flight Mode":
                mode = int(float(value))
                return self.app_controller.px4_interface.get_flight_mode_text(mode)
            else:
                return str(value)
        except (ValueError, AttributeError):
            return "N/A"

    def _safe_get_float(self, field_name: str, default: float = 0.0) -> float:
        """
        Safely retrieve and convert MAVLink data to float.

        Args:
            field_name: MAVLink field name
            default: Default value if retrieval fails

        Returns:
            Float value or default
        """
        if not self.mavlink_data_manager:
            return default

        raw_value = self.mavlink_data_manager.get_data(field_name)
        if raw_value is None:
            return default

        try:
            return float(raw_value)
        except (ValueError, TypeError):
            return default

    def set_enabled(self, enabled: bool):
        """
        Enable or disable OSD rendering.

        Args:
            enabled: True to enable, False to disable
        """
        self.osd_enabled = enabled
        logger.info(f"OSD rendering {'enabled' if enabled else 'disabled'}")

    def is_enabled(self) -> bool:
        """Check if OSD is currently enabled."""
        return self.osd_enabled

    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get rendering performance statistics.

        Returns:
            Dictionary with performance metrics
        """
        return {
            'last_render_time_ms': self.last_render_time * 1000,
            'render_count': self.render_count,
            'frame_size': f"{self.frame_width}x{self.frame_height}",
            'base_font_size': self.text_renderer.base_font_size if self.text_renderer else 0,
            'fonts_cached': len(self.text_renderer.font_cache) if self.text_renderer else 0
        }

    def debug_draw_layout(self, frame: np.ndarray) -> np.ndarray:
        """
        Draw layout debug information (safe zones, grid).

        Args:
            frame: Input frame

        Returns:
            Frame with debug overlays
        """
        return self.layout_manager.debug_draw_safe_zones(frame)

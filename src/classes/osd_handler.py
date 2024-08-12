import cv2
import time
import logging
import numpy as np
from .parameters import Parameters

class OSDHandler:
    def __init__(self, app_controller=None):
        """
        Initialize the OSDHandler with a reference to AppController.
        """
        self.app_controller = app_controller
        self.mavlink_data_manager = self.app_controller.mavlink_data_manager
        self.osd_config = Parameters.OSD_CONFIG
        self.logger = logging.getLogger(__name__)

    def draw_osd(self, frame):
        """
        Draw all enabled OSD elements on the frame.
        """
        for element_name, config in self.osd_config.items():
            if config["enabled"]:
                if element_name == "name":
                    self._draw_name(frame, config)
                elif element_name == "datetime":
                    self._draw_datetime(frame, config)
                elif element_name == "crosshair":
                    self._draw_crosshair(frame, config)
                elif element_name == "mavlink_data" and Parameters.mavlink_enabled:
                    self._draw_mavlink_data(frame, config)
                elif element_name == "attitude_indicator":
                    self._draw_attitude_indicator(frame, config)
                elif element_name == "tracker_status":
                    self._draw_tracker_status(frame, config)
                elif element_name == "follower_status":
                    self._draw_follower_status(frame, config)
        return frame

    def _draw_tracker_status(self, frame, config):
        """
        Draw the tracker status on the frame.
        """
        status = "Active" if self.app_controller.tracking_started else "Not Active"
        # Change color based on the status
        color = (0, 255, 0) if self.app_controller.tracking_started else config["color"]
        position = self._convert_position(frame, config["position"])
        text = f"Tracker: {status}"
        cv2.putText(frame, text, position, cv2.FONT_HERSHEY_SIMPLEX, config["font_size"], color, 2)

    def _draw_follower_status(self, frame, config):
        """
        Draw the follower status on the frame.
        """
        status = "Active" if self.app_controller.following_active else "Not Active"
        # Change color based on the status
        color = (0, 255, 0) if self.app_controller.following_active else config["color"]
        position = self._convert_position(frame, config["position"])
        text = f"Follower: {status}"
        cv2.putText(frame, text, position, cv2.FONT_HERSHEY_SIMPLEX, config["font_size"], color, 2)


    def _convert_position(self, frame, position):
        """
        Convert a position from percentage to pixel coordinates.
        """
        x_percent, y_percent = position
        height, width = frame.shape[:2]
        x = int(width * x_percent / 100)
        y = int(height * y_percent / 100)
        return (x, y)

    def _draw_name(self, frame, config):
        """
        Draw the name on the frame.
        """
        position = self._convert_position(frame, config["position"])
        cv2.putText(frame, config["text"], position, cv2.FONT_HERSHEY_SIMPLEX, config["font_size"], config["color"], 2)

    def _draw_datetime(self, frame, config):
        """
        Draw the current date and time on the frame.
        """
        datetime_str = time.strftime("%Y-%m-%d %H:%M:%S")
        position = self._convert_position(frame, config["position"])
        text_size = cv2.getTextSize(datetime_str, cv2.FONT_HERSHEY_SIMPLEX, config["font_size"], 2)[0]
        adjusted_position = (position[0] - text_size[0], position[1])
        cv2.putText(frame, datetime_str, adjusted_position, cv2.FONT_HERSHEY_SIMPLEX, config["font_size"], config["color"], 2)

    def _draw_crosshair(self, frame, config):
        """
        Draw a crosshair in the center of the frame.
        """
        center_x = frame.shape[1] // 2
        center_y = frame.shape[0] // 2
        cv2.line(frame, (center_x - config["length"], center_y), (center_x + config["length"], center_y), config["color"], config["thickness"])
        cv2.line(frame, (center_x, center_y - config["length"]), (center_x, center_y + config["length"]), config["color"], config["thickness"])

    def _format_value(self, field, value):
        """
        Format the value based on the field type for better display in OSD.
        """
        if value == "N/A":
            return value

        try:
            if field in ["Airspeed", "Groundspeed", "Climb"]:  # Speeds
                return f"{float(value):.1f} m/s"
            elif field in ["Roll", "Pitch"]:  # Angles
                value = np.rad2deg(float(value))
                return f"{int(value)}"
            elif field == "Heading":  # Heading (ensure it's between 0 and 359 degrees)
                heading = float(value) % 360
                return f"{int(heading)}"
            elif field in ["Altitude Msl", "Altitude Agl"]:  # Altitudes
                return f"{float(value):.1f} m" if "agl" in field.lower() else f"{int(float(value))} m"
            elif field == "Voltage":  # Voltage
                return f"{float(value):.1f} V"
            elif field in ["Latitude", "Longitude"]:  # Coordinates
                return f"{float(value):.6f}"
            elif field in ["Hdop", "Vdop"]:  # DOP values
                return f"{float(value):.1f}"
            elif field == "Satellites Visible":  # Satellite count
                return f"{int(float(value))}"
            elif field == "Flight Mode":  # Convert flight mode code to text using PX4InterfaceManager
                mode = int(float(value))
                return self.app_controller.px4_interface.get_flight_mode_text(mode)
            else:
                return value
        except ValueError:
            return "N/A"

    def _draw_mavlink_data(self, frame, config):
        """
        Draw MAVLink data on the frame.
        """
        if not Parameters.mavlink_enabled:
            self.logger.info("MAVLink integration is disabled. Skipping MAVLink data display.")
            return

        if not self.app_controller.mavlink_data_manager:
            self.logger.warning("Mavlink data manager is not initialized. Skipping MAVLink data display.")
            return

        for field, field_config in config["fields"].items():
            raw_value = self.app_controller.mavlink_data_manager.get_data(field.lower())
            formatted_value = self._format_value(field.replace("_", " ").title(), raw_value)
            if formatted_value is None:
                self.logger.warning(f"Failed to retrieve data for {field}. Displaying 'N/A'.")
                formatted_value = "N/A"

            position = self._convert_position(frame, field_config["position"])
            text = f"{field.replace('_', ' ').title()}: {formatted_value}"
            cv2.putText(frame, text, position, cv2.FONT_HERSHEY_SIMPLEX, field_config["font_size"], field_config["color"], 2)
    def _draw_attitude_indicator(self, frame, config):
        """
        Draw the attitude indicator on the frame.
        """
        try:
            roll = float(self.mavlink_data_manager.get_data("roll") or 0)
            pitch = float(self.mavlink_data_manager.get_data("pitch") or 0)

            # Convert from radians to degrees
            roll = np.rad2deg(roll)
            pitch = np.rad2deg(pitch)
                
        except ValueError as e:
            self.logger.error(f"Error converting roll or pitch to float: {e}")
            roll = 0
            pitch = 0

        # Define the center position for the horizon line
        center_x, center_y = self._convert_position(frame, config["position"])
        size_x, size_y = config["size"]

        # Calculate horizon line position based on pitch
        horizon_y = center_y + int(pitch * size_y / 90)  # Simple linear mapping

        # Calculate the rotation matrix for roll
        rotation_matrix = cv2.getRotationMatrix2D((center_x, center_y), -roll, 1)

        # Draw the horizon line (rotated)
        horizon_line = np.array([[center_x - size_x, horizon_y], [center_x + size_x, horizon_y]], dtype=np.float32)
        horizon_line = cv2.transform(np.array([horizon_line]), rotation_matrix)[0]

        # Ensure the coordinates are integers
        pt1 = tuple(map(int, horizon_line[0]))
        pt2 = tuple(map(int, horizon_line[1]))

        # Draw the horizon line
        cv2.line(frame, pt1, pt2, config["horizon_color"], config["thickness"])

        # Draw pitch lines (example: every 10 degrees up and down)
        for i in range(-90, 100, 10):
            tick_y = center_y + int(i * size_y / 90)
            tick_line = np.array([[center_x - size_x / 4, tick_y], [center_x + size_x / 4, tick_y]], dtype=np.float32)
            tick_line = cv2.transform(np.array([tick_line]), rotation_matrix)[0]

            # Ensure the coordinates are integers
            tick_pt1 = tuple(map(int, tick_line[0]))
            tick_pt2 = tuple(map(int, tick_line[1]))

            cv2.line(frame, tick_pt1, tick_pt2, config["grid_color"], config["thickness"])

        # Draw roll indicator (semi-circle at the top of the screen)
        cv2.ellipse(frame, (center_x, center_y), (int(size_x / 2), int(size_y / 2)), 0, 0, 180, config["grid_color"], config["thickness"])
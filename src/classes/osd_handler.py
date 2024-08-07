# src/classes/osd_handler.py
import cv2
import time
from .parameters import Parameters

class OSDHandler:
    def __init__(self):
        self.osd_elements = {
            "name": Parameters.OSD_SHOW_NAME,
            "datetime": Parameters.OSD_SHOW_DATETIME,
            "crosshair": Parameters.OSD_SHOW_CROSSHAIR,
        }

    def draw_osd(self, frame):
        if self.osd_elements["name"]:
            self._draw_name(frame)
        if self.osd_elements["datetime"]:
            self._draw_datetime(frame)
        if self.osd_elements["crosshair"]:
            self._draw_crosshair(frame)
        return frame

    def _convert_position(self, frame, position):
        x_percent, y_percent = position
        height, width = frame.shape[:2]
        x = int(width * x_percent / 100)
        y = int(height * y_percent / 100)
        return (x, y)

    def _draw_name(self, frame):
        name = Parameters.OSD_NAME
        position = self._convert_position(frame, Parameters.OSD_NAME_POSITION)
        color = Parameters.OSD_NAME_COLOR
        font_size = Parameters.OSD_NAME_FONT_SIZE
        cv2.putText(frame, name, position, cv2.FONT_HERSHEY_SIMPLEX, font_size, color, 2)

    def _draw_datetime(self, frame):
        datetime_str = time.strftime("%Y-%m-%d %H:%M:%S")
        position = self._convert_position(frame, Parameters.OSD_DATETIME_POSITION)
        color = Parameters.OSD_DATETIME_COLOR
        font_size = Parameters.OSD_DATETIME_FONT_SIZE

        text_size = cv2.getTextSize(datetime_str, cv2.FONT_HERSHEY_SIMPLEX, font_size, 2)[0]
        adjusted_position = (position[0] - text_size[0], position[1])  # Adjust to ensure it fits within the screen

        cv2.putText(frame, datetime_str, adjusted_position, cv2.FONT_HERSHEY_SIMPLEX, font_size, color, 2)

    def _draw_crosshair(self, frame):
        center_x = frame.shape[1] // 2
        center_y = frame.shape[0] // 2
        color = Parameters.OSD_CROSSHAIR_COLOR
        thickness = Parameters.OSD_CROSSHAIR_THICKNESS
        length = Parameters.OSD_CROSSHAIR_LENGTH
        cv2.line(frame, (center_x - length, center_y), (center_x + length, center_y), color, thickness)
        cv2.line(frame, (center_x, center_y - length), (center_x, center_y + length), color, thickness)

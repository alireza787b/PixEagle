"""Full-frame analysis/display mappings; no crop or padding is implicit."""

from dataclasses import dataclass

import cv2


def resize_pixels(frame, width, height):
    """Use area integration for shrinking and linear interpolation for enlargement."""
    width, height = int(width), int(height)
    if width <= 0 or height <= 0:
        raise ValueError("Frame dimensions must be positive")
    if frame.shape[1] == width and frame.shape[0] == height:
        return frame.copy()
    interpolation = (cv2.INTER_AREA if width <= frame.shape[1] and height <= frame.shape[0]
                     else cv2.INTER_LINEAR)
    return cv2.resize(frame, (width, height), interpolation=interpolation)


def fit_dimensions(source_width, source_height, max_width, max_height):
    """Fit inside delivery bounds without stretching, cropping or upscaling."""
    if min(source_width, source_height, max_width, max_height) <= 0:
        raise ValueError("Frame dimensions must be positive")
    scale = min(1.0, max_width / source_width, max_height / source_height)
    return max(1, round(source_width * scale)), max(1, round(source_height * scale))


@dataclass(frozen=True)
class FrameScale:
    """Map analysis pixels into a display containing the same complete image."""

    x: float
    y: float

    @classmethod
    def between(cls, analysis_shape, display_shape):
        return cls(display_shape[1] / analysis_shape[1], display_shape[0] / analysis_shape[0])

    def point(self, x, y):
        return int(x * self.x), int(y * self.y)

    def xyxy(self, box):
        return (*self.point(box[0], box[1]), *self.point(box[2], box[3]))

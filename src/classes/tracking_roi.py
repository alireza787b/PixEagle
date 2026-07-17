"""Validated coordinate conversion for manual tracking target selection."""

from __future__ import annotations

from math import ceil, floor, isfinite
from typing import Dict, Sequence, Tuple


MIN_TRACKING_ROI_SIDE_PIXELS = 4
TRACKING_ROI_COORDINATE_SPACES = frozenset({"normalized", "pixels"})


class TrackingROIError(ValueError):
    """Raised when a manual tracking ROI is ambiguous or outside its frame."""


def tracking_roi_to_pixels(
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    coordinate_space: str,
    frame_width: int,
    frame_height: int,
) -> Dict[str, int]:
    """Validate an ROI and convert it to bounded integer pixel coordinates.

    The minimum four-pixel side is a tracker input invariant rather than a
    tuning parameter. It prevents zero-area and one-pixel OpenCV initializers.
    """
    if frame_width <= 0 or frame_height <= 0:
        raise TrackingROIError("Tracking frame dimensions must be positive")
    if coordinate_space not in TRACKING_ROI_COORDINATE_SPACES:
        raise TrackingROIError(
            "coordinate_space must be either 'normalized' or 'pixels'"
        )

    values = (float(x), float(y), float(width), float(height))
    if not all(isfinite(value) for value in values):
        raise TrackingROIError("Tracking ROI values must be finite numbers")
    x_value, y_value, width_value, height_value = values
    if x_value < 0 or y_value < 0:
        raise TrackingROIError("Tracking ROI origin must be inside the frame")
    if width_value <= 0 or height_value <= 0:
        raise TrackingROIError("Tracking ROI width and height must be positive")

    if coordinate_space == "normalized":
        if (
            x_value > 1
            or y_value > 1
            or width_value > 1
            or height_value > 1
            or x_value + width_value > 1
            or y_value + height_value > 1
        ):
            raise TrackingROIError(
                "Normalized tracking ROI must fit completely inside 0..1"
            )
        left = floor(x_value * frame_width)
        top = floor(y_value * frame_height)
        right = ceil((x_value + width_value) * frame_width)
        bottom = ceil((y_value + height_value) * frame_height)
    else:
        if (
            x_value >= frame_width
            or y_value >= frame_height
            or x_value + width_value > frame_width
            or y_value + height_value > frame_height
        ):
            raise TrackingROIError(
                "Pixel tracking ROI must fit completely inside the frame"
            )
        left = floor(x_value)
        top = floor(y_value)
        right = ceil(x_value + width_value)
        bottom = ceil(y_value + height_value)

    pixel_width = right - left
    pixel_height = bottom - top
    if (
        pixel_width < MIN_TRACKING_ROI_SIDE_PIXELS
        or pixel_height < MIN_TRACKING_ROI_SIDE_PIXELS
    ):
        raise TrackingROIError(
            "Tracking ROI must be at least "
            f"{MIN_TRACKING_ROI_SIDE_PIXELS}x{MIN_TRACKING_ROI_SIDE_PIXELS} pixels"
        )

    return {
        "x": int(left),
        "y": int(top),
        "width": int(pixel_width),
        "height": int(pixel_height),
    }


def tracking_point_to_pixels(
    *,
    x: float,
    y: float,
    coordinate_space: str,
    frame_width: int,
    frame_height: int,
) -> Tuple[int, int]:
    """Validate a smart-selection point and convert it to bounded pixels."""
    if frame_width <= 0 or frame_height <= 0:
        raise TrackingROIError("Tracking frame dimensions must be positive")
    if coordinate_space not in TRACKING_ROI_COORDINATE_SPACES:
        raise TrackingROIError(
            "coordinate_space must be either 'normalized' or 'pixels'"
        )
    x_value, y_value = float(x), float(y)
    if not isfinite(x_value) or not isfinite(y_value):
        raise TrackingROIError("Tracking point values must be finite numbers")

    if coordinate_space == "normalized":
        if not (0 <= x_value <= 1 and 0 <= y_value <= 1):
            raise TrackingROIError("Normalized tracking point must be inside 0..1")
        return (
            min(frame_width - 1, floor(x_value * frame_width)),
            min(frame_height - 1, floor(y_value * frame_height)),
        )

    if not (0 <= x_value < frame_width and 0 <= y_value < frame_height):
        raise TrackingROIError("Pixel tracking point must be inside the frame")
    return floor(x_value), floor(y_value)


def tracking_xyxy_to_pixels(
    box: Sequence[float],
    *,
    frame_width: int,
    frame_height: int,
) -> Dict[str, int]:
    """Validate a pixel ``(x1, y1, x2, y2)`` box and return ``x/y/w/h``.

    Detector and segmentation boundaries use ``xyxy`` while OpenCV tracker
    initializers use ``xywh``. Keeping this conversion beside the manual ROI
    validator prevents the two formats from being silently interchanged.
    """
    try:
        values = tuple(box)
    except TypeError as exc:
        raise TrackingROIError(
            "Tracking xyxy box must be a four-value sequence"
        ) from exc
    if len(values) != 4:
        raise TrackingROIError("Tracking xyxy box must contain exactly four values")
    try:
        x1, y1, x2, y2 = (float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise TrackingROIError("Tracking xyxy box values must be numbers") from exc
    if not all(isfinite(value) for value in (x1, y1, x2, y2)):
        raise TrackingROIError("Tracking xyxy box values must be finite numbers")
    if x2 <= x1 or y2 <= y1:
        raise TrackingROIError(
            "Tracking xyxy box must have increasing corner coordinates"
        )
    return tracking_roi_to_pixels(
        x=x1,
        y=y1,
        width=x2 - x1,
        height=y2 - y1,
        coordinate_space="pixels",
        frame_width=frame_width,
        frame_height=frame_height,
    )


__all__ = [
    "MIN_TRACKING_ROI_SIDE_PIXELS",
    "TRACKING_ROI_COORDINATE_SPACES",
    "TrackingROIError",
    "tracking_point_to_pixels",
    "tracking_roi_to_pixels",
    "tracking_xyxy_to_pixels",
]

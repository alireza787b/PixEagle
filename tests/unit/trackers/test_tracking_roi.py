"""Manual tracker ROI coordinate and boundary contract tests."""

import math

import pytest

from classes.tracking_roi import (
    TrackingROIError,
    tracking_point_to_pixels,
    tracking_roi_to_pixels,
    tracking_xyxy_to_pixels,
)


def test_normalized_roi_converts_with_bounded_edges():
    assert tracking_roi_to_pixels(
        x=0.25,
        y=0.2,
        width=0.5,
        height=0.6,
        coordinate_space="normalized",
        frame_width=200,
        frame_height=100,
    ) == {"x": 50, "y": 20, "width": 100, "height": 60}


@pytest.mark.parametrize(
    ("frame_width", "frame_height", "expected"),
    [
        (640, 480, {"x": 300, "y": 225, "width": 40, "height": 30}),
        (1920, 1080, {"x": 902, "y": 507, "width": 116, "height": 66}),
    ],
)
def test_six_percent_click_roi_reaches_tracker_pixels(frame_width, frame_height, expected):
    """The dashboard default keeps one normalized contract at common sizes."""
    assert tracking_roi_to_pixels(
        x=0.47,
        y=0.47,
        width=0.06,
        height=0.06,
        coordinate_space="normalized",
        frame_width=frame_width,
        frame_height=frame_height,
    ) == expected


def test_pixel_roi_preserves_explicit_pixel_contract():
    assert tracking_roi_to_pixels(
        x=10.2,
        y=20.1,
        width=30.2,
        height=40.2,
        coordinate_space="pixels",
        frame_width=200,
        frame_height=100,
    ) == {"x": 10, "y": 20, "width": 31, "height": 41}


@pytest.mark.parametrize(
    "overrides",
    [
        {"x": -0.1},
        {"width": 0},
        {"width": math.nan},
        {"x": 0.9, "width": 0.2},
        {"coordinate_space": "guessed"},
    ],
)
def test_invalid_or_ambiguous_normalized_roi_fails_closed(overrides):
    values = {
        "x": 0.1,
        "y": 0.1,
        "width": 0.2,
        "height": 0.2,
        "coordinate_space": "normalized",
        "frame_width": 640,
        "frame_height": 480,
    }
    values.update(overrides)

    with pytest.raises(TrackingROIError):
        tracking_roi_to_pixels(**values)


def test_sub_four_pixel_roi_is_rejected():
    with pytest.raises(TrackingROIError, match="at least 4x4"):
        tracking_roi_to_pixels(
            x=0,
            y=0,
            width=0.001,
            height=0.001,
            coordinate_space="normalized",
            frame_width=640,
            frame_height=480,
        )


def test_normalized_tracking_point_clamps_exact_far_edge():
    assert tracking_point_to_pixels(
        x=1,
        y=1,
        coordinate_space="normalized",
        frame_width=640,
        frame_height=480,
    ) == (639, 479)


def test_pixel_tracking_point_requires_explicit_in_frame_coordinates():
    with pytest.raises(TrackingROIError, match="inside the frame"):
        tracking_point_to_pixels(
            x=640,
            y=10,
            coordinate_space="pixels",
            frame_width=640,
            frame_height=480,
        )


def test_xyxy_detector_box_converts_to_tracker_xywh_contract():
    assert tracking_xyxy_to_pixels(
        (10.2, 20.1, 40.4, 60.2),
        frame_width=200,
        frame_height=100,
    ) == {"x": 10, "y": 20, "width": 31, "height": 41}


@pytest.mark.parametrize(
    "box",
    [
        None,
        (1, 2, 3),
        (20, 10, 20, 40),
        (20, 10, 10, 40),
        (0, 0, math.inf, 20),
        (198, 10, 205, 20),
        (1, 1, 3, 3),
    ],
)
def test_invalid_xyxy_detector_box_fails_closed(box):
    with pytest.raises(TrackingROIError):
        tracking_xyxy_to_pixels(
            box,
            frame_width=200,
            frame_height=100,
        )

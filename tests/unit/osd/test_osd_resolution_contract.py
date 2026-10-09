"""Real renderer measurements must match readable, resolution-scaled pixels."""

import cv2
import numpy as np
import pytest

from classes.osd_text_renderer import OSDTextRenderer, PerformanceMode, TextStyle
from classes.osd_renderer import OSDRenderer


pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize("mode", ["fast", "balanced", "quality"])
def test_small_labels_scale_with_resolution_and_have_a_readable_floor(mode):
    renderer = OSDTextRenderer(640, 480, performance_mode=mode)
    sizes = []
    for width, height in [(640, 480), (1280, 720), (1920, 1080)]:
        renderer.update_frame_size(width, height)
        size = renderer.get_text_size("AGL: 12.3", 0.4)
        sizes.append(size)
        assert renderer.calculate_font_size(0.4) >= round(16 * height / 480)
        sprite = renderer.render_text_sprite("AGL: 12.3", (50, 50), font_scale=0.4)
        assert sprite is not None
        assert sprite.bgr_premult.shape[1] >= size[0]
    assert sizes[1][1] > sizes[0][1]
    assert sizes[2][1] > sizes[1][1]


def test_fast_mode_measurement_matches_actual_font_and_top_left_origin():
    renderer = OSDTextRenderer(1280, 720, performance_mode="fast")
    scale, thickness = renderer._opencv_font_metrics(0.4)
    expected, _ = cv2.getTextSize("ALT: 12.3", cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    assert renderer.get_text_size("ALT: 12.3", 0.4) == expected
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame = renderer.render_text(frame, "ALT: 12.3", (50, 50), font_scale=0.4,
                                 style=TextStyle.PLAIN)
    ys, _ = np.nonzero(np.max(frame, axis=2))
    assert ys.min() >= 48
    assert ys.max() > 50


def test_switching_mode_does_not_reuse_other_font_measurements():
    renderer = OSDTextRenderer(1280, 720, performance_mode="balanced")
    renderer.get_text_size("TARGET", 0.4)
    renderer.performance_mode = PerformanceMode.FAST
    scale, thickness = renderer._opencv_font_metrics(0.4)
    expected, _ = cv2.getTextSize("TARGET", cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    assert renderer.get_text_size("TARGET", 0.4) == expected


def test_changing_telemetry_does_not_grow_measurement_cache_without_bound():
    renderer = OSDTextRenderer(1280, 720, performance_mode="fast")
    for value in range(1000):
        renderer.get_text_size(f"ALT: {value}", 0.4)
    assert len(renderer.text_size_cache) <= 512


def test_preset_offsets_scale_with_the_text_not_just_the_anchors():
    renderer = OSDRenderer()
    config = {"anchor": "center-left", "offset": [12, -80]}
    renderer.sync_frame_size((480, 640, 3))
    small = renderer._calculate_position(config)
    renderer.sync_frame_size((720, 1280, 3))
    large = renderer._calculate_position(config)
    assert small[0] - 32 == 12
    assert large[0] - 64 == 18
    assert large[1] - 360 == -120

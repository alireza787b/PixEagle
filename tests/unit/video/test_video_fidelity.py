"""Source detail, analysis coordinates and displayed overlays stay independent."""
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from classes.parameters import Parameters
from classes.video_geometry import FrameScale, fit_dimensions, resize_pixels
from classes.video_handler import VideoHandler
from classes.trackers.base_tracker import BaseTracker
from classes.segmentor import Segmentor


def video_handler(native=True):
    with patch.object(Parameters, 'NATIVE_CAPTURE_RESOLUTION', native, create=True):
        return VideoHandler(initialize_source=False)


def test_native_rtsp_keeps_source_caps_in_all_fallbacks():
    handler = video_handler()
    for pipeline in [handler._build_gstreamer_rtsp_pipeline(), *handler._build_fallback_rtsp_pipelines()]:
        assert 'width=' not in pipeline
        assert 'height=' not in pipeline
        assert 'videoscale' not in pipeline
        assert 'format=BGR' in pipeline
    assert 'width=' not in handler._build_gstreamer_file_pipeline()


def test_legacy_rtsp_retains_explicit_capture_size_with_filtered_scaling():
    pipeline = video_handler(native=False)._build_gstreamer_rtsp_pipeline()
    assert 'width=640,height=480' in pipeline
    assert 'method=1' in pipeline
    assert 'method=0' not in pipeline


def test_native_orientation_keeps_analysis_geometry_and_source_pixels():
    handler = video_handler()
    source = np.zeros((1080, 1920, 3), np.uint8)
    oriented = handler._apply_frame_orientation(source)
    assert oriented.shape == (1080, 1920, 3)
    assert (handler.source_width, handler.source_height) == (1920, 1080)
    assert (handler.width, handler.height) == (640, 480)
    analysis = handler.analysis_frame(oriented)
    assert analysis.shape == (480, 640, 3)
    stream = handler.resize_frame(oriented, 1280, 720)
    assert stream.shape == (720, 1280, 3)
    # Full-frame scaling has different x/y ratios, preserving old tracker coordinates.
    assert FrameScale.between(analysis.shape, stream.shape).point(320, 240) == (640, 360)


def test_rotated_native_frame_maps_whole_analysis_without_padding():
    handler = video_handler()
    handler._frame_rotation_deg = 90
    source = np.zeros((1080, 1920, 3), np.uint8)
    oriented = handler._apply_frame_orientation(source)
    assert oriented.shape == (1920, 1080, 3)
    assert handler.analysis_frame(oriented).shape == (640, 480, 3)
    assert handler.resize_frame(oriented, 1280, 720).shape == (720, 405, 3)


def test_downscale_integrates_fine_detail_instead_of_aliasing():
    checker = (np.indices((100, 100)).sum(axis=0) % 2 * 255).astype(np.uint8)
    result = resize_pixels(checker, 10, 10)
    assert np.all((result >= 127) & (result <= 128))
    assert fit_dimensions(1920, 1080, 640, 480) == (640, 360)
    assert fit_dimensions(320, 240, 1280, 720) == (320, 240)


def test_classic_overlay_draws_scaled_geometry_without_mutating_tracker_state():
    tracker = SimpleNamespace(
        bbox=(100, 100, 200, 100),
        video_handler=SimpleNamespace(width=640, height=480),
    )
    tracker._display_scale = lambda frame: BaseTracker._display_scale(tracker, frame)
    display = np.full((720, 1280, 3), 77, dtype=np.uint8)
    BaseTracker.draw_normal_bbox(tracker, display)
    assert tuple(display[150, 200]) == (255, 0, 0)
    assert tuple(display[300, 600]) == (255, 0, 0)
    assert tuple(display[200, 400]) == (77, 77, 77)
    assert tracker.bbox == (100, 100, 200, 100)


def test_segmentation_overlay_keeps_source_detail_and_analysis_boxes():
    source = np.full((720, 1280, 3), 99, dtype=np.uint8)
    result = SimpleNamespace(
        masks=None,
        boxes=SimpleNamespace(xyxy=np.array([[100, 100, 300, 200]])),
    )
    rendered = Segmentor._render_display(result, (480, 640, 3), source)
    assert tuple(rendered[150, 200]) == (0, 220, 100)
    np.testing.assert_array_equal(rendered[400:, :], source[400:, :])
    assert np.all(source == 99)

"""SmartTracker command-freshness metadata tests."""

import os
import sys
from types import SimpleNamespace


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from classes.detection_adapter import NormalizedDetection
from classes.smart_tracker import SmartTracker


def _smart_tracker_stub():
    tracker = object.__new__(SmartTracker)
    tracker.app_controller = SimpleNamespace(
        video_handler=SimpleNamespace(width=640, height=480)
    )
    tracker.labels = {0: "target"}
    tracker.conf_threshold = 0.3
    tracker.fps_display = 30
    tracker.last_frame_processing_ms = 0.0
    tracker._frame_errors = 0
    tracker._frame_count = 1
    tracker._geometry_errors = 0
    tracker.tracker_type_str = "bytetrack"
    tracker.runtime_info = {"backend": "test", "effective_device": "cpu"}
    tracker.model_task = "detect"
    tracker.current_geometry_mode = "aabb"
    tracker._obb_auto_disabled = False
    tracker.backend = SimpleNamespace(backend_name="test_backend")
    tracker.geometry_output_mode = "hybrid"
    tracker.model_task_policy = "auto"
    tracker.selected_class_id = 0
    tracker.selected_oriented_bbox = None
    tracker.selected_polygon = None
    return tracker


def test_smart_tracker_prediction_only_output_is_not_command_usable():
    tracker = _smart_tracker_stub()
    tracker.selected_object_id = 7
    tracker.selected_bbox = (100, 100, 150, 150)
    tracker.selected_center = (125, 125)
    tracker.last_detections = []
    tracker._last_tracking_state_result = {
        "track_id": 7,
        "prediction_only": True,
        "frames_predicted": 4,
    }

    output = SmartTracker.get_output(tracker)

    assert output.tracking_active is True
    assert output.raw_data["prediction_only"] is True
    assert output.raw_data["data_is_stale"] is True
    assert output.raw_data["usable_for_following"] is False
    assert output.raw_data["freshness_reason"] == "prediction_only"


def test_smart_tracker_confirmed_detection_output_is_command_usable():
    tracker = _smart_tracker_stub()
    tracker.selected_object_id = 7
    tracker.selected_bbox = (100, 100, 150, 150)
    tracker.selected_center = (125, 125)
    tracker.last_detections = [
        NormalizedDetection(
            track_id=7,
            class_id=0,
            confidence=0.9,
            aabb_xyxy=(100, 100, 150, 150),
            center_xy=(125, 125),
        )
    ]
    tracker._last_tracking_state_result = {"track_id": 7}

    output = SmartTracker.get_output(tracker)

    assert output.tracking_active is True
    assert output.raw_data["usable_for_following"] is True
    assert output.raw_data["data_is_stale"] is False
    assert output.raw_data["freshness_reason"] == "measurement"

"""Segmentation analysis/display and detection-coordinate regressions."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from pathlib import Path

import numpy as np
import yaml

from classes.segmentor import Segmentor


def test_runtime_algorithms_match_canonical_catalog():
    catalog_path = Path(__file__).resolve().parents[3] / "configs" / "segmentation_models.yaml"
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))

    assert list(catalog["models"]) == [
        Segmentor.DISABLED_ALGORITHM,
        *Segmentor.SUPPORTED_ALGORITHMS,
    ]


class _Boxes:
    def __init__(self, rows):
        self.xyxy = SimpleNamespace(tolist=lambda: rows)


class _Result:
    def __init__(self, rows, annotated_frame):
        self.boxes = _Boxes(rows)
        self._annotated_frame = annotated_frame

    def plot(self):
        return self._annotated_frame.copy()


def _yolo_segmentor(rows, annotated_frame):
    segmentor = Segmentor(algorithm="disabled")
    segmentor.requested_algorithm = "yolov8n-seg"
    segmentor.algorithm = "yolov8n-seg"
    segmentor.unavailable_reason = None
    segmentor.model = MagicMock(
        return_value=[_Result(rows, annotated_frame)]
    )
    return segmentor


def test_yolo_segmentation_keeps_analysis_input_clean_and_publishes_xyxy():
    analysis_frame = np.zeros((80, 120, 3), dtype=np.uint8)
    annotated_frame = np.full_like(analysis_frame, 127)
    segmentor = _yolo_segmentor(
        [[10.2, 20.1, 40.4, 60.2, 0.9, 2]],
        annotated_frame,
    )

    displayed = segmentor.segment_frame(analysis_frame)

    assert np.all(analysis_frame == 0)
    assert np.array_equal(displayed, annotated_frame)
    assert segmentor.get_last_detections() == [
        (10.2, 20.1, 40.4, 60.2)
    ]


def test_repeated_stable_detection_remains_selectable_on_every_frame():
    frame = np.zeros((80, 120, 3), dtype=np.uint8)
    box = [10.0, 20.0, 40.0, 60.0]
    segmentor = _yolo_segmentor([box], frame)

    segmentor.segment_frame(frame)
    first = segmentor.get_last_detections()
    segmentor.segment_frame(frame)
    second = segmentor.get_last_detections()

    assert first == [(10.0, 20.0, 40.0, 60.0)]
    assert second == first


def test_detection_extraction_clips_bounds_and_rejects_malformed_boxes():
    frame = np.zeros((80, 120, 3), dtype=np.uint8)
    segmentor = _yolo_segmentor(
        [
            [-5, 10, 130, 90],
            [20, 20, 20, 30],
            [1, 2, 3],
            ["bad", 2, 10, 20],
            [1, 2, float("nan"), 20],
        ],
        frame,
    )

    segmentor.segment_frame(frame)

    assert segmentor.get_last_detections() == [(0.0, 10.0, 120.0, 80.0)]


def test_inference_failure_clears_old_detections_and_returns_clean_copy():
    frame = np.zeros((20, 30, 3), dtype=np.uint8)
    segmentor = _yolo_segmentor([[1, 2, 10, 12]], frame)
    segmentor.segment_frame(frame)
    segmentor.model.side_effect = RuntimeError("inference failed")

    displayed = segmentor.segment_frame(frame)

    assert segmentor.get_last_detections() == []
    assert np.array_equal(displayed, frame)
    assert displayed is not frame


def test_disabled_segmentor_is_truthful_and_never_returns_input_alias():
    import classes.segmentor as segmentor_module

    frame = np.zeros((20, 30, 3), dtype=np.uint8)
    segmentor = Segmentor(algorithm="disabled")
    segmentor._last_detections = [(1.0, 2.0, 10.0, 12.0)]

    displayed = segmentor.segment_frame(frame)

    assert segmentor.get_capability_status() == {
        "available": False,
        "requested_algorithm": "disabled",
        "active_algorithm": "disabled",
        "unavailable_reason": "disabled_by_config",
        "supported_algorithms": list(Segmentor.SUPPORTED_ALGORITHMS),
        "ultralytics_available": bool(segmentor_module.ULTRALYTICS_AVAILABLE),
    }
    assert segmentor.get_last_detections() == []
    assert np.array_equal(displayed, frame)
    assert displayed is not frame


def test_unknown_segmentation_algorithm_is_not_advertised_as_available():
    segmentor = Segmentor(algorithm="Watershed")

    status = segmentor.get_capability_status()

    assert status["available"] is False
    assert status["requested_algorithm"] == "watershed"
    assert status["active_algorithm"] == "disabled"
    assert status["unavailable_reason"] == "unsupported_algorithm"


def test_segmentation_model_name_normalizes_one_weight_suffix(monkeypatch):
    import classes.segmentor as segmentor_module

    model = MagicMock()
    yolo_factory = MagicMock(return_value=model)
    monkeypatch.setattr(segmentor_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(segmentor_module, "YOLO", yolo_factory)

    segmentor = Segmentor(algorithm="YOLOv8n-seg.pt")

    yolo_factory.assert_called_once_with("yolov8n-seg.pt")
    assert segmentor.available is True
    assert segmentor.requested_algorithm == "yolov8n-seg"
    assert segmentor.algorithm == "yolov8n-seg"

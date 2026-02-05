from types import SimpleNamespace

from classes.detection_adapter import detect_result_mode, normalize_results, to_tracking_state_rows


def _fake_boxes_result():
    boxes = SimpleNamespace(
        data=[[0, 0, 10, 10, 1, 0.8, 2]],
        xyxy=[[0, 0, 10, 10]],
        conf=[0.8],
        cls=[2],
        id=[1],
    )
    return SimpleNamespace(boxes=boxes, obb=None)


def _fake_obb_result():
    obb = SimpleNamespace(
        data=[[10, 10, 8, 4, 0.1, 1, 0.9, 3]],
        xywhr=[[10.0, 10.0, 8.0, 4.0, 0.1]],
        conf=[0.9],
        cls=[3],
        id=[1],
        xyxyxyxy=[[[6, 8], [14, 8], [14, 12], [6, 12]]],
    )
    return SimpleNamespace(boxes=None, obb=obb)


def test_detect_result_mode_detect():
    r = _fake_boxes_result()
    assert detect_result_mode(r) == "detect"


def test_detect_result_mode_obb():
    r = _fake_obb_result()
    assert detect_result_mode(r) == "obb"


def test_normalize_detect_results():
    mode, detections = normalize_results([_fake_boxes_result()])
    assert mode == "detect"
    assert len(detections) == 1
    d = detections[0]
    assert d.geometry_type == "aabb"
    assert d.track_id == 1
    assert d.class_id == 2
    assert d.aabb_xyxy == (0, 0, 10, 10)


def test_normalize_obb_results():
    mode, detections = normalize_results([_fake_obb_result()])
    assert mode == "obb"
    assert len(detections) == 1
    d = detections[0]
    assert d.geometry_type == "obb"
    assert d.track_id == 1
    assert d.class_id == 3
    assert d.obb_xywhr is not None


def test_to_tracking_state_rows():
    _, detections = normalize_results([_fake_boxes_result()])
    rows = to_tracking_state_rows(detections)
    assert len(rows) == 1
    assert rows[0][4] == 1
    assert rows[0][6] == 2

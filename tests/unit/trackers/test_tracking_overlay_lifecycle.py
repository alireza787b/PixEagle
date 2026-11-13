"""Display rendering must tolerate a target being cleared during OpenCV drawing."""
from types import MethodType, SimpleNamespace

import cv2
import numpy as np
import pytest

from classes.parameters import Parameters
from classes.trackers.base_tracker import BaseTracker


@pytest.mark.parametrize('style', ['normal', 'fancy'])
@pytest.mark.parametrize('event', ['clear', 'retarget'])
def test_overlay_finishes_one_geometry_snapshot_during_target_change(monkeypatch, style, event):
    tracker = SimpleNamespace(bbox=(100, 100, 80, 60), center=(140, 130),
        video_handler=SimpleNamespace(width=640, height=480),
        app_controller=SimpleNamespace(following_active=False))
    for name in ('_display_scale', 'draw_tracking', 'draw_normal_bbox', 'draw_fancy_bbox'):
        setattr(tracker, name, MethodType(getattr(BaseTracker, name), tracker))
    monkeypatch.setattr(Parameters, 'TRACKED_BBOX_STYLE', style)
    monkeypatch.setattr(Parameters, 'DISPLAY_DEVIATIONS', False)
    actual_line, actual_rectangle = cv2.line, cv2.rectangle
    changed = False

    def change_once(draw):
        def wrapped(*args, **kwargs):
            nonlocal changed
            if not changed:
                changed = True
                tracker.bbox = None if event == 'clear' else (400, 300, 40, 40)
                tracker.center = None if event == 'clear' else (420, 320)
            return draw(*args, **kwargs)
        return wrapped

    monkeypatch.setattr(cv2, 'line', change_once(actual_line))
    monkeypatch.setattr(cv2, 'rectangle', change_once(actual_rectangle))
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    assert tracker.draw_tracking(frame) is frame
    assert changed
    assert tuple(frame[130, 140]) == (0, 255, 0)
    assert tuple(frame[320, 420]) == (0, 0, 0)
    assert tracker.center == (None if event == 'clear' else (420, 320))

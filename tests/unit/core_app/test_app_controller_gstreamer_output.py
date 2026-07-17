"""Frame-layer contract for the optional QGC/GCS UDP output."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from classes.app_controller import AppController
from classes.parameters import Parameters


pytestmark = [pytest.mark.unit]


def _submission_recorder(calls, *, tagged=False, copy_frame=False):
    def submit(frame, submitted_at, prepared):
        recorded_frame = frame.copy() if copy_frame else frame
        if tagged:
            calls.append(("submit", submitted_at, prepared, recorded_frame))
        else:
            calls.append((recorded_frame, submitted_at, prepared))
        return True

    return submit


def _due_recorder(calls):
    def frame_due(submitted_at):
        calls.append(("due", submitted_at))
        return True

    return frame_due


def _controller():
    controller = AppController.__new__(AppController)
    controller.osd_pipeline = SimpleNamespace(
        compose=lambda frame: pytest.fail("browser OSD pipeline must remain independent")
    )
    controller.gstreamer_osd_pipeline = SimpleNamespace(compose=lambda frame: frame + 7)
    return controller


def test_gstreamer_output_can_explicitly_exclude_osd(monkeypatch):
    monkeypatch.setattr(Parameters, "GSTREAMER_INCLUDE_OSD", False, raising=False)
    calls = []

    controller = _controller()
    controller.gstreamer_handler = SimpleNamespace(
        is_frame_due=lambda submitted_at: True,
        prepare_frame_for_osd=lambda frame: pytest.fail("OSD preparation must be skipped"),
        stream_frame=_submission_recorder(calls),
    )
    raw = np.zeros((4, 4, 3), dtype=np.uint8)

    submitted = controller._submit_gstreamer_output_frame(frame=raw)

    assert submitted is True
    assert calls[0][0] is raw
    assert calls[0][2] is False


def test_gstreamer_output_composes_after_aspect_preserving_normalization(monkeypatch):
    monkeypatch.setattr(Parameters, "GSTREAMER_INCLUDE_OSD", True, raising=False)
    calls = []

    controller = _controller()
    raw = np.zeros((4, 4, 3), dtype=np.uint8)
    normalized = np.full((6, 8, 3), 3, dtype=np.uint8)
    controller.gstreamer_handler = SimpleNamespace(
        is_frame_due=lambda submitted_at: True,
        prepare_frame_for_osd=lambda frame: normalized.copy(),
        stream_frame=_submission_recorder(calls, copy_frame=True),
    )

    submitted = controller._submit_gstreamer_output_frame(frame=raw)

    assert submitted is True
    assert np.all(calls[0][0] == 10)
    assert calls[0][0].shape == normalized.shape
    assert calls[0][2] is True
    assert np.all(raw == 0)


def test_gstreamer_output_skips_osd_work_when_frame_is_not_due(monkeypatch):
    controller = _controller()
    compose_calls = []
    controller.gstreamer_osd_pipeline = SimpleNamespace(
        compose=lambda frame: compose_calls.append(frame)
    )
    controller.gstreamer_handler = SimpleNamespace(
        is_frame_due=lambda submitted_at: False,
        stream_frame=lambda *args, **kwargs: pytest.fail("frame must not be submitted"),
    )
    monkeypatch.setattr("classes.app_controller.time.monotonic", lambda: 12.5)

    submitted = controller._submit_gstreamer_output_frame(
        frame=np.zeros((4, 4, 3), dtype=np.uint8),
    )

    assert submitted is False
    assert compose_calls == []


def test_gstreamer_output_uses_same_timestamp_for_due_check_and_submit(monkeypatch):
    calls = []

    controller = _controller()
    controller.gstreamer_handler = SimpleNamespace(
        is_frame_due=_due_recorder(calls),
        stream_frame=_submission_recorder(calls, tagged=True, copy_frame=True),
    )
    monkeypatch.setattr(Parameters, "GSTREAMER_INCLUDE_OSD", False, raising=False)
    monkeypatch.setattr("classes.app_controller.time.monotonic", lambda: 22.0)
    raw = np.zeros((4, 4, 3), dtype=np.uint8)

    submitted = controller._submit_gstreamer_output_frame(
        frame=raw,
    )

    assert submitted is True
    assert calls[0] == ("due", 22.0)
    assert calls[1][0:2] == ("submit", 22.0)
    assert calls[1][2] is False
    assert np.array_equal(calls[1][3], raw)

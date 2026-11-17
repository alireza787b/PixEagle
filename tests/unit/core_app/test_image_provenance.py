"""Actual output builders retain the captured pixels' immutable provenance."""

from dataclasses import replace
import json
import threading
import time
from types import MethodType

import numpy as np
import pytest

from classes.app_controller import AppController
from classes.frame_publisher import FramePublisher
from classes.guidance_observation import ImageMeasurement
from classes.smart_tracker import SmartTracker
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.video_handler import VideoHandler
from tests.unit.trackers.test_base_tracker import ConcreteTracker
from tests.unit.trackers.test_smart_tracker_freshness import _smart_tracker_stub


@pytest.fixture
def controller():
    owner = object.__new__(AppController)
    owner._tracker_model_state_lock = threading.RLock()
    owner._tracking_session_generation = 3
    owner.video_handler = VideoHandler(initialize_source=False)
    owner.video_handler._frame_rotation_deg = 0
    owner.video_handler._frame_flip_mode = 'none'
    owner.frame_publisher = FramePublisher()
    owner.video_handler.set_source_listener(owner.frame_publisher.invalidate_source)
    owner.estimator = None
    owner.tracker = ConcreteTracker(owner.video_handler, app_controller=owner)
    owner.tracker.get_output = lambda: owner.tracker._build_output('fixture')
    owner.tracker.start_tracking(np.zeros((480, 640, 3), np.uint8), (100, 80, 40, 40))
    owner.tracker.normalize_center_coordinates()
    owner.tracker.normalize_bbox()
    owner.smart_tracker = None

    def update(tracker, frame):
        tracker.last_measurement_timestamp = time.time()
        return getattr(tracker, 'accepted', True), tracker.bbox

    owner.tracker.update = MethodType(update, owner.tracker)
    return owner


def capture_context(owner, *, receipt=100.0):
    video = owner.video_handler
    frame = video._apply_frame_orientation(np.zeros((720, 1280, 3), np.uint8))
    video.current_raw_frame = frame
    video._reset_failure_counters(captured_at=receipt)
    stamp, geometry, _ = video.get_capture_context(frame)
    analysis = video.analysis_frame(frame)
    owner._publish_tracking_input_frame(analysis, capture=stamp, capture_geometry=geometry)
    return analysis, owner.tracking_input_context


def update_classic(owner, frame, context):
    owner._update_classic_tracker(frame, image_context=context)
    return owner.tracker.get_output()


def smart_tracker(owner):
    tracker = _smart_tracker_stub()
    tracker.app_controller = owner
    tracker.selected_object_id = 7
    tracker.selected_bbox = (100, 80, 140, 120)
    tracker.selected_center = (120, 100)
    tracker.last_detections = []
    tracker._last_tracking_state_result = {}
    tracker._last_measurement_current = True
    tracker.track_and_draw = lambda frame, **kwargs: frame
    owner.smart_tracker = tracker
    return tracker


def test_classic_accepted_frame_retains_exact_identity_without_calibration_or_polling_refresh(controller, monkeypatch):
    frame, context = capture_context(controller)
    output = update_classic(controller, frame, context)
    measurement = output.image_measurement
    assert measurement is not None and measurement.measured
    assert measurement.pixel_xy == (120.0, 100.0)
    assert measurement.image_size_px == (frame.shape[1], frame.shape[0])
    assert measurement.provenance is context.provenance
    assert measurement.provenance.capture.captured_at == 100.0
    assert measurement.provenance.calibration_revision is None
    assert measurement.image_to_calibration is None
    monkeypatch.setattr('classes.trackers.base_tracker.time.time', lambda: 5000.0)
    polled = controller.tracker.get_output()
    assert polled.timestamp == output.timestamp
    assert polled.image_measurement is measurement


def test_later_capture_does_not_relabel_an_in_flight_result(controller):
    frame, original = capture_context(controller)
    capture_context(controller, receipt=101.0)
    output = update_classic(controller, frame, original)
    assert output.image_measurement.provenance.capture is original.provenance.capture
    assert output.image_measurement.provenance.capture.captured_at == 100.0


def test_classic_adapter_without_its_own_clock_commits_one_output_time(controller, monkeypatch):
    controller.tracker.last_measurement_timestamp = None
    controller.tracker.update = lambda frame: (True, controller.tracker.bbox)
    frame, context = capture_context(controller)
    output = update_classic(controller, frame, context)
    monkeypatch.setattr('classes.trackers.base_tracker.time.time', lambda: 5000.0)
    polled = controller.tracker.get_output()
    assert output.image_measurement is not None
    assert polled.timestamp == output.timestamp
    assert polled.image_measurement is output.image_measurement


def test_uncommitted_new_pixels_cannot_inherit_the_previous_capture_stamp(controller):
    capture_context(controller)
    committed = controller.video_handler.current_raw_frame
    arriving = np.ones_like(committed)
    controller.video_handler.current_raw_frame = arriving
    stamp, geometry, _ = controller.video_handler.get_capture_context(arriving)
    assert stamp.capture_id is None and geometry is None
    original, _, _ = controller.video_handler.get_capture_context(committed)
    assert original.captured_at == 100.0


def test_classic_exception_cannot_refresh_measurement_time(controller):
    frame, context = capture_context(controller)
    previous = update_classic(controller, frame, context)
    frame, context = capture_context(controller, receipt=101.0)

    def fail(tracker, frame):
        tracker.last_measurement_timestamp = 5000.0
        raise RuntimeError('inference failed')

    controller.tracker.update = MethodType(fail, controller.tracker)
    with pytest.raises(RuntimeError, match='inference failed'):
        controller._update_classic_tracker(frame, image_context=context)
    assert controller.tracker.get_output().image_measurement is None
    assert controller.tracker.get_output().timestamp == previous.timestamp


@pytest.mark.parametrize('failure', ['repeated', 'cached', 'prediction', 'rejected'])
def test_non_measurements_cannot_renew_classic_identity_or_timestamp(controller, failure):
    frame, context = capture_context(controller)
    previous = update_classic(controller, frame, context)
    if failure != 'repeated':
        frame, context = capture_context(controller, receipt=101.0)
    if failure == 'cached':
        provenance = replace(context.provenance, capture=replace(context.provenance.capture, state='cached'))
        context = replace(context, provenance=provenance)
    elif failure == 'prediction':
        controller.tracker.failure_count = 1
    elif failure == 'rejected':
        controller.tracker.accepted = False
    output = update_classic(controller, frame, context)
    assert output.image_measurement is None
    assert output.timestamp == previous.timestamp


def test_retarget_cannot_rebind_old_pixels_to_the_new_generation(controller):
    frame, context = capture_context(controller)
    update_classic(controller, frame, context)
    controller._advance_tracking_session_generation()
    assert controller.tracker.get_output().image_measurement is None
    stamp, geometry, _ = controller.video_handler.get_capture_context(controller.video_handler.current_raw_frame)
    controller._publish_tracking_input_frame(frame, capture=stamp, capture_geometry=geometry)
    assert controller.tracking_input_context is context
    assert update_classic(controller, frame, context).image_measurement is None
    frame, following = capture_context(controller, receipt=101.0)
    output = update_classic(controller, frame, following)
    assert output.image_measurement.provenance.target_generation == 4


def test_source_epoch_change_refuses_old_context_and_retired_pixels(controller):
    frame, context = capture_context(controller)
    update_classic(controller, frame, context)
    original = controller.video_handler.current_raw_frame
    controller.video_handler._advance_source_epoch()
    assert controller.tracker.get_output().image_measurement is None
    stamp, geometry, _ = controller.video_handler.get_capture_context(original)
    assert stamp.capture_id is None and geometry is None
    assert update_classic(controller, frame, context).image_measurement is None
    frame, following = capture_context(controller, receipt=101.0)
    output = update_classic(controller, frame, following)
    assert output.image_measurement.provenance.capture.source_epoch != context.provenance.capture.source_epoch


def test_geometry_is_captured_atomically_and_dimension_change_cannot_reuse_context(controller):
    frame, context = capture_context(controller)
    original = controller.video_handler.current_raw_frame
    controller.video_handler._frame_rotation_deg = 90
    stamp, geometry, _ = controller.video_handler.get_capture_context(original)
    assert geometry == (1280, 720, 0, 'none')
    assert stamp is not None
    assert update_classic(controller, frame[:200], context).image_measurement is None
    frame, following = capture_context(controller, receipt=101.0)
    assert following.provenance.geometry_revision != context.provenance.geometry_revision


def test_typed_result_returned_by_update_matches_later_output_poll(controller):
    frame, context = capture_context(controller)

    def update(tracker, frame):
        tracker.last_measurement_timestamp = 200.0
        return True, tracker.get_output()

    controller.tracker.update = MethodType(update, controller.tracker)
    _, output = controller._update_classic_tracker(frame, image_context=context)
    assert output.image_measurement is not None
    assert controller.tracker.get_output().image_measurement is output.image_measurement


def test_external_gimbal_output_remains_independent_of_video_capture(controller):
    frame, context = capture_context(controller)
    output = TrackerOutput(TrackerDataType.GIMBAL_ANGLES, 200.0, True, angular=(1.0, 2.0, 3.0))
    controller.tracker.is_external_tracker = True
    controller.tracker.update = lambda frame: (True, output)
    _, observed = controller._update_classic_tracker(frame, image_context=context)
    assert observed is output
    assert output.image_measurement is None
    assert output.timestamp == 200.0


def test_smart_measurement_and_override_share_the_same_original_capture(controller, monkeypatch):
    tracker = smart_tracker(controller)
    controller.tracker.override_active = True
    frame, context = capture_context(controller)
    controller._track_and_draw_smart_frame(frame, image_context=context)
    first = SmartTracker.get_output(tracker)
    assert first.image_measurement is not None
    assert first.image_measurement.provenance is context.provenance
    assert controller.tracker.image_measurement is first.image_measurement
    assert controller.tracker.get_output().timestamp == first.timestamp
    monkeypatch.setattr('classes.smart_tracker.time.time', lambda: 5000.0)
    assert SmartTracker.get_output(tracker).timestamp == first.timestamp
    assert SmartTracker.get_output(tracker).image_measurement is first.image_measurement
    controller._track_and_draw_smart_frame(frame, image_context=context)
    assert SmartTracker.get_output(tracker).image_measurement is None
    assert SmartTracker.get_output(tracker).timestamp == first.timestamp
    assert not SmartTracker.get_output(tracker).raw_data['usable_for_following']


@pytest.mark.parametrize('state', ['prediction', 'cached', 'retarget'])
def test_smart_non_measurements_cannot_renew_time_or_identity(controller, state):
    tracker = smart_tracker(controller)
    frame, context = capture_context(controller)
    controller._track_and_draw_smart_frame(frame, image_context=context)
    previous = SmartTracker.get_output(tracker)
    if state == 'retarget':
        controller._advance_tracking_session_generation()
    else:
        frame, context = capture_context(controller, receipt=101.0)
        if state == 'prediction':
            tracker._last_measurement_current = False
            tracker._last_tracking_state_result = {'prediction_only': True}
        else:
            context = replace(context, provenance=replace(
                context.provenance, capture=replace(context.provenance.capture, state='cached'),
            ))
    controller._track_and_draw_smart_frame(frame, image_context=context)
    output = SmartTracker.get_output(tracker)
    assert output.image_measurement is None
    assert output.timestamp == previous.timestamp
    assert not output.raw_data['usable_for_following']


def test_smart_unexpected_exception_revokes_previous_current_evidence(controller):
    tracker = smart_tracker(controller)
    controller.tracker.override_active = True
    frame, context = capture_context(controller)
    controller._track_and_draw_smart_frame(frame, image_context=context)
    previous = SmartTracker.get_output(tracker)
    frame, context = capture_context(controller, receipt=101.0)

    def fail(frame, **kwargs):
        tracker.last_measurement_timestamp = 5000.0
        raise RuntimeError('unexpected inference failure')

    tracker.track_and_draw = fail
    with pytest.raises(RuntimeError, match='unexpected inference failure'):
        controller._track_and_draw_smart_frame(frame, image_context=context)
    output = SmartTracker.get_output(tracker)
    assert not tracker._last_measurement_current
    assert not output.raw_data['usable_for_following']
    assert output.image_measurement is None
    assert output.timestamp == previous.timestamp
    assert controller.tracker.image_measurement is None


def test_first_slow_smart_measurement_does_not_use_creation_time_as_measurement_age(controller, monkeypatch):
    tracker = smart_tracker(controller)
    tracker._output_initialized_at = 1.0
    tracker.last_measurement_timestamp = None
    monkeypatch.setattr('classes.smart_tracker.time.time', lambda: 5000.0)
    frame, context = capture_context(controller)

    controller._track_and_draw_smart_frame(frame, image_context=context)

    output = SmartTracker.get_output(tracker)
    assert output.raw_data['usable_for_following']
    assert output.timestamp == 5000.0
    assert output.image_measurement.provenance.capture.captured_at == 100.0


def test_unusable_video_wrapper_removes_measured_metadata(controller):
    frame, context = capture_context(controller)
    output = update_classic(controller, frame, context)
    blocked = controller._with_unusable_tracker_metadata(output, reason='video_stalled')
    assert blocked.image_measurement is None
    assert blocked.timestamp == output.timestamp
    assert output.image_measurement is not None


def test_json_round_trip_preserves_frozen_metadata_and_does_not_mutate_input(controller):
    frame, context = capture_context(controller)
    output = update_classic(controller, frame, context)
    encoded = json.loads(json.dumps(output.to_dict()))
    original = json.loads(json.dumps(encoded))
    decoded = TrackerOutput.from_dict(encoded)
    assert isinstance(decoded.image_measurement, ImageMeasurement)
    assert decoded.image_measurement == output.image_measurement
    assert decoded.image_measurement.provenance.capture.captured_at == 100.0
    assert encoded == original
    encoded['image_measurement']['provenance']['time_basis'] = 'sensor_exposure'
    with pytest.raises(ValueError, match='image_time_basis_invalid'):
        TrackerOutput.from_dict(encoded)

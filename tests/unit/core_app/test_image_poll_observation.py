"""Capture progress and atomic image reads use the real capture/controller path."""

import asyncio
import threading
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest

from classes.app_controller import AppController
from classes.flow_controller import FlowController
from classes.frame_publisher import FramePublisher
from classes.following_readiness import evaluate_following_start_readiness
from classes.parameters import Parameters
from classes.tracker_output import TrackerDataType, TrackerOutput
from classes.video_handler import VideoHandler


@pytest.fixture
def image_owner(monkeypatch):
    monkeypatch.setattr(Parameters, 'VIDEO_SOURCE_TYPE', 'UDP_STREAM')
    video = VideoHandler(initialize_source=False)
    video.cap = Mock(isOpened=Mock(return_value=True))
    video._async_capture_thread = Mock(is_alive=Mock(return_value=True))
    video._async_latest_frame = np.zeros((48, 64, 3), np.uint8)
    video._async_latest_frame_sequence = 1
    video._async_latest_frame_time = time.time()
    video._async_latest_capture_monotonic = 100.
    ctrl = object.__new__(AppController)
    ctrl._tracker_model_state_lock = threading.RLock()
    ctrl._tracking_session_generation = 0
    ctrl.following_active = False
    ctrl.shutdown_flag = False
    ctrl.tracking_started = True
    ctrl.smart_mode_active = False
    ctrl.smart_tracker = None
    ctrl.video_handler = video
    ctrl.frame_publisher = FramePublisher()
    video.set_source_listener(ctrl.frame_publisher.invalidate_source)
    frame = video._get_async_udp_frame()
    stamp, geometry, signature = video.get_capture_context(frame)
    ctrl._publish_tracking_input_frame(frame, capture=stamp, capture_geometry=geometry,
                                       capture_source_signature=signature)
    output = TrackerOutput(TrackerDataType.POSITION_2D, time.time(), True,
                           position_2d=(.1, .1), raw_data={'usable_for_following': True})
    output.image_measurement = ctrl.tracking_input_context.at_pixel((20., 20.))
    ctrl.tracker = SimpleNamespace(is_external_tracker=False, get_output=Mock(return_value=output), update=Mock())
    ctrl._commit_tracking_image_measurement(ctrl.tracker, output, ctrl.tracking_input_context, (20., 20.))
    ctrl.follower = None
    ctrl.offboard_commander = SimpleNamespace(command_ttl_s=.5)
    clock = [100.]
    monkeypatch.setattr('classes.app_controller.time', SimpleNamespace(time=time.time, monotonic=lambda: clock[0]))
    yield SimpleNamespace(ctrl=ctrl, video=video, output=output, frame=frame, stamp=stamp, clock=clock)
    video._async_capture_thread = None
    video.release()


def readiness(owner):
    return evaluate_following_start_readiness(owner.ctrl,
        runtime_status={'usable_for_following': True, 'active_tracking': True})


def test_normal_async_poll_without_new_capture_preserves_the_exact_original_receipt(image_owner):
    o = image_owner
    cached = o.video._get_async_udp_frame()
    receipt = o.video.get_capture_stamp(cached)
    assert receipt.capture_id == o.stamp.capture_id
    assert receipt.captured_at == o.stamp.captured_at == 100.
    assert receipt.source_epoch == o.stamp.source_epoch and receipt.state == 'cached'
    assert o.video.get_frame_status()['awaiting_new_capture'] is True
    assert o.video.get_frame_status()['usable_for_following'] is False
    assert o.video._consecutive_failures == 0


def test_no_new_poll_keeps_start_readiness_without_restamping_a_measurement(image_owner):
    o = image_owner
    old = o.output.image_measurement
    timestamp = o.output.timestamp
    o.video._get_async_udp_frame()
    o.clock[0] += .03
    assert readiness(o)['usable_for_following'] is True
    assert o.output.image_measurement is old and o.output.timestamp == timestamp
    assert o.video.get_capture_stamp().captured_at == 100.
    o.ctrl.tracker.update.assert_not_called()


def test_command_freshness_keeps_only_the_qualified_original_after_no_new_poll(image_owner):
    o = image_owner
    o.video._get_async_udp_frame()
    old = o.output.image_measurement
    timestamp = o.output.timestamp
    o.clock[0] += .03
    result = o.ctrl._apply_command_freshness_contract(o.output)
    assert result is o.output and result.tracking_active
    assert result.image_measurement is old and result.timestamp == timestamp
    assert o.video.get_frame_status()['usable_for_following'] is False


@pytest.mark.parametrize('change', ['cached', 'restamped', 'capture', 'prediction', 'expired'])
def test_command_freshness_does_not_qualify_other_cached_or_prediction_outputs(image_owner, change):
    o = image_owner
    o.video._get_async_udp_frame()
    candidate = replace(o.output)
    if change in ('cached', 'capture'):
        measurement = candidate.image_measurement
        capture = measurement.provenance.capture
        capture = replace(capture, **({'state': 'cached'} if change == 'cached' else {'capture_id': 'other'}))
        candidate.image_measurement = replace(measurement, provenance=replace(measurement.provenance, capture=capture))
    elif change == 'restamped':
        candidate.timestamp += .01
    elif change == 'prediction':
        candidate.raw_data = {'usable_for_following': False, 'prediction_only': True}
    else:
        o.clock[0] = 100.251
    result = o.ctrl._apply_command_freshness_contract(candidate)
    assert not result.tracking_active and result.image_measurement is None


@pytest.mark.parametrize('failure', ['dead', 'closed', 'stopped', 'stale'])
def test_unhealthy_async_capture_cannot_reuse_the_waiting_observation(image_owner, failure):
    o = image_owner
    if failure == 'dead':
        o.video._async_capture_thread.is_alive.return_value = False
    elif failure == 'closed':
        o.video.cap.isOpened.return_value = False
    elif failure == 'stopped':
        o.video._async_capture_stop.set()
    else:
        o.video._async_latest_frame_time -= o.video._connection_timeout + 1.
    o.video._get_async_udp_frame()
    assert o.video.get_frame_status()['awaiting_new_capture'] is False
    assert readiness(o)['usable_for_following'] is False
    assert not o.ctrl._apply_command_freshness_contract(o.output).tracking_active


@pytest.mark.parametrize('change', ['age', 'future', 'source', 'target', 'context', 'measurement', 'shutdown'])
def test_retained_readiness_does_not_survive_an_invalid_original_observation(image_owner, change):
    o = image_owner
    o.video._get_async_udp_frame()
    if change == 'age':
        o.clock[0] = 100.251
    elif change == 'future':
        o.clock[0] = 99.99
    elif change == 'source':
        o.video._advance_source_epoch(clear_frames=True)
    elif change == 'target':
        o.ctrl._tracking_session_generation += 1
    elif change == 'context':
        o.ctrl.tracking_input_context = None
    elif change == 'measurement':
        o.ctrl._commit_tracking_image_measurement(o.ctrl.tracker, o.output, o.ctrl.tracking_input_context,
                                                  None, success=False)
    else:
        o.ctrl.shutdown_flag = True
    assert readiness(o)['usable_for_following'] is False


@pytest.mark.parametrize('smart_active', [False, True])
def test_api_read_cannot_see_the_middle_of_a_measurement_commit(image_owner, smart_active):
    o = image_owner
    o.ctrl.smart_tracker = SimpleNamespace(get_output=Mock(return_value=o.output))
    o.ctrl.smart_mode_active = smart_active
    if smart_active:
        o.ctrl._commit_tracking_image_measurement(o.ctrl.smart_tracker, o.output, o.ctrl.tracking_input_context,
                                                  (20., 20.))
    entered = threading.Event()
    started = threading.Event()
    result = []
    finished = threading.Event()
    old = o.output.image_measurement
    o.ctrl.tracker.get_output.side_effect = lambda: (entered.set(), o.output)[1]
    def read():
        started.set()
        result.append(o.ctrl.get_tracker_output().image_measurement)
        finished.set()
    with o.ctrl._tracker_model_state_lock:
        o.output.image_measurement = None
        worker = threading.Thread(target=read)
        worker.start()
        assert started.wait(1.)
        try:
            assert finished.wait(.1), 'readiness must not wait for image inference'
            assert not entered.is_set(), 'reader observed in-progress tracker state'
        finally:
            o.output.image_measurement = old
    worker.join(1.)
    assert not worker.is_alive() and result == [old]


def test_waiting_status_never_recurses_through_the_public_tracker_getter(image_owner):
    o = image_owner
    o.video._get_async_udp_frame()
    o.ctrl.get_tracker_output = Mock(side_effect=AssertionError('recursive freshness read'))
    assert o.ctrl._get_video_frame_status_for_following()['retained_measurement_usable'] is True
    o.ctrl.get_tracker_output.assert_not_called()


@pytest.mark.parametrize('waiting', [True, False])
def test_flow_does_not_feed_cached_pixels_back_into_image_inference(waiting):
    status = dict(source='cached', usable_for_following=False, awaiting_new_capture=waiting)
    ctrl = SimpleNamespace(shutdown_flag=False, video_handler=SimpleNamespace(
        delay_frame=1, get_frame=lambda: np.zeros((2, 2, 3), np.uint8), get_frame_status=lambda: status),
        update_loop=AsyncMock(), show_current_frame=Mock(), handle_video_frame_unavailable=AsyncMock(),
        handle_video_frame_no_new_capture=AsyncMock())
    async def finish(_status):
        ctrl.shutdown_flag = True
    expected = ctrl.handle_video_frame_no_new_capture if waiting else ctrl.handle_video_frame_unavailable
    expected.side_effect = finish
    flow = object.__new__(FlowController)
    flow.controller = ctrl
    flow._flow_frame_count = 0
    flow._pipeline_mode = 'REALTIME'
    with patch('classes.flow_controller.time.sleep'), patch.object(FlowController, '_shutdown', return_value=None):
        flow.main_loop()
    expected.assert_awaited_once_with(status)
    ctrl.update_loop.assert_not_called()


async def test_no_new_image_poll_pumps_actions_without_reissuing_image_intents(image_owner):
    o = image_owner
    o.ctrl._capture_app_event_loop = Mock()
    o.ctrl._dispatch_tracker_output_on_flight_loop = AsyncMock()
    o.ctrl._last_continuity_dispatch_at = 99.9
    pumped = []
    asyncio.get_running_loop().call_soon(pumped.append, 'pending-action')
    await o.ctrl.handle_video_frame_no_new_capture({'awaiting_new_capture': True})
    assert pumped == ['pending-action']
    assert o.ctrl._last_continuity_dispatch_at == 99.9
    o.ctrl.tracker.update.assert_not_called()
    o.ctrl._dispatch_tracker_output_on_flight_loop.assert_not_called()


@pytest.mark.parametrize('following', [True, False])
async def test_video_independent_tracker_still_updates_on_a_no_new_image_poll(image_owner, following):
    o = image_owner
    o.ctrl.following_active = following
    o.ctrl._capture_app_event_loop = Mock()
    o.ctrl.tracker.is_external_tracker = True
    o.ctrl.tracker.get_capabilities = lambda: {'requires_video': False}
    o.ctrl.tracker.update.return_value = True, o.output
    o.ctrl._dispatch_tracker_output_on_flight_loop = AsyncMock(return_value=True)
    async def run(operation):
        return await operation()
    o.ctrl._run_on_flight_event_loop = run
    await o.ctrl.handle_video_frame_no_new_capture({'awaiting_new_capture': True})
    o.ctrl.tracker.update.assert_called_once_with(None)
    if following:
        o.ctrl._dispatch_tracker_output_on_flight_loop.assert_awaited_once_with(o.output, expected_session_epoch=0)
    else:
        o.ctrl._dispatch_tracker_output_on_flight_loop.assert_not_called()


@pytest.mark.parametrize('source', ['RTSP_STREAM', 'VIDEO_FILE'])
def test_genuine_failure_or_file_boundary_does_not_claim_to_be_waiting(image_owner, monkeypatch, source):
    monkeypatch.setattr(Parameters, 'VIDEO_SOURCE_TYPE', source)
    image_owner.video._get_cached_frame(reason='video_file_eof_stopped' if source == 'VIDEO_FILE' else 'frame_read_failed')
    assert image_owner.video.get_frame_status().get('awaiting_new_capture') is not True
    assert readiness(image_owner)['usable_for_following'] is False

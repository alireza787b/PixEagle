"""Capture identity follows the opened handle, never requested fallback intent."""

from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
import yaml

from classes.parameters import Parameters
from classes.video_handler import VideoHandler
from classes.capture_timing import SourceSampleStamp


@pytest.fixture
def handler(monkeypatch):
    previous = Parameters.get_runtime_config_snapshot()
    defaults = yaml.safe_load((Path(__file__).resolve().parents[3] / 'configs/config_default.yaml').read_text())
    Parameters.publish_config_mapping(defaults)
    owner = VideoHandler(initialize_source=False)
    try:
        yield owner
    finally:
        owner.release()
        Parameters.publish_config_mapping(previous)


def capture(backend='FFMPEG'):
    result = Mock(name='capture')
    result.getBackendName.return_value = backend
    result.isOpened.return_value = True
    return result


def opened(handler, monkeypatch, *, locator='rtsp://camera/stream', backend='FFMPEG'):
    result = capture(backend)
    monkeypatch.setattr(cv2, 'VideoCapture', Mock(return_value=result))
    return handler._open_capture(locator, cv2.CAP_FFMPEG, source_type='RTSP_OPENCV')


def test_identity_is_opaque_and_only_the_accepted_frame_receives_it(handler, monkeypatch):
    handle = opened(handler, monkeypatch, locator='rtsp://admin:private-secret@camera/stream')
    signature = handler._capture_source_signature(handle)
    assert signature.startswith('sha256-v1:') and len(signature) == 74
    assert 'private-secret' not in repr(handler._capture_identities)
    handler.cap = handle
    frame = np.zeros((480, 640, 3), np.uint8)
    handler.current_raw_frame = frame
    handler._reset_failure_counters(captured_at=100.)
    stamp, geometry, stored_signature = handler.get_capture_context(frame)
    assert stamp.state == 'fresh' and stored_signature == signature
    assert geometry == (640, 480, 0, 'none')
    assert handler.get_capture_context(frame.copy())[2] is None
    handler._get_cached_frame(reason='source_stalled')
    cached = handler._frame_cache[-1]
    cached_stamp, _, cached_signature = handler.get_capture_context(cached)
    assert cached_stamp.capture_id == stamp.capture_id
    assert cached_stamp.captured_at == 100.
    assert cached_stamp.state == 'cached' and cached_signature == signature


def test_cached_source_time_retains_original_sample_without_renewing_it(handler, monkeypatch):
    handler.cap = opened(handler, monkeypatch)
    frame = np.zeros((2, 2, 3), np.uint8)
    sample = SourceSampleStamp('world-clock', 'provider', 1, 1_000_000, 'gazebo_sim_us')
    handler.current_raw_frame = frame
    handler._reset_failure_counters(captured_at=100., source_sample=sample)
    current = handler.get_capture_stamp(frame)
    cached_frame = handler._get_cached_frame(reason='awaiting_new_capture')
    cached = handler.get_capture_stamp(cached_frame)
    assert cached.source_sample == current.source_sample == sample
    assert cached.captured_at == current.captured_at == 100.
    assert cached.state == 'cached'


def test_exited_async_reader_uses_shared_backoff_and_explicit_release_stays_stopped(handler, monkeypatch):
    monkeypatch.setattr(Parameters, 'VIDEO_SOURCE_TYPE', 'GAZEBO_CAMERA')
    reconnect = Mock(return_value=True)
    monkeypatch.setattr(handler, 'reconnect', reconnect)
    handler._async_capture_generation = 1
    handler._async_capture_thread = None
    handler._async_capture_stop.clear()
    handler._get_async_capture_frame()
    assert reconnect.call_count == 1
    assert handler._next_recovery_time > 0
    handler._get_async_capture_frame()
    assert reconnect.call_count == 1
    handler.release()
    handler._next_recovery_time = 0.
    handler._get_async_capture_frame()
    assert reconnect.call_count == 1


def test_capture_path_changes_and_release_do_not_reuse_another_handle_identity(handler, monkeypatch):
    first = opened(handler, monkeypatch, locator='rtsp://camera/first')
    first_signature = handler._capture_source_signature(first)
    second = opened(handler, monkeypatch, locator='rtsp://camera/second', backend='GSTREAMER')
    assert handler._capture_source_signature(second) != first_signature
    handler._release_capture_object(first)
    assert handler._capture_source_signature(first) is None
    assert handler._capture_source_signature(second) is not None
    handler._release_capture_object(second)
    assert not handler._capture_identities


def test_missing_backend_identity_never_guesses_from_requested_gstreamer(handler, monkeypatch):
    handle = capture()
    handle.getBackendName.side_effect = RuntimeError('metadata unsupported')
    monkeypatch.setattr(cv2, 'VideoCapture', Mock(return_value=handle))
    assert handler._open_capture('pipeline', cv2.CAP_GSTREAMER, source_type='CUSTOM_GSTREAMER') is handle
    assert handler._capture_source_signature(handle) is None


@pytest.mark.parametrize('mutation_succeeds', [False, True])
def test_even_uncertain_capture_mode_mutation_revokes_identity_and_previous_pixels(handler, monkeypatch, mutation_succeeds):
    handle = opened(handler, monkeypatch)
    handler.cap = handle
    old_frame = np.zeros((480, 640, 3), np.uint8)
    handler.current_raw_frame = old_frame
    handler._reset_failure_counters(captured_at=100.)
    epoch = handler.get_capture_stamp(old_frame).source_epoch
    handle.get.side_effect = [800, 600] if mutation_succeeds else [640, 480]
    assert handler.set_frame_size(800, 600) is mutation_succeeds
    assert handler._capture_source_signature(handle) is None
    assert handler._source_epoch != epoch
    assert handler.get_capture_context(old_frame)[0].capture_id is None


def test_fast_capture_rejects_pixels_returned_by_a_retired_handle(handler, monkeypatch):
    handle = opened(handler, monkeypatch)
    replacement = capture()
    handler.cap = handle
    monkeypatch.setattr(Parameters, 'USE_GSTREAMER', False)
    monkeypatch.setattr(Parameters, 'OPENCV_BUFFER_SIZE', 1)

    def late_retrieve():
        handler.cap = replacement
        return True, np.zeros((480, 640, 3), np.uint8)

    handle.retrieve.side_effect = late_retrieve
    assert handler.get_frame_fast() is None
    assert handler.get_frame_status()['reason'] == 'capture_replaced_during_fast_read'
    assert handler.get_capture_stamp().capture_id is None
    replacement.retrieve.assert_not_called()
    handler._release_capture_object(handle)


def test_fast_capture_requires_new_grab_even_when_backend_buffering_is_zero(handler, monkeypatch):
    handle = opened(handler, monkeypatch)
    handler.cap = handle
    handle.grab.return_value = True
    handle.retrieve.return_value = (True, np.zeros((480, 640, 3), np.uint8))
    monkeypatch.setattr(Parameters, 'USE_GSTREAMER', False)
    monkeypatch.setattr(Parameters, 'OPENCV_BUFFER_SIZE', 0)
    assert handler.get_frame_fast() is not None
    handle.grab.assert_called_once()


def test_fast_udp_uses_the_existing_async_owner_instead_of_another_read(handler, monkeypatch):
    handle = opened(handler, monkeypatch)
    handler.cap = handle
    monkeypatch.setattr(Parameters, 'USE_GSTREAMER', True)
    monkeypatch.setattr(Parameters, 'VIDEO_SOURCE_TYPE', 'UDP_STREAM')
    handler.get_frame = Mock(return_value=None)
    assert handler.get_frame_fast() is None
    handler.get_frame.assert_called_once()
    handle.grab.assert_not_called()
    handle.retrieve.assert_not_called()


@pytest.mark.parametrize('fast', [False, True])
def test_same_handle_epoch_change_during_read_cannot_stamp_old_pixels_fresh(handler, monkeypatch, fast):
    handle = opened(handler, monkeypatch)
    handler.cap = handle
    monkeypatch.setattr(Parameters, 'VIDEO_SOURCE_TYPE', 'RTSP_OPENCV')
    monkeypatch.setattr(Parameters, 'USE_GSTREAMER', False)
    monkeypatch.setattr(Parameters, 'OPENCV_BUFFER_SIZE', 1)

    def retired_read(*args):
        handler._advance_source_epoch(clear_frames=True)
        return True, np.zeros((480, 640, 3), np.uint8)

    handle.grab.return_value = True
    handle.retrieve.side_effect = retired_read
    monkeypatch.setattr(handler, '_read_next_capture_frame', retired_read)
    assert (handler.get_frame_fast() if fast else handler.get_frame()) is None
    assert handler.get_capture_stamp().capture_id is None


@pytest.mark.parametrize('fast', [False, True])
def test_size_change_at_read_unlock_does_not_relabel_the_previous_pixels(handler, monkeypatch, fast):
    handle = opened(handler, monkeypatch)
    handler.cap = handle
    monkeypatch.setattr(Parameters, 'VIDEO_SOURCE_TYPE', 'RTSP_OPENCV')
    monkeypatch.setattr(Parameters, 'USE_GSTREAMER', False)
    monkeypatch.setattr(Parameters, 'OPENCV_BUFFER_SIZE', 1)
    frame = np.zeros((480, 640, 3), np.uint8)
    handle.grab.return_value = True
    handle.retrieve.return_value = (True, frame)
    handle.get.side_effect = [800, 600]
    monkeypatch.setattr(handler, '_read_next_capture_frame', Mock(return_value=(True, frame)))

    class MutateOnceAtUnlock:
        pending = True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            if self.pending:
                self.pending = False
                assert handler.set_frame_size(800, 600)

    handler._capture_read_lock = MutateOnceAtUnlock()
    result = handler.get_frame_fast() if fast else handler.get_frame()
    assert handler.get_capture_context(result)[0].capture_id is None
    assert handler.get_frame_status()['usable_for_following'] is False


def test_async_udp_mode_change_requires_reopen_and_preserves_the_unmutated_source(handler, monkeypatch):
    handle = opened(handler, monkeypatch)
    handler.cap = handle
    monkeypatch.setattr(Parameters, 'USE_GSTREAMER', True)
    monkeypatch.setattr(Parameters, 'VIDEO_SOURCE_TYPE', 'UDP_STREAM')
    frame = np.zeros((480, 640, 3), np.uint8)
    handler.current_raw_frame = frame
    handler._reset_failure_counters(captured_at=100.)
    previous = handler.get_capture_context(frame)
    assert handler.set_frame_size(800, 600) is False
    handle.set.assert_not_called()
    assert handler.get_capture_context(frame) == previous

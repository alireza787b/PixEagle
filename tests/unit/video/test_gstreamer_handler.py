"""Focused tests for the optional QGC H.264/RTP/UDP output."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from classes.gstreamer_handler import EncoderDetector, EncoderInfo, GStreamerHandler
from classes.parameters import Parameters


pytestmark = [pytest.mark.unit]


class FakeWriter:
    def __init__(self, opened: bool = True) -> None:
        self.opened = opened
        self.frames: list[np.ndarray] = []
        self.released = False
        self.frame_written = threading.Event()

    def isOpened(self) -> bool:
        return self.opened and not self.released

    def write(self, frame: np.ndarray) -> None:
        self.frames.append(frame.copy())
        self.frame_written.set()

    def release(self) -> None:
        self.released = True


class StuckThread:
    def join(self, timeout=None) -> None:
        return None

    def is_alive(self) -> bool:
        return True


class BlockingReleaseWriter(FakeWriter):
    def __init__(self) -> None:
        super().__init__(opened=True)
        self.release_started = threading.Event()
        self.allow_release = threading.Event()

    def release(self) -> None:
        self.release_started.set()
        self.allow_release.wait(timeout=2.0)
        super().release()


class ReleaseProbeWriter(BlockingReleaseWriter):
    def __init__(self) -> None:
        super().__init__()
        self.is_opened_calls_during_release = 0

    def isOpened(self) -> bool:
        if self.release_started.is_set() and not self.allow_release.is_set():
            self.is_opened_calls_during_release += 1
        return super().isOpened()


class FailOnceReleaseWriter(FakeWriter):
    def __init__(self) -> None:
        super().__init__()
        self.release_attempts = 0

    def release(self) -> None:
        self.release_attempts += 1
        if self.release_attempts == 1:
            raise RuntimeError("transient release failure")
        super().release()


class RaisingWriteWriter(FakeWriter):
    def write(self, frame: np.ndarray) -> None:
        self.frame_written.set()
        raise RuntimeError("write failed")


@pytest.fixture(autouse=True)
def gstreamer_parameters(monkeypatch):
    values = {
        "ENABLE_HARDWARE_ENCODING": False,
        "GSTREAMER_WIDTH": 320,
        "GSTREAMER_HEIGHT": 240,
        "GSTREAMER_FRAMERATE": 15,
        "GSTREAMER_BITRATE": 2000,
        "GSTREAMER_TUNE": "zerolatency",
        "GSTREAMER_KEY_INT_MAX": 30,
        "GSTREAMER_SPEED_PRESET": "ultrafast",
        "GSTREAMER_HOST": "192.0.2.20",
        "GSTREAMER_PORT": 5600,
        "GSTREAMER_BUFFER_SIZE": 50000000,
    }
    for name, value in values.items():
        monkeypatch.setattr(Parameters, name, value, raising=False)
    EncoderDetector._cached_result = None
    yield
    EncoderDetector._cached_result = None


def test_output_pipeline_is_qgc_compatible_rtp_h264():
    handler = GStreamerHandler()

    assert "appsrc" in handler.pipeline
    assert "x264enc" in handler.pipeline
    assert "rtph264pay config-interval=1 pt=96" in handler.pipeline
    assert 'udpsink host="192.0.2.20" port=5600' in handler.pipeline


def test_output_pipeline_normalizes_bracketed_ipv6_destination(monkeypatch):
    monkeypatch.setattr(Parameters, "GSTREAMER_HOST", "[2001:db8::20]", raising=False)

    handler = GStreamerHandler()

    assert 'udpsink host="2001:db8::20" port=5600' in handler.pipeline
    assert handler.encoder_status["host"] == "2001:db8::20"


@pytest.mark.parametrize(
    ("parameter", "value", "message"),
    [
        ("GSTREAMER_HOST", '192.0.2.20" ! filesink location=/tmp/x', "IP address or DNS hostname"),
        ("GSTREAMER_WIDTH", 321, "must be even"),
        ("GSTREAMER_WIDTH", 4096, "range 16..3840"),
        ("GSTREAMER_TUNE", "not-a-tune", "not supported"),
    ],
)
def test_invalid_output_configuration_fails_closed(monkeypatch, parameter, value, message):
    monkeypatch.setattr(Parameters, parameter, value, raising=False)
    writer_called = False

    def video_writer(*args, **kwargs):
        nonlocal writer_called
        writer_called = True
        return FakeWriter()

    monkeypatch.setattr("classes.gstreamer_handler.cv2.VideoWriter", video_writer)
    handler = GStreamerHandler()

    assert handler.pipeline == ""
    assert handler.initialize_stream() is False
    assert writer_called is False
    assert handler.encoder_status["last_error"] == "invalid_gstreamer_configuration"
    assert message in handler.encoder_status["configuration_error"]


def test_initialize_fails_closed_when_opencv_has_no_gstreamer(monkeypatch):
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.getBuildInformation",
        lambda: "Video I/O:\n    GStreamer: NO\n",
    )
    writer_called = False

    def video_writer(*args, **kwargs):
        nonlocal writer_called
        writer_called = True
        return FakeWriter()

    monkeypatch.setattr("classes.gstreamer_handler.cv2.VideoWriter", video_writer)
    handler = GStreamerHandler()

    assert handler.initialize_stream() is False
    assert writer_called is False
    assert handler.encoder_status["enabled"] is False
    assert handler.encoder_status["last_error"] == "opencv_gstreamer_backend_unavailable"


def test_reinitialize_refuses_to_overlap_a_stuck_previous_writer(monkeypatch):
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.getBuildInformation",
        lambda: "Video I/O:\n    GStreamer: YES (1.22.0)\n",
    )
    writer_called = False

    def video_writer(*args, **kwargs):
        nonlocal writer_called
        writer_called = True
        return FakeWriter()

    monkeypatch.setattr("classes.gstreamer_handler.cv2.VideoWriter", video_writer)
    handler = GStreamerHandler()
    handler.out = FakeWriter(opened=True)
    handler._writer_thread = StuckThread()

    assert handler.initialize_stream() is False
    assert handler.initialize_stream() is False
    assert writer_called is False
    assert handler.encoder_status["last_error"] == "writer_thread_stop_timeout"
    assert handler.out is not None


def test_output_configuration_rejects_excessive_pixel_rate(monkeypatch):
    monkeypatch.setattr(Parameters, "GSTREAMER_WIDTH", 3840, raising=False)
    monkeypatch.setattr(Parameters, "GSTREAMER_HEIGHT", 2160, raising=False)
    monkeypatch.setattr(Parameters, "GSTREAMER_FRAMERATE", 16, raising=False)

    handler = GStreamerHandler()

    assert handler.initialize_stream() is False
    assert "pixel-rate budget" in handler.encoder_status["configuration_error"]


def test_hardware_open_failure_retries_with_software_encoder(monkeypatch):
    monkeypatch.setattr(
        EncoderDetector,
        "detect",
        classmethod(
            lambda cls, allow_hardware=True: EncoderInfo(
                encoder="nvh264enc",
                needs_nvvidconv=False,
                hardware=True,
            )
        ),
    )
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.getBuildInformation",
        lambda: "Video I/O:\n    GStreamer: YES (1.22.0)\n",
    )
    writers = [FakeWriter(opened=False), FakeWriter(opened=True)]
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.VideoWriter",
        lambda *args, **kwargs: writers.pop(0),
    )
    handler = GStreamerHandler()

    assert handler.initialize_stream() is True
    assert handler.encoder_info.encoder == "x264enc"
    assert handler.encoder_info.hardware is False
    assert handler.encoder_status["enabled"] is True
    assert handler.release() is True


def test_failed_pipeline_open_uses_bounded_finalization(monkeypatch):
    writer = BlockingReleaseWriter()
    writer.opened = False
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.getBuildInformation",
        lambda: "Video I/O:\n    GStreamer: YES (1.22.0)\n",
    )
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.VideoWriter",
        lambda *args, **kwargs: writer,
    )
    handler = GStreamerHandler()
    handler._PIPELINE_RELEASE_TIMEOUT_S = 0.02

    started = time.monotonic()
    assert handler.initialize_stream() is False
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert writer.release_started.is_set()
    assert handler.encoder_status["last_error"] == "pipeline_release_timeout"
    release_thread = handler._release_thread
    assert release_thread is not None
    writer.allow_release.set()
    release_thread.join(timeout=1.0)


def test_stream_frame_normalizes_bgra_float_and_dimensions(monkeypatch):
    writer = FakeWriter(opened=True)
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.getBuildInformation",
        lambda: "Video I/O:\n    GStreamer: YES (1.22.0)\n",
    )
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.VideoWriter",
        lambda *args, **kwargs: writer,
    )
    handler = GStreamerHandler()
    assert handler.initialize_stream() is True

    frame = np.full((120, 160, 4), 300.0, dtype=np.float32)
    handler.stream_frame(frame)

    assert writer.frame_written.wait(timeout=1.0)
    assert writer.frames[0].shape == (240, 320, 3)
    assert writer.frames[0].dtype == np.uint8
    assert writer.frames[0].flags.c_contiguous is True
    assert int(writer.frames[0].max()) == 255
    assert handler.encoder_status["frames_resized"] == 1
    assert handler.encoder_status["frames_written"] == 1
    assert handler.release() is True


def test_stream_frame_preserves_aspect_ratio_with_letterboxing(monkeypatch):
    writer = FakeWriter(opened=True)
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.getBuildInformation",
        lambda: "Video I/O:\n    GStreamer: YES (1.22.0)\n",
    )
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.VideoWriter",
        lambda *args, **kwargs: writer,
    )
    handler = GStreamerHandler()
    assert handler.initialize_stream() is True

    handler.stream_frame(np.full((120, 200, 3), 255, dtype=np.uint8), submitted_at=1.0)

    assert writer.frame_written.wait(timeout=1.0)
    output = writer.frames[0]
    assert np.all(output[:24] == 0)
    assert np.all(output[24:216] == 255)
    assert np.all(output[216:] == 0)
    assert handler.encoder_status["frames_letterboxed"] == 1
    assert handler.release() is True


def test_osd_preparation_detaches_an_already_normalized_source_frame():
    handler = GStreamerHandler()
    source = np.zeros((240, 320, 3), dtype=np.uint8)

    prepared = handler.prepare_frame_for_osd(source)

    assert prepared is not None
    assert not np.shares_memory(prepared, source)
    prepared[:] = 255
    assert np.all(source == 0)


def test_stream_frame_enforces_configured_submission_cadence(monkeypatch):
    writer = FakeWriter(opened=True)
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.getBuildInformation",
        lambda: "Video I/O:\n    GStreamer: YES (1.22.0)\n",
    )
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.VideoWriter",
        lambda *args, **kwargs: writer,
    )
    handler = GStreamerHandler()
    assert handler.initialize_stream() is True
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    assert handler.stream_frame(frame, submitted_at=10.0) is True
    assert handler.stream_frame(frame, submitted_at=10.01) is False

    assert writer.frame_written.wait(timeout=1.0)
    assert handler.encoder_status["frames_rate_limited"] == 1
    assert handler.release() is True


def test_writer_failure_disables_status_and_records_error(monkeypatch):
    writer = RaisingWriteWriter(opened=True)
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.getBuildInformation",
        lambda: "Video I/O:\n    GStreamer: YES (1.22.0)\n",
    )
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.VideoWriter",
        lambda *args, **kwargs: writer,
    )
    handler = GStreamerHandler()
    assert handler.initialize_stream() is True

    assert handler.stream_frame(np.zeros((240, 320, 3), dtype=np.uint8)) is True
    assert writer.frame_written.wait(timeout=1.0)
    handler._writer_thread.join(timeout=1.0)

    assert handler.encoder_status["enabled"] is False
    assert handler.encoder_status["last_error"] == "frame_write_failed:RuntimeError"
    assert handler.release() is True


def test_stream_frame_rejects_unsupported_shape_without_queueing():
    handler = GStreamerHandler()
    handler.out = FakeWriter(opened=True)

    handler.stream_frame(np.zeros((2, 3, 5), dtype=np.uint8))

    assert handler.encoder_status["frames_queued"] == 0
    assert handler.encoder_status["last_error"] == "unsupported_frame_shape"


def test_release_is_bounded_when_opencv_finalization_stalls():
    writer = BlockingReleaseWriter()
    handler = GStreamerHandler()
    handler.out = writer
    handler._PIPELINE_RELEASE_TIMEOUT_S = 0.02

    started = time.monotonic()
    assert handler.release() is False
    elapsed = time.monotonic() - started

    assert writer.release_started.is_set()
    assert elapsed < 0.5
    assert handler.encoder_status["last_error"] == "pipeline_release_timeout"
    assert handler.encoder_status["cleanup_pending"] is True
    assert handler.out is writer

    release_thread = handler._release_thread
    assert release_thread is not None
    writer.allow_release.set()
    release_thread.join(timeout=1.0)
    assert handler.release() is True
    assert handler.out is None


def test_encoder_status_does_not_probe_writer_during_async_release():
    writer = ReleaseProbeWriter()
    handler = GStreamerHandler()
    handler.out = writer
    handler._PIPELINE_RELEASE_TIMEOUT_S = 0.02

    assert handler.release() is False
    assert writer.release_started.is_set()

    status = handler.encoder_status

    assert status["enabled"] is False
    assert status["cleanup_pending"] is True
    assert writer.is_opened_calls_during_release == 0

    release_thread = handler._release_thread
    assert release_thread is not None
    writer.allow_release.set()
    release_thread.join(timeout=1.0)
    assert not release_thread.is_alive()
    assert handler.release() is True


def test_release_failure_retains_ownership_and_can_be_retried():
    writer = FailOnceReleaseWriter()
    handler = GStreamerHandler()
    handler.out = writer

    assert handler.release() is False
    assert handler.out is writer
    assert handler.encoder_status["cleanup_pending"] is True
    assert handler.encoder_status["last_error"] == "pipeline_release_failed:RuntimeError"

    assert handler.release() is True
    assert writer.release_attempts == 2
    assert handler.out is None
    assert handler.encoder_status["cleanup_pending"] is False
    assert handler.encoder_status["last_error"] is None


def test_concurrent_initialization_serializes_writer_generation_ownership(monkeypatch):
    monkeypatch.setattr(
        "classes.gstreamer_handler.cv2.getBuildInformation",
        lambda: "Video I/O:\n    GStreamer: YES (1.22.0)\n",
    )
    writers: list[FakeWriter] = []
    writer_lock = threading.Lock()
    live_generations = 0
    max_live_generations = 0

    class GenerationCountingWriter(FakeWriter):
        def __init__(self) -> None:
            nonlocal live_generations, max_live_generations
            super().__init__(opened=True)
            with writer_lock:
                live_generations += 1
                max_live_generations = max(max_live_generations, live_generations)

        def release(self) -> None:
            nonlocal live_generations
            with writer_lock:
                if not self.released:
                    live_generations -= 1
            super().release()

    def create_writer(*args, **kwargs):
        time.sleep(0.05)
        writer = GenerationCountingWriter()
        with writer_lock:
            writers.append(writer)
        return writer

    monkeypatch.setattr("classes.gstreamer_handler.cv2.VideoWriter", create_writer)
    handler = GStreamerHandler()
    start_barrier = threading.Barrier(3)
    results = []

    def initialize():
        start_barrier.wait(timeout=1.0)
        results.append(handler.initialize_stream())

    threads = [threading.Thread(target=initialize) for _ in range(2)]
    for thread in threads:
        thread.start()
    start_barrier.wait(timeout=1.0)
    for thread in threads:
        thread.join(timeout=3.0)

    assert all(not thread.is_alive() for thread in threads)
    assert results == [True, True]
    assert len(writers) == 2
    assert max_live_generations == 1
    assert sum(not writer.released for writer in writers) == 1
    assert handler.out in writers
    assert handler.out.released is False
    assert handler.release() is True

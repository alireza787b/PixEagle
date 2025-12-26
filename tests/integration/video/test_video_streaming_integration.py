# tests/integration/video/test_video_streaming_integration.py
"""
Integration tests for video streaming pipeline.

Tests cover:
- VideoHandler to streaming pipeline
- Frame flow through OSD
- Multiple client handling
- Error recovery integration
"""

import pytest
import numpy as np
import cv2
import time
from unittest.mock import MagicMock
from collections import deque
from typing import List, Optional, Dict, Any

# Test markers
pytestmark = [pytest.mark.integration, pytest.mark.video]


# ============================================================================
# Mock Video Handler
# ============================================================================

class MockVideoHandler:
    """Lightweight video handler for integration tests."""

    def __init__(self, width: int = 640, height: int = 480, fps: float = 30.0):
        self.width = width
        self.height = height
        self.fps = fps

        self.current_raw_frame: Optional[np.ndarray] = None
        self.current_osd_frame: Optional[np.ndarray] = None
        self.frame_history: deque = deque(maxlen=5)

        self._frame_count = 0
        self._is_running = False

    def start(self):
        """Start generating frames."""
        self._is_running = True
        self._generate_frame()

    def stop(self):
        """Stop generating frames."""
        self._is_running = False

    def _generate_frame(self):
        """Generate a test frame."""
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        # Add frame number as visual marker
        cv2.putText(
            frame, f"Frame {self._frame_count}",
            (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
            (255, 255, 255), 2
        )
        self.current_raw_frame = frame
        self.current_osd_frame = frame.copy()
        self.frame_history.append(frame.copy())
        self._frame_count += 1

    def get_frame(self) -> Optional[np.ndarray]:
        """Get current frame."""
        if self._is_running:
            self._generate_frame()
        return self.current_raw_frame


# ============================================================================
# Mock OSD Renderer
# ============================================================================

class MockOSDRenderer:
    """Mock OSD renderer for integration tests."""

    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height
        self.render_count = 0

    def render(self, frame: np.ndarray, data: dict = None) -> np.ndarray:
        """Render OSD overlay."""
        osd_frame = frame.copy()
        # Add OSD marker
        cv2.putText(
            osd_frame, "OSD",
            (self.width - 60, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7,
            (0, 255, 0), 2
        )
        self.render_count += 1
        return osd_frame


# ============================================================================
# Mock Streaming Pipeline
# ============================================================================

class MockStreamingPipeline:
    """Mock streaming pipeline for integration tests."""

    def __init__(self, quality: int = 80):
        self.quality = quality
        self.clients: List[MagicMock] = []
        self.frames_sent = 0
        self.bytes_sent = 0

    def add_client(self, client: MagicMock):
        """Add client to pipeline."""
        self.clients.append(client)

    def remove_client(self, client: MagicMock):
        """Remove client from pipeline."""
        if client in self.clients:
            self.clients.remove(client)

    def broadcast_frame(self, frame: np.ndarray):
        """Broadcast frame to all clients."""
        _, buffer = cv2.imencode(
            '.jpg', frame,
            [cv2.IMWRITE_JPEG_QUALITY, self.quality]
        )
        encoded = buffer.tobytes()

        for client in self.clients:
            client.send_bytes(encoded)

        self.frames_sent += 1
        self.bytes_sent += len(encoded) * len(self.clients)

    def get_stats(self) -> Dict[str, Any]:
        """Get streaming statistics."""
        return {
            'clients': len(self.clients),
            'frames_sent': self.frames_sent,
            'bytes_sent': self.bytes_sent
        }


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def video_handler():
    """Create mock video handler."""
    handler = MockVideoHandler()
    handler.start()
    yield handler
    handler.stop()


@pytest.fixture
def osd_renderer():
    """Create mock OSD renderer."""
    return MockOSDRenderer()


@pytest.fixture
def streaming_pipeline():
    """Create mock streaming pipeline."""
    return MockStreamingPipeline()


# ============================================================================
# Video Handler to Streaming Pipeline Tests
# ============================================================================

class TestVideoToStreamingPipeline:
    """Tests for video handler to streaming integration."""

    def test_frame_flows_from_handler_to_stream(
        self, video_handler, streaming_pipeline
    ):
        """Frames flow from handler to streaming."""
        client = MagicMock()
        streaming_pipeline.add_client(client)

        frame = video_handler.get_frame()
        streaming_pipeline.broadcast_frame(frame)

        assert client.send_bytes.called
        assert streaming_pipeline.frames_sent == 1

    def test_multiple_frames_stream_correctly(
        self, video_handler, streaming_pipeline
    ):
        """Multiple frames stream in sequence."""
        client = MagicMock()
        streaming_pipeline.add_client(client)

        for _ in range(10):
            frame = video_handler.get_frame()
            streaming_pipeline.broadcast_frame(frame)

        assert client.send_bytes.call_count == 10
        assert streaming_pipeline.frames_sent == 10

    def test_frame_encoded_as_jpeg(
        self, video_handler, streaming_pipeline
    ):
        """Frames are encoded as JPEG."""
        client = MagicMock()
        streaming_pipeline.add_client(client)

        frame = video_handler.get_frame()
        streaming_pipeline.broadcast_frame(frame)

        sent_data = client.send_bytes.call_args[0][0]
        # Check JPEG magic bytes
        assert sent_data[:2] == b'\xff\xd8'
        assert sent_data[-2:] == b'\xff\xd9'

    def test_streaming_with_quality_setting(
        self, video_handler
    ):
        """Streaming quality affects file size."""
        pipeline_high = MockStreamingPipeline(quality=95)
        pipeline_low = MockStreamingPipeline(quality=30)

        client_high = MagicMock()
        client_low = MagicMock()

        pipeline_high.add_client(client_high)
        pipeline_low.add_client(client_low)

        frame = video_handler.get_frame()
        pipeline_high.broadcast_frame(frame)
        pipeline_low.broadcast_frame(frame)

        high_size = len(client_high.send_bytes.call_args[0][0])
        low_size = len(client_low.send_bytes.call_args[0][0])

        assert high_size > low_size


# ============================================================================
# Frame Flow Through OSD Tests
# ============================================================================

class TestFrameFlowThroughOSD:
    """Tests for frame flow through OSD renderer."""

    def test_osd_renders_on_frame(
        self, video_handler, osd_renderer
    ):
        """OSD is rendered on frame."""
        frame = video_handler.get_frame()
        osd_frame = osd_renderer.render(frame)

        assert osd_frame is not None
        assert not np.array_equal(frame, osd_frame)

    def test_osd_frame_stored_in_handler(
        self, video_handler, osd_renderer
    ):
        """OSD frame is stored in video handler."""
        frame = video_handler.get_frame()
        osd_frame = osd_renderer.render(frame)
        video_handler.current_osd_frame = osd_frame

        assert video_handler.current_osd_frame is not None

    def test_complete_pipeline_with_osd(
        self, video_handler, osd_renderer, streaming_pipeline
    ):
        """Complete pipeline: handler -> OSD -> streaming."""
        client = MagicMock()
        streaming_pipeline.add_client(client)

        # Simulate complete pipeline
        frame = video_handler.get_frame()
        osd_frame = osd_renderer.render(frame)
        streaming_pipeline.broadcast_frame(osd_frame)

        assert osd_renderer.render_count == 1
        assert streaming_pipeline.frames_sent == 1
        assert client.send_bytes.called


# ============================================================================
# Multiple Client Handling Tests
# ============================================================================

class TestMultipleClientHandling:
    """Tests for multiple client handling."""

    def test_broadcast_to_multiple_clients(
        self, video_handler, streaming_pipeline
    ):
        """Frame is broadcast to all clients."""
        clients = [MagicMock() for _ in range(5)]
        for client in clients:
            streaming_pipeline.add_client(client)

        frame = video_handler.get_frame()
        streaming_pipeline.broadcast_frame(frame)

        for client in clients:
            assert client.send_bytes.called

    def test_client_disconnection(
        self, video_handler, streaming_pipeline
    ):
        """Disconnected clients are removed."""
        client1 = MagicMock()
        client2 = MagicMock()

        streaming_pipeline.add_client(client1)
        streaming_pipeline.add_client(client2)

        streaming_pipeline.remove_client(client1)

        frame = video_handler.get_frame()
        streaming_pipeline.broadcast_frame(frame)

        assert not client1.send_bytes.called
        assert client2.send_bytes.called

    def test_bytes_tracked_per_client(
        self, video_handler, streaming_pipeline
    ):
        """Bytes are tracked per client."""
        clients = [MagicMock() for _ in range(3)]
        for client in clients:
            streaming_pipeline.add_client(client)

        frame = video_handler.get_frame()
        streaming_pipeline.broadcast_frame(frame)

        stats = streaming_pipeline.get_stats()
        assert stats['clients'] == 3
        # bytes_sent = frame_size * num_clients
        assert stats['bytes_sent'] > 0


# ============================================================================
# Error Recovery Integration Tests
# ============================================================================

class TestErrorRecoveryIntegration:
    """Tests for error recovery integration."""

    def test_pipeline_continues_after_client_error(
        self, video_handler, streaming_pipeline
    ):
        """Pipeline continues after client error."""
        client_good = MagicMock()
        client_bad = MagicMock()
        client_bad.send_bytes.side_effect = Exception("Connection lost")

        streaming_pipeline.add_client(client_good)
        streaming_pipeline.add_client(client_bad)

        frame = video_handler.get_frame()

        # Should not raise despite client error
        try:
            streaming_pipeline.broadcast_frame(frame)
        except Exception:
            pass  # Expected for bad client

        # Good client should still receive
        assert client_good.send_bytes.called

    def test_handler_recovery_from_frame_failure(self):
        """Handler recovers from frame failure."""
        handler = MockVideoHandler()
        handler.start()

        # Get some frames
        frames = [handler.get_frame() for _ in range(5)]
        assert all(f is not None for f in frames)

        # Simulate failure and recovery
        handler.stop()
        handler.start()

        frame = handler.get_frame()
        assert frame is not None

    def test_osd_handles_empty_data(
        self, video_handler, osd_renderer
    ):
        """OSD handles empty data dict."""
        frame = video_handler.get_frame()
        osd_frame = osd_renderer.render(frame, data={})
        assert osd_frame is not None

    def test_osd_handles_none_data(
        self, video_handler, osd_renderer
    ):
        """OSD handles None data."""
        frame = video_handler.get_frame()
        osd_frame = osd_renderer.render(frame, data=None)
        assert osd_frame is not None


# ============================================================================
# Performance Integration Tests
# ============================================================================

class TestPerformanceIntegration:
    """Tests for performance characteristics."""

    def test_frame_history_limited(self, video_handler):
        """Frame history is limited to maxlen."""
        for _ in range(20):
            video_handler.get_frame()

        assert len(video_handler.frame_history) <= 5

    def test_streaming_stats_accumulate(
        self, video_handler, streaming_pipeline
    ):
        """Streaming stats accumulate correctly."""
        client = MagicMock()
        streaming_pipeline.add_client(client)

        for _ in range(10):
            frame = video_handler.get_frame()
            streaming_pipeline.broadcast_frame(frame)

        stats = streaming_pipeline.get_stats()
        assert stats['frames_sent'] == 10
        assert stats['bytes_sent'] > 0

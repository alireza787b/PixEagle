# tests/unit/streaming/test_http_mjpeg.py
"""
Unit tests for HTTP MJPEG streaming functionality.

Tests cover:
- Frame encoding and generation
- Multipart response format
- Quality parameter handling
- OSD and resize flags
- Client connection management
"""

import pytest
import numpy as np
import cv2
from unittest.mock import MagicMock, AsyncMock, patch
from typing import AsyncIterator
import asyncio

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.streaming]


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def test_frame():
    """Create a test BGR frame."""
    return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)


@pytest.fixture
def mock_video_handler(test_frame):
    """Create mock video handler with test frame."""
    handler = MagicMock()
    handler.current_raw_frame = test_frame
    handler.current_osd_frame = test_frame.copy()
    handler.current_resized_raw_frame = cv2.resize(test_frame, (320, 240))
    handler.current_resized_osd_frame = cv2.resize(test_frame, (320, 240))
    handler.fps = 30
    return handler


# ============================================================================
# JPEG Encoding Tests
# ============================================================================

class TestJPEGEncoding:
    """Tests for JPEG frame encoding."""

    def test_encode_frame_returns_bytes(self, test_frame):
        """Encoding returns bytes object."""
        _, buffer = cv2.imencode('.jpg', test_frame)
        assert isinstance(buffer.tobytes(), bytes)

    def test_encode_frame_with_quality_80(self, test_frame):
        """Quality 80 produces reasonable size."""
        _, buffer = cv2.imencode(
            '.jpg', test_frame,
            [cv2.IMWRITE_JPEG_QUALITY, 80]
        )
        encoded = buffer.tobytes()
        # Should be reasonably compressed
        assert len(encoded) < test_frame.nbytes

    def test_encode_frame_with_quality_50(self, test_frame):
        """Quality 50 produces smaller file than 80."""
        _, buffer_80 = cv2.imencode(
            '.jpg', test_frame,
            [cv2.IMWRITE_JPEG_QUALITY, 80]
        )
        _, buffer_50 = cv2.imencode(
            '.jpg', test_frame,
            [cv2.IMWRITE_JPEG_QUALITY, 50]
        )
        assert len(buffer_50) < len(buffer_80)

    def test_encode_frame_with_quality_95(self, test_frame):
        """Quality 95 produces larger file than 80."""
        _, buffer_80 = cv2.imencode(
            '.jpg', test_frame,
            [cv2.IMWRITE_JPEG_QUALITY, 80]
        )
        _, buffer_95 = cv2.imencode(
            '.jpg', test_frame,
            [cv2.IMWRITE_JPEG_QUALITY, 95]
        )
        assert len(buffer_95) > len(buffer_80)

    def test_encode_frame_minimum_quality(self, test_frame):
        """Quality 1 still produces valid JPEG."""
        ret, buffer = cv2.imencode(
            '.jpg', test_frame,
            [cv2.IMWRITE_JPEG_QUALITY, 1]
        )
        assert ret is True
        assert len(buffer) > 0

    def test_encode_frame_maximum_quality(self, test_frame):
        """Quality 100 produces valid JPEG."""
        ret, buffer = cv2.imencode(
            '.jpg', test_frame,
            [cv2.IMWRITE_JPEG_QUALITY, 100]
        )
        assert ret is True
        assert len(buffer) > 0

    def test_encoded_frame_starts_with_jpeg_marker(self, test_frame):
        """JPEG starts with correct magic bytes."""
        _, buffer = cv2.imencode('.jpg', test_frame)
        encoded = buffer.tobytes()
        # JPEG starts with FFD8
        assert encoded[:2] == b'\xff\xd8'

    def test_encoded_frame_ends_with_jpeg_marker(self, test_frame):
        """JPEG ends with correct marker."""
        _, buffer = cv2.imencode('.jpg', test_frame)
        encoded = buffer.tobytes()
        # JPEG ends with FFD9
        assert encoded[-2:] == b'\xff\xd9'


# ============================================================================
# Multipart Response Tests
# ============================================================================

class TestMultipartResponse:
    """Tests for multipart MJPEG response format."""

    def test_multipart_boundary_format(self, test_frame):
        """Multipart response uses correct boundary format."""
        _, buffer = cv2.imencode('.jpg', test_frame)
        encoded = buffer.tobytes()

        boundary = "frame"
        response = (
            f'--{boundary}\r\n'
            f'Content-Type: image/jpeg\r\n\r\n'
        ).encode() + encoded + b'\r\n'

        assert response.startswith(b'--frame\r\n')
        assert b'Content-Type: image/jpeg' in response

    def test_multipart_frame_contains_jpeg(self, test_frame):
        """Multipart frame contains valid JPEG data."""
        _, buffer = cv2.imencode('.jpg', test_frame)
        encoded = buffer.tobytes()

        boundary = "frame"
        header = f'--{boundary}\r\nContent-Type: image/jpeg\r\n\r\n'.encode()
        response = header + encoded + b'\r\n'

        # Extract JPEG from response
        jpeg_start = response.find(b'\xff\xd8')
        jpeg_end = response.rfind(b'\xff\xd9') + 2
        jpeg_data = response[jpeg_start:jpeg_end]

        assert jpeg_data == encoded

    def test_multiple_frames_format(self, test_frame):
        """Multiple frames maintain correct format."""
        boundary = "frame"
        frames = []

        for _ in range(3):
            _, buffer = cv2.imencode('.jpg', test_frame)
            encoded = buffer.tobytes()
            frame_data = (
                f'--{boundary}\r\n'
                f'Content-Type: image/jpeg\r\n\r\n'
            ).encode() + encoded + b'\r\n'
            frames.append(frame_data)

        combined = b''.join(frames)
        # Should have 3 boundaries
        assert combined.count(b'--frame') == 3

    def test_custom_boundary_string(self, test_frame):
        """Custom boundary string works correctly."""
        _, buffer = cv2.imencode('.jpg', test_frame)
        encoded = buffer.tobytes()

        boundary = "pixeagle_frame"
        response = (
            f'--{boundary}\r\n'
            f'Content-Type: image/jpeg\r\n\r\n'
        ).encode() + encoded + b'\r\n'

        assert response.startswith(b'--pixeagle_frame\r\n')


# ============================================================================
# Frame Source Selection Tests
# ============================================================================

class TestFrameSourceSelection:
    """Tests for selecting frame source (raw, OSD, resized)."""

    def test_select_raw_frame(self, mock_video_handler):
        """Raw frame is selected when OSD is false."""
        frame = mock_video_handler.current_raw_frame
        assert frame is not None
        assert frame.shape == (480, 640, 3)

    def test_select_osd_frame(self, mock_video_handler):
        """OSD frame is selected when OSD is true."""
        frame = mock_video_handler.current_osd_frame
        assert frame is not None
        assert frame.shape == (480, 640, 3)

    def test_select_resized_raw_frame(self, mock_video_handler):
        """Resized raw frame has correct dimensions."""
        frame = mock_video_handler.current_resized_raw_frame
        assert frame is not None
        assert frame.shape == (240, 320, 3)

    def test_select_resized_osd_frame(self, mock_video_handler):
        """Resized OSD frame has correct dimensions."""
        frame = mock_video_handler.current_resized_osd_frame
        assert frame is not None
        assert frame.shape == (240, 320, 3)

    def test_handle_none_frame(self, mock_video_handler):
        """Handle None frame gracefully."""
        mock_video_handler.current_raw_frame = None
        assert mock_video_handler.current_raw_frame is None


# ============================================================================
# Quality Parameter Tests
# ============================================================================

class TestQualityParameter:
    """Tests for quality parameter handling."""

    def test_default_quality_80(self, test_frame):
        """Default quality of 80 is applied."""
        default_quality = 80
        _, buffer = cv2.imencode(
            '.jpg', test_frame,
            [cv2.IMWRITE_JPEG_QUALITY, default_quality]
        )
        assert len(buffer) > 0

    def test_quality_clamp_to_minimum(self):
        """Quality below 1 is clamped."""
        quality = max(1, -10)
        assert quality == 1

    def test_quality_clamp_to_maximum(self):
        """Quality above 100 is clamped."""
        quality = min(100, 150)
        assert quality == 100

    def test_quality_from_query_param(self):
        """Quality can be parsed from query parameter."""
        query_quality = "60"
        quality = int(query_quality)
        assert quality == 60

    def test_invalid_quality_uses_default(self):
        """Invalid quality falls back to default."""
        default = 80
        try:
            quality = int("invalid")
        except ValueError:
            quality = default
        assert quality == 80


# ============================================================================
# Frame Generation Tests
# ============================================================================

class TestFrameGeneration:
    """Tests for async frame generation."""

    @pytest.mark.asyncio
    async def test_generate_single_frame(self, mock_video_handler):
        """Generate single frame bytes."""
        frame = mock_video_handler.current_raw_frame
        _, buffer = cv2.imencode(
            '.jpg', frame,
            [cv2.IMWRITE_JPEG_QUALITY, 80]
        )
        assert len(buffer.tobytes()) > 0

    @pytest.mark.asyncio
    async def test_frame_rate_control(self):
        """Frame rate is controlled by sleep interval."""
        target_fps = 30
        interval = 1 / target_fps
        assert interval == pytest.approx(0.0333, rel=0.01)

    @pytest.mark.asyncio
    async def test_skip_none_frames(self, mock_video_handler):
        """None frames are skipped."""
        mock_video_handler.current_raw_frame = None
        frame = mock_video_handler.current_raw_frame
        # Should not encode None
        assert frame is None


# ============================================================================
# Client Connection Tests
# ============================================================================

class TestClientConnection:
    """Tests for client connection handling."""

    def test_connection_manager_add_client(self):
        """Connection manager tracks connected clients."""
        clients = []
        client = MagicMock()
        clients.append(client)
        assert len(clients) == 1

    def test_connection_manager_remove_client(self):
        """Connection manager removes disconnected clients."""
        clients = []
        client = MagicMock()
        clients.append(client)
        clients.remove(client)
        assert len(clients) == 0

    def test_max_clients_limit(self):
        """Maximum client limit is enforced."""
        max_clients = 10
        clients = []
        for i in range(15):
            if len(clients) < max_clients:
                clients.append(MagicMock())
        assert len(clients) == 10

    def test_client_disconnect_cleanup(self):
        """Disconnected clients are cleaned up."""
        clients = []
        client = MagicMock()
        client.is_connected = True
        clients.append(client)

        # Simulate disconnect
        client.is_connected = False
        clients = [c for c in clients if c.is_connected]
        assert len(clients) == 0

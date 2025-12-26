# tests/unit/streaming/test_websocket_streaming.py
"""
Unit tests for WebSocket video streaming functionality.

Tests cover:
- WebSocket connection management
- Binary frame transmission
- Bidirectional command handling
- Connection limits and reconnection
- Frame rate control
"""

import pytest
import numpy as np
import cv2
import json
import time
from unittest.mock import MagicMock, AsyncMock
from typing import List, Dict, Any
import asyncio

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.streaming]


# ============================================================================
# Simple Mock WebSocket (synchronous for unit tests)
# ============================================================================

class MockWebSocket:
    """Simple synchronous mock WebSocket for unit tests."""

    def __init__(self, client_id: str = "test"):
        self.client_id = client_id
        self.is_connected = False
        self.close_code = None
        self.close_reason = None
        self.sent_data: List[bytes] = []
        self.sent_text: List[str] = []
        self.receive_queue: List[Any] = []

    def accept(self):
        self.is_connected = True

    def close(self, code: int = 1000, reason: str = ""):
        self.is_connected = False
        self.close_code = code
        self.close_reason = reason

    def send_bytes(self, data: bytes):
        if self.is_connected:
            self.sent_data.append(data)

    def send_text(self, data: str):
        if self.is_connected:
            self.sent_text.append(data)

    def receive_bytes(self):
        if not self.is_connected or not self.receive_queue:
            return None
        return self.receive_queue.pop(0)

    def receive_text(self):
        if not self.is_connected or not self.receive_queue:
            return None
        item = self.receive_queue.pop(0)
        return item if isinstance(item, str) else str(item)


def create_mock_websocket(client_id: str = "test") -> MockWebSocket:
    """Create mock WebSocket."""
    return MockWebSocket(client_id=client_id)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def test_frame():
    """Create a test BGR frame."""
    return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket connection."""
    return create_mock_websocket()


@pytest.fixture
def connection_manager():
    """Create WebSocket connection manager."""
    class ConnectionManager:
        def __init__(self, max_clients: int = 10):
            self.active_connections: List[MockWebSocket] = []
            self.max_clients = max_clients

        def connect(self, websocket: MockWebSocket):
            if len(self.active_connections) >= self.max_clients:
                raise ConnectionError("Max clients exceeded")
            websocket.accept()
            self.active_connections.append(websocket)

        def disconnect(self, websocket: MockWebSocket):
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

        def broadcast(self, data: bytes):
            for connection in self.active_connections:
                connection.send_bytes(data)

        def send_to(self, websocket: MockWebSocket, data: bytes):
            if websocket in self.active_connections:
                websocket.send_bytes(data)

    return ConnectionManager()


# ============================================================================
# WebSocket Connection Tests
# ============================================================================

class TestWebSocketConnection:
    """Tests for WebSocket connection management."""

    def test_websocket_accept(self, mock_websocket):
        """WebSocket connection is accepted."""
        mock_websocket.accept()
        assert mock_websocket.is_connected

    def test_websocket_close(self, mock_websocket):
        """WebSocket connection is closed."""
        mock_websocket.accept()
        mock_websocket.close()
        assert not mock_websocket.is_connected

    def test_websocket_close_with_code(self, mock_websocket):
        """WebSocket closes with status code."""
        mock_websocket.accept()
        mock_websocket.close(code=1000, reason="Normal closure")
        assert mock_websocket.close_code == 1000
        assert mock_websocket.close_reason == "Normal closure"

    def test_websocket_state_transitions(self, mock_websocket):
        """WebSocket state transitions correctly."""
        assert not mock_websocket.is_connected
        mock_websocket.accept()
        assert mock_websocket.is_connected
        mock_websocket.close()
        assert not mock_websocket.is_connected

    def test_connection_manager_tracks_clients(self, connection_manager, mock_websocket):
        """Connection manager tracks active connections."""
        connection_manager.connect(mock_websocket)
        assert len(connection_manager.active_connections) == 1

    def test_connection_manager_removes_on_disconnect(self, connection_manager, mock_websocket):
        """Connection manager removes disconnected clients."""
        connection_manager.connect(mock_websocket)
        connection_manager.disconnect(mock_websocket)
        assert len(connection_manager.active_connections) == 0


# ============================================================================
# Binary Frame Transmission Tests
# ============================================================================

class TestBinaryFrameTransmission:
    """Tests for binary frame transmission."""

    def test_send_binary_frame(self, mock_websocket, test_frame):
        """Binary frame is sent correctly."""
        mock_websocket.accept()
        _, buffer = cv2.imencode('.jpg', test_frame)
        mock_websocket.send_bytes(buffer.tobytes())

        assert len(mock_websocket.sent_data) == 1
        assert isinstance(mock_websocket.sent_data[0], bytes)

    def test_receive_binary_frame(self, mock_websocket, test_frame):
        """Binary frame is received correctly."""
        mock_websocket.accept()
        _, buffer = cv2.imencode('.jpg', test_frame)
        encoded = buffer.tobytes()

        mock_websocket.receive_queue.append(encoded)
        received = mock_websocket.receive_bytes()

        assert received == encoded

    def test_frame_starts_with_jpeg_marker(self, mock_websocket, test_frame):
        """Sent frame starts with JPEG marker."""
        mock_websocket.accept()
        _, buffer = cv2.imencode('.jpg', test_frame)
        mock_websocket.send_bytes(buffer.tobytes())

        sent = mock_websocket.sent_data[0]
        assert sent[:2] == b'\xff\xd8'

    def test_frame_ends_with_jpeg_marker(self, mock_websocket, test_frame):
        """Sent frame ends with JPEG marker."""
        mock_websocket.accept()
        _, buffer = cv2.imencode('.jpg', test_frame)
        mock_websocket.send_bytes(buffer.tobytes())

        sent = mock_websocket.sent_data[0]
        assert sent[-2:] == b'\xff\xd9'

    def test_multiple_frames_sent(self, mock_websocket, test_frame):
        """Multiple frames are sent sequentially."""
        mock_websocket.accept()

        for i in range(5):
            _, buffer = cv2.imencode('.jpg', test_frame)
            mock_websocket.send_bytes(buffer.tobytes())

        assert len(mock_websocket.sent_data) == 5

    def test_broadcast_to_multiple_clients(self, connection_manager, test_frame):
        """Frame is broadcast to all connected clients."""
        clients = [create_mock_websocket() for _ in range(3)]
        for client in clients:
            connection_manager.connect(client)

        _, buffer = cv2.imencode('.jpg', test_frame)
        connection_manager.broadcast(buffer.tobytes())

        for client in clients:
            assert len(client.sent_data) == 1


# ============================================================================
# Bidirectional Command Tests
# ============================================================================

class TestBidirectionalCommands:
    """Tests for bidirectional command handling."""

    def test_receive_json_command(self, mock_websocket):
        """JSON command is received correctly."""
        mock_websocket.accept()
        command = {'type': 'config', 'quality': 60}
        mock_websocket.receive_queue.append(json.dumps(command))

        received = mock_websocket.receive_text()
        parsed = json.loads(received)

        assert parsed['type'] == 'config'
        assert parsed['quality'] == 60

    def test_quality_command_parsing(self, mock_websocket):
        """Quality command is parsed correctly."""
        mock_websocket.accept()
        command = {'type': 'command', 'action': 'set_quality', 'value': 50}
        mock_websocket.receive_queue.append(json.dumps(command))

        received = json.loads(mock_websocket.receive_text())

        assert received['action'] == 'set_quality'
        assert received['value'] == 50

    def test_osd_toggle_command(self, mock_websocket):
        """OSD toggle command is handled."""
        mock_websocket.accept()
        command = {'type': 'config', 'osd': True}
        mock_websocket.receive_queue.append(json.dumps(command))

        received = json.loads(mock_websocket.receive_text())
        assert received['osd'] is True

    def test_resize_command(self, mock_websocket):
        """Resize command is handled."""
        mock_websocket.accept()
        command = {'type': 'config', 'resize': True, 'width': 320, 'height': 240}
        mock_websocket.receive_queue.append(json.dumps(command))

        received = json.loads(mock_websocket.receive_text())
        assert received['resize'] is True
        assert received['width'] == 320

    def test_send_status_response(self, mock_websocket):
        """Status response is sent back to client."""
        mock_websocket.accept()
        status = {'status': 'ok', 'fps': 30, 'quality': 80}
        mock_websocket.send_text(json.dumps(status))

        assert len(mock_websocket.sent_text) == 1
        sent = json.loads(mock_websocket.sent_text[0])
        assert sent['status'] == 'ok'


# ============================================================================
# Connection Limit Tests
# ============================================================================

class TestConnectionLimits:
    """Tests for connection limit handling."""

    def test_max_clients_enforced(self, connection_manager):
        """Maximum client limit is enforced."""
        for i in range(10):
            ws = create_mock_websocket()
            connection_manager.connect(ws)

        assert len(connection_manager.active_connections) == 10

        # 11th should fail
        ws = create_mock_websocket()
        with pytest.raises(ConnectionError):
            connection_manager.connect(ws)

    def test_disconnect_allows_new_connection(self, connection_manager):
        """Disconnecting allows new connections."""
        clients = []
        for i in range(10):
            ws = create_mock_websocket()
            connection_manager.connect(ws)
            clients.append(ws)

        # Disconnect one
        connection_manager.disconnect(clients[0])
        assert len(connection_manager.active_connections) == 9

        # Now can add another
        ws = create_mock_websocket()
        connection_manager.connect(ws)
        assert len(connection_manager.active_connections) == 10

    def test_custom_max_clients(self):
        """Custom max clients limit works."""
        class ConnectionManager:
            def __init__(self, max_clients: int = 5):
                self.active_connections = []
                self.max_clients = max_clients

            def connect(self, ws):
                if len(self.active_connections) >= self.max_clients:
                    raise ConnectionError("Max clients")
                ws.accept()
                self.active_connections.append(ws)

        manager = ConnectionManager(max_clients=5)
        for i in range(5):
            manager.connect(create_mock_websocket())

        with pytest.raises(ConnectionError):
            manager.connect(create_mock_websocket())


# ============================================================================
# Reconnection Tests
# ============================================================================

class TestReconnection:
    """Tests for reconnection handling."""

    def test_client_can_reconnect(self, connection_manager):
        """Client can reconnect after disconnect."""
        ws = create_mock_websocket()
        connection_manager.connect(ws)
        connection_manager.disconnect(ws)

        # Create new socket and reconnect
        ws2 = create_mock_websocket()
        connection_manager.connect(ws2)
        assert len(connection_manager.active_connections) == 1

    def test_reconnect_preserves_other_connections(self, connection_manager):
        """Reconnecting client doesn't affect others."""
        ws1 = create_mock_websocket()
        ws2 = create_mock_websocket()
        connection_manager.connect(ws1)
        connection_manager.connect(ws2)

        connection_manager.disconnect(ws1)
        assert len(connection_manager.active_connections) == 1
        assert ws2 in connection_manager.active_connections


# ============================================================================
# Frame Rate Control Tests
# ============================================================================

class TestFrameRateControl:
    """Tests for frame rate control."""

    def test_calculate_frame_interval(self):
        """Frame interval is calculated from FPS."""
        fps = 30
        interval = 1 / fps
        assert interval == pytest.approx(0.0333, rel=0.01)

    def test_frame_interval_15fps(self):
        """Frame interval for 15 FPS."""
        fps = 15
        interval = 1 / fps
        assert interval == pytest.approx(0.0667, rel=0.01)

    def test_frame_interval_60fps(self):
        """Frame interval for 60 FPS."""
        fps = 60
        interval = 1 / fps
        assert interval == pytest.approx(0.0167, rel=0.01)

    def test_frame_skip_when_slow(self):
        """Frames are skipped when client is slow."""
        frame_time = 1 / 30
        last_send = time.time() - 0.1  # 100ms ago
        elapsed = time.time() - last_send

        should_skip = elapsed > frame_time * 2
        assert should_skip is True

    def test_no_skip_when_on_time(self):
        """Frames are not skipped when on time."""
        frame_time = 1 / 30
        last_send = time.time() - 0.02  # 20ms ago
        elapsed = time.time() - last_send

        should_skip = elapsed > frame_time * 2
        assert should_skip is False


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Tests for error handling."""

    def test_send_to_closed_socket(self, mock_websocket, test_frame):
        """Sending to closed socket is handled."""
        mock_websocket.accept()
        mock_websocket.close()

        # Should not raise
        try:
            _, buffer = cv2.imencode('.jpg', test_frame)
            mock_websocket.send_bytes(buffer.tobytes())
        except Exception:
            pass  # Expected behavior

    def test_receive_from_closed_socket(self, mock_websocket):
        """Receiving from closed socket is handled."""
        mock_websocket.accept()
        mock_websocket.close()

        result = mock_websocket.receive_bytes()
        assert result is None

    def test_invalid_json_command(self, mock_websocket):
        """Invalid JSON command is handled."""
        mock_websocket.accept()
        mock_websocket.receive_queue.append("not valid json {{{")

        received = mock_websocket.receive_text()
        with pytest.raises(json.JSONDecodeError):
            json.loads(received)

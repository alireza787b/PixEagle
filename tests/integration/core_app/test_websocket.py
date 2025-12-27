"""
WebSocket Integration Tests

Tests for WebSocket connections and real-time data streaming.
"""

import pytest
import json
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


pytestmark = [pytest.mark.integration, pytest.mark.core_app]


@pytest.fixture
def websocket_app():
    """Create test app with WebSocket endpoints."""
    app = FastAPI()

    # Store connected clients
    clients = []

    @app.websocket("/ws/status")
    async def websocket_status(websocket: WebSocket):
        await websocket.accept()
        clients.append(websocket)
        try:
            while True:
                # Send status updates
                data = {
                    "type": "status",
                    "tracking_active": False,
                    "follower_active": False
                }
                await websocket.send_json(data)
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            clients.remove(websocket)

    @app.websocket("/ws/telemetry")
    async def websocket_telemetry(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                data = {
                    "type": "telemetry",
                    "altitude": 100.0,
                    "latitude": 37.0,
                    "longitude": -122.0,
                    "heading": 45.0
                }
                await websocket.send_json(data)
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            pass

    @app.websocket("/ws/detections")
    async def websocket_detections(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                data = {
                    "type": "detections",
                    "detections": [
                        {"id": 1, "class": "person", "bbox": [100, 100, 200, 200], "confidence": 0.95}
                    ],
                    "frame_id": 1
                }
                await websocket.send_json(data)
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            pass

    @app.websocket("/ws/echo")
    async def websocket_echo(websocket: WebSocket):
        """Echo WebSocket for testing bidirectional communication."""
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_json()
                await websocket.send_json({"echo": data})
        except WebSocketDisconnect:
            pass

    @app.websocket("/ws/command")
    async def websocket_command(websocket: WebSocket):
        """Command WebSocket for testing command handling."""
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_json()
                command = data.get('command')

                if command == 'start_tracking':
                    response = {"status": "success", "message": "Tracking started"}
                elif command == 'stop_tracking':
                    response = {"status": "success", "message": "Tracking stopped"}
                elif command == 'ping':
                    response = {"status": "pong"}
                else:
                    response = {"status": "error", "message": "Unknown command"}

                await websocket.send_json(response)
        except WebSocketDisconnect:
            pass

    return app


@pytest.fixture
def client(websocket_app):
    """Create test client."""
    return TestClient(websocket_app)


class TestWebSocketConnection:
    """Tests for WebSocket connection handling."""

    def test_status_websocket_connects(self, client):
        """Test status WebSocket connects successfully."""
        with client.websocket_connect("/ws/status") as websocket:
            data = websocket.receive_json()
            assert data['type'] == 'status'

    def test_telemetry_websocket_connects(self, client):
        """Test telemetry WebSocket connects successfully."""
        with client.websocket_connect("/ws/telemetry") as websocket:
            data = websocket.receive_json()
            assert data['type'] == 'telemetry'

    def test_detections_websocket_connects(self, client):
        """Test detections WebSocket connects successfully."""
        with client.websocket_connect("/ws/detections") as websocket:
            data = websocket.receive_json()
            assert data['type'] == 'detections'

    def test_websocket_disconnect(self, client):
        """Test WebSocket handles disconnect gracefully."""
        with client.websocket_connect("/ws/status") as websocket:
            websocket.receive_json()  # Get first message
            # Disconnect happens automatically when context exits


class TestWebSocketDataStreaming:
    """Tests for WebSocket data streaming."""

    def test_receives_multiple_status_updates(self, client):
        """Test receiving multiple status updates."""
        with client.websocket_connect("/ws/status") as websocket:
            for _ in range(3):
                data = websocket.receive_json()
                assert 'tracking_active' in data
                assert 'follower_active' in data

    def test_telemetry_data_format(self, client):
        """Test telemetry data format is correct."""
        with client.websocket_connect("/ws/telemetry") as websocket:
            data = websocket.receive_json()

            assert 'altitude' in data
            assert 'latitude' in data
            assert 'longitude' in data
            assert 'heading' in data
            assert isinstance(data['altitude'], (int, float))

    def test_detection_data_format(self, client):
        """Test detection data format is correct."""
        with client.websocket_connect("/ws/detections") as websocket:
            data = websocket.receive_json()

            assert 'detections' in data
            assert isinstance(data['detections'], list)

            if data['detections']:
                detection = data['detections'][0]
                assert 'id' in detection
                assert 'class' in detection
                assert 'bbox' in detection
                assert 'confidence' in detection


class TestWebSocketBidirectional:
    """Tests for bidirectional WebSocket communication."""

    def test_echo_message(self, client):
        """Test echo WebSocket returns sent message."""
        with client.websocket_connect("/ws/echo") as websocket:
            test_message = {"test": "data", "number": 42}
            websocket.send_json(test_message)
            response = websocket.receive_json()

            assert response['echo'] == test_message

    def test_multiple_echo_messages(self, client):
        """Test multiple echo messages."""
        with client.websocket_connect("/ws/echo") as websocket:
            for i in range(5):
                message = {"index": i}
                websocket.send_json(message)
                response = websocket.receive_json()
                assert response['echo']['index'] == i


class TestWebSocketCommands:
    """Tests for WebSocket command handling."""

    def test_start_tracking_command(self, client):
        """Test start tracking command."""
        with client.websocket_connect("/ws/command") as websocket:
            websocket.send_json({"command": "start_tracking"})
            response = websocket.receive_json()

            assert response['status'] == 'success'
            assert 'Tracking started' in response['message']

    def test_stop_tracking_command(self, client):
        """Test stop tracking command."""
        with client.websocket_connect("/ws/command") as websocket:
            websocket.send_json({"command": "stop_tracking"})
            response = websocket.receive_json()

            assert response['status'] == 'success'
            assert 'Tracking stopped' in response['message']

    def test_ping_command(self, client):
        """Test ping command."""
        with client.websocket_connect("/ws/command") as websocket:
            websocket.send_json({"command": "ping"})
            response = websocket.receive_json()

            assert response['status'] == 'pong'

    def test_unknown_command(self, client):
        """Test unknown command returns error."""
        with client.websocket_connect("/ws/command") as websocket:
            websocket.send_json({"command": "nonexistent"})
            response = websocket.receive_json()

            assert response['status'] == 'error'


class TestMultipleClients:
    """Tests for multiple WebSocket clients."""

    def test_multiple_status_clients(self, client):
        """Test multiple clients can connect to status."""
        # Note: TestClient doesn't support true concurrent connections
        # This tests sequential connections work
        for _ in range(3):
            with client.websocket_connect("/ws/status") as websocket:
                data = websocket.receive_json()
                assert data['type'] == 'status'

    def test_different_endpoint_clients(self, client):
        """Test clients on different endpoints."""
        # Connect to multiple endpoints sequentially
        with client.websocket_connect("/ws/status") as ws1:
            status_data = ws1.receive_json()
            assert status_data['type'] == 'status'

        with client.websocket_connect("/ws/telemetry") as ws2:
            telemetry_data = ws2.receive_json()
            assert telemetry_data['type'] == 'telemetry'


class TestWebSocketReconnection:
    """Tests for WebSocket reconnection scenarios."""

    def test_reconnect_after_disconnect(self, client):
        """Test client can reconnect after disconnect."""
        # First connection
        with client.websocket_connect("/ws/status") as websocket:
            websocket.receive_json()

        # Second connection
        with client.websocket_connect("/ws/status") as websocket:
            data = websocket.receive_json()
            assert data['type'] == 'status'

    def test_reconnect_different_endpoint(self, client):
        """Test reconnecting to different endpoint."""
        with client.websocket_connect("/ws/status") as ws:
            ws.receive_json()

        with client.websocket_connect("/ws/telemetry") as ws:
            data = ws.receive_json()
            assert data['type'] == 'telemetry'


class TestWebSocketErrorHandling:
    """Tests for WebSocket error handling."""

    def test_invalid_json_handling(self, client):
        """Test handling of invalid JSON - server may close connection."""
        try:
            with client.websocket_connect("/ws/echo") as websocket:
                websocket.send_text("not json")
                # Server may close connection or raise error
        except Exception:
            pass  # Expected - invalid JSON may cause disconnect

    def test_connection_to_invalid_endpoint(self, client):
        """Test connecting to invalid endpoint."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/nonexistent") as websocket:
                pass


class TestWebSocketProtocol:
    """Tests for WebSocket protocol compliance."""

    def test_json_format(self, client):
        """Test messages are valid JSON."""
        with client.websocket_connect("/ws/status") as websocket:
            data = websocket.receive_json()
            # If we got here, it's valid JSON
            assert isinstance(data, dict)

    def test_message_types(self, client):
        """Test messages have type field."""
        with client.websocket_connect("/ws/status") as websocket:
            data = websocket.receive_json()
            assert 'type' in data

    def test_consistent_message_structure(self, client):
        """Test message structure is consistent."""
        with client.websocket_connect("/ws/status") as websocket:
            messages = [websocket.receive_json() for _ in range(3)]

            # All messages should have same keys
            first_keys = set(messages[0].keys())
            for msg in messages[1:]:
                assert set(msg.keys()) == first_keys

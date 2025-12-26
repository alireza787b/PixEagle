# tests/fixtures/mock_streaming.py
"""
Mock streaming objects for testing FastAPI video streaming handlers.

Provides mock implementations for HTTP clients, WebSocket connections,
WebRTC peer connections, and streaming optimization components.
"""

import asyncio
import json
import time
from typing import List, Dict, Any, Optional, Callable, AsyncIterator
from collections import deque
from dataclasses import dataclass, field
from unittest.mock import MagicMock, AsyncMock
import numpy as np


@dataclass
class MockWebSocketMessage:
    """Represents a WebSocket message."""
    type: str  # 'text', 'bytes', 'json'
    data: Any
    timestamp: float = field(default_factory=time.time)


class MockWebSocket:
    """
    Mock FastAPI WebSocket for testing streaming endpoints.

    Simulates bidirectional WebSocket communication with message tracking.
    """

    def __init__(self, client_id: str = "test_client"):
        """
        Initialize mock WebSocket.

        Args:
            client_id: Unique client identifier
        """
        self.client_id = client_id
        self.accepted = False
        self.closed = False
        self.close_code: Optional[int] = None
        self.close_reason: str = ""

        # Message tracking
        self.sent_messages: List[MockWebSocketMessage] = []
        self.sent_bytes: List[bytes] = []
        self.sent_json: List[Dict] = []

        # Receive queue for simulating client messages
        self.receive_queue: asyncio.Queue = asyncio.Queue()

        # Connection state
        self.connected_at = time.time()
        self.last_message_time = time.time()

        # Configuration
        self._should_disconnect = False
        self._disconnect_after_n: Optional[int] = None
        self._message_count = 0

    async def accept(self) -> None:
        """Accept WebSocket connection."""
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Close WebSocket connection.

        Args:
            code: Close status code
            reason: Close reason string
        """
        self.closed = True
        self.close_code = code
        self.close_reason = reason

    async def send_json(self, data: Dict) -> None:
        """
        Send JSON message.

        Args:
            data: Dictionary to send as JSON
        """
        if self.closed:
            raise RuntimeError("WebSocket is closed")

        self._message_count += 1
        self.sent_json.append(data)
        self.sent_messages.append(MockWebSocketMessage('json', data))
        self.last_message_time = time.time()

        self._check_disconnect()

    async def send_bytes(self, data: bytes) -> None:
        """
        Send binary data.

        Args:
            data: Bytes to send
        """
        if self.closed:
            raise RuntimeError("WebSocket is closed")

        self._message_count += 1
        self.sent_bytes.append(data)
        self.sent_messages.append(MockWebSocketMessage('bytes', data))
        self.last_message_time = time.time()

        self._check_disconnect()

    async def send_text(self, data: str) -> None:
        """
        Send text message.

        Args:
            data: String to send
        """
        if self.closed:
            raise RuntimeError("WebSocket is closed")

        self._message_count += 1
        self.sent_messages.append(MockWebSocketMessage('text', data))
        self.last_message_time = time.time()

    async def receive_json(self) -> Dict:
        """
        Receive JSON message from client.

        Returns:
            Dictionary from client
        """
        if self.closed:
            raise RuntimeError("WebSocket is closed")

        msg = await self.receive_queue.get()
        return msg if isinstance(msg, dict) else json.loads(msg)

    async def receive_text(self) -> str:
        """
        Receive text message from client.

        Returns:
            String from client
        """
        if self.closed:
            raise RuntimeError("WebSocket is closed")

        msg = await self.receive_queue.get()
        return json.dumps(msg) if isinstance(msg, dict) else str(msg)

    async def receive_bytes(self) -> bytes:
        """
        Receive binary data from client.

        Returns:
            Bytes from client
        """
        if self.closed:
            raise RuntimeError("WebSocket is closed")

        msg = await self.receive_queue.get()
        return msg if isinstance(msg, bytes) else str(msg).encode()

    async def iter_text(self) -> AsyncIterator[str]:
        """Iterate over text messages."""
        while not self.closed:
            try:
                msg = await asyncio.wait_for(self.receive_queue.get(), timeout=0.1)
                yield json.dumps(msg) if isinstance(msg, dict) else str(msg)
            except asyncio.TimeoutError:
                break

    async def iter_json(self) -> AsyncIterator[Dict]:
        """Iterate over JSON messages."""
        while not self.closed:
            try:
                msg = await asyncio.wait_for(self.receive_queue.get(), timeout=0.1)
                yield msg if isinstance(msg, dict) else json.loads(msg)
            except asyncio.TimeoutError:
                break

    def _check_disconnect(self) -> None:
        """Check if should simulate disconnect."""
        if self._should_disconnect:
            self.closed = True
        if self._disconnect_after_n and self._message_count >= self._disconnect_after_n:
            self.closed = True

    # Test helper methods

    def add_message(self, message: Any) -> None:
        """Add message to receive queue (simulates client sending)."""
        self.receive_queue.put_nowait(message)

    def set_disconnect_after(self, n: int) -> None:
        """Configure to disconnect after N sent messages."""
        self._disconnect_after_n = n

    def force_disconnect(self) -> None:
        """Force immediate disconnect."""
        self._should_disconnect = True
        self.closed = True

    def get_sent_frame_count(self) -> int:
        """Get count of binary (frame) messages sent."""
        return len(self.sent_bytes)

    def get_all_sent_json(self) -> List[Dict]:
        """Get all JSON messages sent."""
        return self.sent_json.copy()


@dataclass
class MockClientConnection:
    """Mock client connection for tracking streaming state."""
    id: str
    connected_at: float = field(default_factory=time.time)
    last_frame_time: float = field(default_factory=time.time)
    quality: int = 50
    frame_drops: int = 0
    bandwidth_estimate: float = 100000.0  # bytes/second
    frame_queue: deque = field(default_factory=lambda: deque(maxlen=3))


class MockHTTPResponse:
    """Mock HTTP response for streaming."""

    def __init__(
        self,
        status_code: int = 200,
        content_type: str = "multipart/x-mixed-replace; boundary=frame",
        headers: Optional[Dict] = None
    ):
        self.status_code = status_code
        self.content_type = content_type
        self.headers = headers or {"Content-Type": content_type}
        self.body_iterator: Optional[AsyncIterator] = None

    async def iter_bytes(self) -> AsyncIterator[bytes]:
        """Iterate over response bytes."""
        if self.body_iterator:
            async for chunk in self.body_iterator:
                yield chunk


class MockHTTPClient:
    """Mock HTTP client for testing MJPEG streaming endpoints."""

    def __init__(self):
        """Initialize mock HTTP client."""
        self.requests: List[Dict] = []
        self.connected = False
        self.frames_received: List[bytes] = []
        self._frame_callback: Optional[Callable] = None

    async def get_stream(self, url: str, timeout: float = 30.0) -> MockHTTPResponse:
        """
        Simulate GET request for streaming endpoint.

        Args:
            url: Request URL
            timeout: Request timeout

        Returns:
            MockHTTPResponse instance
        """
        self.requests.append({
            'method': 'GET',
            'url': url,
            'timestamp': time.time(),
        })
        self.connected = True

        response = MockHTTPResponse()
        return response

    async def receive_frame(self, frame_data: bytes) -> None:
        """
        Simulate receiving a frame from stream.

        Args:
            frame_data: JPEG frame bytes
        """
        self.frames_received.append(frame_data)
        if self._frame_callback:
            self._frame_callback(frame_data)

    def set_frame_callback(self, callback: Callable) -> None:
        """Set callback for frame reception."""
        self._frame_callback = callback

    def disconnect(self) -> None:
        """Disconnect from stream."""
        self.connected = False


class MockRTCPeerConnection:
    """
    Mock aiortc RTCPeerConnection for testing WebRTC.

    Simulates peer connection lifecycle and signaling.
    """

    def __init__(self):
        """Initialize mock peer connection."""
        self.tracks: List[Any] = []
        self.local_description: Optional[MagicMock] = None
        self.remote_description: Optional[MagicMock] = None
        self.connection_state = "new"
        self.ice_connection_state = "new"
        self.ice_candidates: List[Dict] = []
        self.data_channels: List[Any] = []

        # Callbacks
        self._on_track: Optional[Callable] = None
        self._on_ice_candidate: Optional[Callable] = None
        self._on_connection_state_change: Optional[Callable] = None

    def addTrack(self, track: Any) -> Any:
        """
        Add media track to connection.

        Args:
            track: Media track to add

        Returns:
            RTP sender (mock)
        """
        self.tracks.append(track)
        sender = MagicMock()
        sender.track = track
        return sender

    async def setRemoteDescription(self, sdp: Any) -> None:
        """
        Set remote SDP description.

        Args:
            sdp: SDP object with sdp and type attributes
        """
        self.remote_description = sdp
        self.connection_state = "connecting"

    async def setLocalDescription(self, sdp: Any) -> None:
        """
        Set local SDP description.

        Args:
            sdp: SDP object with sdp and type attributes
        """
        self.local_description = sdp

    async def createOffer(self) -> MagicMock:
        """
        Create SDP offer.

        Returns:
            Mock SDP offer
        """
        offer = MagicMock()
        offer.sdp = "v=0\r\no=- mock_offer\r\n"
        offer.type = "offer"
        return offer

    async def createAnswer(self) -> MagicMock:
        """
        Create SDP answer.

        Returns:
            Mock SDP answer
        """
        answer = MagicMock()
        answer.sdp = "v=0\r\no=- mock_answer\r\n"
        answer.type = "answer"
        return answer

    async def addIceCandidate(self, candidate: Dict) -> None:
        """
        Add ICE candidate.

        Args:
            candidate: ICE candidate dictionary
        """
        self.ice_candidates.append(candidate)

    async def close(self) -> None:
        """Close peer connection."""
        self.connection_state = "closed"
        self.ice_connection_state = "closed"

    def createDataChannel(self, label: str, **kwargs) -> MagicMock:
        """
        Create data channel.

        Args:
            label: Channel label

        Returns:
            Mock data channel
        """
        channel = MagicMock()
        channel.label = label
        self.data_channels.append(channel)
        return channel

    # Event handlers
    @property
    def on_track(self) -> Optional[Callable]:
        return self._on_track

    @on_track.setter
    def on_track(self, callback: Callable) -> None:
        self._on_track = callback

    @property
    def on_icecandidate(self) -> Optional[Callable]:
        return self._on_ice_candidate

    @on_icecandidate.setter
    def on_icecandidate(self, callback: Callable) -> None:
        self._on_ice_candidate = callback

    # Test helpers

    def simulate_connected(self) -> None:
        """Simulate successful connection."""
        self.connection_state = "connected"
        self.ice_connection_state = "connected"

    def simulate_failed(self) -> None:
        """Simulate connection failure."""
        self.connection_state = "failed"
        self.ice_connection_state = "failed"


class MockRTCSessionDescription:
    """Mock RTCSessionDescription."""

    def __init__(self, sdp: str = "", type: str = "offer"):
        self.sdp = sdp
        self.type = type


class MockVideoStreamTrack:
    """Mock video track for WebRTC streaming."""

    def __init__(self, width: int = 640, height: int = 480, fps: int = 30):
        """
        Initialize mock video track.

        Args:
            width: Frame width
            height: Frame height
            fps: Frames per second
        """
        self.kind = "video"
        self.width = width
        self.height = height
        self.fps = fps
        self._running = False
        self._frame_count = 0

    def start(self) -> None:
        """Start track."""
        self._running = True

    def stop(self) -> None:
        """Stop track."""
        self._running = False

    async def recv(self) -> MagicMock:
        """
        Receive video frame.

        Returns:
            Mock video frame
        """
        self._frame_count += 1
        frame = MagicMock()
        frame.width = self.width
        frame.height = self.height
        frame.pts = self._frame_count * (1 / self.fps)
        return frame


class MockStreamingOptimizer:
    """Mock StreamingOptimizer for testing quality control."""

    def __init__(self, initial_quality: int = 50):
        """
        Initialize mock optimizer.

        Args:
            initial_quality: Starting JPEG quality
        """
        self.quality = initial_quality
        self.min_quality = 30
        self.max_quality = 85
        self.quality_step = 10
        self.adaptive_enabled = True

        # Cache state
        self.cache_enabled = True
        self.cache: Dict[str, bytes] = {}
        self.cache_hits = 0
        self.cache_misses = 0

        # Statistics
        self.frames_encoded = 0
        self.total_bytes = 0

    async def encode_frame_async(
        self,
        frame: np.ndarray,
        quality: Optional[int] = None
    ) -> bytes:
        """
        Encode frame to JPEG.

        Args:
            frame: BGR frame array
            quality: JPEG quality (uses self.quality if None)

        Returns:
            JPEG encoded bytes
        """
        import cv2

        q = quality or self.quality
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, q])
        self.frames_encoded += 1
        self.total_bytes += len(buffer)
        return buffer.tobytes()

    def adjust_quality_up(self) -> int:
        """Increase quality if possible."""
        if self.quality < self.max_quality:
            self.quality = min(self.max_quality, self.quality + self.quality_step)
        return self.quality

    def adjust_quality_down(self) -> int:
        """Decrease quality if possible."""
        if self.quality > self.min_quality:
            self.quality = max(self.min_quality, self.quality - self.quality_step)
        return self.quality

    def get_cached_frame(self, frame_hash: str) -> Optional[bytes]:
        """Get cached frame by hash."""
        if frame_hash in self.cache:
            self.cache_hits += 1
            return self.cache[frame_hash]
        self.cache_misses += 1
        return None

    def cache_frame(self, frame_hash: str, data: bytes) -> None:
        """Cache encoded frame."""
        self.cache[frame_hash] = data


# Factory functions

def create_mock_websocket(client_id: str = "test") -> MockWebSocket:
    """Create configured mock WebSocket."""
    return MockWebSocket(client_id=client_id)


def create_mock_rtc_peer_connection() -> MockRTCPeerConnection:
    """Create mock RTC peer connection."""
    return MockRTCPeerConnection()


def create_mock_streaming_optimizer(quality: int = 50) -> MockStreamingOptimizer:
    """Create mock streaming optimizer."""
    return MockStreamingOptimizer(initial_quality=quality)


def create_multiple_websockets(count: int = 5) -> List[MockWebSocket]:
    """Create multiple mock WebSocket connections."""
    return [MockWebSocket(client_id=f"client_{i}") for i in range(count)]


async def create_connected_websocket() -> MockWebSocket:
    """Create and accept a mock WebSocket."""
    ws = MockWebSocket()
    await ws.accept()
    return ws

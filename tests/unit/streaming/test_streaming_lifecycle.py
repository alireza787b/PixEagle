"""Streaming lifecycle cleanup regression tests."""

import asyncio
import logging
import queue
import threading
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from classes.app_controller import AppController
from classes.fastapi_handler import ClientConnection, FastAPIHandler
from classes.gstreamer_handler import GStreamerHandler
from classes.webrtc_manager import WebRTCManager


pytestmark = [pytest.mark.unit, pytest.mark.streaming]


def _handler_for_lifecycle_tests() -> FastAPIHandler:
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.connection_lock = asyncio.Lock()
    handler.ws_connections = {}
    handler.http_connections = set()
    handler.stats = {
        "frames_sent": 0,
        "frames_dropped": 0,
        "total_bandwidth": 0,
        "active_connections": 0,
    }
    handler.quality_engine = SimpleNamespace(unregister_client=MagicMock())
    handler.frame_publisher = SimpleNamespace(unregister_client=MagicMock())
    handler.logger = logging.getLogger("test.streaming_lifecycle")
    return handler


def _client(
    *,
    client_id: str,
    connected_at: float,
    last_frame_time: float,
    websocket=None,
) -> ClientConnection:
    return ClientConnection(
        id=client_id,
        connected_at=connected_at,
        last_frame_time=last_frame_time,
        quality=80,
        frame_drops=0,
        bandwidth_estimate=0,
        frame_queue=deque(maxlen=2),
        websocket=websocket,
    )


def test_stale_websocket_ids_include_clients_that_never_received_frames():
    handler = _handler_for_lifecycle_tests()
    handler.ws_connections = {
        "fresh-never-fed": _client(
            client_id="fresh-never-fed",
            connected_at=95.0,
            last_frame_time=0.0,
        ),
        "stale-never-fed": _client(
            client_id="stale-never-fed",
            connected_at=60.0,
            last_frame_time=0.0,
        ),
        "fresh-fed": _client(
            client_id="fresh-fed",
            connected_at=10.0,
            last_frame_time=90.0,
        ),
        "stale-fed": _client(
            client_id="stale-fed",
            connected_at=10.0,
            last_frame_time=40.0,
        ),
    }

    stale_ids = handler._stale_websocket_client_ids(
        current_time=100.0,
        stale_timeout=30.0,
    )

    assert stale_ids == ["stale-never-fed", "stale-fed"]


@pytest.mark.asyncio
async def test_websocket_cleanup_closes_transport_and_unregisters_once():
    handler = _handler_for_lifecycle_tests()
    websocket = SimpleNamespace(close=AsyncMock())
    handler.ws_connections["ws-test"] = _client(
        client_id="ws-test",
        connected_at=1.0,
        last_frame_time=0.0,
        websocket=websocket,
    )
    handler.stats["active_connections"] = 1

    cleaned = await handler._cleanup_websocket_client(
        "ws-test",
        close_code=1001,
        close_reason="stale",
    )
    cleaned_again = await handler._cleanup_websocket_client(
        "ws-test",
        close_code=1001,
        close_reason="stale",
    )

    assert cleaned is True
    assert cleaned_again is False
    assert handler.ws_connections == {}
    assert handler.stats["active_connections"] == 0
    websocket.close.assert_awaited_once_with(code=1001, reason="stale")
    handler.quality_engine.unregister_client.assert_called_once_with("ws-test")
    handler.frame_publisher.unregister_client.assert_called_once_with()


@pytest.mark.asyncio
async def test_close_all_websocket_clients_uses_single_cleanup_path():
    handler = _handler_for_lifecycle_tests()
    websockets = [SimpleNamespace(close=AsyncMock()) for _ in range(2)]
    for index, websocket in enumerate(websockets):
        client_id = f"ws-{index}"
        handler.ws_connections[client_id] = _client(
            client_id=client_id,
            connected_at=1.0,
            last_frame_time=0.0,
            websocket=websocket,
        )

    closed = await handler._close_all_websocket_clients(
        close_code=1001,
        close_reason="server stopping",
    )

    assert closed == 2
    assert handler.ws_connections == {}
    for websocket in websockets:
        websocket.close.assert_awaited_once_with(
            code=1001,
            reason="server stopping",
        )
    assert handler.quality_engine.unregister_client.call_count == 2
    assert handler.frame_publisher.unregister_client.call_count == 2


@pytest.mark.asyncio
async def test_fastapi_stop_drains_streaming_resources():
    handler = _handler_for_lifecycle_tests()
    websocket = SimpleNamespace(close=AsyncMock())
    handler.ws_connections["ws-stop"] = _client(
        client_id="ws-stop",
        connected_at=1.0,
        last_frame_time=0.0,
        websocket=websocket,
    )
    handler.is_shutting_down = False
    handler.background_tasks = []
    handler.webrtc_manager = SimpleNamespace(shutdown=AsyncMock(return_value=1))
    handler.stream_optimizer = SimpleNamespace(
        encoder_pool=SimpleNamespace(shutdown=MagicMock())
    )
    handler.server = SimpleNamespace(should_exit=False, shutdown=AsyncMock())

    await handler.stop()

    assert handler.is_shutting_down is True
    assert handler.ws_connections == {}
    websocket.close.assert_awaited_once_with(
        code=1001,
        reason="PixEagle API server stopping",
    )
    handler.webrtc_manager.shutdown.assert_awaited_once_with()
    handler.stream_optimizer.encoder_pool.shutdown.assert_called_once_with(wait=True)
    assert handler.server.should_exit is True
    handler.server.shutdown.assert_awaited_once_with()


class _FakePeerConnection:
    def __init__(self):
        self.close_count = 0

    async def close(self):
        self.close_count += 1


class _HangingPeerConnection:
    def __init__(self):
        self.close_count = 0

    async def close(self):
        self.close_count += 1
        await asyncio.sleep(30.0)


@pytest.mark.asyncio
async def test_webrtc_manager_shutdown_closes_all_peers_once():
    manager = WebRTCManager.__new__(WebRTCManager)
    peers = {
        "peer-a": _FakePeerConnection(),
        "peer-b": _FakePeerConnection(),
    }
    manager.peer_connections = dict(peers)
    manager.frame_publisher = SimpleNamespace(unregister_client=MagicMock())
    manager.logger = logging.getLogger("test.webrtc_lifecycle")

    closed = await manager.shutdown()
    closed_again = await manager.shutdown()

    assert closed == 2
    assert closed_again == 0
    assert manager.peer_connections == {}
    assert {peer.close_count for peer in peers.values()} == {1}
    assert manager.frame_publisher.unregister_client.call_count == 2


@pytest.mark.asyncio
async def test_webrtc_manager_shutdown_unregisters_after_close_timeout(monkeypatch):
    manager = WebRTCManager.__new__(WebRTCManager)
    peer = _HangingPeerConnection()
    manager.peer_connections = {"peer-timeout": peer}
    manager.frame_publisher = SimpleNamespace(unregister_client=MagicMock())
    manager.logger = logging.getLogger("test.webrtc_lifecycle_timeout")
    monkeypatch.setattr(
        "classes.webrtc_manager.Parameters.WEBRTC_CLOSE_TIMEOUT_SECONDS",
        0.01,
        raising=False,
    )

    closed = await asyncio.wait_for(manager.shutdown(), timeout=1.0)
    await asyncio.sleep(0)

    assert closed == 1
    assert peer.close_count == 1
    assert manager.peer_connections == {}
    manager.frame_publisher.unregister_client.assert_called_once_with()


class _FakeVideoWriter:
    def __init__(self):
        self.opened = True
        self.release_count = 0

    def isOpened(self):
        return self.opened

    def release(self):
        self.release_count += 1
        self.opened = False


class _RaisingVideoWriter(_FakeVideoWriter):
    def release(self):
        self.release_count += 1
        self.opened = False
        raise RuntimeError("release failed")


class _FakeThread:
    def __init__(self, *args, **kwargs):
        self.started = False

    def start(self):
        self.started = True

    def join(self, timeout=None):
        pass


def test_gstreamer_release_nulls_writer_and_drains_queue():
    handler = GStreamerHandler.__new__(GStreamerHandler)
    writer = _FakeVideoWriter()
    handler.out = writer
    handler._writer_stop = threading.Event()
    handler._writer_thread = None
    handler._frame_queue = queue.Queue(maxsize=2)
    handler._frame_queue.put_nowait(object())

    handler.release()
    handler.release()

    assert writer.release_count == 1
    assert handler.out is None
    assert handler._frame_queue.empty()


def test_gstreamer_release_drains_queue_when_writer_release_fails():
    handler = GStreamerHandler.__new__(GStreamerHandler)
    writer = _RaisingVideoWriter()
    handler.out = writer
    handler._writer_stop = threading.Event()
    handler._writer_thread = None
    handler._frame_queue = queue.Queue(maxsize=2)
    handler._frame_queue.put_nowait(object())

    with pytest.raises(RuntimeError, match="release failed"):
        handler.release()

    assert writer.release_count == 1
    assert handler.out is None
    assert handler._frame_queue.empty()


def test_gstreamer_initialize_releases_existing_writer_before_replacing_it():
    handler = GStreamerHandler.__new__(GStreamerHandler)
    old_writer = _FakeVideoWriter()
    old_writer.opened = False
    new_writer = _FakeVideoWriter()
    handler.out = old_writer
    handler.WIDTH = 2
    handler.HEIGHT = 2
    handler.FRAMERATE = 30
    handler.pipeline = "fake-pipeline"
    handler.encoder_info = SimpleNamespace(encoder="x264enc", hardware=False)
    handler._writer_stop = threading.Event()
    handler._writer_thread = None
    handler._frame_queue = queue.Queue(maxsize=2)
    handler._queue_drops = 0

    with patch("classes.gstreamer_handler.cv2.VideoWriter", return_value=new_writer), \
            patch("classes.gstreamer_handler.threading.Thread", _FakeThread):
        handler.initialize_stream()

    assert old_writer.release_count == 1
    assert handler.out is new_writer
    assert handler._writer_thread is not None


@pytest.mark.asyncio
async def test_app_controller_shutdown_releases_gstreamer_output():
    controller = object.__new__(AppController)
    controller.following_active = False
    controller.video_handler = None
    controller.gstreamer_handler = SimpleNamespace(release=MagicMock())
    controller.recording_manager = None
    controller.storage_manager = None

    with patch("classes.app_controller.Parameters.MAVLINK_ENABLED", False):
        result = await controller.shutdown()

    controller.gstreamer_handler.release.assert_called_once_with()
    assert "GStreamer output released" in result["steps"]
    assert result["errors"] == []

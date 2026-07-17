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
from classes.api_auth_runtime import (
    API_AUTH_MODE_BROWSER_SESSION,
    APIAuthRuntime,
    APIUserRecord,
    hash_password_pbkdf2_sha256,
)
from classes.api_security_types import APIPrincipal
from classes.api_exposure_policy import (
    TRUSTED_LAN_LEGACY,
    resolve_api_exposure_policy,
)
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
    principal=None,
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
        principal=principal,
    )


def _browser_session_runtime() -> tuple[APIAuthRuntime, APIPrincipal, str]:
    runtime = APIAuthRuntime(
        mode=API_AUTH_MODE_BROWSER_SESSION,
        users_by_username={
            "operator": APIUserRecord(
                username="operator",
                role="operator",
                password_pbkdf2_sha256=hash_password_pbkdf2_sha256("test-password"),
            )
        },
    )
    session = runtime.create_session_for_user(runtime.users_by_username["operator"])
    principal = APIPrincipal.session(
        username=session.username,
        role=session.role,
        session_id=session.session_id,
    )
    return runtime, principal, session.session_id


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
async def test_video_websocket_monitor_closes_after_browser_session_revocation():
    runtime, principal, session_id = _browser_session_runtime()
    handler = _handler_for_lifecycle_tests()
    handler.api_auth_runtime = runtime
    handler.is_shutting_down = False
    handler._record_security_audit_event = MagicMock(return_value=True)
    websocket = SimpleNamespace(close=AsyncMock())
    client = _client(
        client_id="session-ws",
        connected_at=1.0,
        last_frame_time=0.0,
        websocket=websocket,
        principal=principal,
    )

    monitor = asyncio.create_task(handler._ws_monitor_session(websocket, client))
    await asyncio.sleep(0)
    runtime.revoke_session_id(session_id)
    await asyncio.wait_for(monitor, timeout=1.0)

    websocket.close.assert_awaited_once_with(
        code=1008,
        reason="Browser session expired or revoked",
    )
    handler._record_security_audit_event.assert_called_once()


@pytest.mark.asyncio
async def test_video_websocket_send_frames_emits_metadata_then_jpeg(monkeypatch):
    handler = _handler_for_lifecycle_tests()
    handler.is_shutting_down = False
    handler.frame_interval = 0
    stamped_frame = SimpleNamespace(frame=object(), frame_id=42)
    handler.frame_publisher = SimpleNamespace(get_latest=MagicMock(return_value=stamped_frame))
    handler.stream_optimizer = SimpleNamespace(
        encode_frame_async=AsyncMock(return_value=b"jpeg-frame")
    )
    handler.quality_engine = SimpleNamespace(
        report_frame_sent=MagicMock(return_value=72)
    )
    monkeypatch.setattr("classes.fastapi_handler.Parameters.ENABLE_ADAPTIVE_QUALITY", True)
    websocket = SimpleNamespace(send_json=AsyncMock(), send_bytes=AsyncMock())
    client = _client(client_id="ws-send", connected_at=1.0, last_frame_time=0.0)

    async def stop_after_bytes(_payload):
        handler.is_shutting_down = True

    websocket.send_bytes.side_effect = stop_after_bytes

    await handler._ws_send_frames(websocket, client)

    websocket.send_json.assert_awaited_once()
    metadata = websocket.send_json.await_args.args[0]
    assert metadata["type"] == "frame"
    assert metadata["quality"] == 72
    assert metadata["size"] == len(b"jpeg-frame")
    assert metadata["frame_id"] == 42
    websocket.send_bytes.assert_awaited_once_with(b"jpeg-frame")
    handler.stream_optimizer.encode_frame_async.assert_awaited_once_with(
        stamped_frame.frame,
        stamped_frame.frame_id,
        80,
    )
    handler.quality_engine.report_frame_sent.assert_called_once()
    assert client.quality == 72
    assert client.last_frame_time > 0
    assert handler.stats["frames_sent"] == 1
    assert handler.stats["total_bandwidth"] == len(b"jpeg-frame")


@pytest.mark.asyncio
async def test_video_websocket_receive_quality_and_ping(monkeypatch):
    handler = _handler_for_lifecycle_tests()
    handler.is_shutting_down = False
    handler.quality_engine = SimpleNamespace(set_client_quality=MagicMock())
    monkeypatch.setattr("classes.fastapi_handler.Parameters.MIN_QUALITY", 20)
    monkeypatch.setattr("classes.fastapi_handler.Parameters.MAX_QUALITY", 95)
    websocket = SimpleNamespace(
        receive_json=AsyncMock(
            side_effect=[
                {"type": "quality", "quality": 55.8},
                {"type": "ping", "client_timestamp": 123.0},
            ]
        ),
        send_json=AsyncMock(),
    )
    client = _client(client_id="ws-recv", connected_at=1.0, last_frame_time=0.0)

    async def stop_after_pong(_message):
        handler.is_shutting_down = True

    websocket.send_json.side_effect = stop_after_pong

    await handler._ws_receive_messages(websocket, client)

    handler.quality_engine.set_client_quality.assert_called_once_with("ws-recv", 55)
    assert client.quality == 55
    websocket.send_json.assert_awaited_once()
    pong = websocket.send_json.await_args.args[0]
    assert pong["type"] == "pong"
    assert pong["client_timestamp"] == 123.0
    assert "timestamp" in pong


@pytest.mark.asyncio
async def test_video_websocket_send_frames_stops_after_three_send_errors(monkeypatch):
    handler = _handler_for_lifecycle_tests()
    handler.is_shutting_down = False
    handler.frame_interval = 0
    handler.frame_publisher = SimpleNamespace(
        get_latest=MagicMock(return_value=SimpleNamespace(frame=object(), frame_id=10))
    )
    handler.stream_optimizer = SimpleNamespace(
        encode_frame_async=AsyncMock(return_value=b"jpeg-frame")
    )
    handler.quality_engine = SimpleNamespace(report_frame_sent=MagicMock())
    monkeypatch.setattr("classes.fastapi_handler.Parameters.ENABLE_ADAPTIVE_QUALITY", False)
    websocket = SimpleNamespace(
        send_json=AsyncMock(side_effect=RuntimeError("send failed")),
        send_bytes=AsyncMock(),
    )
    client = _client(client_id="ws-errors", connected_at=1.0, last_frame_time=0.0)

    await handler._ws_send_frames(websocket, client)

    assert websocket.send_json.await_count == 3
    websocket.send_bytes.assert_not_awaited()
    assert client.frame_drops == 3
    assert handler.stats["frames_dropped"] == 3


@pytest.mark.asyncio
async def test_http_mjpeg_generator_stops_after_browser_session_revocation(monkeypatch):
    runtime, principal, session_id = _browser_session_runtime()
    handler = _handler_for_lifecycle_tests()
    handler.api_auth_runtime = runtime
    handler.is_shutting_down = False
    handler.frame_interval = 0.01
    handler.frame_publisher = SimpleNamespace(
        register_client=MagicMock(),
        unregister_client=MagicMock(),
        get_latest=MagicMock(return_value=None),
    )
    handler.quality_engine = SimpleNamespace(
        register_client=MagicMock(),
        unregister_client=MagicMock(),
    )
    handler._record_security_audit_event = MagicMock(return_value=True)
    monkeypatch.setattr("classes.fastapi_handler.Parameters.ENABLE_STREAMING", True)
    request = SimpleNamespace(state=SimpleNamespace(api_principal=principal))

    response = await handler.video_feed(request)
    messages = []

    async def send(message):
        messages.append(message)

    stream_task = asyncio.create_task(response.stream_response(send))
    await asyncio.sleep(0)
    runtime.revoke_session_id(session_id)
    await asyncio.wait_for(stream_task, timeout=1.0)

    assert handler.http_connections == set()
    handler.frame_publisher.unregister_client.assert_called_once_with()
    handler._record_security_audit_event.assert_called_once()
    assert messages[-1] == {
        "type": "http.response.body",
        "body": b"",
        "more_body": False,
    }


@pytest.mark.asyncio
async def test_http_mjpeg_revocation_cancels_blocked_response_delivery(monkeypatch):
    runtime, principal, session_id = _browser_session_runtime()
    handler = _handler_for_lifecycle_tests()
    handler.api_auth_runtime = runtime
    handler.is_shutting_down = False
    handler.frame_interval = 0
    handler.frame_publisher = SimpleNamespace(
        register_client=MagicMock(),
        unregister_client=MagicMock(),
        get_latest=MagicMock(
            return_value=SimpleNamespace(frame=object(), frame_id=1)
        ),
    )
    handler.stream_optimizer = SimpleNamespace(
        encode_frame_async=AsyncMock(return_value=b"jpeg")
    )
    handler.quality_engine = SimpleNamespace(
        register_client=MagicMock(),
        unregister_client=MagicMock(),
        report_frame_sent=MagicMock(return_value=50),
    )
    handler._record_security_audit_event = MagicMock(return_value=True)
    monkeypatch.setattr("classes.fastapi_handler.Parameters.ENABLE_STREAMING", True)
    monkeypatch.setattr(
        "classes.fastapi_handler.Parameters.ENABLE_ADAPTIVE_QUALITY",
        False,
    )
    request = SimpleNamespace(state=SimpleNamespace(api_principal=principal))
    response = await handler.video_feed(request)
    body_send_started = asyncio.Event()
    release_body_send = asyncio.Event()

    async def blocked_send(message):
        if message["type"] == "http.response.body" and message.get("more_body"):
            body_send_started.set()
            await release_body_send.wait()

    stream_task = asyncio.create_task(response.stream_response(blocked_send))
    await asyncio.wait_for(body_send_started.wait(), timeout=1.0)
    runtime.revoke_session_id(session_id)
    await asyncio.wait_for(stream_task, timeout=1.0)

    assert handler.http_connections == set()
    handler.frame_publisher.unregister_client.assert_called_once_with()
    handler._record_security_audit_event.assert_called_once()


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

    def on(self, _event_name):
        def decorator(callback):
            return callback
        return decorator

    connectionState = "new"


class _HangingPeerConnection:
    def __init__(self):
        self.close_count = 0

    async def close(self):
        self.close_count += 1
        await asyncio.sleep(30.0)


def test_webrtc_ice_configuration_uses_stun_and_turn_without_exposing_secret(
    monkeypatch,
):
    monkeypatch.setattr(
        "classes.webrtc_manager.Parameters.WEBRTC_STUN_SERVER",
        "stun:stun.example.test:3478",
        raising=False,
    )
    monkeypatch.setattr(
        "classes.webrtc_manager.Parameters.WEBRTC_TURN_SERVER",
        "turns:turn.example.test:5349?transport=tcp",
        raising=False,
    )
    monkeypatch.setattr(
        "classes.webrtc_manager.Parameters.WEBRTC_TURN_USERNAME",
        "pixeagle",
        raising=False,
    )
    monkeypatch.setattr(
        "classes.webrtc_manager.Parameters.WEBRTC_TURN_CREDENTIAL",
        "turn-secret",
        raising=False,
    )

    configuration, summary = WebRTCManager._build_rtc_configuration()

    assert len(configuration.iceServers) == 2
    assert configuration.iceServers[0].urls == "stun:stun.example.test:3478"
    assert configuration.iceServers[1].urls.startswith("turns:turn.example.test")
    assert configuration.iceServers[1].username == "pixeagle"
    assert configuration.iceServers[1].credential == "turn-secret"
    assert summary == [
        {
            "kind": "stun",
            "url": "stun:stun.example.test:3478",
            "configured": True,
        },
        {
            "kind": "turn",
            "url": "turns:turn.example.test:5349?transport=tcp",
            "configured": True,
            "credentials_configured": True,
        },
    ]
    assert "turn-secret" not in repr(summary)


def test_webrtc_ice_configuration_rejects_partial_turn_credentials(monkeypatch):
    monkeypatch.setattr(
        "classes.webrtc_manager.Parameters.WEBRTC_STUN_SERVER",
        "",
        raising=False,
    )
    monkeypatch.setattr(
        "classes.webrtc_manager.Parameters.WEBRTC_TURN_SERVER",
        "turn:turn.example.test:3478",
        raising=False,
    )
    monkeypatch.setattr(
        "classes.webrtc_manager.Parameters.WEBRTC_TURN_USERNAME",
        "pixeagle",
        raising=False,
    )
    monkeypatch.setattr(
        "classes.webrtc_manager.Parameters.WEBRTC_TURN_CREDENTIAL",
        "",
        raising=False,
    )

    configuration, summary = WebRTCManager._build_rtc_configuration()

    assert configuration.iceServers == []
    assert summary == [
        {
            "kind": "turn",
            "url": None,
            "configured": False,
            "credentials_configured": False,
        }
    ]


def test_webrtc_peer_creation_applies_configured_ice_servers(monkeypatch):
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.rtc_configuration = object()
    peer = _FakePeerConnection()
    peer_factory = MagicMock(return_value=peer)
    monkeypatch.setattr("classes.webrtc_manager.RTCPeerConnection", peer_factory)

    assert manager._create_peer_connection() is peer
    peer_factory.assert_called_once_with(configuration=manager.rtc_configuration)


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


@pytest.mark.asyncio
async def test_webrtc_monitor_closes_after_browser_session_revocation():
    runtime, principal, session_id = _browser_session_runtime()
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.api_auth_runtime = runtime
    manager.security_audit_logger = None
    manager.logger = logging.getLogger("test.webrtc_session_monitor")
    websocket = SimpleNamespace(
        headers={},
        client=SimpleNamespace(host="127.0.0.1"),
        close=AsyncMock(),
    )

    monitor = asyncio.create_task(manager._monitor_session(websocket, principal))
    await asyncio.sleep(0)
    runtime.revoke_session_id(session_id)
    await asyncio.wait_for(monitor, timeout=1.0)

    websocket.close.assert_awaited_once_with(
        code=1008,
        reason="Browser session expired or revoked",
    )


@pytest.mark.asyncio
async def test_webrtc_signaling_handler_cancels_blocked_receive_and_closes_peer_on_revocation(
    monkeypatch,
):
    runtime, principal, session_id = _browser_session_runtime()
    session = runtime.session_record_for_principal(principal)
    assert session is not None

    class BlockingWebSocket:
        def __init__(self):
            self.headers = {
                "host": "pixeagle.test:8443",
                "origin": "https://pixeagle.test:8443",
                "cookie": f"{runtime.session_cookie_name}={session.session_id}",
            }
            self.client = SimpleNamespace(host="127.0.0.1")
            self.url = SimpleNamespace(query="")
            self.accept = AsyncMock()
            self.close = AsyncMock()
            self.send_text = AsyncMock()
            self._blocked = asyncio.Event()

        async def iter_text(self):
            yield '{"type":"noop","peer_id":"peer-session"}'
            await self._blocked.wait()

    websocket = BlockingWebSocket()
    peer = _FakePeerConnection()
    monkeypatch.setattr(
        "classes.webrtc_manager.RTCPeerConnection",
        lambda: peer,
    )
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=TRUSTED_LAN_LEGACY,
        cors_allowed_origins=["https://pixeagle.test:8443"],
        allowed_hosts=["pixeagle.test:8443"],
        api_port=5077,
        allow_credentials=True,
    )
    manager.api_auth_runtime = runtime
    manager.security_audit_logger = None
    manager.peer_connections = {}
    manager.max_connections = 3
    manager.frame_publisher = SimpleNamespace(
        register_client=MagicMock(),
        unregister_client=MagicMock(),
    )
    manager.logger = logging.getLogger("test.webrtc_revocation_handler")

    handler_task = asyncio.create_task(manager.signaling_handler(websocket))
    for _ in range(20):
        if manager.peer_connections:
            break
        await asyncio.sleep(0.01)
    assert len(manager.peer_connections) == 1
    assert "peer-session" not in manager.peer_connections

    runtime.revoke_session_id(session_id)
    await asyncio.wait_for(handler_task, timeout=1.0)

    websocket.close.assert_awaited_once_with(
        code=1008,
        reason="Browser session expired or revoked",
    )
    assert manager.peer_connections == {}
    assert peer.close_count == 1
    manager.frame_publisher.unregister_client.assert_called_once_with()


@pytest.mark.asyncio
async def test_webrtc_client_peer_ids_cannot_overwrite_existing_peers(monkeypatch):
    peers = [_FakePeerConnection(), _FakePeerConnection()]
    peer_iter = iter(peers)
    monkeypatch.setattr(
        "classes.webrtc_manager.RTCPeerConnection",
        lambda: next(peer_iter),
    )
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.peer_connections = {}
    manager.frame_publisher = SimpleNamespace(
        register_client=MagicMock(),
        unregister_client=MagicMock(),
    )
    manager.logger = logging.getLogger("test.webrtc_server_peer_ids")

    class OneMessageWebSocket:
        async def iter_text(self):
            yield '{"type":"noop","peer_id":"client-selected"}'

        send_text = AsyncMock()

    first_state = {"peer_id": None, "registered": False}
    second_state = {"peer_id": None, "registered": False}
    await manager._consume_signaling_messages(OneMessageWebSocket(), first_state)
    await manager._consume_signaling_messages(OneMessageWebSocket(), second_state)

    assert first_state["peer_id"] != second_state["peer_id"]
    assert "client-selected" not in manager.peer_connections
    assert set(manager.peer_connections) == {
        first_state["peer_id"],
        second_state["peer_id"],
    }
    assert manager.frame_publisher.register_client.call_count == 2

    await manager.shutdown()
    assert manager.peer_connections == {}
    assert manager.frame_publisher.unregister_client.call_count == 2


@pytest.mark.asyncio
async def test_webrtc_signaling_limit_reserves_capacity_before_peer_allocation():
    class IdleWebSocket:
        def __init__(self):
            self.headers = {
                "host": "pixeagle.test:8443",
                "origin": "https://pixeagle.test:8443",
            }
            self.client = SimpleNamespace(host="127.0.0.1")
            self.url = SimpleNamespace(query="")
            self.accept = AsyncMock()
            self.close = AsyncMock()
            self.send_text = AsyncMock()
            self.release = asyncio.Event()

        async def iter_text(self):
            await self.release.wait()
            if False:
                yield ""

    manager = WebRTCManager.__new__(WebRTCManager)
    manager.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=TRUSTED_LAN_LEGACY,
        cors_allowed_origins=["https://pixeagle.test:8443"],
        allowed_hosts=["pixeagle.test:8443"],
        api_port=5077,
        allow_credentials=True,
    )
    manager.api_auth_runtime = None
    manager.security_audit_logger = None
    manager.peer_connections = {}
    manager.max_connections = 1
    manager.frame_publisher = SimpleNamespace(
        register_client=MagicMock(),
        unregister_client=MagicMock(),
    )
    manager.logger = logging.getLogger("test.webrtc_signaling_capacity")

    first = IdleWebSocket()
    second = IdleWebSocket()
    first_task = asyncio.create_task(manager.signaling_handler(first))
    for _ in range(20):
        if getattr(manager, "_active_signaling_sessions", 0) == 1:
            break
        await asyncio.sleep(0.01)
    assert manager._active_signaling_sessions == 1

    await asyncio.wait_for(manager.signaling_handler(second), timeout=1.0)

    second.accept.assert_awaited_once_with()
    second.send_text.assert_awaited_once()
    second.close.assert_awaited_once_with(
        code=1008,
        reason="Max connections reached",
    )
    assert manager._active_signaling_sessions == 1

    first.release.set()
    await asyncio.wait_for(first_task, timeout=1.0)
    assert manager._active_signaling_sessions == 0
    assert manager.peer_connections == {}


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
        self._target = kwargs.get("target")
        self._args = kwargs.get("args", ())
        self._name = kwargs.get("name", "")
        self._alive = False

    def start(self):
        self.started = True
        if self._name == "gstreamer-release" and self._target is not None:
            self._target(*self._args)
        else:
            self._alive = True

    def join(self, timeout=None):
        pass

    def is_alive(self):
        return self._alive


def _bare_gstreamer_handler(writer):
    handler = GStreamerHandler.__new__(GStreamerHandler)
    handler.out = writer
    handler._writer_stop = threading.Event()
    handler._writer_thread = None
    handler._release_thread = None
    handler._retiring_output = None
    handler._frame_queue = queue.Queue(maxsize=2)
    handler._state_lock = threading.RLock()
    handler._lifecycle_lock = threading.RLock()
    handler._last_error = None
    handler._configuration_error = None
    handler._opencv_gstreamer_available = None
    handler._frames_letterboxed = 0
    handler._frames_rate_limited = 0
    handler._last_submit_monotonic = None
    handler._WRITER_STOP_TIMEOUT_S = 0.05
    handler._PIPELINE_RELEASE_TIMEOUT_S = 0.05
    return handler


def test_gstreamer_release_nulls_writer_and_drains_queue():
    writer = _FakeVideoWriter()
    handler = _bare_gstreamer_handler(writer)
    handler._frame_queue.put_nowait(object())

    assert handler.release() is True
    assert handler.release() is True

    assert writer.release_count == 1
    assert handler.out is None
    assert handler._frame_queue.empty()


def test_gstreamer_release_drains_queue_when_writer_release_fails():
    writer = _RaisingVideoWriter()
    handler = _bare_gstreamer_handler(writer)
    handler._frame_queue.put_nowait(object())

    assert handler.release() is False

    assert writer.release_count == 1
    assert handler.out is writer
    assert handler._retiring_output is writer
    assert handler._frame_queue.empty()
    assert handler._last_error == "pipeline_release_failed:RuntimeError"


def test_gstreamer_initialize_releases_existing_writer_before_replacing_it():
    old_writer = _FakeVideoWriter()
    old_writer.opened = False
    new_writer = _FakeVideoWriter()
    handler = _bare_gstreamer_handler(old_writer)
    handler.WIDTH = 2
    handler.HEIGHT = 2
    handler.FRAMERATE = 30
    handler.pipeline = "fake-pipeline"
    handler._config = SimpleNamespace(host="192.0.2.20", port=5600)
    handler.encoder_info = SimpleNamespace(encoder="x264enc", hardware=False)
    handler._queue_drops = 0
    handler._frames_queued = 0
    handler._frames_written = 0
    handler._frames_resized = 0

    with patch("classes.gstreamer_handler.cv2.VideoWriter", return_value=new_writer), \
            patch("classes.gstreamer_handler.cv2.getBuildInformation", return_value="GStreamer: YES"), \
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
    controller.gstreamer_handler = SimpleNamespace(
        release=MagicMock(return_value=True),
        encoder_status={"last_error": None},
    )
    controller.recording_manager = None
    controller.storage_manager = None

    with patch("classes.app_controller.Parameters.MAVLINK_ENABLED", False):
        result = await controller.shutdown()

    controller.gstreamer_handler.release.assert_called_once_with()
    assert "GStreamer output released" in result["steps"]
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_app_controller_shutdown_joins_px4_interface_tasks():
    controller = object.__new__(AppController)
    controller.following_active = False
    controller.video_handler = None
    controller.recording_manager = None
    controller.storage_manager = None
    controller.px4_interface = SimpleNamespace(stop=AsyncMock())

    with patch("classes.app_controller.Parameters.MAVLINK_ENABLED", False):
        result = await controller.shutdown()

    controller.px4_interface.stop.assert_awaited_once_with()
    assert "PX4 interface tasks stopped" in result["steps"]
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_app_controller_shutdown_reports_incomplete_gstreamer_cleanup():
    controller = object.__new__(AppController)
    controller.following_active = False
    controller.video_handler = None
    controller.gstreamer_handler = SimpleNamespace(
        release=MagicMock(return_value=False),
        encoder_status={"last_error": "pipeline_release_timeout"},
    )
    controller.recording_manager = None
    controller.storage_manager = None

    with patch("classes.app_controller.Parameters.MAVLINK_ENABLED", False):
        result = await controller.shutdown()

    assert "GStreamer output released" not in result["steps"]
    assert result["errors"] == [
        "GStreamer output cleanup incomplete: pipeline_release_timeout"
    ]

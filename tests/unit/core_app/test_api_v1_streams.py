"""Tests for typed /api/v1 streaming media health snapshots."""

import asyncio
import time
from types import SimpleNamespace

import pytest

from classes.api_v1_contracts import APIStreamingMediaHealthResponse
from classes.api_v1_streams import get_streaming_media_health_snapshot
from classes.parameters import Parameters


def _set_streaming_defaults(
    monkeypatch,
    *,
    streaming_enabled=True,
    gstreamer_enabled=False,
    http_max=20,
    ws_max=10,
    webrtc_max=3,
):
    monkeypatch.setattr(
        Parameters,
        "ENABLE_STREAMING",
        streaming_enabled,
        raising=False,
    )
    monkeypatch.setattr(Parameters, "HTTP_STREAM_HOST", "127.0.0.1", raising=False)
    monkeypatch.setattr(Parameters, "HTTP_STREAM_PORT", 5077, raising=False)
    monkeypatch.setattr(Parameters, "STREAM_FPS", 10, raising=False)
    monkeypatch.setattr(Parameters, "STREAM_WIDTH", 640, raising=False)
    monkeypatch.setattr(Parameters, "STREAM_HEIGHT", 480, raising=False)
    monkeypatch.setattr(Parameters, "STREAM_QUALITY", 50, raising=False)
    monkeypatch.setattr(Parameters, "STREAM_PROCESSED_OSD", True, raising=False)
    monkeypatch.setattr(Parameters, "ENABLE_ADAPTIVE_QUALITY", True, raising=False)
    monkeypatch.setattr(Parameters, "DEFAULT_PROTOCOL", "auto", raising=False)
    monkeypatch.setattr(Parameters, "PIPELINE_MODE", "REALTIME", raising=False)
    monkeypatch.setattr(Parameters, "HTTP_MAX_CONNECTIONS", http_max, raising=False)
    monkeypatch.setattr(Parameters, "WS_MAX_CONNECTIONS", ws_max, raising=False)
    monkeypatch.setattr(Parameters, "WEBRTC_MAX_CONNECTIONS", webrtc_max, raising=False)
    monkeypatch.setattr(Parameters, "WS_HEARTBEAT_INTERVAL", 30, raising=False)
    monkeypatch.setattr(Parameters, "WS_STALE_TIMEOUT_MULTIPLIER", 2, raising=False)
    monkeypatch.setattr(Parameters, "API_EXPOSURE_MODE", "local_only", raising=False)
    monkeypatch.setattr(Parameters, "API_AUTH_MODE", "local_compat", raising=False)
    monkeypatch.setattr(
        Parameters,
        "ENABLE_GSTREAMER_STREAM",
        gstreamer_enabled,
        raising=False,
    )
    monkeypatch.setattr(Parameters, "GSTREAMER_HOST", "192.0.2.10", raising=False)
    monkeypatch.setattr(Parameters, "GSTREAMER_PORT", 5600, raising=False)


class _Publisher:
    def __init__(self, latest):
        self._latest = latest
        self.client_count = 3

    def get_latest(self, prefer_osd=True):
        assert prefer_osd is True
        return self._latest


@pytest.mark.asyncio
async def test_streaming_media_health_reports_active_transports(monkeypatch):
    _set_streaming_defaults(monkeypatch, gstreamer_enabled=True)
    stamped_frame = SimpleNamespace(
        frame_id=42,
        timestamp=time.monotonic() - 0.25,
        is_osd=True,
    )
    websocket_client = SimpleNamespace(
        id="ws-test",
        connected_at=time.time() - 5.0,
        last_frame_time=time.time() - 0.1,
        quality=45,
        frame_drops=1,
        bandwidth_estimate=2048.0,
    )
    owner = SimpleNamespace(
        connection_lock=asyncio.Lock(),
        http_connections={"http-test"},
        ws_connections={"ws-test": websocket_client},
        webrtc_manager=SimpleNamespace(
            peer_connections={"peer-test": object()},
            ice_server_summary=[
                {
                    "kind": "turn",
                    "url": "turns:turn.example.test:5349",
                    "configured": True,
                    "credentials_configured": True,
                }
            ],
        ),
        frame_publisher=_Publisher(stamped_frame),
        stats={
            "frames_sent": 10,
            "frames_dropped": 2,
            "total_bandwidth": 1024 * 1024,
        },
        stream_optimizer=SimpleNamespace(frame_cache={"42_45": b"jpeg"}),
        quality_engine=SimpleNamespace(
            get_all_states=lambda: {"active_clients": 2, "cpu_monitoring_active": True}
        ),
        exposure_policy=SimpleNamespace(mode="local_only", bind_host="127.0.0.1"),
        api_auth_runtime=SimpleNamespace(mode="local_compat"),
        app_controller=SimpleNamespace(
            gstreamer_handler=SimpleNamespace(
                encoder_status={
                    "enabled": True,
                    "encoder": "x264enc",
                    "host": "192.0.2.10",
                    "port": 5600,
                }
            )
        ),
        is_shutting_down=False,
    )

    payload = await get_streaming_media_health_snapshot(owner)
    response = APIStreamingMediaHealthResponse(**payload)

    assert response.status == "active"
    assert response.consumer_guidance == "serving_media"
    assert response.health_issues == []
    assert response.frames.source_available is True
    assert response.frames.latest_frame_id == 42
    assert response.frames.latest_frame_stale is False
    assert response.frames.stale_timeout_s == 1.0
    assert response.frames.frames_sent == 10
    assert response.frames.frames_dropped == 2
    assert response.frames.drop_ratio == 0.1667
    transports = {transport.name: transport for transport in response.transports}
    assert transports["http_mjpeg"].status == "active"
    assert transports["websocket_jpeg"].details["clients"][0]["id"] == "ws-test"
    assert transports["webrtc_signaling"].details["peer_ids"] == ["peer-test"]
    assert transports["webrtc_signaling"].details["ice_servers"] == [
        {
            "kind": "turn",
            "url": "turns:turn.example.test:5349",
            "configured": True,
            "credentials_configured": True,
        }
    ]
    assert "credential" not in str(
        transports["webrtc_signaling"].details["ice_servers"]
    ).lower().replace("credentials_configured", "")
    assert transports["gstreamer_udp_h264"].status == "active"
    assert transports["gstreamer_udp_h264"].active_connections == 0
    assert (
        transports["gstreamer_udp_h264"].details["connection_semantics"]
        == "udp_output_has_no_client_connection_count"
    )
    assert response.security.required_scope == "media:read"
    assert response.security.query_string_tokens_allowed is False
    assert "process-local media transport" in response.claim_boundary


@pytest.mark.asyncio
async def test_streaming_media_health_degrades_when_clients_have_no_frame(monkeypatch):
    _set_streaming_defaults(monkeypatch, gstreamer_enabled=False)
    owner = SimpleNamespace(
        connection_lock=asyncio.Lock(),
        http_connections={"http-test"},
        ws_connections={},
        webrtc_manager=SimpleNamespace(peer_connections={}),
        frame_publisher=_Publisher(None),
        stats={"frames_sent": 0, "frames_dropped": 0, "total_bandwidth": 0},
        stream_optimizer=SimpleNamespace(frame_cache={}),
        quality_engine=SimpleNamespace(get_all_states=lambda: {}),
        exposure_policy=SimpleNamespace(mode="local_only", bind_host="127.0.0.1"),
        api_auth_runtime=SimpleNamespace(mode="local_compat"),
        app_controller=SimpleNamespace(gstreamer_handler=None),
        is_shutting_down=False,
    )

    payload = await get_streaming_media_health_snapshot(owner)
    response = APIStreamingMediaHealthResponse(**payload)

    assert response.status == "degraded"
    assert response.consumer_guidance == "operator_attention"
    assert response.frames.source_available is False
    assert "active_media_clients_without_published_frame" in response.health_issues
    transports = {transport.name: transport for transport in response.transports}
    assert transports["http_mjpeg"].status == "active"
    assert transports["gstreamer_udp_h264"].status == "disabled"


@pytest.mark.asyncio
async def test_streaming_media_health_degrades_when_latest_frame_is_stale(monkeypatch):
    _set_streaming_defaults(monkeypatch, gstreamer_enabled=False)
    stale_frame = SimpleNamespace(
        frame_id=9,
        timestamp=time.monotonic() - 2.0,
        is_osd=True,
    )
    owner = SimpleNamespace(
        connection_lock=asyncio.Lock(),
        http_connections={"http-test"},
        ws_connections={},
        webrtc_manager=SimpleNamespace(peer_connections={}),
        frame_publisher=_Publisher(stale_frame),
        stats={"frames_sent": 3, "frames_dropped": 0, "total_bandwidth": 1024},
        stream_optimizer=SimpleNamespace(frame_cache={}),
        quality_engine=SimpleNamespace(get_all_states=lambda: {}),
        exposure_policy=SimpleNamespace(mode="local_only", bind_host="127.0.0.1"),
        api_auth_runtime=SimpleNamespace(mode="local_compat"),
        app_controller=SimpleNamespace(gstreamer_handler=None),
        is_shutting_down=False,
    )

    payload = await get_streaming_media_health_snapshot(owner)
    response = APIStreamingMediaHealthResponse(**payload)

    assert response.status == "degraded"
    assert response.consumer_guidance == "operator_attention"
    assert response.frames.source_available is True
    assert response.frames.latest_frame_stale is True
    assert response.frames.latest_frame_age_s >= response.frames.stale_timeout_s
    assert "published_frame_stale" in response.health_issues


@pytest.mark.asyncio
async def test_streaming_media_health_degrades_when_gstreamer_active_without_frame(monkeypatch):
    _set_streaming_defaults(monkeypatch, gstreamer_enabled=True)
    owner = SimpleNamespace(
        connection_lock=asyncio.Lock(),
        http_connections=set(),
        ws_connections={},
        webrtc_manager=SimpleNamespace(peer_connections={}),
        frame_publisher=_Publisher(None),
        stats={"frames_sent": 0, "frames_dropped": 0, "total_bandwidth": 0},
        stream_optimizer=SimpleNamespace(frame_cache={}),
        quality_engine=SimpleNamespace(get_all_states=lambda: {}),
        exposure_policy=SimpleNamespace(mode="local_only", bind_host="127.0.0.1"),
        api_auth_runtime=SimpleNamespace(mode="local_compat"),
        app_controller=SimpleNamespace(
            gstreamer_handler=SimpleNamespace(encoder_status={"enabled": True})
        ),
        is_shutting_down=False,
    )

    payload = await get_streaming_media_health_snapshot(owner)
    response = APIStreamingMediaHealthResponse(**payload)

    assert response.status == "degraded"
    assert response.consumer_guidance == "operator_attention"
    assert "active_media_clients_without_published_frame" in response.health_issues
    transports = {transport.name: transport for transport in response.transports}
    assert transports["gstreamer_udp_h264"].status == "active"
    assert transports["gstreamer_udp_h264"].active_connections == 0


@pytest.mark.asyncio
async def test_streaming_media_health_surfaces_pending_gstreamer_cleanup(monkeypatch):
    _set_streaming_defaults(monkeypatch, gstreamer_enabled=True)
    owner = SimpleNamespace(
        connection_lock=asyncio.Lock(),
        http_connections=set(),
        ws_connections={},
        webrtc_manager=SimpleNamespace(peer_connections={}),
        frame_publisher=_Publisher(None),
        stats={"frames_sent": 0, "frames_dropped": 0, "total_bandwidth": 0},
        stream_optimizer=SimpleNamespace(frame_cache={}),
        quality_engine=SimpleNamespace(get_all_states=lambda: {}),
        exposure_policy=SimpleNamespace(mode="local_only", bind_host="127.0.0.1"),
        api_auth_runtime=SimpleNamespace(mode="local_compat"),
        app_controller=SimpleNamespace(
            gstreamer_handler=SimpleNamespace(
                encoder_status={
                    "enabled": False,
                    "cleanup_pending": True,
                    "last_error": "pipeline_release_timeout",
                }
            )
        ),
        is_shutting_down=False,
    )

    payload = await get_streaming_media_health_snapshot(owner)
    response = APIStreamingMediaHealthResponse(**payload)

    assert response.status == "degraded"
    assert "gstreamer_output_cleanup_pending" in response.health_issues
    transports = {transport.name: transport for transport in response.transports}
    transport = transports["gstreamer_udp_h264"]
    assert transport.status == "unavailable"
    assert transport.cleanup_pending is True
    assert transport.last_error == "pipeline_release_timeout"
    assert "cleanup_pending" not in transport.details
    assert "last_error" not in transport.details


@pytest.mark.asyncio
async def test_streaming_media_health_reports_disabled_backend_streaming(monkeypatch):
    _set_streaming_defaults(monkeypatch, streaming_enabled=False)
    owner = SimpleNamespace(
        connection_lock=asyncio.Lock(),
        http_connections=set(),
        ws_connections={},
        webrtc_manager=SimpleNamespace(peer_connections={}),
        frame_publisher=_Publisher(None),
        stats={"frames_sent": 0, "frames_dropped": 0, "total_bandwidth": 0},
        stream_optimizer=SimpleNamespace(frame_cache={}),
        quality_engine=SimpleNamespace(get_all_states=lambda: {}),
        exposure_policy=SimpleNamespace(mode="local_only", bind_host="127.0.0.1"),
        api_auth_runtime=SimpleNamespace(mode="local_compat"),
        app_controller=SimpleNamespace(gstreamer_handler=None),
        is_shutting_down=False,
    )

    payload = await get_streaming_media_health_snapshot(owner)
    response = APIStreamingMediaHealthResponse(**payload)

    assert response.status == "idle"
    assert response.config.streaming_enabled is False
    transports = {transport.name: transport for transport in response.transports}
    assert transports["http_mjpeg"].status == "disabled"
    assert transports["websocket_jpeg"].status == "disabled"
    assert transports["webrtc_signaling"].status == "disabled"


@pytest.mark.asyncio
async def test_streaming_media_health_reports_zero_capacity_transports_disabled(monkeypatch):
    _set_streaming_defaults(monkeypatch, http_max=0, ws_max=0, webrtc_max=0)
    owner = SimpleNamespace(
        connection_lock=asyncio.Lock(),
        http_connections=set(),
        ws_connections={},
        webrtc_manager=SimpleNamespace(peer_connections={}),
        frame_publisher=_Publisher(None),
        stats={"frames_sent": 0, "frames_dropped": 0, "total_bandwidth": 0},
        stream_optimizer=SimpleNamespace(frame_cache={}),
        quality_engine=SimpleNamespace(get_all_states=lambda: {}),
        exposure_policy=SimpleNamespace(mode="local_only", bind_host="127.0.0.1"),
        api_auth_runtime=SimpleNamespace(mode="local_compat"),
        app_controller=SimpleNamespace(gstreamer_handler=None),
        is_shutting_down=False,
    )

    payload = await get_streaming_media_health_snapshot(owner)
    response = APIStreamingMediaHealthResponse(**payload)

    transports = {transport.name: transport for transport in response.transports}
    assert transports["http_mjpeg"].status == "disabled"
    assert transports["websocket_jpeg"].status == "disabled"
    assert transports["webrtc_signaling"].status == "disabled"


@pytest.mark.asyncio
async def test_streaming_media_health_degrades_when_quality_engine_fails(monkeypatch):
    _set_streaming_defaults(monkeypatch, gstreamer_enabled=False)
    stamped_frame = SimpleNamespace(
        frame_id=7,
        timestamp=time.monotonic(),
        is_osd=True,
    )

    def raise_quality_error():
        raise RuntimeError("quality unavailable")

    owner = SimpleNamespace(
        connection_lock=asyncio.Lock(),
        http_connections=set(),
        ws_connections={},
        webrtc_manager=SimpleNamespace(peer_connections={}),
        frame_publisher=_Publisher(stamped_frame),
        stats={"frames_sent": 1, "frames_dropped": 0, "total_bandwidth": 512},
        stream_optimizer=SimpleNamespace(frame_cache={}),
        quality_engine=SimpleNamespace(get_all_states=raise_quality_error),
        exposure_policy=SimpleNamespace(mode="local_only", bind_host="127.0.0.1"),
        api_auth_runtime=SimpleNamespace(mode="local_compat"),
        app_controller=SimpleNamespace(gstreamer_handler=None),
        is_shutting_down=False,
    )

    payload = await get_streaming_media_health_snapshot(owner)
    response = APIStreamingMediaHealthResponse(**payload)

    assert response.status == "degraded"
    assert response.consumer_guidance == "operator_attention"
    assert response.quality_engine == {}
    assert response.health_issues == [
        "quality_engine_unavailable:quality unavailable",
    ]

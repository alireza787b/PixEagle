"""Tests for legacy media route helper extraction."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from classes import api_legacy_media_routes as routes


pytestmark = [pytest.mark.unit]


class FakeLogger:
    def __init__(self) -> None:
        self.debugs = []
        self.errors = []

    def debug(self, *args):
        self.debugs.append(args)

    def error(self, *args):
        self.errors.append(args)


class FakeVideoHandler:
    def __init__(self, *, recovery_success: bool = True, health=None) -> None:
        self.recovery_success = recovery_success
        self.health = health or {"status": "healthy", "source": "test"}
        self.recovery_calls = 0

    def force_recovery(self):
        self.recovery_calls += 1
        return self.recovery_success

    def get_connection_health(self):
        return self.health


class FailingVideoHandler(FakeVideoHandler):
    def get_connection_health(self):
        raise RuntimeError("health failed")


class FakeOSDPipeline:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def get_stats(self):
        if self.fail:
            raise RuntimeError("osd unavailable")
        return {"frames_processed": 9}


class FakeHandler:
    def __init__(self) -> None:
        self.connection_lock = asyncio.Lock()
        self.http_connections = {"http-a"}
        self.ws_connections = {}
        self.webrtc_manager = SimpleNamespace(peer_connections={})
        self.quality_engine = SimpleNamespace(
            get_all_states=lambda: {"client-a": {"quality": 70}}
        )
        self.app_controller = SimpleNamespace(_pipeline_metrics={"fps": 22.0})
        self.stream_optimizer = SimpleNamespace(frame_cache={"a": object()})
        self.stats = {
            "frames_sent": 10,
            "frames_dropped": 2,
            "total_bandwidth": 2 * 1024 * 1024,
            "active_connections": 1,
        }
        self.server = SimpleNamespace(started=90.0)
        self.video_handler = FakeVideoHandler()
        self.logger = FakeLogger()


def response_body(response):
    return json.loads(response.body.decode("utf-8"))


@pytest.mark.asyncio
async def test_streaming_status_reports_active_transport_and_config(monkeypatch):
    handler = FakeHandler()
    handler.ws_connections = {"ws-a": object()}
    handler.webrtc_manager.peer_connections = {"peer-a": object()}
    handler.app_controller.gstreamer_handler = SimpleNamespace(
        encoder_status={"running": True}
    )
    monkeypatch.setattr(routes.time, "time", lambda: 100.0)
    monkeypatch.setattr(routes.Parameters, "STREAM_FPS", 15, raising=False)
    monkeypatch.setattr(routes.Parameters, "STREAM_WIDTH", 800, raising=False)
    monkeypatch.setattr(routes.Parameters, "STREAM_HEIGHT", 600, raising=False)
    monkeypatch.setattr(routes.Parameters, "MIN_QUALITY", 25, raising=False)
    monkeypatch.setattr(routes.Parameters, "MAX_QUALITY", 90, raising=False)
    monkeypatch.setattr(routes.Parameters, "DEFAULT_PROTOCOL", "websocket", raising=False)
    monkeypatch.setattr(routes.Parameters, "PIPELINE_MODE", "REALTIME", raising=False)
    monkeypatch.setattr(
        routes.Parameters,
        "ENABLE_ADAPTIVE_QUALITY",
        True,
        raising=False,
    )

    body = response_body(await routes.get_streaming_status(handler))

    assert body["active_method"] == "webrtc"
    assert body["http_clients"] == 1
    assert body["websocket_clients"] == 1
    assert body["webrtc_clients"] == 1
    assert body["quality_engine"] == {"client-a": {"quality": 70}}
    assert body["gstreamer"] == {"running": True}
    assert body["pipeline"] == {"fps": 22.0}
    assert body["config"] == {
        "stream_fps": 15,
        "stream_width": 800,
        "stream_height": 600,
        "min_quality": 25,
        "max_quality": 90,
        "default_protocol": "websocket",
        "pipeline_mode": "REALTIME",
    }
    assert body["timestamp"] == 100.0


@pytest.mark.asyncio
async def test_streaming_status_active_method_fallbacks(monkeypatch):
    handler = FakeHandler()
    monkeypatch.setattr(routes.time, "time", lambda: 100.0)

    assert response_body(await routes.get_streaming_status(handler))[
        "active_method"
    ] == "http"

    handler.http_connections = set()
    handler.ws_connections = {"ws-a": object()}
    assert response_body(await routes.get_streaming_status(handler))[
        "active_method"
    ] == "websocket"

    handler.ws_connections = {}
    assert response_body(await routes.get_streaming_status(handler))[
        "active_method"
    ] == "none"


@pytest.mark.asyncio
async def test_streaming_stats_reports_clients_cache_uptime_and_osd(monkeypatch):
    handler = FakeHandler()
    handler.ws_connections = {
        "ws-a": SimpleNamespace(
            id="ws-a",
            connected_at=80.0,
            quality=65,
            frame_drops=3,
            bandwidth_estimate=2048.0,
        )
    }
    handler.app_controller.osd_pipeline = FakeOSDPipeline()
    monkeypatch.setattr(routes.time, "time", lambda: 100.0)

    body = response_body(await routes.get_streaming_stats(handler))

    assert body["frames_sent"] == 10
    assert body["frames_dropped"] == 2
    assert body["total_bandwidth_mb"] == 2.0
    assert body["http_connections"] == 1
    assert body["websocket_connections"] == 1
    assert body["cache_size"] == 1
    assert body["uptime"] == 10.0
    assert body["osd_pipeline"] == {"frames_processed": 9}
    assert body["websocket_clients"] == [
        {
            "id": "ws-a",
            "connected_duration": 20.0,
            "quality": 65,
            "frame_drops": 3,
            "bandwidth_kbps": 16.0,
        }
    ]


@pytest.mark.asyncio
async def test_streaming_stats_preserves_osd_failure_fallback(monkeypatch):
    handler = FakeHandler()
    handler.app_controller.osd_pipeline = FakeOSDPipeline(fail=True)
    monkeypatch.setattr(routes.time, "time", lambda: 100.0)

    body = response_body(await routes.get_streaming_stats(handler))

    assert body["osd_pipeline"] == {}
    assert handler.logger.debugs


@pytest.mark.asyncio
async def test_video_health_reports_video_and_obb_state(monkeypatch):
    handler = FakeHandler()
    handler.app_controller.smart_tracker = SimpleNamespace(
        model=object(),
        last_detections=[],
        current_geometry_mode="obb",
        model_task="detect",
    )
    monkeypatch.setattr(routes.time, "time", lambda: 100.0)

    body = response_body(await routes.get_video_health(handler))

    assert body["success"] is True
    assert body["video"] == {"status": "healthy", "source": "test"}
    assert body["obb_pipeline"] == {
        "model_loaded": True,
        "adapter_initialized": True,
        "geometry_utils_available": True,
        "geometry_mode": "obb",
        "model_task": "detect",
    }
    assert body["timestamp"] == 100.0


@pytest.mark.asyncio
async def test_video_health_unavailable_and_error_paths(monkeypatch):
    handler = FakeHandler()
    handler.video_handler = None
    monkeypatch.setattr(routes.time, "time", lambda: 100.0)

    unavailable = response_body(await routes.get_video_health(handler))
    assert unavailable["video"] == {"status": "unavailable"}
    assert unavailable["obb_pipeline"]["model_loaded"] is False

    handler.video_handler = FailingVideoHandler()
    with pytest.raises(HTTPException) as exc_info:
        await routes.get_video_health(handler)
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "health failed"
    assert handler.logger.errors


@pytest.mark.asyncio
async def test_reconnect_video_reports_success_and_updated_health(monkeypatch):
    handler = FakeHandler()
    handler.video_handler = FakeVideoHandler(
        recovery_success=True,
        health={"status": "healthy", "source": "reconnected"},
    )
    monkeypatch.setattr(routes.time, "time", lambda: 100.0)

    response = await routes.reconnect_video(handler)
    body = response_body(response)

    assert response.status_code == 200
    assert body == {
        "success": True,
        "message": "Video reconnect succeeded",
        "video": {"status": "healthy", "source": "reconnected"},
        "timestamp": 100.0,
    }
    assert handler.video_handler.recovery_calls == 1


@pytest.mark.asyncio
async def test_reconnect_video_reports_failed_recovery_with_503(monkeypatch):
    handler = FakeHandler()
    handler.video_handler = FakeVideoHandler(
        recovery_success=False,
        health={"status": "unavailable", "source": "camera"},
    )
    monkeypatch.setattr(routes.time, "time", lambda: 100.0)

    response = await routes.reconnect_video(handler)
    body = response_body(response)

    assert response.status_code == 503
    assert body == {
        "success": False,
        "message": "Video reconnect attempted but source still unavailable",
        "video": {"status": "unavailable", "source": "camera"},
        "timestamp": 100.0,
    }
    assert handler.video_handler.recovery_calls == 1


@pytest.mark.asyncio
async def test_reconnect_video_error_paths():
    handler = FakeHandler()
    handler.video_handler = None

    with pytest.raises(HTTPException) as unavailable:
        await routes.reconnect_video(handler)
    assert unavailable.value.status_code == 503
    assert unavailable.value.detail == "Video handler not initialized"

    handler.video_handler = FailingVideoHandler()
    with pytest.raises(HTTPException) as failed:
        await routes.reconnect_video(handler)
    assert failed.value.status_code == 500
    assert failed.value.detail == "health failed"
    assert handler.video_handler.recovery_calls == 1
    assert handler.logger.errors

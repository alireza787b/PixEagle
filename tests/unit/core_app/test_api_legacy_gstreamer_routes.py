"""Tests for legacy GStreamer route helper extraction."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from classes import api_legacy_gstreamer_routes as routes
from classes.parameters import Parameters


pytestmark = [pytest.mark.unit]


class FakeWriter:
    def __init__(self, opened=True) -> None:
        self.opened = opened

    def isOpened(self):
        return self.opened


class FakeGStreamerHandler:
    def __init__(self, *, opened=False, init_opens=True, hardware=False) -> None:
        self.out = FakeWriter(opened) if opened else None
        self.init_opens = init_opens
        self.initialize_calls = 0
        self.release_calls = 0
        self.encoder_info = SimpleNamespace(encoder="x264enc", hardware=hardware)

    def initialize_stream(self):
        self.initialize_calls += 1
        self.out = FakeWriter(True) if self.init_opens else None

    def release(self):
        self.release_calls += 1
        self.out = None


class RaisingGStreamerHandler(FakeGStreamerHandler):
    def initialize_stream(self):
        self.initialize_calls += 1
        raise RuntimeError("gst unavailable")


def make_handler(gstreamer_handler=None):
    app_controller = SimpleNamespace(gstreamer_handler=gstreamer_handler)
    return SimpleNamespace(
        app_controller=app_controller,
        logger=logging.getLogger("test.api_legacy_gstreamer_routes"),
    )


def response_body(response):
    return json.loads(response.body.decode("utf-8"))


@pytest.fixture(autouse=True)
def restore_gstreamer_parameters(monkeypatch):
    monkeypatch.setattr(Parameters, "ENABLE_GSTREAMER_STREAM", False, raising=False)
    monkeypatch.setattr(Parameters, "GSTREAMER_HOST", "192.168.10.20", raising=False)
    monkeypatch.setattr(Parameters, "GSTREAMER_PORT", 5600, raising=False)
    monkeypatch.setattr(Parameters, "GSTREAMER_WIDTH", 1280, raising=False)
    monkeypatch.setattr(Parameters, "GSTREAMER_HEIGHT", 720, raising=False)
    monkeypatch.setattr(Parameters, "GSTREAMER_FRAMERATE", 15, raising=False)
    monkeypatch.setattr(Parameters, "GSTREAMER_BITRATE", 2000, raising=False)


@pytest.mark.asyncio
async def test_status_reports_config_and_inactive_handler_absence():
    handler = make_handler(gstreamer_handler=None)

    status = response_body(await routes.get_gstreamer_status(handler))

    assert status["available"] is True
    assert status["enabled"] is False
    assert status["config_enabled"] is False
    assert status["encoder"] is None
    assert status["hardware_accelerated"] is False
    assert status["host"] == "192.168.10.20"
    assert status["port"] == 5600
    assert status["resolution"] == "1280x720"
    assert status["framerate"] == 15
    assert status["bitrate_kbps"] == 2000
    assert status["qgc_setup_hint"].endswith("port 5600")


@pytest.mark.asyncio
async def test_status_reports_active_encoder_details(monkeypatch):
    monkeypatch.setattr(Parameters, "ENABLE_GSTREAMER_STREAM", True, raising=False)
    gstreamer_handler = FakeGStreamerHandler(opened=True, hardware=True)
    gstreamer_handler.encoder_info.encoder = "nvh264enc"
    handler = make_handler(gstreamer_handler)

    status = response_body(await routes.get_gstreamer_status(handler))

    assert status["enabled"] is True
    assert status["config_enabled"] is True
    assert status["encoder"] == "nvh264enc"
    assert status["hardware_accelerated"] is True


@pytest.mark.asyncio
async def test_toggle_stops_active_stream_and_updates_parameter(monkeypatch):
    monkeypatch.setattr(Parameters, "ENABLE_GSTREAMER_STREAM", True, raising=False)
    gstreamer_handler = FakeGStreamerHandler(opened=True)
    handler = make_handler(gstreamer_handler)

    stopped = response_body(await routes.toggle_gstreamer(handler))

    assert stopped["status"] == "success"
    assert stopped["enabled"] is False
    assert stopped["action"] == "stopped"
    assert stopped["message"] == "GStreamer QGC output stream stopped"
    assert gstreamer_handler.release_calls == 1
    assert Parameters.ENABLE_GSTREAMER_STREAM is False


@pytest.mark.asyncio
async def test_toggle_creates_handler_and_reports_success(monkeypatch):
    created = FakeGStreamerHandler(init_opens=True, hardware=True)
    created.encoder_info.encoder = "vaapih264enc"
    monkeypatch.setattr(routes, "_new_gstreamer_handler", lambda: created)
    handler = make_handler(gstreamer_handler=None)

    started = response_body(await routes.toggle_gstreamer(handler))

    assert handler.app_controller.gstreamer_handler is created
    assert created.initialize_calls == 1
    assert started["status"] == "success"
    assert started["enabled"] is True
    assert started["action"] == "started"
    assert started["encoder"] == "vaapih264enc"
    assert started["hardware_accelerated"] is True
    assert started["message"] == "GStreamer QGC output started (vaapih264enc)"
    assert Parameters.ENABLE_GSTREAMER_STREAM is True


@pytest.mark.asyncio
async def test_toggle_existing_inactive_stream_failed_open_preserves_legacy_500():
    gstreamer_handler = FakeGStreamerHandler(init_opens=False)
    handler = make_handler(gstreamer_handler)

    response = await routes.toggle_gstreamer(handler)
    failed = response_body(response)

    assert response.status_code == 500
    assert failed["status"] == "error"
    assert failed["enabled"] is False
    assert failed["action"] == "failed"
    assert failed["message"] == (
        "GStreamer pipeline failed to open. Check GStreamer installation."
    )
    assert gstreamer_handler.initialize_calls == 1
    assert Parameters.ENABLE_GSTREAMER_STREAM is False


@pytest.mark.asyncio
async def test_toggle_initialize_exception_maps_to_http_500():
    handler = make_handler(RaisingGStreamerHandler())

    with pytest.raises(HTTPException) as exc:
        await routes.toggle_gstreamer(handler)

    assert exc.value.status_code == 500
    assert exc.value.detail == "gst unavailable"

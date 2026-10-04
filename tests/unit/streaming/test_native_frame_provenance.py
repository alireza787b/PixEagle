"""Camera-free provenance through production publisher/encoder/auth/WS routes."""

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from classes.api_v1_contracts import APIFrameProvenance
from classes.frame_publisher import CaptureStamp, FramePublisher
from classes.fastapi_handler import StreamingOptimizer
from classes.parameters import Parameters
from classes.video_handler import VideoHandler
from tools.native_integration_fixture import SyntheticMedia, create_app
from tests.unit.streaming.test_streaming_lifecycle import _handler_for_lifecycle_tests, _client

pytestmark = [pytest.mark.unit, pytest.mark.streaming]


def _pixels(value=50, width=40, height=20):
    return np.full((height, width, 3), value, dtype=np.uint8)


def _decode_number(jpeg):
    decoded = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    number = sum(1 << bit for bit in range(64)
                 if decoded[22 + (bit // 8) * 12, 22 + (bit % 8) * 12].mean() > 128)
    return decoded, number


def test_publication_owns_pixels_and_separates_capture_from_publication(monkeypatch):
    publisher = FramePublisher()
    pixels = _pixels()
    publisher.publish(pixels, None, capture=CaptureStamp("camera", "9007199254740993", 5.0, "cached"))
    frame = publisher.get_latest()
    pixels[:] = 255
    assert frame.frame.mean() == 50 and not frame.frame.flags.writeable
    metadata = frame.provenance(now=frame.timestamp + 1)
    assert metadata["frame_id"] == "1" and metadata["capture_id"] == "9007199254740993"
    assert metadata["publication_age_ms"] == 1000
    assert metadata["capture_age_ms"] > metadata["publication_age_ms"]
    assert metadata["capture_state"] == "cached" and metadata["geometry_verified"] is False
    APIFrameProvenance.model_validate(metadata)
    assert publisher.video_context()["capture_state"] == "unknown"


@pytest.mark.parametrize("field,value", [
    ("frame_id", 1), ("frame_id", "01"), ("capture_id", "0"),
    ("encoded_width", True), ("capture_age_ms", float("nan")),
    ("geometry_verified", True), ("version", "2"),
])
def test_provenance_contract_rejects_ambiguous_values(field, value):
    publisher = FramePublisher()
    publisher.publish(_pixels(), None)
    metadata = publisher.get_latest().provenance()
    metadata[field] = value
    with pytest.raises(ValidationError):
        APIFrameProvenance.model_validate(metadata)


def test_source_reset_drops_old_variants_and_rejects_late_processing():
    publisher = FramePublisher()
    capture = CaptureStamp("source-a", "1", time.monotonic(), "fresh")
    publisher.publish(_pixels(), _pixels(100), capture=capture)
    old = publisher.get_latest()
    publisher.invalidate_source("source-b")
    assert publisher.get_latest() is None and not publisher.is_current(old)
    publisher.publish(_pixels(200), None, capture=capture)
    assert publisher.get_latest() is None
    publisher.publish(None, _pixels(150), capture=CaptureStamp("source-b", "1", time.monotonic(), "fresh"))
    new = publisher.get_latest(prefer_osd=True)
    assert new.variant == "raw" and new.frame.mean() == 150
    assert new.stream_epoch != old.stream_epoch and new.frame_id > old.frame_id


def test_variant_and_output_size_change_epoch_and_encoder_cache():
    publisher = FramePublisher()
    optimizer = StreamingOptimizer()
    try:
        publisher.publish(_pixels(0), _pixels(255))
        osd = publisher.get_latest(True)
        raw = publisher.get_latest(False)
        black = optimizer.encode_frame_for_id(osd.frame, osd.cache_identity, 80)
        white = optimizer.encode_frame_for_id(raw.frame, raw.cache_identity, 80)
        assert black != white and osd.frame_id == raw.frame_id
        publisher.publish(None, _pixels(100, width=60))
        changed = publisher.get_latest(True)
        assert changed.stream_epoch != raw.stream_epoch
        assert changed.provenance()["encoded_width"] == 60 and changed.variant == "raw"
        assert not publisher.is_current(osd)
    finally:
        optimizer.encoder_pool.shutdown(wait=True)


def test_capture_cache_retains_identity_and_source_reset_invalidates_pixels(monkeypatch):
    monkeypatch.setattr(Parameters, "VIDEO_SOURCE_TYPE", "USB_CAMERA")
    handler = VideoHandler(initialize_source=False)
    publisher = FramePublisher()
    handler.set_source_listener(publisher.invalidate_source)
    frame = _pixels()
    handler.current_raw_frame = frame
    handler._reset_failure_counters(captured_at=123.0)
    fresh = handler.get_capture_stamp(frame)
    publisher.publish(frame, None, capture=fresh)
    cached_frame = handler._get_cached_frame()
    cached = handler.get_capture_stamp(cached_frame)
    assert cached.capture_id == fresh.capture_id and cached.captured_at == 123.0
    assert cached.state == "cached"
    handler._advance_source_epoch(clear_frames=True)
    assert publisher.get_latest() is None
    assert handler.get_capture_stamp(frame).source_epoch is None
    publisher.publish(frame, None, capture=fresh)
    assert publisher.get_latest() is None


def test_delivered_selection_survives_capture_ring_pressure_until_release():
    publisher = FramePublisher()
    publisher.selection_max_bytes = _pixels().nbytes * 2
    first_capture = CaptureStamp("camera", "1", time.monotonic(), "fresh")
    publisher.publish(_pixels(), None, analysis_frame=_pixels(width=80, height=40),
                      capture=first_capture, target_revision=0,
                      retain_analysis_pixels=False, selectable_variant="processed_osd")
    first = publisher.get_latest()
    token = first.selection_geometry["token"]
    assert publisher.pin_selection_delivery(first, "slow-client")
    for number in range(2, 20):
        publisher.publish(_pixels(), None, analysis_frame=_pixels(width=80, height=40),
                          capture=CaptureStamp("camera", str(number), time.monotonic(), "fresh"),
                          target_revision=0, retain_analysis_pixels=False,
                          selectable_variant="processed_osd")
    assert publisher.selection_snapshot(token) is not None
    publisher.unpin_selection_client("slow-client")
    assert publisher.selection_snapshot(token) is None


@pytest.mark.asyncio
async def test_websocket_pins_sampled_selection_before_slow_encoding(monkeypatch):
    monkeypatch.setattr(Parameters, "ENABLE_ADAPTIVE_QUALITY", False)
    handler = _handler_for_lifecycle_tests()
    handler.is_shutting_down = False
    handler.frame_interval = 0
    publisher = FramePublisher()
    publisher.selection_max_bytes = _pixels().nbytes * 2
    publisher.publish(_pixels(), None, analysis_frame=_pixels(width=80, height=40),
                      capture=CaptureStamp("camera", "1", time.monotonic(), "fresh"),
                      target_revision=0, retain_analysis_pixels=False,
                      selectable_variant="processed_osd")
    first = publisher.get_latest()
    token = first.selection_geometry["token"]
    handler.frame_publisher = publisher

    async def encode(*_args):
        for number in range(2, 20):
            publisher.publish(_pixels(), None, analysis_frame=_pixels(width=80, height=40),
                              capture=CaptureStamp("camera", str(number), time.monotonic(), "fresh"),
                              target_revision=0, retain_analysis_pixels=False,
                              selectable_variant="processed_osd")
        return b"jpeg"

    handler.stream_optimizer = SimpleNamespace(encode_frame_async=encode)
    websocket = SimpleNamespace(send_json=AsyncMock(), send_bytes=AsyncMock())
    websocket.send_bytes.side_effect = lambda _payload: setattr(handler, "is_shutting_down", True)
    await handler._ws_send_frames(websocket, _client(client_id="slow-client", connected_at=1, last_frame_time=0))
    assert websocket.send_json.await_args.args[0]["selection_geometry"]["token"] == token
    assert publisher.selection_snapshot(token) is not None


def test_async_capture_age_uses_reader_time_not_later_consumer_time(monkeypatch):
    monkeypatch.setattr(Parameters, "VIDEO_SOURCE_TYPE", "UDP_STREAM")
    handler = VideoHandler(initialize_source=False)
    handler._async_latest_frame = _pixels()
    handler._async_latest_frame_sequence = 1
    handler._async_latest_frame_time = time.time() - 2
    handler._async_latest_capture_monotonic = time.monotonic() - 2
    frame = handler._get_async_udp_frame()
    capture = handler.get_capture_stamp(frame)
    assert time.monotonic() - capture.captured_at >= 2


@pytest.mark.asyncio
async def test_source_changed_while_encoding_never_sends_retired_frame(monkeypatch):
    handler = _handler_for_lifecycle_tests()
    handler.is_shutting_down = False
    handler.frame_interval = 0
    handler.frame_publisher = FramePublisher()
    handler.frame_publisher.publish(_pixels(), None)
    async def encode(*args):
        handler.frame_publisher.invalidate_source("replacement")
        handler.is_shutting_down = True
        return b"retired"
    handler.stream_optimizer = SimpleNamespace(encode_frame_async=encode)
    websocket = SimpleNamespace(send_json=AsyncMock(), send_bytes=AsyncMock())
    await handler._ws_send_frames(websocket, _client(client_id="stale", connected_at=1, last_frame_time=0))
    websocket.send_json.assert_not_awaited()
    websocket.send_bytes.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_pair_failure_closes_and_clears_ack_without_waiting(monkeypatch):
    monkeypatch.setattr(Parameters, "ENABLE_ADAPTIVE_QUALITY", False)
    handler = _handler_for_lifecycle_tests()
    handler.is_shutting_down = False
    handler.frame_interval = 0
    handler.frame_publisher = FramePublisher()
    handler.frame_publisher.publish(_pixels(), None)
    handler.stream_optimizer = SimpleNamespace(encode_frame_async=AsyncMock(return_value=b"jpeg"))
    websocket = SimpleNamespace(send_json=AsyncMock(), send_bytes=AsyncMock(side_effect=RuntimeError("broken")), close=AsyncMock())
    client = _client(client_id="partial", connected_at=1, last_frame_time=0)
    client.latest_frame_ack_enabled = True
    await asyncio.wait_for(handler._ws_send_frames(websocket, client), timeout=1)
    websocket.close.assert_awaited_once_with(code=1011, reason="Incomplete video frame pair")
    assert client.frame_in_flight_id is None and client.frame_ack_event.is_set()
    assert websocket.send_json.await_count == 1


@pytest.mark.asyncio
async def test_pong_cannot_interleave_between_metadata_and_jpeg():
    handler = _handler_for_lifecycle_tests()
    handler.is_shutting_down = False
    client = _client(client_id="pair", connected_at=1, last_frame_time=0)
    metadata_sent = asyncio.Event()
    release_pair = asyncio.Event()
    events = []
    async def send_json(message):
        events.append(message["type"])
        if message["type"] == "frame":
            metadata_sent.set()
            await release_pair.wait()
        else:
            handler.is_shutting_down = True
    async def send_bytes(data):
        events.append("jpeg")
    websocket = SimpleNamespace(send_json=send_json, send_bytes=send_bytes,
                                receive_json=AsyncMock(return_value={"type": "ping"}))
    pair = asyncio.create_task(handler._ws_send_frame_pair(websocket, client, {"type": "frame", "frame_id": 1}, b"jpeg"))
    await metadata_sent.wait()
    receiver = asyncio.create_task(handler._ws_receive_messages(websocket, client))
    await asyncio.sleep(0)
    assert events == ["frame"]
    release_pair.set()
    await asyncio.gather(pair, receiver)
    assert events == ["frame", "jpeg", "pong"]


def test_fixture_freeze_drop_reset_and_source_size_variants(tmp_path):
    control = tmp_path / "media.json"
    publisher = FramePublisher()
    media = SyntheticMedia(publisher, 1, control)
    media.step()
    first = publisher.get_latest()
    control.write_text(json.dumps({"mode": "freeze"}))
    media.step()
    cached = publisher.get_latest()
    assert cached.capture.state == "cached" and cached.capture == CaptureStamp(
        first.capture.source_epoch, first.capture.capture_id, first.capture.captured_at, "cached")
    assert cached.frame_id > first.frame_id
    control.write_text(json.dumps({"mode": "drop"}))
    media.step()
    assert publisher.get_latest() is cached
    control.write_text(json.dumps({"source": "camera-b", "width": 800, "height": 600, "variant": "raw"}))
    media.step()
    changed = publisher.get_latest()
    assert changed.capture.source_epoch != first.capture.source_epoch
    assert changed.frame.shape == (600, 800, 3) and changed.variant == "raw"
    assert changed.stream_epoch != first.stream_epoch
    control.write_text(json.dumps({"source": "camera-b", "width": 800, "height": 600, "variant": "raw", "reset": "again"}))
    media.step()
    assert publisher.get_latest().stream_epoch != changed.stream_epoch


def test_real_fixture_auth_ws_pixels_provenance_status_and_logout(tmp_path, monkeypatch):
    monkeypatch.setattr(Parameters, "ENABLE_STREAMING", True)
    app = create_app(port=8091, system_id=1, uid="18446744073709551001", audit_path=tmp_path / "audit.jsonl")
    with TestClient(app, base_url="http://127.0.0.1:8091", client=("127.0.0.1", 32000)) as http:
        with pytest.raises(WebSocketDisconnect) as denied:
            with http.websocket_connect("ws://127.0.0.1:8091/ws/video_feed"):
                pass
        assert denied.value.code == 1008
        login = http.post("/api/v1/auth/login", json={"username": "operator", "password": "fixture-only"}).json()
        context = http.get("/api/v1/integration/context").json()
        assert "video.frame_provenance.v1" in context["capabilities"]
        assert "status.tracker_runtime.v1" in context["capabilities"]
        status = http.get("/api/v1/tracking/runtime-status")
        assert status.status_code == 200
        assert status.json()["status"] == "no_output" and not status.json()["following_active"]
        with http.websocket_connect("ws://127.0.0.1:8091/ws/video_feed") as ws:
            token = "initial-delivery-challenge"
            ws.send_json({"type": "stream_capabilities", "latest_frame_ack": True, "delivery_token": token})
            metadata = ws.receive_json()
            jpeg = ws.receive_bytes()
            if "delivery_token" not in metadata:
                # Initial pre-negotiation frames cannot prove transit age.
                ws.send_json({"type": "frame_ack", "frame_id": metadata["frame_id"], "delivery_token": token})
                metadata = ws.receive_json()
                jpeg = ws.receive_bytes()
            assert metadata["delivery_token"] == token
            next_token = "next-delivery-challenge-01"
            ws.send_json({"type": "frame_ack", "frame_id": metadata["frame_id"], "delivery_token": next_token})
            metadata = ws.receive_json()
            jpeg = ws.receive_bytes()
            assert metadata["delivery_token"] == next_token
            provenance = APIFrameProvenance.model_validate(metadata["provenance"])
            decoded, number = _decode_number(jpeg)
            assert str(number) == provenance.capture_id
            assert decoded.shape[:2] == (provenance.encoded_height, provenance.encoded_width)
            assert provenance.runtime_id == context["runtime_id"]
            assert provenance.instance_id == context["instance_id"]
            headers = {login["csrf_header_name"]: login["csrf_token"]}
            assert http.post("/api/v1/auth/logout", headers=headers).status_code == 200
            with pytest.raises(WebSocketDisconnect) as closed:
                for _ in range(4):
                    ws.receive_json()
                    ws.receive_bytes()
            assert closed.value.code == 1008
        # Login again to distinguish Origin/query rejection from logged-out denial.
        http.post("/api/v1/auth/login", json={"username": "operator", "password": "fixture-only"})
        for path, headers in [("/ws/video_feed", {"Origin": "http://evil.invalid"}),
                              ("/ws/video_feed?token=fixture-rejected", {})]:
            with pytest.raises(WebSocketDisconnect) as denied:
                with http.websocket_connect("ws://127.0.0.1:8091" + path, headers=headers):
                    pass
            assert denied.value.code == 1008


def test_no_aircraft_fixture_keeps_media_live_and_discovery_disconnected(tmp_path, monkeypatch):
    monkeypatch.setattr(Parameters, "ENABLE_STREAMING", True)
    app = create_app(port=8093, no_aircraft=True, audit_path=tmp_path / "audit.jsonl")
    with TestClient(app, base_url="http://127.0.0.1:8093", client=("127.0.0.1", 32000)) as http:
        assert http.get("/api/v1/integration/context").status_code == 401
        login = http.post("/api/v1/auth/login", json={"username": "operator", "password": "fixture-only"}).json()
        before = http.get("/api/v1/integration/context").json()
        headers = {login["csrf_header_name"]: login["csrf_token"]}
        discovery = http.post("/api/v1/integration/connection", json={}, headers=headers)
        assert discovery.status_code == 200
        after = discovery.json()
        for channel in ("command", "telemetry"):
            assert before[channel] == after[channel]
            assert after[channel]["connected"] is False
            assert after[channel]["autopilot_uid"] is None
            assert after[channel]["system_id"] is None
        assert after["telemetry"]["fresh"] is False
        assert after["association"]["verified"] is False
        assert {"command_disconnected", "telemetry_disconnected", "telemetry_route_unobserved"} <= set(
            after["association"]["reason_codes"])
        assert after["readiness"]["connection_ready"] is False
        assert after["readiness"]["following_allowed"] is False
        assert "video.frame_provenance.v1" in after["capabilities"]
        status = http.get("/api/v1/tracking/runtime-status").json()
        assert status["status"] == "no_output" and status["following_active"] is False
        with http.websocket_connect("ws://127.0.0.1:8093/ws/video_feed") as ws:
            frames = []
            for _ in range(2):
                metadata, jpeg = ws.receive_json(), ws.receive_bytes()
                provenance = APIFrameProvenance.model_validate(metadata["provenance"])
                decoded, number = _decode_number(jpeg)
                assert str(number) == provenance.capture_id
                assert decoded.shape[:2] == (provenance.encoded_height, provenance.encoded_width)
                assert provenance.runtime_id == after["runtime_id"]
                assert provenance.instance_id == after["instance_id"]
                assert provenance.geometry_verified is False
                frames.append(number)
            assert frames[1] > frames[0]
        final = http.get("/api/v1/integration/context").json()
        assert final["command"] == after["command"] and final["telemetry"] == after["telemetry"]


@pytest.mark.parametrize("aircraft_option", [
    {"system_id": 1}, {"uid": "123"}, {"telemetry_uid": "123"}, {"stale": True},
])
def test_no_aircraft_fixture_rejects_synthetic_aircraft_options(tmp_path, aircraft_option):
    with pytest.raises(ValueError, match="No-aircraft mode"):
        create_app(port=8093, no_aircraft=True, audit_path=tmp_path / "audit.jsonl", **aircraft_option)


def test_capture_release_retires_async_pixels_and_publisher_immediately(monkeypatch):
    monkeypatch.setattr(Parameters, "VIDEO_SOURCE_TYPE", "UDP_STREAM")
    handler = VideoHandler(initialize_source=False)
    publisher = FramePublisher()
    handler.set_source_listener(publisher.invalidate_source)
    handler._async_latest_frame = _pixels()
    handler._async_latest_frame_sequence = 1
    handler._async_latest_frame_time = time.time()
    handler._async_latest_capture_monotonic = time.monotonic()
    frame = handler._get_async_udp_frame()
    publisher.publish(frame, None, capture=handler.get_capture_stamp(frame))
    assert publisher.get_latest() is not None
    handler.release()
    assert publisher.get_latest() is None
    assert handler._get_async_udp_frame() is None
    assert handler.get_capture_stamp(frame).source_epoch is None


def test_prefetched_file_keeps_probe_receipt_time_until_publication(monkeypatch):
    monkeypatch.setattr(Parameters, "VIDEO_SOURCE_TYPE", "VIDEO_FILE")
    handler = VideoHandler(initialize_source=False)
    original = time.monotonic() - 3
    handler._prefetched_frame = _pixels()
    handler._prefetched_capture_monotonic = original
    ok, frame = handler._read_next_capture_frame()
    assert ok
    handler.current_raw_frame = frame
    handler._reset_failure_counters(captured_at=handler._last_read_capture_monotonic)
    assert handler.get_capture_stamp(frame).captured_at == original
    assert not handler.is_current_frame_usable_for_following()


def test_failed_source_open_cannot_republish_previous_camera(monkeypatch):
    monkeypatch.setattr(Parameters, "VIDEO_SOURCE_TYPE", "USB_CAMERA")
    monkeypatch.setattr(Parameters, "USE_GSTREAMER", False)
    handler = VideoHandler(initialize_source=False)
    publisher = FramePublisher()
    handler.set_source_listener(publisher.invalidate_source)
    handler.current_raw_frame = _pixels()
    handler._reset_failure_counters()
    publisher.publish(handler.current_raw_frame, None, capture=handler.get_capture_stamp())
    epoch = publisher.get_latest().capture.source_epoch
    monkeypatch.setattr(handler, "_create_capture_object", lambda: None)
    assert handler.initialize_source(max_retries=1, retry_delay=0) is False
    assert publisher.get_latest() is None and handler._get_cached_frame() is None
    assert publisher.video_context()["source_epoch"] != epoch


@pytest.mark.asyncio
async def test_cancelled_partial_pair_closes_socket_and_resets_ack():
    handler = _handler_for_lifecycle_tests()
    client = _client(client_id="cancel", connected_at=1, last_frame_time=0)
    client.latest_frame_ack_enabled = True
    started = asyncio.Event()
    async def binary(_data):
        started.set()
        await asyncio.Future()
    websocket = SimpleNamespace(send_json=AsyncMock(), send_bytes=binary, close=AsyncMock())
    sender = asyncio.create_task(handler._ws_send_frame_pair(websocket, client, {"frame_id": 1}, b"jpeg"))
    await started.wait()
    sender.cancel()
    with pytest.raises(asyncio.CancelledError):
        await sender
    assert client.frame_in_flight_id is None
    websocket.close.assert_awaited_once()


def test_video_disabled_context_does_not_advertise_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(Parameters, "ENABLE_STREAMING", False)
    app = create_app(port=8091, system_id=1, uid="1", audit_path=tmp_path / "audit.jsonl")
    with TestClient(app, base_url="http://127.0.0.1:8091", client=("127.0.0.1", 32000)) as http:
        http.post("/api/v1/auth/login", json={"username": "operator", "password": "fixture-only"})
        context = http.get("/api/v1/integration/context").json()
        assert "video.frame_provenance.v1" not in context["capabilities"]
        assert context["video"]["ws_path"] is None


@pytest.mark.asyncio
async def test_delivery_token_rotates_only_on_exact_ack_and_resets_with_negotiation():
    handler = _handler_for_lifecycle_tests()
    handler.is_shutting_down = False
    client = _client(client_id="nonce", connected_at=1, last_frame_time=0)
    first, second = "initial-challenge-0001", "next-challenge-000002"
    messages = asyncio.Queue()
    websocket = SimpleNamespace(receive_json=messages.get, send_json=AsyncMock())
    receiver = asyncio.create_task(handler._ws_receive_messages(websocket, client))
    async def deliver(message):
        await messages.put(message)
        await asyncio.sleep(0)
    await deliver({"type": "stream_capabilities", "latest_frame_ack": True, "delivery_token": first})
    assert client.delivery_token == first
    client.frame_in_flight_id = 3
    await deliver({"type": "frame_ack", "frame_id": 2, "delivery_token": second})
    assert client.delivery_token == first and client.frame_in_flight_id == 3
    await deliver({"type": "frame_ack", "frame_id": True, "delivery_token": second})
    assert client.delivery_token == first
    await deliver({"type": "frame_ack", "frame_id": 3, "delivery_token": second})
    assert client.delivery_token == second and client.frame_in_flight_id is None
    client.frame_in_flight_id = 4
    await deliver({"type": "frame_ack", "frame_id": 4, "delivery_token": "invalid?"})
    assert client.delivery_token == second and client.frame_in_flight_id is None
    await deliver({"type": "stream_capabilities", "latest_frame_ack": False})
    assert client.delivery_token is None
    receiver.cancel()
    await asyncio.gather(receiver, return_exceptions=True)
    assert _client(client_id="new-socket", connected_at=1, last_frame_time=0).delivery_token is None


@pytest.mark.parametrize("token", [None, 3, True, "short", "x" * 129, "x" * 16 + "?", "é" * 20])
def test_delivery_token_is_bounded_and_ascii(token):
    client = _client(client_id="bounds", connected_at=1, last_frame_time=0)
    client.accept_delivery_token(token)
    assert client.delivery_token is None


@pytest.mark.asyncio
async def test_delivery_token_and_ages_sampled_after_send_lock_delay(monkeypatch):
    handler = _handler_for_lifecycle_tests()
    handler.frame_publisher = FramePublisher()
    handler.frame_publisher.publish(_pixels(), None, capture=CaptureStamp("camera", "1", 10.0, "fresh"))
    stamped = handler.frame_publisher.get_latest()
    client = _client(client_id="delay", connected_at=1, last_frame_time=0)
    client.latest_frame_ack_enabled = True
    client.accept_delivery_token("old-challenge-000001")
    websocket = SimpleNamespace(send_json=AsyncMock(), send_bytes=AsyncMock())
    message = {"type": "frame", "frame_id": stamped.frame_id}
    async with client.send_lock:
        pair = asyncio.create_task(handler._ws_send_frame_pair(websocket, client, message, b"jpeg", stamped=stamped))
        await asyncio.sleep(0)
        client.accept_delivery_token("new-challenge-000002")
        assert not websocket.send_json.await_count
    with monkeypatch.context() as patch:
        patch.setattr("classes.frame_publisher.time.monotonic", lambda: stamped.timestamp + 2)
        await pair
    metadata = websocket.send_json.await_args.args[0]
    assert metadata["delivery_token"] == "new-challenge-000002"
    assert metadata["provenance"]["publication_age_ms"] == 2000
    assert metadata["frame_age_ms"] == 2000
    assert metadata["provenance"]["capture_age_ms"] >= 2000

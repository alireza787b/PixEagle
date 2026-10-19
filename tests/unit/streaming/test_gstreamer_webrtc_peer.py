"""Provider lifecycle and opt-in actual encrypted media qualification."""

import asyncio
import importlib.util
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from classes.gstreamer_webrtc_peer import GStreamerWebRTCPeer
from classes.parameters import Parameters
from classes.webrtc_manager import WebRTCManager

pytestmark = [pytest.mark.unit, pytest.mark.streaming]


def test_without_optional_runtime_browser_media_remains_available(monkeypatch):
    monkeypatch.setattr("classes.webrtc_manager._native_runtime", lambda: {"available": False})
    capability = WebRTCManager.native_client_capabilities()
    assert capability["available"] is False
    assert capability["runtime_ready"] is False
    assert "gstreamer_python_introspection" in capability["missing_components"]
    assert WebRTCManager.media_capabilities()["provider"] == "aiortc"
    assert WebRTCManager.media_capabilities()["interactive_native_transport"] == "websocket_jpeg"


def test_one_supported_codec_is_sufficient_for_sender_runtime_readiness(monkeypatch):
    monkeypatch.setattr("classes.webrtc_manager._native_runtime", lambda: {
        "available": True, "available_codecs": ["vp8"],
        "missing_elements": {"h264_association": ["x264enc"], "vp8_association": [],
                             "webrtc_transport": [], "congestion_control": []},
    })
    capability = WebRTCManager.native_client_capabilities()
    assert capability["runtime_ready"] is True
    assert capability["missing_components"] == []
    assert capability["available"] is False


@pytest.mark.parametrize("options", [{"fps": 0}, {"fps": True}, {"fps": 61},
                                     {"bitrate_bps": 0}, {"maximum_bitrate_bps": 20_000_000}])
def test_invalid_rate_limits_are_refused_without_loading_gstreamer(options):
    with pytest.raises(ValueError):
        GStreamerWebRTCPeer(None, **options)


@pytest.mark.asyncio
async def test_close_before_setup_is_idempotent_and_prevents_late_negotiation():
    peer = GStreamerWebRTCPeer(None)
    await asyncio.gather(peer.close(), peer.close())
    with pytest.raises(RuntimeError, match="closed"):
        await peer.answer("late offer")
    await peer.add_ice_candidate("candidate:late", 0)
    assert peer.drain_events() == []


@pytest.mark.asyncio
async def test_unconsumed_metadata_and_signaling_are_bounded():
    peer = GStreamerWebRTCPeer(None)
    try:
        for i in range(100):
            peer._event({"type": "ice-candidate", "candidate": str(i)})
        assert len(peer.drain_events()) <= 64
        assert peer.snapshot()["error"] == "signaling_backlog"
    finally:
        await peer.close()


@pytest.mark.asyncio
async def test_unknown_native_provider_is_refused_before_peer_or_publisher_allocation():
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.logger = logging.getLogger(__name__)
    manager.peer_connections = {}

    async def messages():
        yield json.dumps({"provider": "gstreamer", "type": "offer", "payload": {"sdp": "unqualified"}})

    websocket = SimpleNamespace(iter_text=messages, send_text=AsyncMock(), close=AsyncMock())
    state = {"peer_id": None}
    await manager._consume_signaling_messages(websocket, state)
    assert state["peer_id"] is None
    assert manager.peer_connections == {}
    assert json.loads(websocket.send_text.call_args.args[0])["stage"] == "native_provider_unavailable"
    websocket.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_late_native_offer_cannot_silently_use_the_browser_provider():
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.logger = logging.getLogger(__name__)
    manager.peer_connections = {}
    manager.frame_publisher = MagicMock()
    manager.handle_offer = AsyncMock()

    async def messages():
        yield json.dumps({"type": "ice-candidate", "payload": {}})
        yield json.dumps({"provider": "gstreamer", "type": "offer", "payload": {"sdp": "too late"}})

    websocket = SimpleNamespace(iter_text=messages, send_text=AsyncMock(), close=AsyncMock())
    state = {"peer_id": None, "pending_ice_candidates": []}
    try:
        await manager._consume_signaling_messages(websocket, state)
        manager.handle_offer.assert_not_awaited()
        assert json.loads(websocket.send_text.call_args.args[0])["stage"] == "provider_changed"
    finally:
        if state["peer_id"]:
            await manager._cleanup_peer(state["peer_id"])


@pytest.mark.asyncio
async def test_failed_native_event_delivery_ends_the_signaling_session():
    manager = WebRTCManager.__new__(WebRTCManager)
    manager._send_signaling_message = AsyncMock(return_value=False)
    peer = SimpleNamespace(drain_events=lambda: [{"type": "frame-context"}])
    websocket = SimpleNamespace(close=AsyncMock())
    await manager._forward_native_events(websocket, "fixture", peer)
    websocket.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancelled_negotiation_retires_sender_and_releases_it_once(monkeypatch):
    peer = GStreamerWebRTCPeer(None)
    entered = asyncio.Event()

    async def blocked_worker(*args):
        entered.set()
        await asyncio.Future()

    monkeypatch.setattr(peer, "_run", blocked_worker)
    negotiation = asyncio.create_task(peer.answer("fixture"))
    await entered.wait()
    negotiation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await negotiation
    monkeypatch.undo()
    await asyncio.gather(peer.close(), peer.close())
    assert peer.drain_events() == []


@pytest.mark.asyncio
async def test_timed_out_native_cleanup_retains_its_resource_slot_until_completion(monkeypatch):
    finished = asyncio.Event()

    class DelayedClose(GStreamerWebRTCPeer):
        def __init__(self):
            pass

        async def close(self):
            await finished.wait()

    manager = WebRTCManager.__new__(WebRTCManager)
    manager.max_connections = 1
    manager.logger = MagicMock()
    monkeypatch.setattr(Parameters, "WEBRTC_CLOSE_TIMEOUT_SECONDS", 0.01, raising=False)
    await manager._close_peer_connection("retiring", DelayedClose())
    assert not await manager._reserve_signaling_slot()
    pending = manager._pending_native_cleanup["retiring"]
    assert not pending.cancelled()
    finished.set()
    await asyncio.wait_for(pending, timeout=1)
    assert await manager._reserve_signaling_slot()
    await manager._release_signaling_slot()


@pytest.mark.asyncio
@pytest.mark.parametrize("codec,width,height", [("h264", 160, 120), ("vp8", 160, 120), ("h264", 1920, 1080)])
async def test_actual_encrypted_loopback_and_independent_decoded_identity(codec, width, height):
    if importlib.util.find_spec("gi") is None:
        pytest.skip("Optional GStreamer introspection is not installed")
    from classes.gstreamer_frame_association import gstreamer_capabilities

    capabilities = gstreamer_capabilities()
    if not capabilities["available"]:
        pytest.skip(capabilities["reason"])
    required = capabilities["missing_elements"][f"{codec}_association"] + capabilities["missing_elements"]["webrtc_transport"]
    if required:
        pytest.skip(f"Optional WebRTC elements missing: {required}")
    from tools.qualify_gstreamer_webrtc import qualify_peer

    result = await qualify_peer(codec, source_width=width, source_height=height)
    assert result["passed"] and result["late_metadata_rejected"]
    assert result["qgc_presentation_verified"] is False
    assert result["adaptation_qualified"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("codec", ["h264", "vp8"])
async def test_negotiated_congestion_controller_receives_actual_rtcp_feedback(codec):
    if importlib.util.find_spec("gi") is None:
        pytest.skip("Optional GStreamer introspection is not installed")
    from classes.gstreamer_frame_association import gstreamer_capabilities

    runtime = gstreamer_capabilities()
    required = runtime.get("missing_elements", {})
    if (not runtime["available"] or codec not in runtime.get("available_codecs", [])
            or required.get("webrtc_transport") or required.get("congestion_control")):
        pytest.skip("Optional adaptive WebRTC runtime is not installed")
    from tools.qualify_gstreamer_webrtc import qualify_peer

    result = await qualify_peer(codec, congestion_control=True, minimum_media_seconds=5)
    assert result["passed"]
    assert result["sender"]["congestion_feedback_events"] > 0
    assert result["sender"]["packet_recovery_negotiated"]
    assert 64_000 <= result["sender"]["encoder_target_bitrate_bps"] <= 4_000_000
    assert result["adaptation_qualified"] is False


@pytest.mark.parametrize("aggregate,connections,expected", [(8000, 3, (1_000_000, 2_666_666)),
                                                             (1000, 3, (333_333, 333_333)),
                                                             (20000, 1, (1_000_000, 4_000_000))])
def test_native_rate_limits_share_the_existing_aggregate_budget(monkeypatch, aggregate, connections, expected):
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.max_connections = connections
    monkeypatch.setattr(Parameters, "STREAM_MAX_BITRATE_KBPS", aggregate, raising=False)
    assert manager.native_rate_limits() == expected

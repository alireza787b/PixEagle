"""Codec negotiation and honest WebRTC transport diagnostics."""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiortc import RTCConfiguration, RTCPeerConnection, RTCRtpSender, RTCSessionDescription

from classes.webrtc_manager import WebRTCManager


pytestmark = [pytest.mark.unit, pytest.mark.streaming]


def test_preferences_preserve_every_local_codec_and_rtx():
    available = RTCRtpSender.getCapabilities("video").codecs
    preferred = WebRTCManager.preferred_video_codecs()

    assert len(preferred) == len(available)
    assert all(codec in preferred for codec in available)
    assert [codec for codec in preferred if codec.mimeType == "video/rtx"] == [
        codec for codec in available if codec.mimeType == "video/rtx"
    ]
    mime_types = [codec.mimeType.lower() for codec in preferred]
    assert mime_types.index("video/h264") < mime_types.index("video/vp8")


@pytest.mark.asyncio
@pytest.mark.parametrize("vp8_only", [False, True])
async def test_real_offer_prefers_h264_with_vp8_only_fallback(vp8_only):
    offerer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    answerer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.frame_publisher = SimpleNamespace(get_latest=lambda **kwargs: None)
    manager.logger = logging.getLogger(__name__)
    websocket = SimpleNamespace(send_text=AsyncMock())
    try:
        transceiver = offerer.addTransceiver("video", direction="recvonly")
        if vp8_only:
            transceiver.setCodecPreferences([
                codec for codec in RTCRtpSender.getCapabilities("video").codecs
                if codec.mimeType.lower() in {"video/vp8", "video/rtx"}
            ])
        await offerer.setLocalDescription(await offerer.createOffer())
        offer = offerer.localDescription
        assert await manager.handle_offer(
            answerer, {"sdp": offer.sdp, "type": offer.type}, websocket, "test-peer"
        )
        message = json.loads(websocket.send_text.call_args.args[0])
        sdp = message["payload"]["sdp"]
        video_line = next(line for line in sdp.splitlines() if line.startswith("m=video"))
        first_payload = video_line.split()[3]
        expected = "VP8" if vp8_only else "H264"
        assert f"a=rtpmap:{first_payload} {expected}/90000" in sdp
        assert " rtx/90000" in sdp
        assert message["media_capabilities"]["native_frame_association"] is False
        assert message["media_capabilities"]["presentation_verified"] is False
        connected = asyncio.Event()

        @offerer.on("connectionstatechange")
        def on_connection_state():
            if offerer.connectionState == "connected":
                connected.set()

        await offerer.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="answer"))
        await asyncio.wait_for(connected.wait(), timeout=5.0)
    finally:
        await offerer.close()
        await answerer.close()


def test_codec_preferences_leave_audio_unchanged():
    audio = SimpleNamespace(kind="audio", setCodecPreferences=MagicMock())
    video = SimpleNamespace(kind="video", setCodecPreferences=MagicMock())
    peer = SimpleNamespace(getTransceivers=lambda: [audio, video])
    WebRTCManager._prefer_video_codecs(peer)
    audio.setCodecPreferences.assert_not_called()
    video.setCodecPreferences.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_reports_session_payload_rate_not_client_presentation(monkeypatch):
    peer = SimpleNamespace(
        getStats=AsyncMock(return_value={
            "video": SimpleNamespace(
                type="outbound-rtp", kind="video", bytesSent=1000, packetsSent=10
            ),
            "audio": SimpleNamespace(
                type="outbound-rtp", kind="audio", bytesSent=9000, packetsSent=90
            ),
        }),
    )
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.peer_connections = {"test-peer": peer}
    manager._peer_created_at = {"test-peer": 10.0}
    manager.frame_publisher = SimpleNamespace(unregister_client=MagicMock())
    manager._close_peer_connection = AsyncMock()
    manager.logger = MagicMock()
    monkeypatch.setattr("classes.webrtc_manager.time.monotonic", lambda: 12.0)
    await manager._cleanup_peer("test-peer")
    result = json.loads(manager.logger.info.call_args.args[2])
    assert result["session_duration_seconds"] == 2.0
    assert result["session_average_video_payload_bps"] == 4000.0
    assert result["measurement_scope"] == "sender_payload_session_average"
    assert "presentation_verified" not in result
    assert manager._peer_created_at == {}
    manager.frame_publisher.unregister_client.assert_called_once()


@pytest.mark.asyncio
async def test_failed_stats_do_not_report_rate(monkeypatch):
    peer = SimpleNamespace(getStats=AsyncMock(side_effect=RuntimeError("unavailable")))
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.peer_connections = {"test-peer": peer}
    manager._peer_created_at = {"test-peer": 10.0}
    manager.frame_publisher = SimpleNamespace(unregister_client=MagicMock())
    manager._close_peer_connection = AsyncMock()
    manager.logger = MagicMock()
    monkeypatch.setattr("classes.webrtc_manager.time.monotonic", lambda: 12.0)
    await manager._cleanup_peer("test-peer")
    result = json.loads(manager.logger.info.call_args.args[2])
    assert result["stats_available"] is False
    assert "session_average_video_payload_bps" not in result

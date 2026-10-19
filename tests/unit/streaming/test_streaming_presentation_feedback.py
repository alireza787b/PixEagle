"""Peer-local presentation feedback is typed QoS evidence, never authority."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from classes.frame_publisher import FramePublisher
from classes.gstreamer_webrtc_peer import GStreamerWebRTCPeer
from classes.streaming_presentation_feedback import VideoPresentationFeedback
from classes.webrtc_manager import WebRTCManager

pytestmark = [pytest.mark.unit, pytest.mark.streaming]


def sample(**overrides):
    return dict(version=1, epoch='1', elapsed_ms=1000, verified_frames=20, presented_frames=19,
                last_presented_age_bound_ms=120.0, since_last_presentation_ms=20) | overrides


@pytest.mark.parametrize('invalid', [
    {'version': True}, {'epoch': '0'}, {'elapsed_ms': -1}, {'verified_frames': 3},
    {'presented_frames': True}, {'last_presented_age_bound_ms': float('nan')},
    {'last_presented_age_bound_ms': float('inf')}, {'since_last_presentation_ms': -1},
    {'capacity_mbps': 1000}, {'verified_frames': 0, 'presented_frames': 0},
])
def test_invalid_or_inconsistent_feedback_is_refused(invalid):
    with pytest.raises(ValidationError):
        VideoPresentationFeedback.model_validate(sample(**invalid))


@pytest.mark.asyncio
async def test_feedback_needs_no_optional_runtime_and_cannot_survive_peer_close():
    peer = GStreamerWebRTCPeer(FramePublisher())
    try:
        assert peer.update_presentation(sample())
        assert not peer.update_presentation(sample(version=True))
        assert peer.snapshot()['delivery_policy']['receiver_feedback_age_ms'] is not None
    finally:
        await peer.close()
    assert not peer.update_presentation(sample(elapsed_ms=2000))


@pytest.mark.asyncio
async def test_optional_invalid_feedback_preserves_age_challenge_and_peer_isolation():
    manager = WebRTCManager.__new__(WebRTCManager)
    manager._send_signaling_message = AsyncMock()
    peer = GStreamerWebRTCPeer(FramePublisher())
    other = GStreamerWebRTCPeer(FramePublisher())
    try:
        token = 'ab' * 16
        assert await manager._handle_native_message(
            peer, {'type': 'frame-challenge', 'payload': {'token': token, 'presentation': sample(version=True)}},
            SimpleNamespace(), 'peer-a')
        assert peer._challenge == token
        assert peer.snapshot()['delivery_policy']['receiver_feedback_age_ms'] is None
        assert await manager._handle_native_message(
            peer, {'type': 'frame-challenge', 'payload': {'token': token, 'presentation': sample()}},
            SimpleNamespace(), 'peer-a')
        assert peer.snapshot()['delivery_policy']['receiver_feedback_age_ms'] is not None
        assert other.snapshot()['delivery_policy']['receiver_feedback_age_ms'] is None
        assert other._challenge is None
        manager._send_signaling_message.assert_not_awaited()
    finally:
        await peer.close()
        await other.close()


@pytest.mark.asyncio
async def test_delivery_diagnostics_distinguishes_native_reservations_and_browser_gap():
    from classes.video_delivery_budget import VideoDeliveryBudget

    manager = WebRTCManager.__new__(WebRTCManager)
    manager.video_budget = VideoDeliveryBudget(8000)
    manager.video_budget.reserve_encoded('peer-a', 2_000_000)
    peer = GStreamerWebRTCPeer(FramePublisher())
    manager.peer_connections = {'peer-a': peer, 'browser': SimpleNamespace()}
    try:
        peer.update_presentation(sample())
        observed = manager.delivery_diagnostics()
        assert observed['browser_peers_outside_allocation'] == 1
        assert observed['native_peers_omitted'] == 0
        assert observed['payload_allocation']['jpeg_available_bps'] == 6_000_000
        assert observed['native_peers'][0]['delivery_policy']['receiver_feedback_age_ms'] is not None
        assert 'ice_servers' not in observed['native_peers'][0]
    finally:
        await peer.close()

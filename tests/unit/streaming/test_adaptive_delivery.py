"""Real delivery-path invariants, independent of camera or aircraft hardware."""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from classes.fastapi_handler import StreamingOptimizer
from classes.frame_publisher import CaptureStamp, FramePublisher
from classes.parameters import Parameters
from tests.unit.streaming.test_streaming_lifecycle import _client, _handler_for_lifecycle_tests

pytestmark = [pytest.mark.unit, pytest.mark.streaming]


def test_identical_concurrent_encodes_share_one_result(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def encode(*args):
        calls.append(args)
        entered.set()
        assert release.wait(2)
        return True, np.array([1, 2, 3], dtype=np.uint8)
    monkeypatch.setattr('classes.fastapi_handler.cv2.imencode', encode)
    optimizer = StreamingOptimizer(max_cache_size=2)
    pixels = np.zeros((20, 40, 3), dtype=np.uint8)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(optimizer.encode_frame_for_id, pixels, 'epoch:1', 80)
            assert entered.wait(2)
            second = workers.submit(optimizer.encode_frame_for_id, pixels, 'epoch:1', 80)
            release.set()
            assert first.result(2) == second.result(2) == b'\x01\x02\x03'
        assert len(calls) == 1
        assert optimizer.encoding_seconds('epoch:1', 80) >= 0
        for frame_id in ('epoch:2', 'epoch:3', 'epoch:4'):
            optimizer.encode_frame_for_id(pixels, frame_id, 80)
        assert len(optimizer.frame_cache) == 2
        assert not optimizer._inflight
    finally:
        release.set()
        optimizer.encoder_pool.shutdown()


def test_failed_encoder_does_not_poison_retry(monkeypatch):
    optimizer = StreamingOptimizer()
    try:
        monkeypatch.setattr('classes.fastapi_handler.cv2.imencode', lambda *args: (False, None))
        with pytest.raises(ValueError, match='Failed to encode'):
            optimizer.encode_frame_for_id(np.zeros((10, 10, 3)), 'retry', 80)
        monkeypatch.setattr('classes.fastapi_handler.cv2.imencode',
                            lambda *args: (True, np.array([3], dtype=np.uint8)))
        assert optimizer.encode_frame_for_id(np.zeros((10, 10, 3)), 'retry', 80) == b'\x03'
        assert not optimizer._inflight
    finally:
        optimizer.encoder_pool.shutdown()


def test_resized_delivery_retains_analysis_and_frame_identity():
    publisher = FramePublisher()
    pixels = np.zeros((180, 320, 3), dtype=np.uint8)
    analysis = np.ones((60, 80, 3), dtype=np.uint8)
    publisher.publish(pixels, None, analysis_frame=analysis, target_revision=4,
                      capture=CaptureStamp('camera', '7', time.monotonic(), 'fresh'))
    source = publisher.get_latest()
    resized = publisher.delivery_variant(source, 0.5)
    assert resized.frame.shape == (90, 160, 3)
    assert resized.capture == source.capture and resized.frame_id == source.frame_id
    assert resized.stream_epoch == source.stream_epoch
    assert resized.cache_identity != source.cache_identity
    assert resized.selection_geometry['analysis_width'] == 80
    assert resized.selection_geometry['encoded_width'] == 160
    assert resized.selection_geometry['token'] != source.selection_geometry['token']
    assert publisher.pin_selection_delivery(resized, 'client')
    retained = publisher.selection_snapshot(resized.selection_geometry['token'])
    assert np.array_equal(retained['analysis'], analysis)
    assert not resized.frame.flags.writeable
    publisher.invalidate_source('replacement')
    assert publisher.selection_snapshot(resized.selection_geometry['token']) is None
    assert not publisher.is_current(resized)


@pytest.mark.asyncio
async def test_unacknowledged_frame_retires_socket_without_another_send(monkeypatch):
    monkeypatch.setattr(Parameters, 'ENABLE_ADAPTIVE_QUALITY', False)
    handler = _handler_for_lifecycle_tests()
    handler.is_shutting_down = False
    handler.frame_interval = 0
    client = _client(client_id='stalled', connected_at=0, last_frame_time=0)
    client.latest_frame_ack_enabled = True
    client.frame_in_flight_id = 12
    client.frame_ack_timeout_seconds = 0.01
    socket = SimpleNamespace(close=AsyncMock(), send_bytes=AsyncMock())
    await asyncio.wait_for(handler._ws_send_frames(socket, client), timeout=0.5)
    socket.close.assert_awaited_once_with(code=1013, reason='Video acknowledgement timed out')
    socket.send_bytes.assert_not_awaited()


@pytest.mark.asyncio
async def test_resized_duplicate_is_not_resent(monkeypatch):
    monkeypatch.setattr(Parameters, 'ENABLE_ADAPTIVE_QUALITY', False)
    handler = _handler_for_lifecycle_tests()
    handler.is_shutting_down = False
    handler.frame_interval = 0
    handler.frame_publisher = FramePublisher()
    handler.frame_publisher.publish(np.zeros((20, 40, 3), dtype=np.uint8), None)
    handler.stream_optimizer = SimpleNamespace(
        encode_frame_async=AsyncMock(return_value=b'jpeg'), encoding_seconds=lambda *args: 0.001,
        encoder_pool=None)
    client = _client(client_id='scaled', connected_at=0, last_frame_time=0)
    client.adaptive_dimensions = True
    client.delivery_scale = 0.5
    sent = asyncio.Event()
    socket = SimpleNamespace(send_json=AsyncMock(), send_bytes=AsyncMock(side_effect=lambda _: sent.set()))
    task = asyncio.create_task(handler._ws_send_frames(socket, client))
    await asyncio.wait_for(sent.wait(), 0.5)
    # A bounded observation window catches a sender spinning on the variant key.
    await asyncio.sleep(0.025)
    handler.is_shutting_down = True
    await asyncio.wait_for(task, 0.5)
    socket.send_bytes.assert_awaited_once()


@pytest.mark.asyncio
async def test_ack_waits_for_write_measurement(monkeypatch):
    monkeypatch.setattr(Parameters, 'ENABLE_ADAPTIVE_QUALITY', True)
    handler = _handler_for_lifecycle_tests()
    handler.is_shutting_down = False
    client = _client(client_id='early-ack', connected_at=0, last_frame_time=0)
    client.latest_frame_ack_enabled = True
    started, release = asyncio.Event(), asyncio.Event()
    delivered = []

    async def write_bytes(_):
        started.set()
        await release.wait()

    async def receive_json():
        await started.wait()
        if not delivered:
            delivered.append(True)
            return {'type': 'frame_ack', 'frame_id': 7}
        handler.is_shutting_down = True
        return {'type': 'ping'}

    socket = SimpleNamespace(send_json=AsyncMock(), send_bytes=write_bytes,
                             receive_json=receive_json, close=AsyncMock())
    sender = asyncio.create_task(handler._ws_send_frame_pair(
        socket, client, {'type': 'frame', 'frame_id': 7}, b'jpeg'))
    await started.wait()
    receiver = asyncio.create_task(handler._ws_receive_messages(socket, client))
    await asyncio.sleep(0)
    handler.quality_engine.report_delivery.assert_not_called()
    release.set()
    await asyncio.wait_for(asyncio.gather(sender, receiver), 0.5)
    sample = handler.quality_engine.report_delivery.call_args.kwargs
    assert sample['send_time_seconds'] > 0
    assert sample['ack_time_seconds'] >= sample['send_time_seconds']
    assert client.frame_delivery_started is None and client.frame_in_flight_id is None


@pytest.mark.asyncio
async def test_stalled_close_does_not_block_client_cleanup():
    handler = _handler_for_lifecycle_tests()
    client = _client(client_id='close-stall', connected_at=0, last_frame_time=0)
    async def stalled_close(**kwargs):
        await asyncio.sleep(10)
    client.websocket = SimpleNamespace(close=AsyncMock(side_effect=stalled_close))
    handler.ws_connections[client.id] = client
    await asyncio.wait_for(handler._cleanup_websocket_client(
        client.id, close_code=1013, close_reason='stalled'), 0.8)
    assert client.id not in handler.ws_connections
    handler.quality_engine.unregister_client.assert_called_once_with(client.id)
    handler.frame_publisher.unregister_client.assert_called_once()

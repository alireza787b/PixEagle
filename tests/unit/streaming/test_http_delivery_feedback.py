"""HTTP reports completed ASGI writes, never fabricated presentation evidence."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from classes import api_legacy_media_routes as routes
from classes.adaptive_quality_engine import AdaptiveQualityEngine
from classes.frame_publisher import FramePublisher
from classes.parameters import Parameters
from classes.video_delivery_budget import VideoDeliveryBudget

pytestmark = [pytest.mark.unit, pytest.mark.streaming]


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def stream(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(routes, "time", SimpleNamespace(time=clock, monotonic=clock))
    for key, value in {"ENABLE_STREAMING": True, "ENABLE_ADAPTIVE_QUALITY": True,
                       "HTTP_MAX_CONNECTIONS": 10, "STREAM_PROFILE": "automatic",
                       "STREAM_QUALITY": 75, "STREAM_FPS": 20,
                       "STREAM_PROCESSED_OSD": True}.items():
        monkeypatch.setattr(Parameters, key, value, raising=False)
    publisher = FramePublisher()
    publisher.publish(np.zeros((8, 8, 3), dtype=np.uint8), None)
    engine = AdaptiveQualityEngine(clock=clock)
    engine.report_delivery = MagicMock(wraps=engine.report_delivery)
    engine.report_budget_pressure = MagicMock(wraps=engine.report_budget_pressure)

    async def encode(*_args):
        clock.now += 0.4  # Executor delay is deliberately much longer than service time.
        return b"jpeg-payload"

    handler = SimpleNamespace(
        connection_lock=asyncio.Lock(), http_connections=set(), ws_connections={},
        _update_active_connection_count=MagicMock(), frame_publisher=publisher,
        quality_engine=engine, is_shutting_down=False, frame_interval=0.05,
        stream_optimizer=SimpleNamespace(encode_frame_async=AsyncMock(side_effect=encode),
                                         encoding_seconds=MagicMock(return_value=0.003)),
        video_budget=VideoDeliveryBudget(8000, clock=clock), logger=MagicMock(),
        stats={"frames_sent": 0, "frames_dropped": 0, "total_bandwidth": 0},
    )
    return handler, clock


@pytest.mark.asyncio
async def test_report_follows_actual_asgi_write_and_excludes_encoder_queue(stream):
    handler, clock = stream
    response = await routes.video_feed(handler, SimpleNamespace(state=SimpleNamespace()))

    async def send(message):
        if message["type"] == "http.response.body" and message.get("more_body"):
            assert handler.quality_engine.report_delivery.call_count == 0
            clock.now += 0.07
            handler.is_shutting_down = True

    await response.stream_response(send)
    handler.quality_engine.report_delivery.assert_called_once()
    feedback = handler.quality_engine.report_delivery.call_args
    assert feedback.args[1] == len(b"jpeg-payload")
    assert feedback.kwargs["send_time_seconds"] == pytest.approx(0.07)
    assert feedback.kwargs["encoding_time_seconds"] == 0.003
    assert "ack_time_seconds" not in feedback.kwargs
    assert "presentation_delay_seconds" not in feedback.kwargs
    assert handler.stats["frames_sent"] == 1
    assert handler.frame_publisher.client_count == 0
    assert not handler.http_connections


@pytest.mark.asyncio
async def test_cancelled_yield_never_counts_as_completed_delivery(stream):
    handler, _ = stream
    response = await routes.video_feed(handler, SimpleNamespace(state=SimpleNamespace()))
    await anext(response.body_iterator)
    await response.body_iterator.aclose()
    handler.quality_engine.report_delivery.assert_not_called()
    assert handler.stats["frames_sent"] == 0
    assert handler.frame_publisher.client_count == 0


@pytest.mark.asyncio
async def test_budget_rejection_drops_work_without_successful_delivery(stream):
    handler, _ = stream

    def reject(_size):
        handler.is_shutting_down = True
        return None

    handler.video_budget = SimpleNamespace(reserve=reject, max_frame_bytes=1000)
    response = await routes.video_feed(handler, SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(StopAsyncIteration):
        await anext(response.body_iterator)
    handler.quality_engine.report_budget_pressure.assert_called_once()
    handler.quality_engine.report_delivery.assert_not_called()
    assert handler.stats["frames_dropped"] == 1
    assert handler.stats["frames_sent"] == 0


@pytest.mark.asyncio
async def test_source_retired_during_budget_wait_is_not_sent(stream):
    handler, _ = stream

    def retire(_size):
        handler.frame_publisher.invalidate_source("replacement")
        handler.is_shutting_down = True
        return 0.001

    handler.video_budget = SimpleNamespace(reserve=retire)
    response = await routes.video_feed(handler, SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(StopAsyncIteration):
        await anext(response.body_iterator)
    handler.quality_engine.report_delivery.assert_not_called()
    assert handler.stats["frames_sent"] == 0


@pytest.mark.asyncio
async def test_profile_scale_applies_to_first_frame_and_does_not_replay_source(stream, monkeypatch):
    handler, _ = stream
    monkeypatch.setattr(Parameters, "STREAM_PROFILE", "low_bandwidth")
    handler.quality_engine.default_profile = "low_bandwidth"
    original_latest = handler.frame_publisher.get_latest
    lookups = 0

    def latest(**kwargs):
        nonlocal lookups
        lookups += 1
        if lookups == 2:
            handler.is_shutting_down = True
        return original_latest(**kwargs)

    handler.frame_publisher.get_latest = latest
    response = await routes.video_feed(handler, SimpleNamespace(state=SimpleNamespace()))
    await anext(response.body_iterator)
    with pytest.raises(StopAsyncIteration):
        await anext(response.body_iterator)
    handler.stream_optimizer.encode_frame_async.assert_awaited_once()
    image = handler.stream_optimizer.encode_frame_async.call_args.args[0]
    assert image.shape == (6, 6, 3)


@pytest.mark.asyncio
async def test_slow_encode_and_write_do_not_add_an_extra_cadence_interval(stream, monkeypatch):
    handler, clock = stream
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        clock.now += seconds

    monkeypatch.setattr(routes, "asyncio", SimpleNamespace(sleep=sleep))
    response = await routes.video_feed(handler, SimpleNamespace(state=SimpleNamespace()))
    sent = 0

    async def send(message):
        nonlocal sent
        if message["type"] == "http.response.body" and message.get("more_body"):
            sent += 1
            clock.now += 0.07
            handler.frame_publisher.publish(np.zeros((8, 8, 3), dtype=np.uint8), None)
            if sent == 2:
                handler.is_shutting_down = True

    await response.stream_response(send)
    assert sent == 2
    assert len(sleeps) == 2  # Only the two short byte-budget waits remain.
    assert max(sleeps) < 0.001

"""Deterministic JPEG/budget matrix; this is not physical-link qualification."""

import cv2
import numpy as np
import pytest

from classes.adaptive_quality_engine import AdaptiveQualityEngine
from classes.parameters import Parameters
from classes.video_delivery_budget import VideoDeliveryBudget

pytestmark = [pytest.mark.unit, pytest.mark.streaming]


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def jpeg_sizes(monkeypatch):
    for key, value in {"STREAM_PROFILE": "automatic", "STREAM_QUALITY": 75,
                       "MIN_QUALITY": 30, "MAX_QUALITY": 85, "STREAM_FPS": 20,
                       "STREAM_STARTUP_FPS": 20, "STREAM_STARTUP_SCALE": 1.0,
                       "QUALITY_STEP_ADAPTIVE": 5, "QUALITY_COOLDOWN_SECONDS": 2}.items():
        monkeypatch.setattr(Parameters, key, value, raising=False)
    horizontal = np.linspace(0, 255, 1280, dtype=np.uint8)
    vertical = np.linspace(0, 255, 720, dtype=np.uint8)
    frame = np.stack(np.broadcast_arrays(
        horizontal[None, :], vertical[:, None], np.zeros((720, 1280), dtype=np.uint8)), axis=-1)
    cv2.putText(frame, "FRAME 00123 TARGET", (120, 330), cv2.FONT_HERSHEY_SIMPLEX,
                2, (255, 255, 255), 3)
    cached = {}

    def size(policy):
        key = (policy["resolution_scale"], policy["quality"])
        if key not in cached:
            scale, quality = key
            pixels = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            encoded, jpeg = cv2.imencode(".jpg", pixels, [cv2.IMWRITE_JPEG_QUALITY, quality])
            assert encoded
            cached[key] = len(jpeg)
        return cached[key]

    return size


@pytest.mark.parametrize("mbps", [0.5, 1, 2, 5, 10])
def test_automatic_policy_admits_real_jpegs_within_aggregate_budget(mbps, jpeg_sizes):
    clock = Clock()
    budget = VideoDeliveryBudget(mbps * 1000, clock=clock)
    engine = AdaptiveQualityEngine(clock=clock)
    engine.register_client("http")
    engine.register_client("websocket")
    delivered = {"http": 0, "websocket": 0}
    total_bytes = 0
    started = clock()
    for index in range(1200):
        client = "http" if index % 2 == 0 else "websocket"
        policy = engine.get_client_policy(client)
        payload_bytes = jpeg_sizes(policy)
        delay = budget.reserve(payload_bytes)
        if delay is None:
            policy = engine.report_budget_pressure(
                client, oversized=payload_bytes > budget.max_frame_bytes)
        else:
            assert 0 <= delay <= 0.25
            clock.now += delay
            total_bytes += payload_bytes
            delivered[client] += 1
            policy = engine.report_delivery(
                client, payload_bytes, send_time_seconds=0.002,
                ack_time_seconds=0.02 if client == "websocket" else None,
                encoding_time_seconds=0.004,
            )
        assert 55 <= policy["quality"] <= 85
        assert 5 <= policy["fps"] <= 20
        assert 0.25 <= policy["resolution_scale"] <= 1
        clock.now += 1 / policy["fps"]
    assert min(delivered.values()) > 20
    assert total_bytes / (clock() - started) <= mbps * 1_000_000 / 8


def test_unachievable_high_quality_floor_rejects_without_exceeding_budget(jpeg_sizes):
    clock = Clock()
    budget = VideoDeliveryBudget(500, clock=clock)
    engine = AdaptiveQualityEngine(clock=clock)
    engine.register_client("client", profile="high_quality")
    for _ in range(150):
        policy = engine.get_client_policy("client")
        # This fixture cannot fit the 250 ms horizon at the high-quality floor.
        assert budget.reserve(jpeg_sizes(policy)) is None
        clock.now += 0.5
        engine.report_budget_pressure("client", oversized=True)
    state = engine.get_client_state("client")
    assert state["quality"] == 70
    assert state["fps"] == 20
    assert state["resolution_scale"] == 0.75
    assert state["adjustment_reason"] == "unavailable_at_configured_limits"
    assert state["total_bytes"] == state["total_frames"] == 0


def test_dense_scene_can_exceed_automatic_floor_without_unbounded_wait(jpeg_sizes):
    clock = Clock()
    budget = VideoDeliveryBudget(500, clock=clock)
    engine = AdaptiveQualityEngine(clock=clock)
    engine.register_client("client")
    noise = np.random.default_rng(7).integers(0, 256, (180, 320, 3), dtype=np.uint8)
    frame = np.repeat(np.repeat(noise, 4, axis=0), 4, axis=1)
    for _ in range(12):
        policy = engine.get_client_policy("client")
        scale = policy["resolution_scale"]
        pixels = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        _, jpeg = cv2.imencode(".jpg", pixels, [cv2.IMWRITE_JPEG_QUALITY, policy["quality"]])
        assert len(jpeg) > budget.max_frame_bytes
        assert budget.reserve(len(jpeg)) is None
        engine.report_budget_pressure("client", oversized=True)
        clock.now += 1 / policy["fps"]
    state = engine.get_client_state("client")
    assert state["resolution_scale"] == 0.25
    assert state["quality"] == 55
    assert state["adjustment_reason"] == "unavailable_at_configured_limits"
    assert state["total_frames"] == 0

"""Shared JPEG budget admission remains bounded across concurrent clients."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from classes.video_delivery_budget import VideoDeliveryBudget

pytestmark = [pytest.mark.unit, pytest.mark.streaming]


class Clock:
    def __init__(self):
        self.now = 10.0

    def __call__(self):
        return self.now


def test_decimal_kbps_budget_reserves_serialization_time():
    clock = Clock()
    budget = VideoDeliveryBudget(8000, clock=clock)
    assert budget.reserve(100_000) == pytest.approx(0.1)
    assert budget.reserve(100_000) == pytest.approx(0.2)
    assert budget.reserve(100_000) is None
    clock.now += 0.1
    assert budget.reserve(100_000) == pytest.approx(0.2)


def test_oversized_frame_rejection_does_not_consume_capacity():
    budget = VideoDeliveryBudget(8000, clock=Clock())
    assert budget.reserve(250_001) is None
    assert budget.reserve(250_000) == pytest.approx(0.25)
    assert budget.reserve(1) is None


def test_idle_time_cannot_accumulate_an_unbounded_burst():
    clock = Clock()
    budget = VideoDeliveryBudget(8000, clock=clock)
    assert budget.reserve(100_000) == pytest.approx(0.1)
    clock.now += 3600
    assert budget.reserve(100_000) == pytest.approx(0.1)
    assert budget.reserve(100_000) == pytest.approx(0.2)
    assert budget.reserve(100_000) is None


def test_cancelled_reservation_expires_within_bounded_horizon():
    clock = Clock()
    budget = VideoDeliveryBudget(8000, clock=clock)
    assert budget.reserve(250_000) == pytest.approx(0.25)
    clock.now += 0.25
    assert budget.reserve(250_000) == pytest.approx(0.25)


def test_concurrent_http_and_websocket_clients_share_one_budget():
    budget = VideoDeliveryBudget(8000, clock=Clock())
    with ThreadPoolExecutor(max_workers=10) as executor:
        outcomes = list(executor.map(budget.reserve, [25_000] * 100))
    accepted = [delay for delay in outcomes if delay is not None]
    assert len(accepted) == 10
    assert max(accepted) <= 0.25
    assert sum(delay is None for delay in outcomes) >= 90


@pytest.mark.parametrize("value", [0, -1, True, float("nan"), float("inf"), "8000"])
def test_invalid_bitrate_is_rejected(value):
    with pytest.raises(ValueError):
        VideoDeliveryBudget(value)


@pytest.mark.parametrize("value", [0, -1, 0.251, True, float("nan"), float("inf")])
def test_delay_cannot_exceed_bound(value):
    with pytest.raises(ValueError):
        VideoDeliveryBudget(8000, max_delay_seconds=value)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "100"])
def test_invalid_payload_is_rejected(value):
    budget = VideoDeliveryBudget(8000)
    with pytest.raises(ValueError):
        budget.reserve(value)


def test_encoded_ceiling_drains_existing_jpeg_and_preserves_fallback_capacity():
    clock = Clock()
    budget = VideoDeliveryBudget(8000, clock=clock)
    assert budget.reserve(200_000) == pytest.approx(0.2)
    assert budget.reserve_encoded('native-a', 2_000_000) == pytest.approx(0.2)
    assert budget.reserve_encoded('native-a', 2_000_000) is None
    assert budget.reserve_encoded('native-b', 6_000_000) is None
    assert budget.max_frame_bytes == 187_500
    assert budget.reserve(187_501) is None
    clock.now += 0.2
    assert budget.reserve(187_500) == pytest.approx(0.25)
    budget.release_encoded('native-a')
    budget.release_encoded('native-a')
    assert budget.max_frame_bytes == 250_000
    assert budget.snapshot() == {'payload_budget_bps': 8_000_000, 'native_encoder_ceiling_bps': 0,
                                 'jpeg_available_bps': 8_000_000, 'native_reservations': 0}


def test_concurrent_encoder_reservations_cannot_claim_jpeg_or_another_encoder_share():
    budget = VideoDeliveryBudget(8000, clock=Clock())
    with ThreadPoolExecutor(max_workers=8) as executor:
        result = list(executor.map(lambda index: budget.reserve_encoded(str(index), 2_000_000), range(8)))
    assert sum(delay is not None for delay in result) == 3
    assert budget.snapshot()['jpeg_available_bps'] == 2_000_000
    assert budget.max_frame_bytes == 62_500
    assert budget.reserve(62_500) == pytest.approx(0.25)


def test_fractional_budget_does_not_round_to_zero_or_divide_by_zero():
    budget = VideoDeliveryBudget(0.0001, clock=Clock())
    assert budget.reserve(1) is None
    assert budget.reserve_encoded('too-large', 1) is None

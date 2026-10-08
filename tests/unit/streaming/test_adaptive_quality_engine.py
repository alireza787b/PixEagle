"""Real adaptive-engine regressions with deterministic delivery timing."""

import pytest

from classes.adaptive_quality_engine import AdaptiveQualityEngine
from classes.parameters import Parameters

pytestmark = [pytest.mark.unit, pytest.mark.streaming]


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds=0.1):
        self.now += seconds


@pytest.fixture
def engine(monkeypatch):
    settings = {
        "STREAM_PROFILE": "automatic", "MIN_QUALITY": 30, "MAX_QUALITY": 85,
        "STREAM_QUALITY": 75, "STREAM_FPS": 20, "QUALITY_STEP_ADAPTIVE": 5,
        "QUALITY_COOLDOWN_SECONDS": 2.0, "BANDWIDTH_EWMA_ALPHA": 0.3,
        "ENCODING_EWMA_ALPHA": 0.2, "ENCODING_TIME_THRESHOLD_MS": 20,
    }
    for key, value in settings.items():
        monkeypatch.setattr(Parameters, key, value, raising=False)
    clock = Clock()
    return AdaptiveQualityEngine(clock=clock), clock


def deliver(engine, clock, client="client", *, count=1, elapsed=0.1, **feedback):
    policy = None
    defaults = {"send_time_seconds": 0.002, "ack_time_seconds": 0.01,
                "encoding_time_seconds": 0.004}
    defaults.update(feedback)
    for _ in range(count):
        clock.advance(elapsed)
        policy = engine.report_delivery(client, 100_000, **defaults)
    return policy


def test_legacy_size_and_executor_wait_never_imply_congestion(engine):
    adaptive, clock = engine
    adaptive.register_client("legacy")
    before = adaptive.get_client_policy("legacy")
    for _ in range(40):
        clock.advance(1)
        assert adaptive.report_frame_sent("legacy", 900_000, 0.8) == 75
    assert adaptive.get_client_policy("legacy") == before
    state = adaptive.get_client_state("legacy")
    assert state["total_bytes"] == 36_000_000
    assert state["bandwidth_kbps"] == 0
    assert not state["feedback_available"]


def test_detailed_frames_on_fast_lan_recover_instead_of_losing_quality(engine):
    adaptive, clock = engine
    adaptive.register_client("client")
    policy = deliver(adaptive, clock, count=100)
    assert policy == {"profile": "automatic", "quality": 85, "fps": 20,
                      "resolution_scale": 1.0}
    assert adaptive.get_client_state("client")["bandwidth_kbps"] > 7000


def test_bandwidth_uses_observed_intervals_not_configured_fps(engine):
    adaptive, clock = engine
    adaptive.register_client("client")
    deliver(adaptive, clock)
    assert adaptive.get_client_state("client")["bandwidth_kbps"] == 0
    deliver(adaptive, clock, elapsed=0.5)
    assert adaptive.get_client_state("client")["bandwidth_kbps"] == pytest.approx(1562.5)


def test_delivery_pressure_reduces_fps_before_pixels_or_quality(engine):
    adaptive, clock = engine
    adaptive.register_client("client")
    policy = deliver(adaptive, clock, count=4, elapsed=0.6, ack_time_seconds=0.5)
    assert policy["fps"] < 20
    assert policy["resolution_scale"] == 1.0
    assert policy["quality"] == 75
    assert adaptive.get_client_state("client")["adjustment_reason"] == "delivery_delay"


def test_slow_client_and_global_cpu_do_not_reduce_fast_client(engine):
    adaptive, clock = engine
    adaptive.register_client("slow")
    adaptive.register_client("fast")
    adaptive.update_cpu_load(99)
    for _ in range(20):
        deliver(adaptive, clock, "slow", elapsed=0.5, ack_time_seconds=0.4)
        deliver(adaptive, clock, "fast")
    assert adaptive.get_client_policy("slow")["fps"] < 20
    assert adaptive.get_client_policy("fast")["fps"] == 20
    assert adaptive.get_client_policy("fast")["quality"] >= 75


@pytest.mark.parametrize("profile,min_scale,min_quality,max_fps", [
    ("automatic", 0.25, 55, 20),
    ("high_quality", 0.75, 70, 20),
    ("low_bandwidth", 0.25, 45, 10),
])
def test_sustained_pressure_respects_profile_bounds(engine, profile, min_scale, min_quality, max_fps):
    adaptive, clock = engine
    adaptive.register_client("client", profile=profile)
    initial = adaptive.get_client_policy("client")
    assert initial["fps"] == max_fps
    policy = deliver(adaptive, clock, count=120, elapsed=1, send_time_seconds=0.8, ack_time_seconds=1.0)
    assert policy["fps"] == 5
    assert policy["resolution_scale"] == min_scale
    assert policy["quality"] == min_quality


def test_quality_recovers_before_resolution_and_rate(engine):
    adaptive, clock = engine
    adaptive.register_client("client")
    policy = deliver(adaptive, clock, count=120, elapsed=1, send_time_seconds=0.8, ack_time_seconds=1.0)
    assert policy["quality"] == 55
    quality_recovered = False
    resolution_recovered = False
    for _ in range(1500):
        policy = deliver(adaptive, clock)
        if policy["resolution_scale"] > 0.25:
            quality_recovered = True
            assert policy["quality"] == 85
        if policy["fps"] > 5:
            resolution_recovered = True
            assert policy["resolution_scale"] == 1.0
    assert quality_recovered and resolution_recovered
    assert policy["fps"] == 20


def test_single_delay_spike_cannot_adjust_policy(engine):
    adaptive, clock = engine
    adaptive.register_client("client")
    before = adaptive.get_client_policy("client")
    clock.advance(3)
    deliver(adaptive, clock, ack_time_seconds=1.0)
    deliver(adaptive, clock, count=10)
    assert adaptive.get_client_policy("client") == before


def test_cooldown_and_evidence_count_both_gate_adjustments(engine):
    adaptive, clock = engine
    adaptive.register_client("client")
    deliver(adaptive, clock, count=10, elapsed=0.1, ack_time_seconds=0.5)
    assert adaptive.get_client_policy("client")["fps"] == 20
    deliver(adaptive, clock, count=3, elapsed=0.5, ack_time_seconds=0.5)
    assert adaptive.get_client_policy("client")["fps"] == 16
    deliver(adaptive, clock, count=8, elapsed=0.1, ack_time_seconds=0.5)
    assert adaptive.get_client_policy("client")["fps"] == 16


def test_ack_is_not_presentation_and_receiver_pressure_is_independent(engine):
    adaptive, clock = engine
    adaptive.register_client("client")
    deliver(adaptive, clock)
    state = adaptive.get_client_state("client")
    assert state["ack_time_ms"] == 10
    assert state["presentation_delay_ms"] is None
    deliver(adaptive, clock, count=6, elapsed=0.5, dropped_frames=2)
    assert adaptive.get_client_state("client")["adjustment_reason"] == "presentation_pressure"
    assert adaptive.get_client_policy("client")["fps"] < 20


def test_encoder_service_pressure_is_separate_from_delivery(engine):
    adaptive, clock = engine
    adaptive.register_client("client")
    deliver(adaptive, clock, count=6, elapsed=0.5, encoding_time_seconds=0.2)
    assert adaptive.get_client_state("client")["adjustment_reason"] == "encoding_pressure"
    assert adaptive.get_client_policy("client")["fps"] < 20


def test_write_completion_can_report_backpressure_without_an_ack(engine):
    adaptive, clock = engine
    adaptive.register_client("client")
    deliver(adaptive, clock, count=6, elapsed=0.5, send_time_seconds=0.2, ack_time_seconds=None)
    state = adaptive.get_client_state("client")
    assert state["ack_time_ms"] is None
    assert state["presentation_delay_ms"] is None
    assert state["adjustment_reason"] == "send_delay"


@pytest.mark.parametrize("invalid", [
    {"send_time_seconds": float("nan")}, {"ack_time_seconds": float("inf")},
    {"encoding_time_seconds": -1}, {"presentation_delay_seconds": True},
    {"dropped_frames": -1}, {"dropped_frames": 0.5},
    {"send_time_seconds": 0.1, "ack_time_seconds": 0.01},
])
def test_invalid_feedback_is_ignored_atomically(engine, invalid):
    adaptive, clock = engine
    adaptive.register_client("client")
    before = adaptive.get_client_state("client")
    deliver(adaptive, clock, **invalid)
    assert adaptive.get_client_state("client") == before


def test_stale_pressure_does_not_survive_idle_gap_or_profile_change(engine):
    adaptive, clock = engine
    adaptive.register_client("client")
    deliver(adaptive, clock, count=2, ack_time_seconds=0.5)
    clock.advance(10)
    policy = deliver(adaptive, clock)
    assert policy["fps"] == 20
    assert adaptive.get_client_state("client")["ack_time_ms"] == 10
    adaptive.set_client_profile("client", "low_bandwidth")
    state = adaptive.get_client_state("client")
    assert state["profile"] == "low_bandwidth"
    assert state["fps"] == 10
    assert state["quality"] <= 65
    assert state["ack_time_ms"] is None
    assert not state["feedback_available"]


def test_manual_quality_and_profile_requests_respect_bounds(engine):
    adaptive, clock = engine
    adaptive.register_client("client", profile="high_quality")
    adaptive.set_client_quality("client", 1)
    assert adaptive.get_client_quality("client") == 70
    adaptive.set_client_quality("client", 100)
    assert adaptive.get_client_quality("client") == 85
    with pytest.raises(ValueError, match="profile"):
        adaptive.set_client_profile("client", "unbounded")
    assert adaptive.get_client_policy("client")["profile"] == "high_quality"


def test_configured_default_and_small_fps_ceiling_are_preserved(monkeypatch, engine):
    _, clock = engine
    monkeypatch.delattr(Parameters, "STREAM_PROFILE")
    monkeypatch.setattr(Parameters, "STREAM_QUALITY", 40)
    monkeypatch.setattr(Parameters, "STREAM_FPS", 2)
    adaptive = AdaptiveQualityEngine(clock=clock)
    adaptive.register_client("client")
    assert adaptive.get_client_policy("client") == {
        "profile": "automatic", "quality": 40, "fps": 2, "resolution_scale": 1.0,
    }
    policy = deliver(adaptive, clock, count=120, elapsed=1, send_time_seconds=0.8, ack_time_seconds=1.0)
    assert policy["fps"] == 2
    assert policy["quality"] == 40


def test_unknown_or_removed_client_never_gains_state(engine):
    adaptive, clock = engine
    assert deliver(adaptive, clock) is None
    assert adaptive.get_client_state("client") is None
    assert adaptive.report_frame_sent("client", 123, 0.1) == 75
    adaptive.register_client("client")
    # Existing dashboards format this field directly, before the first frame.
    assert adaptive.get_client_state("client")["encoding_time_ms"] == 0
    snapshot = adaptive.get_client_policy("client")
    snapshot["fps"] = 1000
    assert adaptive.get_client_policy("client")["fps"] == 20
    adaptive.unregister_client("client")
    assert adaptive.get_all_states()["active_clients"] == 0


def test_shared_budget_rejection_changes_policy_without_fake_delivery(engine):
    adaptive, clock = engine
    adaptive.register_client("client")
    for _ in range(6):
        clock.advance(0.5)
        policy = adaptive.report_budget_pressure("client")
    assert policy["fps"] < 20
    state = adaptive.get_client_state("client")
    assert state["adjustment_reason"] == "shared_budget"
    assert state["total_bytes"] == state["total_frames"] == 0
    assert not state["feedback_available"]
    assert state["ack_time_ms"] is None


def test_oversized_payload_reduces_pixels_immediately_without_reducing_fps(engine):
    adaptive, clock = engine
    adaptive.register_client("client")
    policy = adaptive.report_budget_pressure("client", oversized=True)
    assert policy["resolution_scale"] == 0.75
    assert policy["fps"] == 20
    assert policy["quality"] == 75
    for _ in range(15):
        policy = adaptive.report_budget_pressure("client", oversized=True)
    assert policy["resolution_scale"] == 0.25
    assert policy["quality"] == 55
    state = adaptive.get_client_state("client")
    assert state["adjustment_reason"] == "unavailable_at_configured_limits"
    assert state["total_frames"] == 0


def test_legacy_fixed_dimensions_never_select_an_ineffective_smaller_size(engine):
    adaptive, _ = engine
    adaptive.register_client("client")
    policy = adaptive.report_budget_pressure("client", oversized=True, can_resize=False)
    assert policy["resolution_scale"] == 1
    assert policy["quality"] == 70
    assert policy["fps"] == 20
    for _ in range(10):
        adaptive.report_budget_pressure("client", oversized=True, can_resize=False)
    state = adaptive.get_client_state("client")
    assert state["resolution_scale"] == 1
    assert state["quality"] == 55
    assert state["adjustment_reason"] == "unavailable_at_configured_limits"


def test_feedback_diagnostics_expire_without_a_new_delivery(engine):
    adaptive, clock = engine
    adaptive.register_client("client")
    deliver(adaptive, clock)
    state = adaptive.get_client_state("client")
    assert state["feedback_available"]
    assert state["feedback_age_ms"] == 0
    assert not state["feedback_stale"]
    clock.advance(10)
    stale = adaptive.get_client_state("client")
    assert not stale["feedback_available"]
    assert stale["feedback_age_ms"] == 10_000
    assert stale["feedback_stale"]
    assert stale["total_frames"] == 1
    deliver(adaptive, clock)
    assert adaptive.get_client_state("client")["feedback_available"]

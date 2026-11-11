import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from classes.gimbal_guidance import (
    GimbalManoeuvreSupport,
    GimbalObservationLimits,
    GimbalGuidanceClassifier,
    GimbalGuidancePolicy,
    GuidanceState,
)


class Ray:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


def classifier(clock):
    return GimbalGuidanceClassifier(
        GimbalGuidancePolicy(),
        GimbalManoeuvreSupport(
            supports_vertical=True,
            supports_reverse=True,
            supports_yaw_fallback=True,
        ),
        clock=clock,
    )


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None])
def test_implemented_manoeuvres_are_typed_and_cannot_enable_guidance_by_truthiness(value):
    with pytest.raises(ValueError, match="manoeuvre_support_invalid"):
        GimbalManoeuvreSupport(supports_vertical=value)


def test_navigation_direction_does_not_reinterpret_physical_provider_limits():
    capabilities = GimbalManoeuvreSupport(
        supports_vertical=True, supports_yaw_fallback=True,
    )
    state = GimbalGuidanceClassifier(GimbalGuidancePolicy(), capabilities,
        observation_limits=GimbalObservationLimits((-45., 45.), (-30., 30.)))
    for now in (0., .31):
        decision = state.update(Ray(0., 0., 1.), now=now, provider_ray=Ray(1., 0., 0.))
    assert decision.state is GuidanceState.VERTICAL
    assert decision.bearing_deg is None
    invalid = state.update(Ray(1., 0., 0.), now=.4, provider_ray=Ray(0., 1., 0.))
    assert invalid.state is GuidanceState.UNREACHABLE
    assert invalid.reason == "gimbal_observation_limit"


def test_vertical_hysteresis_and_fresh_dwell():
    now = [0.0]
    state = classifier(lambda: now[0])
    assert state.update(Ray(1.0, 0.0, 0.0)).state is GuidanceState.FORWARD
    now[0] = 0.1
    assert state.update(Ray(0.1, 0.0, 0.995)).transition_pending
    now[0] = 0.41
    assert state.update(Ray(0.1, 0.0, 0.995)).state is GuidanceState.VERTICAL
    now[0] = 0.45
    assert state.update(Ray(0.25, 0.0, 0.968)).state is GuidanceState.VERTICAL
    now[0] = 1.07
    assert state.update(Ray(0.31, 0.0, 0.951)).transition_pending
    now[0] = 1.38
    assert state.update(Ray(0.31, 0.0, 0.951)).state is GuidanceState.FORWARD


def test_processing_the_same_angle_cannot_complete_vertical_or_rearward_dwell():
    state = classifier(lambda: 101.)
    for ray in (Ray(0., 0., 1.), Ray(-1., 0., 0.)):
        state.reset()
        first = state.update(ray, now=100., observed_at_monotonic_s=100.)
        repeated = state.update(ray, now=100.6, observed_at_monotonic_s=100.)
        assert repeated.state is first.state
        assert repeated.transition_pending
        fresh = state.update(ray, now=100.61, observed_at_monotonic_s=100.61)
        assert fresh.state in (GuidanceState.VERTICAL, GuidanceState.YAW_FIRST)


@pytest.mark.parametrize("observed", [True, float("nan"), float("inf"), 102., "100"])
def test_invalid_angle_receipt_clock_cannot_advance_guidance(observed):
    state = classifier(lambda: 101.)
    with pytest.raises(ValueError, match="observation_time_invalid"):
        state.update(Ray(0., 0., 1.), observed_at_monotonic_s=observed)


def test_reordered_angle_receipt_is_rejected_without_advancing_dwell():
    state = classifier(lambda: 101.)
    state.update(Ray(0., 0., 1.), observed_at_monotonic_s=100.5)
    with pytest.raises(ValueError, match="observation_reordered"):
        state.update(Ray(0., 0., 1.), observed_at_monotonic_s=100.4)
    assert state.last_decision.transition_pending


def test_rearward_grace_then_yaw_first_and_forward_reentry():
    now = [0.0]
    state = classifier(lambda: now[0])
    state.update(Ray(1.0, 0.0, 0.0))
    now[0] = 0.1
    assert state.update(Ray(-1.0, 0.0, 0.0)).transition_pending
    now[0] = 0.41
    assert state.update(Ray(-1.0, 0.0, 0.0)).state is GuidanceState.REARWARD_GRACE
    now[0] = 0.61
    assert state.update(Ray(-1.0, 0.0, 0.0)).state is GuidanceState.YAW_FIRST
    now[0] = 1.0
    assert state.update(Ray(math.cos(math.radians(75)), math.sin(math.radians(75)), 0.0)).transition_pending
    now[0] = 1.31
    assert state.update(Ray(math.cos(math.radians(75)), math.sin(math.radians(75)), 0.0)).state is GuidanceState.FORWARD


def test_forward_reentry_starts_a_new_rearward_grace_window():
    now = [0.0]
    state = classifier(lambda: now[0])
    state.update(Ray(1.0, 0.0, 0.0))
    now[0] = 0.31
    state.update(Ray(-1.0, 0.0, 0.0))
    now[0] = 0.61
    state.update(Ray(-1.0, 0.0, 0.0))
    now[0] = 0.7
    state.update(Ray(1.0, 0.0, 0.0))
    now[0] = 1.01
    assert state.update(Ray(1.0, 0.0, 0.0)).state is GuidanceState.FORWARD
    now[0] = 1.11
    state.update(Ray(-1.0, 0.0, 0.0))
    now[0] = 1.42
    assert state.update(Ray(-1.0, 0.0, 0.0)).state is GuidanceState.REARWARD_GRACE


def test_vertical_does_not_compute_an_azimuth():
    state = classifier(lambda: 0.0)
    decision = state.update(Ray(0.0, 0.0, 1.0))
    assert decision.bearing_deg is None


def test_strategy_without_special_manoeuvres_fails_closed():
    state = GimbalGuidanceClassifier(GimbalGuidancePolicy(), clock=lambda: 0.0)
    state.update(Ray(1.0, 0.0, 0.0))
    assert state.update(Ray(0.0, 0.0, 1.0), now=0.31).state is GuidanceState.UNREACHABLE


def test_policy_rejects_collapsed_hysteresis():
    with pytest.raises(ValueError):
        GimbalGuidancePolicy(vertical_enter_horizontal_norm=0.4, vertical_exit_horizontal_norm=0.2)


def test_forward_only_policy_never_commands_reverse_translation():
    now = [0.0]
    policy = GimbalGuidancePolicy(policy="forward_only")
    state = GimbalGuidanceClassifier(
        policy,
        GimbalManoeuvreSupport(supports_yaw_fallback=True),
        clock=lambda: now[0],
    )
    state.update(Ray(1.0, 0.0, 0.0))
    now[0] = 0.31
    assert state.update(Ray(-1.0, 0.0, 0.0)).state is GuidanceState.YAW_FIRST

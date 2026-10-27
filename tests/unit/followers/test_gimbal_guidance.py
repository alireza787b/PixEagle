import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from classes.gimbal_guidance import (
    GimbalGuidanceCapabilities,
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
        GimbalGuidanceCapabilities(
            known=True,
            supports_vertical=True,
            supports_reverse=True,
            supports_yaw_fallback=True,
            azimuth_limits_deg=(-180.0, 180.0),
            depression_limits_deg=(-90.0, 90.0),
        ),
        clock=clock,
    )


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


def test_unknown_provider_fails_closed_for_special_states():
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
        GimbalGuidanceCapabilities(known=True, supports_yaw_fallback=True),
        clock=lambda: now[0],
    )
    state.update(Ray(1.0, 0.0, 0.0))
    now[0] = 0.31
    assert state.update(Ray(-1.0, 0.0, 0.0)).state is GuidanceState.YAW_FIRST

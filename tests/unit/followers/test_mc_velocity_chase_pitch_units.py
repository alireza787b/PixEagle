"""Pitch-unit contract tests for MC velocity chase compensation."""

import math
import time
from types import SimpleNamespace

import pytest

from classes.followers.mc_velocity_chase_follower import MCVelocityChaseFollower


def _follower(controller):
    follower = MCVelocityChaseFollower.__new__(MCVelocityChaseFollower)
    follower.px4_controller = controller
    follower.pitch_compensation_enabled = True
    follower.pitch_data_max_age = 1.0
    follower.pitch_max_angle = 45.0
    follower.pitch_smoothing_alpha = 0.5
    follower.smoothed_pitch_angle = 0.0
    follower.current_pitch_angle = 0.0
    follower.pitch_data_valid = False
    follower.pitch_compensation_active = False
    follower.last_pitch_timestamp = None
    return follower


def test_current_pitch_uses_px4_interface_degree_contract_without_reconversion():
    follower = _follower(
        SimpleNamespace(
            current_pitch=10.0,
            attitude_timestamp=time.time(),
        )
    )

    pitch_deg, valid = follower._get_current_pitch_angle()

    assert valid is True
    assert pitch_deg == pytest.approx(10.0)
    assert follower.current_pitch_angle == pytest.approx(10.0)


def test_explicit_radian_fallback_matches_degree_contract():
    follower = _follower(
        SimpleNamespace(
            current_pitch=None,
            attitude=SimpleNamespace(pitch_rad=math.radians(-12.0)),
            attitude_timestamp=time.time(),
        )
    )

    pitch_deg, valid = follower._get_current_pitch_angle()

    assert valid is True
    assert pitch_deg == pytest.approx(-12.0)


def test_ambiguous_pitch_attribute_fails_closed():
    follower = _follower(
        SimpleNamespace(
            current_pitch=None,
            attitude=SimpleNamespace(pitch=0.25),
            attitude_timestamp=time.time(),
        )
    )

    assert follower._get_current_pitch_angle() == (0.0, False)

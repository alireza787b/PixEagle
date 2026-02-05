"""
Unit tests for MCVelocityChaseFollower lateral guidance mode selection.

These tests focus on mode-selection logic only and avoid full follower
initialization to keep tests fast and deterministic.
"""

import os
import sys
from unittest.mock import patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from classes.followers.mc_velocity_chase_follower import MCVelocityChaseFollower


def _build_mode_stub(
    configured_mode: str,
    auto_switch: bool = False,
    active_mode: str = None,
    current_forward_velocity: float = 0.0,
    switch_velocity: float = 3.0,
    hysteresis: float = 0.5,
    min_interval: float = 2.0,
    last_switch_time: float = 0.0,
):
    """Create a minimal MCVelocityChaseFollower instance for mode-logic testing."""
    follower = MCVelocityChaseFollower.__new__(MCVelocityChaseFollower)
    follower.lateral_guidance_mode = configured_mode
    follower.enable_auto_mode_switching = auto_switch
    follower.active_lateral_mode = active_mode
    follower.current_forward_velocity = current_forward_velocity
    follower.guidance_mode_switch_velocity = switch_velocity
    follower.mode_switch_hysteresis = hysteresis
    follower.min_mode_switch_interval = min_interval
    follower.last_mode_switch_time = last_switch_time
    follower._sideslip_advisory_logged = False
    return follower


def test_manual_mode_uses_configured_sideslip():
    follower = _build_mode_stub(configured_mode='sideslip', auto_switch=False)
    assert follower._get_active_lateral_mode() == 'sideslip'


def test_manual_mode_uses_configured_coordinated_turn():
    follower = _build_mode_stub(configured_mode='coordinated_turn', auto_switch=False)
    assert follower._get_active_lateral_mode() == 'coordinated_turn'


def test_invalid_configured_mode_falls_back_to_coordinated_turn():
    follower = _build_mode_stub(configured_mode='invalid_mode', auto_switch=False)
    assert follower._get_active_lateral_mode() == 'coordinated_turn'


def test_auto_switch_from_sideslip_to_coordinated_turn():
    follower = _build_mode_stub(
        configured_mode='sideslip',
        auto_switch=True,
        active_mode='sideslip',
        current_forward_velocity=3.7,  # >= 3.0 + 0.5
        last_switch_time=0.0,
    )
    with patch('classes.followers.mc_velocity_chase_follower.time.time', return_value=100.0):
        assert follower._get_active_lateral_mode() == 'coordinated_turn'


def test_auto_switch_from_coordinated_turn_to_sideslip():
    follower = _build_mode_stub(
        configured_mode='coordinated_turn',
        auto_switch=True,
        active_mode='coordinated_turn',
        current_forward_velocity=2.3,  # <= 3.0 - 0.5
        last_switch_time=0.0,
    )
    with patch('classes.followers.mc_velocity_chase_follower.time.time', return_value=100.0):
        assert follower._get_active_lateral_mode() == 'sideslip'

"""Focused follower-manager and shared-fixture command contract tests."""

from unittest.mock import MagicMock

import pytest

from classes.follower import Follower
from tests.fixtures.mock_drone_interface import MockSetpointHandler


def test_follower_manager_control_type_failure_is_fail_closed():
    manager = object.__new__(Follower)
    manager.follower = MagicMock()
    manager.follower.get_control_type.side_effect = ValueError("invalid profile")

    with pytest.raises(
        RuntimeError,
        match="Unable to determine the active follower control type",
    ):
        manager.get_control_type()


def test_mock_setpoint_handler_defaults_to_canonical_velocity_profile():
    handler = MockSetpointHandler()

    assert handler._profile_name == "mc_velocity_chase"
    assert handler.get_control_type() == "velocity_body_offboard"
    assert set(handler.get_fields()) == {
        "vel_body_fwd",
        "vel_body_right",
        "vel_body_down",
        "yawspeed_deg_s",
    }


def test_mock_setpoint_handler_rejects_retired_velocity_body_control():
    with pytest.raises(ValueError, match="Unsupported mock control type: 'velocity_body'"):
        MockSetpointHandler(control_type="velocity_body")

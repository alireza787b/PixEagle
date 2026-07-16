"""Follower command-intent atomicity tests."""

import math
from pathlib import Path

import pytest

from classes.followers.fw_attitude_rate_follower import FWAttitudeRateFollower
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower
from classes.followers.mc_attitude_rate_follower import MCAttitudeRateFollower
from classes.followers.mc_velocity_chase_follower import MCVelocityChaseFollower
from classes.setpoint_handler import SetpointHandler


FOLLOWER_DIR = Path(__file__).resolve().parents[3] / "src" / "classes" / "followers"


@pytest.mark.parametrize(
    "follower_cls,profile,fields",
    [
        (
            MCVelocityChaseFollower,
            "mc_velocity_chase",
            {
                "vel_body_fwd": 0.25,
                "vel_body_right": 0.2,
                "vel_body_down": -0.1,
                "yawspeed_deg_s": 3.0,
            },
        ),
        (
            GMVelocityVectorFollower,
            "gm_velocity_vector",
            {
                "vel_body_fwd": 0.3,
                "vel_body_right": 0.4,
                "vel_body_down": 0.1,
                "yawspeed_deg_s": 0.0,
            },
        ),
        (
            MCAttitudeRateFollower,
            "mc_attitude_rate",
            {
                "rollspeed_deg_s": 1.0,
                "pitchspeed_deg_s": -2.0,
                "yawspeed_deg_s": 3.0,
                "thrust": 0.55,
            },
        ),
        (
            FWAttitudeRateFollower,
            "fw_attitude_rate",
            {
                "rollspeed_deg_s": 5.0,
                "pitchspeed_deg_s": 1.0,
                "yawspeed_deg_s": 2.0,
                "thrust": 0.65,
            },
        ),
    ],
)
def test_concrete_followers_accept_atomic_command_intents(follower_cls, profile, fields):
    """Main follower families can publish complete atomic command snapshots."""
    follower = follower_cls.__new__(follower_cls)
    follower.setpoint_handler = SetpointHandler(profile)

    assert follower.set_command_fields(fields, reason="unit_test") is True

    assert follower.setpoint_handler.get_fields() == fields
    intent = follower.get_last_command_intent()
    assert intent is not None
    assert intent.fields == fields
    assert intent.source == follower_cls.__name__
    assert intent.reason == "unit_test"


def test_atomic_command_rejection_preserves_previous_fields():
    """Rejected command intents must not mix new valid values with old state."""
    follower = MCVelocityChaseFollower.__new__(MCVelocityChaseFollower)
    follower.setpoint_handler = SetpointHandler("mc_velocity_chase")
    baseline = {
        "vel_body_fwd": 0.25,
        "vel_body_right": 0.2,
        "vel_body_down": -0.1,
        "yawspeed_deg_s": 3.0,
    }
    assert follower.set_command_fields(baseline, reason="baseline") is True

    rejected = {
        "vel_body_fwd": 4.0,
        "vel_body_right": math.nan,
        "vel_body_down": 1.0,
        "yawspeed_deg_s": 0.0,
    }
    assert follower.set_command_fields(rejected, reason="nan_rejected") is False

    assert follower.setpoint_handler.get_fields() == baseline
    assert follower.get_last_command_intent() is None
    assert follower.setpoint_handler.get_last_command_intent() is None


def test_atomic_command_requires_all_profile_fields():
    """Optional yaw fields must be explicit, not inherited from old commands."""
    follower = GMVelocityVectorFollower.__new__(GMVelocityVectorFollower)
    follower.setpoint_handler = SetpointHandler("gm_velocity_vector")
    baseline = {
        "vel_body_fwd": 0.25,
        "vel_body_right": 0.0,
        "vel_body_down": 0.0,
        "yawspeed_deg_s": 12.0,
    }
    assert follower.set_command_fields(baseline, reason="baseline") is True

    assert follower.set_command_fields(
        {
            "vel_body_fwd": 0.0,
            "vel_body_right": 0.0,
            "vel_body_down": 0.0,
        },
        reason="missing_yaw",
    ) is False

    assert follower.setpoint_handler.get_fields() == baseline
    assert follower.get_last_command_intent() is None
    assert follower.setpoint_handler.get_last_command_intent() is None


def test_reset_clears_manager_and_handler_command_intents():
    follower = MCVelocityChaseFollower.__new__(MCVelocityChaseFollower)
    follower.setpoint_handler = SetpointHandler("mc_velocity_chase")
    follower._telemetry_metadata = {}
    fields = {
        "vel_body_fwd": 0.25,
        "vel_body_right": 0.0,
        "vel_body_down": 0.0,
        "yawspeed_deg_s": 0.0,
    }
    assert follower.set_command_fields(fields, reason="baseline") is True

    assert follower.reset_command_fields() is True

    assert follower.get_last_command_intent() is None
    assert follower.setpoint_handler.get_last_command_intent() is None
    assert follower._telemetry_metadata["last_command_intent"] is None


def test_concrete_followers_do_not_publish_with_single_field_mutation():
    """Concrete followers should use atomic command snapshots, not field mutation."""
    offenders = []
    for path in sorted(FOLLOWER_DIR.glob("*_follower.py")):
        if path.name == "base_follower.py":
            continue
        if "set_command_field(" in path.read_text(encoding="utf-8"):
            offenders.append(path.name)

    assert offenders == []

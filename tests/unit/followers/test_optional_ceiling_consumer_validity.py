"""Direct legacy consumers require measured height before optional-bound checks."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from classes.followers.fw_attitude_rate_follower import FWAttitudeRateFollower
from classes.followers.gm_velocity_chase_follower import GMVelocityChaseFollower
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower
from classes.followers.mc_attitude_rate_follower import MCAttitudeRateFollower
from classes.followers.mc_velocity_chase_follower import MCVelocityChaseFollower
from classes.followers.mc_velocity_distance_follower import MCVelocityDistanceFollower
from classes.followers.mc_velocity_position_follower import MCVelocityPositionFollower
from classes.safety_types import AltitudeLimits


CHECKERS = (FWAttitudeRateFollower, MCAttitudeRateFollower, MCVelocityChaseFollower,
            GMVelocityChaseFollower, GMVelocityVectorFollower)
COMMANDERS = (MCVelocityDistanceFollower, MCVelocityPositionFollower)
KINDS = COMMANDERS + CHECKERS
INVALID_HEIGHTS = (float("nan"), float("inf"), -float("inf"), None)


def follower_stub(kind, altitude, ceiling, *, safety_enabled=True):
    follower = kind.__new__(kind)
    follower.px4_controller = SimpleNamespace(current_altitude=altitude)
    follower._safety_checks_bypassed_for_testing = lambda: False
    follower.is_altitude_safety_enabled = lambda: safety_enabled
    follower._follower_config_name = "TEST"
    follower.min_altitude_limit = follower.min_altitude_safety = follower.min_descent_height = 3.
    follower.max_altitude_limit = follower.max_altitude_safety = follower.max_climb_height = ceiling
    follower.altitude_warning_buffer = 2.
    follower.max_vertical_velocity = 2.
    follower.last_altitude_check_time = follower.altitude_check_interval = 0.
    follower.altitude_violation_count = 0
    follower.emergency_stop_active = follower.rtl_triggered = False
    follower.rtl_on_altitude_violation = True
    follower._trigger_rtl = Mock()
    follower.safety_manager = SimpleNamespace(get_safety_behavior=lambda _: SimpleNamespace(rtl_on_violation=False))
    follower.update_telemetry_metadata = Mock()
    follower.pid_z = Mock(setpoint=0., return_value=-1. if kind is MCVelocityDistanceFollower else 1.)
    return follower


def observe(follower):
    if isinstance(follower, MCVelocityDistanceFollower):
        return follower._control_altitude_bidirectional(-1.)
    if isinstance(follower, MCVelocityPositionFollower):
        return follower._calculate_altitude_command(-1.)
    return follower._check_altitude_safety()


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("ceiling", [120., None], ids=["finite", "unbounded"])
@pytest.mark.parametrize("altitude", INVALID_HEIGHTS, ids=["nan", "positive-inf", "negative-inf", "missing"])
def test_invalid_height_cannot_authorize_climb_or_pass_safety(kind, ceiling, altitude):
    follower = follower_stub(kind, altitude, ceiling)
    result = observe(follower)
    if kind in COMMANDERS:
        assert result == 0.
        follower.pid_z.assert_not_called()
    else:
        assert (result["safe"] if isinstance(result, dict) else result) is False
        follower._trigger_rtl.assert_not_called()


@pytest.mark.parametrize("kind", CHECKERS)
@pytest.mark.parametrize("ceiling", [120., None])
def test_disabling_altitude_safety_preserves_existing_check_bypass(kind, ceiling):
    follower = follower_stub(kind, None, ceiling, safety_enabled=False)
    result = observe(follower)
    assert (result["safe"] if isinstance(result, dict) else result) is True
    assert follower.last_altitude_check_time == 0.


@pytest.mark.parametrize("kind", CHECKERS)
def test_disabling_guidance_does_not_disable_the_separate_safety_check(kind):
    follower = follower_stub(kind, None, None)
    follower.altitude_control_enabled = False
    result = observe(follower)
    assert (result["safe"] if isinstance(result, dict) else result) is False


@pytest.mark.parametrize("kind", CHECKERS)
def test_invalid_height_is_not_hidden_by_a_recent_periodic_check(kind):
    follower = follower_stub(kind, float("nan"), None)
    follower.last_altitude_check_time = float("inf")
    follower.altitude_check_interval = 1.
    result = observe(follower)
    assert (result["safe"] if isinstance(result, dict) else result) is False


@pytest.mark.parametrize("kind", COMMANDERS)
@pytest.mark.parametrize("ceiling", [120., None])
def test_valid_below_floor_climb_recovery_is_retained(kind, ceiling):
    follower = follower_stub(kind, 2., ceiling)
    assert observe(follower) == (-1. if kind is MCVelocityDistanceFollower else 1.)
    follower.pid_z.return_value *= -1.
    assert observe(follower) == 0.


@pytest.mark.parametrize("kind", COMMANDERS)
@pytest.mark.parametrize("ceiling,allowed", [(120., False), (None, True)])
def test_valid_climb_above_old_ceiling_only_when_explicitly_unbounded(kind, ceiling, allowed):
    follower = follower_stub(kind, 1000., ceiling)
    command = -1. if kind is MCVelocityDistanceFollower else 1.
    assert observe(follower) == (command if allowed else 0.)


@pytest.mark.parametrize("altitude", INVALID_HEIGHTS)
@pytest.mark.parametrize("ceiling", [120., None])
def test_positive_upper_query_rejects_invalid_height_without_redefining_absent_ceiling(altitude, ceiling):
    assert not AltitudeLimits.below(altitude, ceiling)
    assert not AltitudeLimits(3., ceiling, 2.).contains(altitude)
    assert not AltitudeLimits.above(altitude, None)

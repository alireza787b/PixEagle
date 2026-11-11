"""Characterize lifecycle seams without changing controller math or authority."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from classes.followers.base_follower import BaseFollower
from classes.followers.gm_velocity_chase_follower import GMVelocityChaseFollower
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower
from classes.followers.mc_velocity_chase_follower import MCVelocityChaseFollower
from classes.followers.mc_velocity_position_follower import MCVelocityPositionFollower
from classes.followers.mc_attitude_rate_follower import MCAttitudeRateFollower
from classes.followers.fw_attitude_rate_follower import FWAttitudeRateFollower
from classes.fixed_wing_vector_guidance import FixedWingCommand
from tests.unit.followers.test_vector_guidance_session import session
from classes.aircraft_state import AirframePhase
from tests.unit.drone_interface.test_aircraft_state import aircraft_state


@pytest.mark.parametrize("follower_class", [GMVelocityChaseFollower, GMVelocityVectorFollower])
@pytest.mark.parametrize("loss", [False, True])
def test_post_continuity_shaping_keeps_order_and_loss_restrictions(follower_class, loss):
    follower = object.__new__(follower_class)
    events = []
    original = dict(vel_body_fwd=3., vel_body_right=2., vel_body_down=1., yawspeed_deg_s=4.)

    def limit(fields):
        events.append("session")
        fields['vel_body_fwd'] = 2.
        return fields

    def shape(fields):
        events.append("guard" if loss else "slew")
        assert fields['vel_body_fwd'] == 2.
        return dict(fields, vel_body_right=1.)

    follower.limit_session_control_command = limit
    follower.guard_authorized_command = shape
    follower.limit_authorized_command = shape
    follower.record_submitted_command = Mock()
    fields = follower.prepare_authorized_command(original, loss_decay=loss)
    assert events == ["session", "guard" if loss else "slew"]
    assert original['vel_body_fwd'] == 3.
    assert fields == dict(vel_body_fwd=2., vel_body_right=1., vel_body_down=0. if loss else 1.,
                          yawspeed_deg_s=0. if loss else 4.)
    follower.record_submitted_command.assert_not_called()
    follower.on_command_submitted(fields)
    follower.record_submitted_command.assert_called_once_with(fields)


def test_ordinary_profile_does_not_gain_gimbal_shaping():
    follower = object.__new__(MCVelocityPositionFollower)
    follower.limit_session_control_command = lambda fields: dict(fields, vel_body_fwd=0.)
    follower.guard_authorized_command = Mock(side_effect=AssertionError)
    follower.limit_authorized_command = Mock(side_effect=AssertionError)
    follower.record_submitted_command = Mock(side_effect=AssertionError)
    assert follower.prepare_authorized_command({'vel_body_fwd': 1.}, loss_decay=True) == {'vel_body_fwd': 0.}
    follower.on_command_submitted({'vel_body_fwd': 0.})


@pytest.mark.parametrize("follower_class,legacy", [
    (MCVelocityChaseFollower, "reset_chase_state"),
    (MCVelocityPositionFollower, "reset_pid_controllers"),
    (MCAttitudeRateFollower, "reset_follower_state"),
    (FWAttitudeRateFollower, "reset_state"),
])
@pytest.mark.parametrize("result", [None, True, False])
def test_explicit_retarget_hooks_preserve_existing_reset_result(follower_class, legacy, result):
    follower = object.__new__(follower_class)
    events = []

    def invalidate():
        events.append("invalidate")
        return True

    def reset_controller():
        events.append("controller")
        return result

    follower.reset_command_fields = invalidate
    reset = Mock(side_effect=reset_controller)
    setattr(follower, legacy, reset)
    if follower_class is MCVelocityPositionFollower:
        follower.yaw_smoother = Mock()
    controls = follower._session_controls = {'acknowledged': object()}
    assert follower.prepare_for_target_transition("new_target") is (result is not False)
    assert events == ["invalidate", "controller"]
    assert follower._session_controls is controls
    reset.assert_called_once_with()


def test_retarget_does_not_discover_unrelated_reset_names():
    follower = object.__new__(GMVelocityVectorFollower)
    follower.reset_command_fields = Mock(return_value=True)
    follower.reset_state = Mock(side_effect=AssertionError)
    assert follower.prepare_for_target_transition("new_target")
    follower.reset_state.assert_not_called()


def test_native_fixed_wing_intent_keeps_explicit_profile_identity():
    owner, _, _ = session()
    intent = FixedWingCommand(.3, 18., 0., None).intent(
        owner.identity, profile_name="recipe_fixture", source="test")
    assert intent.profile_name == "recipe_fixture"
    assert intent.control_type == "fixed_wing_external"
    assert intent.guidance_identity == owner.identity


@pytest.mark.parametrize("phase", [AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING])
def test_native_baseline_keeps_session_profile_identity(phase):
    owner, _, state = session(state=aircraft_state(phase=phase))
    owner.profile_name = "recipe_fixture"
    owner.observe(state, owner_confirmed=True, target_confirmed=True)
    assert owner.baseline().profile_name == "recipe_fixture"


def test_renamed_implementation_retains_declared_config_and_velocity_owner():
    class RenamedImplementation(GMVelocityVectorFollower):
        pass

    follower = object.__new__(RenamedImplementation)
    follower.mount_type = "VERTICAL"
    BaseFollower.__init__(follower, SimpleNamespace(), "gm_velocity_vector")
    assert follower._follower_config_name == "GM_VELOCITY_VECTOR"
    assert follower.velocity_limits == follower.safety_manager.get_velocity_limits("GM_VELOCITY_VECTOR")
    follower.safety_manager = Mock()
    follower._clear_session_velocity()
    follower.safety_manager.clear_session_velocity.assert_called_once_with(follower)


@pytest.mark.parametrize("bad", [None, "", "mc_velocity_chase", [], "MC-VELOCITY-CHASE"])
def test_config_identity_is_required_and_validated(bad):
    from pathlib import Path
    from classes.setpoint_handler import SetpointHandler, validate_follower_command_schema
    schema = SetpointHandler.load_and_validate_schema(
        Path(__file__).resolve().parents[3] / "configs/follower_commands.yaml")
    schema['follower_profiles']['mc_velocity_chase']['config_section'] = bad
    with pytest.raises(ValueError, match='config_section'):
        validate_follower_command_schema(schema)


def test_native_fw_authorized_fields_never_enter_multicopter_slew_or_limits():
    follower = object.__new__(GMVelocityVectorFollower)
    fields = dict(course_rad=.3, equivalent_airspeed_m_s=18., height_rate_m_s=0.)
    guarded = dict(fields, equivalent_airspeed_m_s=16.)
    follower._synchronize_native_phase = Mock()
    follower._airframe_session = SimpleNamespace(
        control_type='fixed_wing_external', guard_native_fields=Mock(return_value=guarded))
    follower.clamp_velocity = Mock(side_effect=AssertionError)
    follower.guard_gimbal_vertical_velocity = Mock(side_effect=AssertionError)
    assert follower.prepare_authorized_command(fields, loss_decay=False) == guarded
    follower._airframe_session.guard_native_fields.assert_called_once_with(fields)
    follower.clamp_velocity.assert_not_called()
    follower.guard_gimbal_vertical_velocity.assert_not_called()

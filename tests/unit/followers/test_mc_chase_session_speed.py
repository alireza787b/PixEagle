"""MC Chase shares session speed ownership without changing image guidance."""

import asyncio
import json
import math
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from classes.aircraft_state import AirframePhase, GuidanceSessionIdentity
from classes.airframe_session_controls import AirframeSessionControls
from classes.api_v1_contracts import APIFollowingSessionControl, APINativeFollowingStatus
from classes.api_v1_native_following import following_snapshot
from classes.followers.base_follower import BaseFollower
from classes.followers.mc_velocity_chase_follower import MCVelocityChaseFollower
from classes.command_safety import validate_and_clamp_command_values
from classes.parameters import Parameters
from classes.safety_manager import SafetyManager
from classes.setpoint_handler import SetpointHandler, validate_follower_command_schema
from classes.tracker_output import TrackerDataType, TrackerOutput
from tests.unit.core_app.test_following_session_controls import active_owner, body, invoke
from tests.unit.core_app.test_native_following import owner
from tests.unit.core_app.test_native_target_operations import owner as target_owner
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tests.unit.followers.test_session_speed import follower_with_control


@pytest.fixture
def chase(mock_px4, monkeypatch):
    safety = SafetyManager()
    safety.load_from_config({'Safety': {'ALLOW_SESSION_VELOCITY_OVERRIDE': True, 'GlobalLimits': {
        'MAX_VELOCITY': 1., 'MAX_VELOCITY_FORWARD': .5,
        'MAX_VELOCITY_LATERAL': .4, 'MAX_VELOCITY_VERTICAL': .3,
    }}})
    monkeypatch.setattr(SafetyManager, '_instance', safety)
    monkeypatch.setattr(Parameters, 'MC_VELOCITY_CHASE', {
        **Parameters.MC_VELOCITY_CHASE, 'INITIAL_FORWARD_VELOCITY': 0., 'FORWARD_RAMP_RATE': .5,
        'RAMP_UPDATE_RATE': 20., 'REQUESTED_SPEED': None,
    })
    follower = MCVelocityChaseFollower(mock_px4, (0., 0.))
    return follower


def command(forward=.5, right=.4, down=.3, yaw=10.):
    return dict(vel_body_fwd=forward, vel_body_right=right, vel_body_down=down, yawspeed_deg_s=yaw)


def magnitude(fields):
    return math.hypot(*(fields[name] for name in ('vel_body_fwd', 'vel_body_right', 'vel_body_down')))


def test_normal_chase_constructor_can_shape_session_speed_without_vector_attributes(mock_px4):
    follower = MCVelocityChaseFollower(mock_px4, (0., 0.))
    assert not hasattr(follower, 'update_rate')
    for requested in (.5, 0., 1.):
        control, = follower.session_controls()
        follower.update_session_control('requested_speed', requested, control['revision'])
        shaped = follower.prepare_authorized_command(command(), loss_decay=False)
        assert all(math.isfinite(value) for value in shaped.values())
        follower.on_command_submitted(shaped)
    follower.release_session_controls()


def test_declared_chase_control_preserves_saved_forward_target_before_adjustment(chase):
    control, = chase.session_controls()
    assert control['value'] == control['configured_maximum'] == 1.
    assert not control['override_active']
    assert control['maximum'] is None
    assert chase._update_forward_velocity(1.) == .5
    assert chase._update_forward_velocity(1.) == .5
    assert chase.prepare_authorized_command(command(), loss_decay=False) == command()
    assert BaseFollower.create_session_controls(chase) == {}


@pytest.mark.parametrize('startup', [0., .5, 1.5])
def test_configured_public_startup_and_adjustments_keep_one_saved_ceiling(chase, startup):
    chase.safety_manager.load_from_config({'Safety': {
        'ALLOW_SESSION_VELOCITY_OVERRIDE': False,
        'GlobalLimits': {'MAX_VELOCITY': 4., 'MAX_VELOCITY_FORWARD': 4.,
                         'MAX_VELOCITY_LATERAL': .5, 'MAX_VELOCITY_VERTICAL': .5},
    }})
    chase.max_forward_velocity = 4.
    chase.startup_requested_speed = startup
    chase._session_controls = chase.create_session_controls()
    control, = chase.session_controls()
    assert control['value'] == startup and control['maximum'] == 4.
    for _ in range(10):
        chase._update_forward_velocity(1.)
    assert chase.current_forward_velocity == startup
    chase.update_session_control('requested_speed', 4., 0)
    for _ in range(10):
        chase._update_forward_velocity(1.)
    assert chase.current_forward_velocity == 4.
    with pytest.raises(ValueError, match='session_control_out_of_range'):
        chase.update_session_control('requested_speed', 4.5, 1)
    assert chase.safety_manager._session_velocity_binding is None


def test_explicit_chase_speed_uses_the_existing_owned_override_and_forward_ramp(chase):
    chase.update_session_control('requested_speed', 3., 0)
    assert chase.velocity_limits.forward == chase.velocity_limits.max_magnitude == 3.
    assert chase._update_forward_velocity(2.) == 1.
    assert chase._update_forward_velocity(2.) == 2.
    assert chase._update_forward_velocity(2.) == 3.
    assert chase.altitude_limits.safety_enabled
    assert chase.safety_manager.get_limit('MAX_YAW_RATE', 'MC_VELOCITY_CHASE') == 45.
    assert chase.safety_manager.get_velocity_limits('MC_VELOCITY_POSITION').forward == .5


def test_chase_zero_relimits_all_retained_translation_with_bounded_radial_deceleration(chase, monkeypatch):
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: 100.)
    chase.update_session_control('requested_speed', 3., 0)
    chase.current_forward_velocity = 3.
    retained = command(2., 1., -2.)
    chase.on_command_submitted(retained)
    chase.update_session_control('requested_speed', 0., 1)
    assert chase._update_forward_velocity(.1) == pytest.approx(2.95)
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: 100.05)
    limited = chase.prepare_authorized_command(retained, loss_decay=True)
    assert magnitude(limited) == pytest.approx(3. - .5 / 20.)
    assert limited['vel_body_fwd'] / retained['vel_body_fwd'] == pytest.approx(
        limited['vel_body_down'] / retained['vel_body_down'])
    assert limited['yawspeed_deg_s'] == retained['yawspeed_deg_s']
    chase.on_command_submitted(command(0., 0., 0.))
    assert magnitude(chase.prepare_authorized_command(retained, loss_decay=False)) == 0.


def test_chase_restore_revision_and_owner_cleanup_do_not_mutate_saved_limits(chase):
    chase.update_session_control('requested_speed', 3., 0)
    with pytest.raises(ValueError, match='revision_stale'):
        chase.update_session_control('requested_speed', 2., 0)
    chase.update_session_control('requested_speed', None, 1)
    control, = chase.session_controls()
    assert control['value'] == 1. and not control['override_active']
    assert chase.velocity_limits.forward == .5
    restored = validate_and_clamp_command_values('velocity_body_offboard', command(3., 3., 3.),
                                                follower_name='MC_VELOCITY_CHASE')
    assert restored == command(.5, .4, .3)
    chase.update_session_control('requested_speed', .2, 2)
    chase.release_session_controls()
    assert chase.velocity_limits.forward == .5
    chase.reset_control_session()
    control, = chase.session_controls()
    assert control['value'] == 1. and control['revision'] == 0


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), -1.])
def test_chase_speed_rejects_invalid_values_without_activating_override(chase, value):
    with pytest.raises(ValueError, match='session_control_value_invalid|session_control_out_of_range'):
        chase.update_session_control('requested_speed', value, 0)
    assert chase.safety_manager._session_velocity_binding is None


def test_chase_image_pid_commands_share_the_ceiling_without_changing_their_direction(chase):
    chase.enable_altitude_control = True
    chase._initialize_pid_controllers()
    chase.update_session_control('requested_speed', 2., 0)
    chase.current_forward_velocity = 2.
    output = TrackerOutput(TrackerDataType.POSITION_2D, time.time(), True, position_2d=(.3, -.3))
    assert chase.calculate_control_commands(output)
    nominal = chase.get_last_command_intent().fields
    limited = chase.prepare_authorized_command(nominal, loss_decay=False)
    assert nominal['vel_body_down'] < 0.
    assert magnitude(limited) <= 2. + 1e-9
    assert limited['vel_body_fwd'] / nominal['vel_body_fwd'] == pytest.approx(
        limited['vel_body_down'] / nominal['vel_body_down'])
    assert limited['yawspeed_deg_s'] == nominal['yawspeed_deg_s']


def test_chase_adjustment_and_restore_refresh_existing_translation_pid_limits(chase):
    chase.enable_altitude_control = True
    chase.lateral_guidance_mode = 'sideslip'
    chase.enable_auto_mode_switching = False
    chase._initialize_pid_controllers()
    right, down = chase.pid_right, chase.pid_down
    gains = (right.tunings, down.tunings)
    assert right.output_limits == (-.4, .4)
    assert down.output_limits == (-.3, .3)
    chase.update_session_control('requested_speed', 3., 0)
    assert right.output_limits == down.output_limits == (-3., 3.)
    down.set_auto_mode(False)
    down.set_auto_mode(True, last_output=2.5)
    assert down.components[1] == 2.5
    chase.update_session_control('requested_speed', None, 1)
    assert (chase.pid_right, chase.pid_down) == (right, down)
    assert (right.tunings, down.tunings) == gains
    assert right.output_limits == (-.4, .4)
    assert down.output_limits == (-.3, .3)
    assert down.components[1] == .3


def test_chase_zero_to_increase_bounds_real_pid_translation_without_gimbal_slew(chase, monkeypatch):
    chase.enable_altitude_control = True
    chase.lateral_guidance_mode = 'sideslip'
    chase.enable_auto_mode_switching = False
    chase.adaptive_mode_enabled = False
    chase.velocity_smoothing_enabled = False
    chase._initialize_pid_controllers()
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: 100.)
    chase.update_session_control('requested_speed', 0., 0)
    chase.on_command_submitted(command(0., 0., 0.))
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: 100.05)
    chase.update_session_control('requested_speed', 3., 1)
    output = TrackerOutput(TrackerDataType.POSITION_2D, time.time(), True, position_2d=(.8, -.8))
    assert chase.calculate_control_commands(output)
    nominal = chase.get_last_command_intent().fields
    assert nominal['vel_body_right'] > 0. and nominal['vel_body_down'] < 0.
    limited = chase.prepare_authorized_command(nominal, loss_decay=False)
    assert magnitude(limited) == pytest.approx(chase.forward_ramp_rate / chase.ramp_update_rate)
    assert limited['vel_body_right'] / nominal['vel_body_right'] == pytest.approx(
        limited['vel_body_down'] / nominal['vel_body_down'])
    assert limited['yawspeed_deg_s'] == nominal['yawspeed_deg_s']
    assert getattr(chase, 'authorized_command_acceleration', None) is None
    chase.on_command_submitted(limited)
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: 100.1)
    next_command = chase.prepare_authorized_command(nominal, loss_decay=False)
    assert magnitude(next_command) == pytest.approx(.05)
    chase.on_command_submitted(next_command)
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: 105.)
    assert magnitude(chase.prepare_authorized_command(nominal, loss_decay=False)) == pytest.approx(.075)
    smaller = command(0., .001, -.001)
    assert chase.prepare_authorized_command(smaller, loss_decay=False) == smaller
    assert chase.prepare_authorized_command(command(0., 0., 0.), loss_decay=False) == command(0., 0., 0.)


def test_retarget_preserves_speed_revision_and_stop_cannot_clear_replacement(chase, mock_px4):
    chase.update_session_control('requested_speed', 3., 0)
    before = chase.session_controls()
    assert chase.reset_target_state('operator_target_retarget')
    assert chase.session_controls() == before
    chase.release_session_controls()
    replacement = MCVelocityChaseFollower(mock_px4, (0., 0.))
    replacement.update_session_control('requested_speed', 4., 0)
    chase.release_session_controls()
    assert replacement.velocity_limits.forward == 4.
    replacement.activate_emergency_stop()
    assert replacement.velocity_limits.forward == .5


def test_unsupported_stationary_follower_does_not_acquire_a_speed_control(chase, mock_px4):
    from classes.followers.mc_velocity_position_follower import MCVelocityPositionFollower

    stationary = MCVelocityPositionFollower(mock_px4, (0., 0.))
    stationary.reset_control_session()
    assert stationary.session_controls() == []


@pytest.mark.parametrize('transition_pending', [False, True])
async def test_real_chase_control_reuses_recovery_action_without_renewing_budget(
        chase, active_owner, transition_pending):
    app = active_owner.app_controller
    app.follower.follower = chase
    continuity = dict(authority_state='REACQUIRING', elapsed_s=2., distance_m=1.,
                      target_transition_pending=transition_pending)
    app.get_target_continuity_status = lambda: dict(continuity)
    refused = await invoke(active_owner, body(value=3.))
    assert json.loads(refused.body)['code'] == 'session_control_recovery_active'
    result = await invoke(active_owner, body(value=0., idempotency_key='chase-slow'))
    assert result['executed']
    assert chase.session_controls()[0]['value'] == 0.
    assert continuity == dict(authority_state='REACQUIRING', elapsed_s=2., distance_m=1.,
                              target_transition_pending=transition_pending)


@pytest.mark.parametrize('failure', ['stop', 'replacement'])
async def test_real_chase_action_cannot_cross_stop_or_replacement(chase, active_owner, failure):
    app = active_owner.app_controller
    app.follower.follower = chase
    if failure == 'stop':
        app._following_stopping = True
    else:
        app._following_session_id = 'b' * 32
    result = await invoke(active_owner)
    assert result.status_code == 409
    assert chase.session_controls()[0]['revision'] == 0
    assert chase.safety_manager._session_velocity_binding is None


async def test_chase_description_is_exposed_by_the_actual_status_and_action(chase, active_owner):
    app = active_owner.app_controller
    app.follower.follower = chase
    status = APINativeFollowingStatus.model_validate(following_snapshot(active_owner, active_owner.principal_test))
    row, = status.session_controls
    assert row.speed_basis == 'translation_3d'
    assert 'ceiling' in row.description
    assert 'image' in row.description
    assert row.value == 1. and chase._update_forward_velocity(1.) == .5
    adjusted = await invoke(active_owner, body(value=3.))
    assert adjusted['result']['session_controls'][0]['description'] == row.description
    assert adjusted['result']['session_controls'][0]['revision'] == 1
    zero = await invoke(active_owner, body(value=0., expected_revision=1, idempotency_key='zero'))
    assert zero['result']['session_controls'][0]['value'] == 0.
    restored = await invoke(active_owner, body(value=None, expected_revision=2, idempotency_key='restore'))
    reset, = restored['result']['session_controls']
    assert reset['description'] == row.description
    assert reset['value'] == 0. and reset['revision'] == 3 and not reset['override_active']
    assert chase.velocity_limits.forward == .5


@pytest.mark.parametrize('phase', [AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING])
def test_vector_description_survives_the_native_phase_binding_without_changing_speed_basis(phase):
    vector = follower_with_control()
    vector.config = {}
    vector.setpoint_handler = SimpleNamespace(profile_config=SetpointHandler.get_profile_info('gm_velocity_vector'))
    vector.safety_manager.get_velocity_limits = lambda _: SimpleNamespace(forward=1., max_magnitude=1.)
    vector._session_controls = vector.create_session_controls()
    declared, = vector.session_controls()
    assert 'magnitude' in declared['description']
    assert 'ceiling' not in declared['description']
    state = replace(aircraft_state(), phase=phase)
    identity = GuidanceSessionIdentity('follow', state.binding, 1)
    controls = AirframeSessionControls.from_multicopter_control(identity, vector._requested_speed_control())
    controls.enter_phase(identity, state, now=100., timeout_s=.5)
    row = APIFollowingSessionControl.model_validate(dict(
        controls.snapshot(client_contract_version=2), available=True, increase_allowed=True))
    if phase is AirframePhase.MULTICOPTER:
        assert row.description == declared['description']
        assert row.speed_basis == 'translation_3d'
    else:
        assert 'airspeed reference' in row.description
        assert 'magnitude' not in row.description
        assert row.speed_basis == 'equivalent_airspeed'
        assert row.minimum > 0.


@pytest.mark.parametrize('description', [True, 5, {'text': 'ceiling'}])
def test_description_remains_typed_optional_display_metadata(chase, description):
    row, = chase.session_controls()
    with pytest.raises(ValidationError):
        APIFollowingSessionControl.model_validate(dict(
            row, description=description, available=True, increase_allowed=True))


@pytest.mark.parametrize('description', ['', None, True, 5])
def test_control_declaration_rejects_a_nonmeaningful_description(description):
    schema = SetpointHandler.load_and_validate_schema(Path(__file__).resolve().parents[3]
                                                     / 'configs/follower_commands.yaml')
    schema['follower_profiles']['mc_velocity_chase']['session_controls']['requested_speed']['description'] = description
    with pytest.raises(ValueError, match='requested_speed.description'):
        validate_follower_command_schema(schema)


@pytest.mark.parametrize('change', ['missing_required', 'unknown_field'])
def test_optional_description_does_not_loosen_other_control_declaration_fields(change):
    schema = SetpointHandler.load_and_validate_schema(Path(__file__).resolve().parents[3]
                                                     / 'configs/follower_commands.yaml')
    declaration = schema['follower_profiles']['mc_velocity_chase']['session_controls']['requested_speed']
    if change == 'missing_required':
        declaration.pop('label')
    else:
        declaration['unrecognized'] = 'unexpected'
    with pytest.raises(ValueError, match='Session controls must declare'):
        validate_follower_command_schema(schema)


@pytest.mark.parametrize('change', ['stop', 'replacement'])
async def test_queued_chase_action_cannot_mutate_a_stopped_or_replaced_owner(
        chase, active_owner, mock_px4, change):
    app = active_owner.app_controller
    app.follower.follower = chase
    chase.update_session_control('requested_speed', 3., 0)
    replacement = None
    async with app._follower_state_lock:
        pending = asyncio.create_task(invoke(active_owner, body(value=2., expected_revision=1)))
        await asyncio.sleep(0)
        chase.release_session_controls()
        if change == 'stop':
            app._following_stopping = True
        else:
            replacement = MCVelocityChaseFollower(mock_px4, (0., 0.))
            replacement.update_session_control('requested_speed', 4., 0)
            app.follower.follower = replacement
            app._following_session_id = 'b' * 32
    result = await pending
    assert result.status_code == 409
    assert chase.session_controls()[0]['revision'] == 1
    chase.release_session_controls()
    if replacement is not None:
        assert replacement.session_controls()[0]['value'] == 4.
        assert replacement.session_controls()[0]['revision'] == 1
        assert replacement.velocity_limits.forward == 4.
    else:
        assert chase.safety_manager._session_velocity_binding is None

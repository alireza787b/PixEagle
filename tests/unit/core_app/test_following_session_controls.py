"""The same session mutation is guarded for browser and native callers."""

import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import Response
from pydantic import ValidationError

from classes.api_v1_contracts import APIFollowingControlRequest, APINativeFollowingStatus
from classes.api_security_types import APIPrincipal
from classes.api_v1_following_controls import session_control_snapshot, set_following_control
from classes.api_v1_native_following import following_snapshot, get_native_following
from classes.aircraft_state import AircraftBinding, AircraftStateOwner, AirframePhase, AirspeedObservation, Vector3
from classes.followers.base_follower import BaseFollower
from classes.follower_session_controls import SessionControl
from classes.runtime_identity import INSTANCE_ID, RUNTIME_ID
from tests.unit.core_app.test_native_following import owner, action_request
from tests.unit.core_app.test_native_target_operations import owner as target_owner
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tests.unit.followers.test_vector_guidance_session import session, settle

pytestmark = pytest.mark.unit


@pytest.fixture
def active_owner(owner, monkeypatch):
    app = owner.app_controller
    app.following_active = True
    app._following_stopping = False
    app._following_session_id = 'a' * 32
    app._following_session_aircraft_uid = '42'
    app._following_session_connection_generation = 'connection-1'
    app._is_command_preview_session = lambda: False
    app.get_target_continuity_status = lambda: {'authority_state': 'ACTIVE'}
    follower = SimpleNamespace(_session_controls={
        'requested_speed': SessionControl('requested_speed', 'Requested speed', 'm/s', 0, 5, .5, 3)
    })
    follower.session_controls = lambda: BaseFollower.session_controls(follower)
    follower.validate_session_control = lambda *args: BaseFollower.validate_session_control(follower, *args)
    follower.update_session_control = lambda *args: BaseFollower.update_session_control(follower, *args)
    app.follower = SimpleNamespace(follower=follower)
    app.px4_interface.get_aircraft_identity = lambda: {
        **owner.command_test, 'autopilot_uid': '42', 'connection_generation': 'connection-1'
    }
    app.px4_interface.is_command_connection_ready = lambda **kwargs: True
    app.mavlink_data_manager.get_flight_state = lambda: {'fresh': True, 'flight_mode': 393216, 'autopilot_uid': '42'}
    app.mavlink_data_manager.offboard_mode_code = 393216
    monkeypatch.setattr('classes.circuit_breaker.FollowerCircuitBreaker.is_active', lambda: False)
    return owner


def body(**changes):
    return APIFollowingControlRequest(
        **dict(dict(instance_id=INSTANCE_ID, runtime_id=RUNTIME_ID, follow_session_id='a' * 32,
                    aircraft_uid='42', connection_generation='connection-1', control_id='requested_speed',
                    expected_revision=0, value=3.5, confirm=True, idempotency_key='speed-1'), **changes)
    )


async def invoke(owner, request=None):
    return await set_following_control(owner, request or body(), Response(), action_request(owner))


async def test_shared_value_revision_replay_and_no_persistence(active_owner):
    app = active_owner.app_controller
    app.save_config = Mock(side_effect=AssertionError('Must never persist session control'))
    result = await invoke(active_owner)
    assert result['executed']
    assert result['result']['session_controls'][0]['value'] == 3.5
    assert result['result']['session_controls'][0]['revision'] == 1
    replay = await invoke(active_owner)
    assert replay['idempotent_replay']
    assert replay['result']['session_controls'][0]['revision'] == 1
    stale = await invoke(active_owner, body(idempotency_key='another-client'))
    assert stale.status_code == 409
    assert json.loads(stale.body)['code'] == 'session_control_revision_stale'
    snapshot = following_snapshot(active_owner, active_owner.principal_test)
    assert snapshot['session_controls'][0]['value'] == 3.5
    assert snapshot['follow_connection_generation'] == 'connection-1'
    app.save_config.assert_not_called()


async def test_phase_generation_is_checked_before_any_speed_mutation(active_owner):
    follower = active_owner.app_controller.follower.follower
    getter = follower.session_controls
    follower.session_controls = lambda: [dict(item, guidance_generation=4) for item in getter()]
    for generation in (None, 3, 5):
        result = await invoke(active_owner, body(guidance_generation=generation))
        assert result.status_code == 409
        assert json.loads(result.body)['code'] == 'session_control_phase_stale'
        assert follower._session_controls['requested_speed'].revision == 0
    result = await invoke(active_owner, body(guidance_generation=4))
    assert result['executed']


def test_legacy_clients_never_receive_airspeed_with_mc_semantics(active_owner):
    follower = active_owner.app_controller.follower.follower
    getter = follower.session_controls
    follower.session_controls = lambda: [dict(item, speed_basis='equivalent_airspeed', aircraft_phase='fixed_wing',
                                             guidance_generation=4) for item in getter()]
    assert session_control_snapshot(active_owner.app_controller, active_owner.principal_test) == []
    current = session_control_snapshot(active_owner.app_controller, active_owner.principal_test, client_contract_version=2)
    assert current[0]['speed_basis'] == 'equivalent_airspeed'


@pytest.mark.parametrize('changes', [
    {'instance_id': 'another'}, {'runtime_id': 'another'}, {'follow_session_id': 'b' * 32},
    {'aircraft_uid': '43'}, {'connection_generation': 'another'},
    {'control_id': 'unsupported'}, {'value': 5.1}, {'expected_revision': 1},
])
async def test_wrong_identity_and_invalid_control_do_not_mutate(active_owner, changes):
    result = await invoke(active_owner, body(**changes))
    assert result.status_code == 409
    assert active_owner.app_controller.follower.follower.session_controls()[0]['revision'] == 0


@pytest.mark.parametrize('value', [True, '3', float('nan'), float('inf'), -1])
def test_wire_value_is_strict_and_finite(value):
    with pytest.raises(ValidationError):
        body(value=value)


async def test_preview_audit_and_duplicate_key_guards(active_owner):
    result = await invoke(active_owner, body(dry_run=True, confirm=False, idempotency_key=None))
    assert result['status'] == 'validated'
    assert active_owner.app_controller.follower.follower.session_controls()[0]['revision'] == 0
    active_owner._record_security_audit_event.return_value = False
    result = await invoke(active_owner)
    assert result.status_code == 503
    active_owner._record_security_audit_event.return_value = True
    await invoke(active_owner)
    result = await invoke(active_owner, body(value=4))
    assert json.loads(result.body)['code'] == 'idempotency_conflict'


async def test_recovery_reductions_zero_and_unchanged_budget(active_owner):
    app = active_owner.app_controller
    continuity = {'authority_state': 'REACQUIRING', 'elapsed_s': 2, 'distance_m': 1,
                  'target_transition_pending': True}
    app.get_target_continuity_status = lambda: dict(continuity)
    refused = await invoke(active_owner)
    assert json.loads(refused.body)['code'] == 'session_control_recovery_active'
    result = await invoke(active_owner, body(value=0))
    assert result['result']['session_controls'][0]['value'] == 0
    assert continuity == {'authority_state': 'REACQUIRING', 'elapsed_s': 2, 'distance_m': 1,
                          'target_transition_pending': True}


@pytest.mark.parametrize('guard', ['stopping', 'inactive', 'stale_aircraft', 'circuit_breaker', 'unsupported'])
async def test_session_stop_and_safety_have_precedence(active_owner, monkeypatch, guard):
    app = active_owner.app_controller
    if guard == 'stopping':
        app._following_stopping = True
    elif guard == 'inactive':
        app.following_active = False
    elif guard == 'stale_aircraft':
        app.px4_interface.is_command_connection_ready = lambda **kwargs: False
    elif guard == 'circuit_breaker':
        monkeypatch.setattr('classes.circuit_breaker.FollowerCircuitBreaker.is_active', lambda: True)
    else:
        app.follower.follower._session_controls = {}
    result = await invoke(active_owner)
    assert result.status_code == 409


async def test_waiting_update_cannot_cross_session_stop(active_owner):
    app = active_owner.app_controller
    async with app._follower_state_lock:
        pending = asyncio.create_task(invoke(active_owner))
        app._following_stopping = True
    result = await pending
    assert result.status_code == 409


def test_unsupported_follower_has_no_controls(active_owner):
    active_owner.app_controller.follower = None
    assert session_control_snapshot(active_owner.app_controller, active_owner.principal_test) == []


async def test_read_only_client_cannot_adjust_a_control(active_owner):
    active_owner.principal_test = APIPrincipal.bearer(
        subject='viewer', token_id='viewer', scopes={'status:read', 'telemetry:read'},
    )
    assert session_control_snapshot(active_owner.app_controller, active_owner.principal_test)[0]['available'] is False
    result = await invoke(active_owner)
    assert result.status_code == 403
    assert active_owner.app_controller.follower.follower.session_controls()[0]['revision'] == 0


@pytest.mark.parametrize('mode', [196608, 100925440, 84148224])
async def test_speed_update_after_pilot_mode_transition_is_refused(active_owner, mode):
    app = active_owner.app_controller
    app.mavlink_data_manager.get_flight_state = lambda: {'fresh': True, 'flight_mode': mode, 'autopilot_uid': '42'}
    result = await invoke(active_owner)
    assert result.status_code == 409
    assert app.follower.follower.session_controls()[0]['revision'] == 0


@pytest.mark.parametrize(('submitted', 'reason'), [(2, 'guidance_limited'), (4, 'slowing_down'), (3, None)])
def test_feedback_uses_submitted_command_not_a_promised_aircraft_speed(active_owner, submitted, reason):
    app = active_owner.app_controller
    app.follower.follower._submitted_command_fields = dict(vel_body_fwd=submitted, vel_body_right=0, vel_body_down=0)
    control = session_control_snapshot(app, active_owner.principal_test)[0]
    assert control['effective_command_magnitude'] == submitted
    assert control['limiting_reason'] == reason


@pytest.mark.parametrize('requested', [2, 8])
async def test_restore_uses_same_action_and_never_raises_speed_during_recovery(active_owner, requested):
    app = active_owner.app_controller
    app.follower.follower._session_controls = {'requested_speed': SessionControl(
        'requested_speed', 'Requested speed', 'm/s', 0, None, .5, requested,
        configured_maximum=5, override_active=True,
    )}
    app.get_target_continuity_status = lambda: {'authority_state': 'REACQUIRING', 'elapsed_s': 2}
    result = await invoke(active_owner, body(value=None))
    control = result['result']['session_controls'][0]
    assert control['value'] == min(requested, 5)
    assert control['override_active'] is False
    assert control['revision'] == 1
    replay = await invoke(active_owner, body(value=None))
    assert replay['idempotent_replay']
    assert app.get_target_continuity_status()['elapsed_s'] == 2


@pytest.mark.parametrize('metadata', [
    {}, {'guidance_generation': None}, {'guidance_generation': 0}, {'guidance_generation': 4},
    {'speed_basis': 'equivalent_airspeed', 'guidance_generation': 4, 'aircraft_phase': 'fixed_wing'},
])
@pytest.mark.parametrize('version', [1, 2])
async def test_wire_contract_hides_controls_older_clients_cannot_submit(active_owner, metadata, version):
    follower = active_owner.app_controller.follower.follower
    getter = follower.session_controls
    follower.session_controls = lambda: [dict(item, **metadata) for item in getter()]
    response = await get_native_following(active_owner, action_request(active_owner),
                                          client_control_contract_version=version)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    parsed = APINativeFollowingStatus.model_validate_json(response.body).model_dump(mode='json')
    supported = version >= 2 or (metadata.get('guidance_generation') is None
                                and metadata.get('speed_basis', 'translation_3d') == 'translation_3d')
    assert bool(parsed['session_controls']) is supported
    if supported:
        assert parsed['session_controls'][0]['value'] == 3


@pytest.fixture
def observed_owner(active_owner, monkeypatch):
    app = active_owner.app_controller
    state = aircraft_state(binding=AircraftBinding('42', 'connection-1', 1))
    guidance, clock, state = session(state=state, session_id=app._following_session_id)
    state = settle(guidance, clock, state)
    states = AircraftStateOwner(clock=lambda: clock[0])
    states.bind(state.binding)
    assert states.commit(state)
    app.px4_interface.get_aircraft_state = lambda: states.snapshot(timeout_s=.75)
    app.px4_interface.get_telemetry_stale_timeout_s = lambda: .75
    transport = SimpleNamespace(identity=guidance.identity, last_feedback=None)
    app._native_follow_binding = SimpleNamespace(
        guidance=guidance, owner_confirmed=True, pursuit_paused=False, transport=transport,
    )
    app.follower.follower.session_controls = lambda: [guidance.controls.snapshot(client_contract_version=2)]
    monkeypatch.setattr('classes.api_v1_following_controls.time', SimpleNamespace(monotonic=lambda: clock[0]), raising=False)
    return SimpleNamespace(owner=active_owner, app=app, guidance=guidance, state=state,
                           states=states, clock=clock, transport=transport)


def observed_control(f):
    payload = following_snapshot(f.owner, f.owner.principal_test, client_control_contract_version=2)
    return APINativeFollowingStatus.model_validate(payload).model_dump(mode='json')['session_controls'][0]


@pytest.mark.parametrize('source', ['sensor', 'ground_minus_wind'])
@pytest.mark.parametrize('speed', [0., 2., 20.])
def test_observed_eas_is_selected_fresh_measurement_even_below_native_minimum(observed_owner, source, speed):
    f = observed_owner
    measured = replace(f.state, sequence=f.state.sequence + 1,
                       airspeed=AirspeedObservation(source, speed, speed + 1, f.clock[0], True))
    assert f.states.commit(measured)
    f.app.follower.follower._submitted_command_fields = {'equivalent_airspeed_m_s': 23.}
    f.transport.last_feedback = {'effective_eas_m_s': 24.}
    control = observed_control(f)
    assert control['observed_speed_m_s'] == speed
    assert control['observed_speed_source'] == source
    assert control['speed_basis'] == 'equivalent_airspeed'
    assert control['effective_command_magnitude'] == 23.
    assert 'native_effective_eas_m_s' not in control and 'effective_eas_m_s' not in control


@pytest.mark.parametrize('failure', [
    'missing', 'stale', 'future', 'wrong_aircraft', 'wrong_connection', 'wrong_telemetry',
    'wrong_session', 'wrong_generation', 'phase_change', 'transition', 'ended', 'rescue',
    'unready_connection', 'owner_lost', 'control_phase', 'preview',
])
def test_observation_cannot_cross_freshness_phase_or_session_binding(observed_owner, failure):
    f = observed_owner
    state = f.state
    if failure == 'missing':
        f.app.px4_interface.get_aircraft_state = lambda: None
    elif failure == 'stale':
        f.clock[0] += 1.
    elif failure == 'future':
        f.app.px4_interface.get_aircraft_state = lambda: replace(state, observed_at_monotonic_s=f.clock[0] + 1)
    elif failure.startswith('wrong_') and failure in {'wrong_aircraft', 'wrong_connection', 'wrong_telemetry'}:
        key, value = {'wrong_aircraft': ('aircraft_uid', 'other'),
                      'wrong_connection': ('connection_generation', 'other'),
                      'wrong_telemetry': ('telemetry_generation', 2)}[failure]
        f.app.px4_interface.get_aircraft_state = lambda: replace(state, binding=replace(state.binding, **{key: value}))
    elif failure == 'wrong_session':
        f.app._following_session_id = 'replacement'
    elif failure == 'wrong_generation':
        getter = f.app.follower.follower.session_controls
        f.app.follower.follower.session_controls = lambda: [dict(item, guidance_generation=99) for item in getter()]
    elif failure in {'phase_change', 'transition'}:
        phase = AirframePhase.MULTICOPTER if failure == 'phase_change' else AirframePhase.VTOL_TRANSITION
        f.app.px4_interface.get_aircraft_state = lambda: replace(state, phase=phase, is_vtol=True)
    elif failure == 'ended':
        f.guidance.end('operator_stop')
        # Retained stale rows must not gain an observation after their owner ended.
        f.app.follower.follower.session_controls = lambda: [dict(
            control_id='requested_speed', label='Airspeed', unit='m/s', minimum=10., maximum=30., step=.5,
            value=20., revision=0, guidance_generation=1, aircraft_phase='fixed_wing', speed_basis='equivalent_airspeed')]
    elif failure == 'rescue':
        f.app.px4_interface.get_aircraft_state = lambda: replace(state, rescue_active=True)
    elif failure == 'owner_lost':
        f.app._native_follow_binding.owner_confirmed = False
    elif failure == 'control_phase':
        getter = f.app.follower.follower.session_controls
        f.app.follower.follower.session_controls = lambda: [dict(item, aircraft_phase='multicopter') for item in getter()]
    elif failure == 'unready_connection':
        f.app.px4_interface.is_command_connection_ready = lambda **_: False
    else:
        f.app._is_command_preview_session = lambda: True
    control = observed_control(f)
    assert control['observed_speed_m_s'] is None
    assert control['observed_speed_source'] is None


@pytest.mark.parametrize('failure', ['stale', 'future', 'invalid', 'unavailable'])
def test_missing_qualified_eas_never_becomes_groundspeed_or_a_sensorless_claim(observed_owner, failure):
    f = observed_owner
    changes = {'observed_at_monotonic_s': f.clock[0] - 1.} if failure == 'stale' else (
        {'observed_at_monotonic_s': f.clock[0] + 1.} if failure == 'future' else {'valid': False})
    if failure == 'unavailable':
        changes.update(source='unavailable', equivalent_m_s=None, true_m_s=None)
    assert f.states.commit(replace(f.state, sequence=f.state.sequence + 1,
                                   airspeed=replace(f.state.airspeed, **changes)))
    f.app.px4_interface.current_ground_speed = 50.
    control = observed_control(f)
    assert control['observed_speed_m_s'] is None and control['observed_speed_source'] is None


@pytest.mark.parametrize('feedback_case', [
    'qualified', 'missing', 'stale', 'future', 'precedes_state', 'nonfinite', 'boolean_time',
    'enabled', 'unknown_enabled', 'inactive', 'unsupported', 'wrong_identity',
])
def test_sensorless_label_requires_fresh_matching_native_feedback(observed_owner, feedback_case):
    f = observed_owner
    assert f.states.commit(replace(f.state, sequence=f.state.sequence + 1,
        airspeed=AirspeedObservation('unavailable', None, None, f.clock[0], False)))
    feedback = dict(observed_at_monotonic_s=f.clock[0], controller_active=True, airspeed_control_enabled=False)
    if feedback_case in {'stale', 'future'}:
        feedback['observed_at_monotonic_s'] += -1. if feedback_case == 'stale' else 1.
    elif feedback_case == 'precedes_state':
        feedback['observed_at_monotonic_s'] -= .01
    elif feedback_case == 'nonfinite':
        feedback['observed_at_monotonic_s'] = float('nan')
    elif feedback_case == 'boolean_time':
        feedback['observed_at_monotonic_s'] = True
    elif feedback_case == 'unsupported':
        f.guidance.phase_owner.capabilities = replace(f.guidance.phase_owner.capabilities, fixed_wing_supported=False)
    elif feedback_case == 'enabled':
        feedback['airspeed_control_enabled'] = True
    elif feedback_case == 'unknown_enabled':
        feedback.pop('airspeed_control_enabled')
    elif feedback_case == 'inactive':
        feedback['controller_active'] = False
    elif feedback_case == 'wrong_identity':
        f.transport.identity = replace(f.guidance.identity, guidance_generation=99)
    f.transport.last_feedback = None if feedback_case == 'missing' else feedback
    control = observed_control(f)
    assert control['observed_speed_m_s'] is None
    assert control['observed_speed_source'] == ('native_airspeedless' if feedback_case == 'qualified' else None)


@pytest.mark.parametrize('velocity, expected', [
    (Vector3(3., -4., 12.), 13.), (Vector3(-3., 4., -12.), 13.), (Vector3(0., 0., 0.), 0.),
    (Vector3(1.7e308, 1.7e308, 1.7e308), None),
])
def test_mc_observation_uses_all_three_ned_components_without_airspeed_label(active_owner, monkeypatch, velocity, expected):
    app = active_owner.app_controller
    state = aircraft_state(binding=AircraftBinding('42', 'connection-1', 1), phase=AirframePhase.MULTICOPTER,
                           velocity_ned_m_s=velocity)
    states = AircraftStateOwner(clock=lambda: 100.)
    states.bind(state.binding)
    assert states.commit(state)
    app.px4_interface.get_aircraft_state = lambda: states.snapshot(timeout_s=.75)
    app.px4_interface.get_telemetry_stale_timeout_s = lambda: .75
    monkeypatch.setattr('classes.api_v1_following_controls.time', SimpleNamespace(monotonic=lambda: 100.), raising=False)
    control = following_snapshot(active_owner, active_owner.principal_test)['session_controls'][0]
    assert control['observed_speed_m_s'] == expected
    assert control['observed_speed_source'] is None
    assert control.get('speed_basis', 'translation_3d') == 'translation_3d'


def test_legacy_mc_scalar_telemetry_is_not_an_observed_3d_vector(active_owner):
    app = active_owner.app_controller
    app.px4_interface.current_ground_speed = 13.
    app.px4_interface.current_vertical_speed = 0.
    payload = following_snapshot(active_owner, active_owner.principal_test)
    control = APINativeFollowingStatus.model_validate(payload).session_controls[0]
    assert control.observed_speed_m_s is None and control.observed_speed_source is None


@pytest.mark.parametrize('sample', [None, {'ground_speed_m_s': 13.},
                                   {'velocity_ned_m_s': {'x': 3., 'y': -4.}}])
def test_untyped_or_incomplete_mc_telemetry_is_not_filled_from_scalar_speed(active_owner, sample):
    app = active_owner.app_controller
    app.px4_interface.get_aircraft_state = lambda: sample
    app.px4_interface.current_ground_speed = 13.
    control = following_snapshot(active_owner, active_owner.principal_test)['session_controls'][0]
    assert control['observed_speed_m_s'] is None and control['observed_speed_source'] is None

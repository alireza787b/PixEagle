"""The same session mutation is guarded for browser and native callers."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import Response
from pydantic import ValidationError

from classes.api_v1_contracts import APIFollowingControlRequest
from classes.api_security_types import APIPrincipal
from classes.api_v1_following_controls import session_control_snapshot, set_following_control
from classes.api_v1_native_following import following_snapshot
from classes.followers.base_follower import BaseFollower
from classes.follower_session_controls import SessionControl
from classes.runtime_identity import INSTANCE_ID, RUNTIME_ID
from tests.unit.core_app.test_native_following import owner, action_request
from tests.unit.core_app.test_native_target_operations import owner as target_owner

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

"""Capture one passive native epoch before startup can cross an await."""

from dataclasses import replace
import json
from unittest.mock import AsyncMock, Mock

from fastapi import Response
import pytest
from pydantic import ValidationError

from classes.aircraft_state import AircraftKind, AirframePhase
from classes.api_v1_contracts import APIActionRequest, APINativeFollowerSelectRequest, APINativeTargetGuard
from classes.api_v1_native_following import following_snapshot, native_follow_action, native_follower_select
from classes.api_v1_native_targets import target_state
from classes.app_controller import AppController
from classes.native_guidance import NativeGuidanceError
from classes.parameters import Parameters
from tests.fixtures.native_ownership import start_context
from tests.unit.core_app.test_native_follow_application import app as app_fixture
from tests.unit.core_app.test_native_follow_binding import fixture
from tests.unit.core_app.test_native_follow_binding import CONFIG
from tests.unit.core_app.test_native_following import (
    action_request, owner as owner_fixture, ready_owner, start_body,
)
from tests.unit.core_app.test_native_target_operations import execute, owner as target_owner
from tests.unit.drone_interface.test_aircraft_state import aircraft_state


app = app_fixture
owner = owner_fixture


@pytest.fixture
def native_owner(owner, monkeypatch):
    ready_owner(owner, monkeypatch)
    # This fixture isolates opaque command-epoch guards. Real gimbal/image
    # acquisition-clock readiness is exercised by the resolver domain tests.
    monkeypatch.setattr('classes.gazebo_guidance_alignment.native_guidance_input_readiness',
                        lambda *_: {'ready': True, 'reason_code': None})
    monkeypatch.setattr(Parameters, 'FOLLOWER_MODE', 'gm_velocity_vector')
    owner._get_config_service = lambda: Mock(get_parameter=lambda *_: 'gm_velocity_vector')
    monkeypatch.setattr('classes.api_v1_native_following._selected_tracker_output',
                        lambda *_: ('GimbalTracker', 'GIMBAL_ANGLES'))
    owner.flight_test['aircraft_kind'] = 'fixed_wing'
    state = aircraft_state()
    from classes.aircraft_state import GuidanceSessionIdentity
    original = start_context(GuidanceSessionIdentity('fixture', state.binding, 0))
    owner.app_controller.px4_interface.get_aircraft_state.return_value = state
    owner.app_controller._capture_native_start_context = Mock(return_value=original)
    owner.app_controller.connect_px4 = AsyncMock()
    return owner, original


def test_following_guard_advertises_only_opaque_native_context(native_owner):
    owner, original = native_owner
    snapshot = following_snapshot(owner, owner.principal_test)
    assert snapshot['start_allowed'], snapshot['start_reason_codes']
    assert snapshot['guard']['start_context_id'] == original.context_id
    assert 'source_nav_state_timestamp' not in snapshot['guard']
    assert APINativeTargetGuard.model_validate(snapshot['guard']).start_context_id == original.context_id
    owner.app_controller.refresh_native_following_state.assert_not_awaited()


@pytest.mark.parametrize('use_following_guard', [False, True])
async def test_target_cancel_keeps_its_exact_target_guard_separate(native_owner, use_following_guard):
    owner, original = native_owner
    target = target_state(owner, owner.principal_test)
    following = following_snapshot(owner, owner.principal_test)
    assert target['guard']['start_context_id'] is None
    assert following['guard']['start_context_id'] == original.context_id
    request = APIActionRequest(dry_run=True, native_context={
        'binding_mode': 'vehicle', 'guard': following['guard'] if use_following_guard else target['guard']})
    result, response = await execute(owner, request, 'tracking_stop')
    if use_following_guard:
        assert result.status_code == 409 and json.loads(result.body)['code'] == 'native_context_stale'
    else:
        assert response.status_code == 200 and result['status'] == 'validated'
    owner.app_controller.connect_px4.assert_not_awaited()


@pytest.mark.parametrize('use_following_guard', [False, True])
async def test_follower_choice_uses_full_following_guard(native_owner, use_following_guard):
    owner, _ = native_owner
    following = following_snapshot(owner, owner.principal_test)
    guard = (following if use_following_guard else target_state(owner, owner.principal_test))['guard']
    request = APINativeFollowerSelectRequest(dry_run=True, profile_mode='gm_velocity_vector',
        profile_generation=following['profile_generation'],
        native_context={'binding_mode': 'vehicle', 'guard': guard})
    response = Response()
    result = await native_follower_select(owner, request, response, action_request(owner))
    if use_following_guard:
        assert response.status_code == 200 and result['status'] == 'validated'
    else:
        assert result.status_code == 409 and json.loads(result.body)['code'] == 'native_follow_context_stale'
    owner.app_controller.connect_px4.assert_not_awaited()


@pytest.mark.parametrize('value', ['', 'x' * 64, 'A' * 64, 123, True])
def test_opaque_start_context_has_strict_digest_shape(native_owner, value):
    owner, _ = native_owner
    guard = following_snapshot(owner, owner.principal_test)['guard'] | {'start_context_id': value}
    with pytest.raises(ValidationError):
        APINativeTargetGuard.model_validate(guard)


@pytest.mark.parametrize('fault', ['missing_id', 'wrong_id', 'missing_context', 'mode_epoch'])
async def test_native_start_refuses_wrong_or_missing_original_before_any_await(native_owner, fault):
    owner, original = native_owner
    request = start_body(following_snapshot(owner, owner.principal_test))
    if fault == 'missing_id':
        request.native_context.guard.start_context_id = None
    elif fault == 'wrong_id':
        request.native_context.guard.start_context_id = 'f' * 64
    elif fault == 'missing_context':
        owner.app_controller._capture_native_start_context.return_value = None
    else:
        # Even a return to the same numeric nav state is a different mode epoch.
        owner.app_controller._capture_native_start_context.return_value = replace(
            original, source_nav_state_timestamp=original.source_nav_state_timestamp + 1)
    response = await native_follow_action(owner, request, Response(), action_request(owner), start=True)
    assert response.status_code == 409
    owner.app_controller.refresh_native_following_state.assert_not_awaited()
    owner.app_controller.connect_px4.assert_not_awaited()


@pytest.mark.parametrize('field,value', [('phase_revision', 1), ('runtime_id', 'replacement'),
                                        ('source_nav_state_timestamp', 101)])
async def test_passive_change_during_refresh_cannot_be_recaptured(native_owner, field, value):
    owner, original = native_owner
    request = start_body(following_snapshot(owner, owner.principal_test))

    async def change(_mode):
        changes = {field: value}
        if field == 'phase_revision':
            changes['phase_source_instance'] = 9
        owner.app_controller._capture_native_start_context.return_value = replace(original, **changes)

    owner.app_controller.refresh_native_following_state.side_effect = change
    response = await native_follow_action(owner, request, Response(), action_request(owner), start=True)
    assert response.status_code == 409
    assert json.loads(response.body)['code'] == 'native_follow_context_stale'
    owner.app_controller.connect_px4.assert_not_awaited()


async def test_acquired_checks_keep_original_id_but_still_fence_live_target(native_owner):
    owner, original = native_owner
    request = start_body(following_snapshot(owner, owner.principal_test))

    async def start(native_start_guard, *, native_attempt_id, native_aircraft_uid, native_start_context):
        assert native_start_context is original
        native_start_guard('before_start')
        native_start_guard('before_offboard')
        owner.app_controller._capture_native_start_context.return_value = None
        native_start_guard('after_offboard')
        native_start_guard('before_activation')
        owner.telemetry_test['connection_generation'] = 'replacement'
        with pytest.raises(Exception, match='changed'):
            native_start_guard('before_activation')
        owner.telemetry_test['connection_generation'] = request.native_context.guard.telemetry_generation
        owner.app_controller.following_active = True
        return {'steps': [], 'errors': []}

    owner.app_controller.connect_px4.side_effect = start
    response = Response()
    record = await native_follow_action(owner, request, response, action_request(owner), start=True)
    assert response.status_code == 202 and record['status'] == 'success'


async def test_app_captures_once_before_owner_loop_handoff(app):
    ctrl, original = app.ctrl, app.f.start_context
    capture = Mock(wraps=ctrl._capture_native_start_context)
    ctrl._capture_native_start_context = capture
    received = []

    async def run(operation):
        assert capture.call_count == 1
        ctrl.px4_interface.native_start_context = replace(original, source_nav_state_timestamp=101)
        return await operation()

    async def once(*args, native_start_context):
        received.append(native_start_context)
        return {'steps': [], 'errors': []}

    ctrl._run_on_flight_event_loop = run
    ctrl._connect_px4_once_on_flight_loop = once
    assert (await ctrl.connect_px4())['errors'] == []
    assert received == [original] and received[0] is original
    assert capture.call_count == 1


async def test_normal_app_start_forwards_one_original_context_through_all_startup_layers(app):
    ctrl, original = app.ctrl, app.f.start_context
    capture = Mock(wraps=ctrl._capture_native_start_context)
    ctrl._capture_native_start_context = capture

    async def run(operation):
        return await operation()

    ctrl._run_on_flight_event_loop = run
    result = await ctrl.connect_px4()
    assert result['errors'] == [] and ctrl.following_active
    assert capture.call_count == 1
    assert ctrl._prepare_native_follow_binding.call_args.args[0] is original
    assert app.f.client.engage.call_args.kwargs['start_context'] is original


async def test_explicit_absence_cannot_capture_a_new_native_context_after_config_await(app):
    ctrl = app.ctrl
    app.manager.follower.setpoint_handler.profile_config = {'native_phase_contracts': {
        'multicopter': 'velocity_body_offboard', 'fixed_wing': 'fixed_wing_external'}}
    ctrl._capture_native_start_context = Mock(side_effect=AssertionError('recaptured'))
    ctrl._prepare_native_follow_binding = AppController._prepare_native_follow_binding.__get__(ctrl)
    result = await ctrl._connect_px4_on_flight_loop(native_start_context=None)
    assert not ctrl.following_active
    assert any('native_start_context_required' in error for error in result['errors'])
    ctrl._capture_native_start_context.assert_not_called()
    app.f.client.engage.assert_not_called()


@pytest.mark.parametrize('fault', ['phase', 'runtime', 'binding'])
async def test_prepare_refuses_changed_context_without_any_acquisition(app, fault):
    ctrl, original = app.ctrl, app.f.start_context
    ctrl.follower = app.manager
    app.manager.follower.setpoint_handler.profile_config = {'native_phase_contracts': {
        'multicopter': 'velocity_body_offboard', 'fixed_wing': 'fixed_wing_external'}}
    state = app.f.state
    if fault == 'phase':
        state = replace(state, phase=AirframePhase.MULTICOPTER)
    elif fault == 'binding':
        state = replace(state, binding=replace(state.binding, telemetry_generation=2))
    else:
        ctrl.px4_interface.native_guidance_client.capabilities = replace(
            app.f.client.capabilities, runtime_id='replacement')
    ctrl.px4_interface.get_aircraft_state.return_value = state
    with pytest.raises(NativeGuidanceError, match='native_start_context_changed'):
        await AppController._prepare_native_follow_binding(ctrl, original)
    app.f.client.engage.assert_not_called()


@pytest.mark.parametrize('refused', [False, True])
async def test_prepare_awaits_declared_image_binding_before_creating_session(app, monkeypatch, refused):
    ctrl, original = app.ctrl, app.f.start_context
    ctrl.follower = app.manager
    ctrl._following_session_id = app.f.guidance.identity.follow_session_id
    ctrl._following_continuity_config = CONFIG
    ctrl._freeze_following_observation_source()
    ctrl._get_target_continuity_supervisor = Mock(return_value=app.f.continuity)
    concrete = app.manager.follower
    concrete.setpoint_handler.profile_config = {'native_phase_contracts': {
        'multicopter': 'velocity_body_offboard', 'fixed_wing': 'fixed_wing_external'}}
    calls = []

    async def bind(actual_app, follower, state, capabilities, *, validate_input):
        validate_input()
        assert actual_app is ctrl and follower is concrete and state is app.f.state
        assert capabilities is app.f.client.capabilities
        calls.append('bind')
        ctrl.px4_interface.native_start_context = replace(original, source_nav_state_timestamp=101)
        if refused:
            raise ValueError('physical_capture_timing_unqualified')

    def create(*args, **kwargs):
        assert calls == ['bind']
        calls.append('create')
        return app.f.guidance

    hook = AsyncMock(side_effect=bind)
    monkeypatch.setattr('classes.gazebo_guidance_alignment.bind_native_input_resolver', hook)
    concrete.create_airframe_session = Mock(side_effect=create)
    if refused:
        with pytest.raises(NativeGuidanceError, match='physical_capture_timing_unqualified'):
            await AppController._prepare_native_follow_binding(ctrl, original)
        concrete.create_airframe_session.assert_not_called()
    else:
        await AppController._prepare_native_follow_binding(ctrl, original)
        assert calls == ['bind', 'create']
    assert original.source_nav_state_timestamp == 100
    hook.assert_awaited_once()
    app.f.client.engage.assert_not_awaited()


def test_pure_mc_capture_does_not_consume_or_require_a_native_context(app):
    ctrl = app.ctrl
    ctrl.px4_interface.get_aircraft_kind.return_value = AircraftKind.MULTICOPTER
    ctrl.px4_interface.native_start_context = None
    ctrl.px4_interface.native_guidance_client = None
    assert ctrl._capture_native_start_context() is None


@pytest.mark.parametrize('fault', ['context', 'state'])
async def test_app_missing_original_refuses_without_connecting_or_discovering(app, fault):
    ctrl = app.ctrl
    if fault == 'context':
        ctrl.px4_interface.native_start_context = None
    else:
        ctrl.px4_interface.get_aircraft_state.return_value = None
    result = await ctrl.connect_px4()
    assert result['precondition']['code'] == 'native_start_context_required'
    ctrl.px4_interface.connect.assert_not_awaited()
    ctrl.px4_interface.prepare_native_guidance.assert_not_awaited()
    app.f.client.engage.assert_not_awaited()


async def test_binding_missing_context_fails_before_mode_rpc():
    f = fixture()
    with pytest.raises(NativeGuidanceError, match='native_start_context_required'):
        await f.binding.engage()
    f.client.engage.assert_not_awaited()


@pytest.mark.parametrize('accepted', [False, True])
async def test_binding_commits_full_original_observation_through_manager_hook(accepted):
    f = fixture()
    packet = f.packet()
    packet['raw_pose_timing'] = {'uninterpreted_source_receipt': 99}
    f.client.observe = AsyncMock(return_value=packet)
    f.connection.commit_native_observation = Mock(return_value=accepted)
    f.connection.commit_aircraft_state = Mock(side_effect=AssertionError('state-only fallback'))
    if accepted:
        await f.binding.engage(start_context=f.start_context)
    else:
        with pytest.raises(NativeGuidanceError, match='native_aircraft_state_rejected'):
            await f.binding.engage(start_context=f.start_context)
    f.connection.commit_native_observation.assert_called_once_with(packet)
    assert f.connection.commit_native_observation.call_args.args[0] is packet
    f.connection.commit_aircraft_state.assert_not_called()

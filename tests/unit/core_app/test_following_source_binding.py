"""A follow session never adopts a different observation source or queued target."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from classes.app_controller import AppController
from classes.command_dispatch_guard import DispatchRefused, DispatchRefusalKind, validate_before_dispatch
from classes.following_observation_source import ObservationSourceVerdict
from classes.target_continuity import TargetEvidenceState
from tests.fixtures.following_observation import bind_image_source
from tests.unit.core_app.test_native_follow_application import app


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def command_admission(monkeypatch):
    from classes.parameters import Parameters
    monkeypatch.setattr(Parameters, 'FOLLOWER_CIRCUIT_BREAKER', False)


def controller():
    value = object.__new__(AppController)
    value.following_active = False
    value._tracking_session_generation = 1
    value.px4_interface = SimpleNamespace(get_aircraft_identity=Mock(return_value={}))
    output = bind_image_source(value)
    return value, output


def test_pending_source_is_immutable_across_new_frames_retarget_and_delivery_changes():
    ctrl, output = controller()
    identity = ctrl._freeze_following_observation_source()
    pin = ctrl._following_observation_source
    first = ctrl._command_dispatch_guard()
    provenance = replace(ctrl.tracking_input_context.provenance, target_generation=99)
    ctrl.tracking_input_context = replace(ctrl.tracking_input_context, provenance=provenance)
    output.image_measurement = ctrl.tracking_input_context.at_pixel((30., 40.))
    ctrl.frame_publisher.stream_epoch = 'delivery-reconnect-only'
    ctrl._require_follow_start_input_identity(identity, {}, stage='test')
    first()
    ctrl._tracking_session_generation += 1
    assert ctrl._following_observation_source is pin
    with pytest.raises(DispatchRefused) as error:
        first()
    assert error.value.kind is DispatchRefusalKind.SUPERSEDED
    ctrl._command_dispatch_guard()()


def test_owner_restart_is_terminal_before_any_new_analysis_or_sample():
    ctrl, output = controller()
    ctrl._freeze_following_observation_source()
    guard = ctrl._command_dispatch_guard()
    ctrl.frame_publisher.control_source_epoch = 'restarted-capture'
    ctrl.tracking_input_context = None
    assert ctrl._following_source_verdict(output.image_measurement) is ObservationSourceVerdict.DEFINITELY_CHANGED
    with pytest.raises(DispatchRefused, match='observation_source_changed') as error:
        guard()
    assert error.value.kind is DispatchRefusalKind.TERMINAL


def test_missing_context_uses_uncertain_evidence_and_does_not_refuse_every_heartbeat():
    ctrl, output = controller()
    ctrl._freeze_following_observation_source()
    ctrl.following_active = True
    guard = ctrl._command_dispatch_guard()
    ctrl.tracking_input_context = None
    result = ctrl._target_evidence_snapshot(output)
    assert result.state is TargetEvidenceState.UNCERTAIN
    assert result.reason_code == 'following_observation_source_unavailable'
    guard()


def test_no_active_session_can_invent_missing_pin_from_a_current_measurement():
    ctrl, output = controller()
    ctrl.following_active = True
    assert ctrl._guidance_source_readiness(output) == {
        'ready': False, 'reason_code': 'following_observation_source_unavailable'}


def test_final_guard_never_reads_inference_or_acquires_model_lock():
    ctrl, _ = controller()
    ctrl._freeze_following_observation_source()
    guard = ctrl._command_dispatch_guard()
    ctrl.get_tracker_output = Mock(side_effect=AssertionError('inference read'))
    class ForbiddenLock:
        def __enter__(self):
            raise AssertionError('model lock')
    ctrl._tracker_model_state_lock = ForbiddenLock()
    guard()
    ctrl.get_tracker_output.assert_not_called()


def test_old_session_and_old_target_are_benign_even_if_the_source_has_changed():
    ctrl, _ = controller()
    ctrl._freeze_following_observation_source()
    guard = ctrl._command_dispatch_guard()
    ctrl.frame_publisher.control_source_epoch = 'other'
    ctrl._following_session_id = 'replacement-session'
    with pytest.raises(DispatchRefused) as error:
        guard()
    assert error.value.kind is DispatchRefusalKind.SUPERSEDED


def test_retarget_rejects_changed_source_before_mutating_follower_or_target():
    ctrl, _ = controller()
    ctrl._freeze_following_observation_source()
    ctrl.following_active = True
    ctrl.follower = SimpleNamespace(prepare_for_target_transition=Mock())
    ctrl.frame_publisher.control_source_epoch = 'restarted-capture'
    pin, target = ctrl._following_observation_source, ctrl._tracking_session_generation
    result = ctrl._prepare_following_target_transition('retarget')
    assert result == {'prepared': False, 'reason': 'following_observation_source_changed'}
    ctrl.follower.prepare_for_target_transition.assert_not_called()
    assert ctrl._following_observation_source is pin
    assert ctrl._tracking_session_generation == target


async def test_source_change_during_connection_cannot_engage_any_command_owner(app):
    async def connect():
        app.ctrl.frame_publisher.control_source_epoch = 'changed-while-connecting'
        return {'connected': True}
    app.ctrl.px4_interface.connect.side_effect = connect
    result = await app.ctrl._connect_px4_on_flight_loop()
    assert result['precondition']['code'] == 'following_input_context_changed'
    app.f.client.engage.assert_not_called()
    app.ctrl.px4_interface.start_offboard_mode.assert_not_called()
    assert app.ctrl._following_observation_source is None


async def test_target_change_during_connection_cannot_acquire_native_owner(app):
    async def connect():
        app.ctrl._tracking_session_generation = 5
        return {'connected': True}
    app.ctrl.px4_interface.connect.side_effect = connect
    result = await app.ctrl._connect_px4_on_flight_loop()
    assert result['precondition']['code'] == 'following_input_context_changed'
    app.f.client.engage.assert_not_called()


async def test_native_source_change_while_acquisition_is_queued_sends_no_mode_or_hold(app):
    async def engage(_identity, *, before_dispatch, on_mode_dispatch, **_kwargs):
        app.ctrl.frame_publisher.control_source_epoch = 'changed-at-acquire-lock'
        validate_before_dispatch(before_dispatch)
        on_mode_dispatch()
        raise AssertionError('must not write native engage')
    app.f.client.engage.side_effect = engage
    result = await app.ctrl._connect_px4_on_flight_loop()
    assert result['errors']
    assert not app.f.binding.acquire_dispatched
    app.f.client.handoff.assert_not_called()
    app.f.client.observe_after_release.assert_not_called()
    app.ctrl.px4_interface.stop_offboard_mode.assert_not_called()
    assert app.ctrl._following_session_id is None


async def test_unresolved_primed_sender_retains_original_owner_without_hold(app):
    from classes.aircraft_state import AircraftKind
    app.ctrl.px4_interface.get_aircraft_kind.return_value = AircraftKind.MULTICOPTER
    async def acquire(*, before_dispatch, on_mode_dispatch):
        app.ctrl.frame_publisher.control_source_epoch = 'changed-before-mode-write'
        app.ctrl.px4_interface.last_start_cleanup_outcome = {'attempted': True, 'local_sender_quiesced': False}
        validate_before_dispatch(before_dispatch)
        raise AssertionError('must not start mode')
    app.ctrl.px4_interface.start_offboard_mode.side_effect = acquire
    result = await app.ctrl._connect_px4_on_flight_loop()
    assert result['errors']
    assert app.ctrl._following_offboard_cleanup_required
    assert app.ctrl._following_session_id
    assert app.ctrl._following_observation_source
    assert app.ctrl._following_teardown_context['acquire_dispatched'] is False
    app.ctrl.px4_interface.stop_offboard_mode.assert_not_called()
    second = await app.ctrl._connect_px4_on_flight_loop()
    assert second['precondition']['code'] == 'following_stop_pending'


async def test_late_failed_publisher_callback_cannot_stop_a_new_session(app):
    app.ctrl.following_active = True
    app.ctrl._following_session_id = 'new-follow-session'
    app.ctrl._disconnect_px4_internal = AsyncMock()
    await app.ctrl._handle_offboard_commander_failure_on_flight_loop({
        'follow_session_id': 'old-follow-session', 'terminal_failure_reason': 'following_observation_source_changed'})
    app.ctrl._disconnect_px4_internal.assert_not_called()
    assert app.ctrl.following_active


@pytest.mark.parametrize('change,terminal', [('target', False), ('session', False), ('source', True)])
async def test_queued_publication_rechecks_accepted_semantic_context_and_never_counts_a_link_failure(change, terminal):
    from classes.offboard_commander import OffboardCommander
    from tests.unit.drone_interface.test_offboard_commander import _handler, _intent
    ctrl, _ = controller()
    ctrl._freeze_following_observation_source()
    entered, release = asyncio.Event(), asyncio.Event()
    sent, events = [], []
    async def setter(*, command_intent, before_dispatch):
        entered.set()
        await release.wait()
        validate_before_dispatch(before_dispatch)
        sent.append(command_intent)
        return True
    ctrl.px4_interface.send_commands_unified = setter
    callback = Mock()
    commander = OffboardCommander(ctrl.px4_interface, _handler(), on_failure_threshold=callback,
        on_publish_result=events.append)
    ctrl.offboard_commander = commander
    assert ctrl._submit_command_intent_to_commander(_intent())
    task = asyncio.create_task(commander.publish_once())
    await asyncio.wait_for(entered.wait(), timeout=1.)
    if change == 'source':
        ctrl.frame_publisher.control_source_epoch = 'new-source'
    elif change == 'target':
        ctrl._tracking_session_generation += 1
    else:
        ctrl._following_session_id = 'new-session'
    release.set()
    assert not await task
    assert not sent
    assert commander.publish_count == commander.failed_publishes == commander.consecutive_failures == 0
    assert events[-1]['publication_attempted'] is False
    assert events[-1]['submitted_fields'] is None
    assert events[-1]['publish_status']['last_publish_success'] is None
    assert events[-1]['dispatch_context']['target_generation'] == 1
    assert commander.terminal_failure is terminal
    assert callback.call_count == int(terminal)
    if not terminal:
        assert commander.last_error is None


async def test_new_same_target_frame_does_not_starve_a_queued_attempt_or_change_its_snapshot():
    from classes.offboard_commander import OffboardCommander
    from tests.unit.drone_interface.test_offboard_commander import _handler, _intent
    ctrl, _ = controller()
    ctrl._freeze_following_observation_source()
    entered, release = asyncio.Event(), asyncio.Event()
    sent = []
    async def setter(*, command_intent, before_dispatch):
        entered.set()
        await release.wait()
        validate_before_dispatch(before_dispatch)
        sent.append(command_intent)
        return True
    ctrl.px4_interface.send_commands_unified = setter
    commander = ctrl.offboard_commander = OffboardCommander(ctrl.px4_interface, _handler())
    first = _intent()
    assert ctrl._submit_command_intent_to_commander(first)
    task = asyncio.create_task(commander.publish_once())
    await asyncio.wait_for(entered.wait(), timeout=1.)
    newer = replace(first, fields={**first.fields, 'vel_body_fwd': 2.})
    assert ctrl._submit_command_intent_to_commander(newer)
    release.set()
    assert await task
    assert sent[0].fields == first.fields
    assert commander._last_intent.fields == newer.fields


async def test_retry_of_unresolved_preacquire_sender_never_requests_hold(app):
    from classes.aircraft_state import AircraftKind
    app.ctrl.px4_interface.get_aircraft_kind.return_value = AircraftKind.MULTICOPTER
    async def refused(*, before_dispatch, **_kwargs):
        app.ctrl.frame_publisher.control_source_epoch = 'restarted'
        app.ctrl.px4_interface.last_start_cleanup_outcome = {'attempted': True, 'local_sender_quiesced': False}
        validate_before_dispatch(before_dispatch)
    app.ctrl.px4_interface.start_offboard_mode.side_effect = refused
    await app.ctrl._connect_px4_on_flight_loop()
    original = app.ctrl._following_teardown_context.copy()
    app.ctrl.px4_interface.quiesce_offboard_sender = AsyncMock(return_value={
        'attempted': True, 'local_sender_quiesced': True, 'state_after': 'quiesced'})
    result = await app.ctrl._disconnect_px4_internal(reason_code='operator_stop', retry_failed=True)
    assert result['errors'] == []
    app.ctrl.px4_interface.stop_offboard_mode.assert_not_called()
    app.ctrl.px4_interface.quiesce_offboard_sender.assert_awaited_once_with(reason='local_follow_cleanup', allow_hold=False)
    assert original['aircraft_uid'] == app.f.state.binding.aircraft_uid
    assert not app.ctrl._following_offboard_cleanup_required
    assert app.ctrl._following_session_id is None


def test_definite_source_change_retains_authority_guard_priority_in_shared_supervisor():
    from classes.target_continuity import (AirframePhase, ContinuityContext, ContinuityPolicy,
        TargetContinuitySupervisor, TargetEvidenceSnapshot, IdentityVerdict)
    supervisor = TargetContinuitySupervisor(ContinuityPolicy.from_mapping(None), clock=lambda: 1.)
    supervisor.reset_session(session_epoch=1, reason='test')
    evidence = TargetEvidenceSnapshot(TargetEvidenceState.UNCERTAIN, 1., 1, None, IdentityVerdict.UNCONFIRMED, 'source_changed', observation_source_changed=True)
    context = ContinuityContext('PX4', AirframePhase.MULTICOPTER, 'velocity_body_offboard', True, True, True)
    assert supervisor.evaluate(evidence, replace(context, operator_abort=True)).reason_code == 'operator_abort'
    supervisor.reset_session(session_epoch=1, reason='test')
    assert supervisor.evaluate(evidence, replace(context, vehicle_state_fresh=False)).reason_code == 'vehicle_state_stale'
    supervisor.reset_session(session_epoch=1, reason='test')
    assert supervisor.evaluate(evidence, context).reason_code == 'following_observation_source_changed'


@pytest.mark.parametrize('cause', ['circuit_breaker', 'shutdown', 'takeover'])
async def test_final_guard_observes_new_authority_loss_while_the_setter_is_queued(monkeypatch, cause):
    from classes.parameters import Parameters
    from classes.offboard_commander import OffboardCommander
    from tests.unit.drone_interface.test_offboard_commander import _handler, _intent
    ctrl, _ = controller()
    ctrl._freeze_following_observation_source()
    ctrl.px4_interface.get_aircraft_identity.return_value = {'autopilot_uid': 'actual-aircraft', 'connection_generation': 1}
    flight = {'fresh': True, 'autopilot_uid': 'actual-aircraft', 'offboard_exit_observed_at_monotonic_s': None}
    ctrl.px4_interface.mavlink_data_manager = SimpleNamespace(get_flight_state=lambda: dict(flight))
    ctrl.px4_interface._offboard_start_attempt_monotonic_s = 100.
    entered, release = asyncio.Event(), asyncio.Event()
    sent = []
    async def setter(*, command_intent, before_dispatch):
        entered.set()
        await release.wait()
        validate_before_dispatch(before_dispatch)
        sent.append(command_intent)
        return True
    ctrl.px4_interface.send_commands_unified = setter
    ctrl.offboard_commander = OffboardCommander(ctrl.px4_interface, _handler())
    assert ctrl._submit_command_intent_to_commander(_intent())
    task = asyncio.create_task(ctrl.offboard_commander.publish_once())
    await asyncio.wait_for(entered.wait(), timeout=1.)
    if cause == 'circuit_breaker':
        monkeypatch.setattr(Parameters, 'FOLLOWER_CIRCUIT_BREAKER', True)
    elif cause == 'shutdown':
        ctrl.shutdown_flag = True
    else:
        flight['offboard_exit_observed_at_monotonic_s'] = 101.
    release.set()
    assert not await task
    assert not sent
    assert ctrl.offboard_commander.terminal_failure
    assert ctrl.offboard_commander.consecutive_failures == 0


async def test_final_native_acquire_guard_rechecks_circuit_breaker_after_the_rpc_wait(app, monkeypatch):
    from classes.parameters import Parameters
    async def engage(_identity, *, before_dispatch, on_mode_dispatch, **_kwargs):
        monkeypatch.setattr(Parameters, 'FOLLOWER_CIRCUIT_BREAKER', True)
        validate_before_dispatch(before_dispatch)
        on_mode_dispatch()
        raise AssertionError('must not write native acquire')
    app.f.client.engage.side_effect = engage
    result = await app.ctrl._connect_px4_on_flight_loop()
    assert result['errors']
    assert not app.f.binding.acquire_dispatched
    app.f.client.handoff.assert_not_called()
    app.ctrl.px4_interface.stop_offboard_mode.assert_not_called()


async def test_delayed_mavlink_exit_callback_cannot_stop_a_new_session(app):
    app.ctrl.following_active = True
    app.ctrl._following_session_id = 'new-session'
    app.ctrl._disconnect_px4_on_flight_loop = AsyncMock()
    await app.ctrl._handle_offboard_mode_exit_on_flight_loop(393216, 4, expected_session_id='old-session')
    app.ctrl._disconnect_px4_on_flight_loop.assert_not_called()
    assert app.ctrl.following_active


def test_old_offboard_exit_is_not_reused_against_an_explicit_new_start_or_native_owner():
    ctrl, _ = controller()
    ctrl._freeze_following_observation_source()
    ctrl.px4_interface.get_aircraft_identity.return_value = {'autopilot_uid': 'actual-aircraft'}
    ctrl.px4_interface._offboard_start_attempt_monotonic_s = 100.
    ctrl.mavlink_data_manager = SimpleNamespace(get_flight_state=lambda: {
        'fresh': True, 'autopilot_uid': 'actual-aircraft', 'offboard_exit_observed_at_monotonic_s': 99.})
    ctrl._command_dispatch_guard()()
    ctrl._airframe_follow_binding = SimpleNamespace()
    ctrl.mavlink_data_manager.get_flight_state = lambda: {
        'fresh': True, 'autopilot_uid': 'actual-aircraft', 'offboard_exit_observed_at_monotonic_s': 101.}
    ctrl._command_dispatch_guard()()


def test_external_source_pin_survives_manual_stop_and_retarget_but_rejects_real_provider_close():
    from tests.fixtures.following_observation import bind_controller_source, gimbal_output
    from classes.tracker_output import TrackerOutput, TrackerDataType
    import time
    ctrl, _ = controller()
    output = gimbal_output(TrackerOutput(TrackerDataType.GIMBAL_ANGLES, time.time(), True, angular=(0., 90., 0.)))
    bind_controller_source(ctrl, output)
    ctrl.get_tracker_output = lambda: output
    ctrl._freeze_following_observation_source()
    guard = ctrl._command_dispatch_guard()
    pin = ctrl._following_observation_source
    ctrl.camera_runtime.acquire('operator', 'stop')
    ctrl.camera_runtime.detach_tracker()
    guard()
    assert ctrl._following_observation_source is pin
    ctrl.camera_runtime.close()
    with pytest.raises(DispatchRefused, match='observation_source_changed'):
        guard()


@pytest.mark.parametrize('requested_value', [2., None])
async def test_acknowledged_session_control_change_supersedes_queued_high_speed_without_resetting_recovery(requested_value):
    from classes.follower_session_controls import SessionControl
    from classes.followers.base_follower import BaseFollower
    from classes.offboard_commander import OffboardCommander
    from tests.unit.drone_interface.test_offboard_commander import _handler, _intent
    ctrl, _ = controller()
    ctrl._freeze_following_observation_source()
    concrete = SimpleNamespace(_session_controls={'speed': SessionControl(
        'speed', 'Translation', 'm/s', 0., None, .5, 10., configured_maximum=6., override_active=True)})
    concrete.session_controls = lambda: BaseFollower.session_controls(concrete)
    concrete.validate_session_control = lambda *args: BaseFollower.validate_session_control(concrete, *args)
    ctrl.follower = SimpleNamespace(follower=concrete)
    recovery = ctrl.get_target_continuity_status()
    entered, release = asyncio.Event(), asyncio.Event()
    sent = []
    async def setter(*, command_intent, before_dispatch):
        entered.set()
        await release.wait()
        validate_before_dispatch(before_dispatch)
        sent.append(command_intent)
        return True
    ctrl.px4_interface.send_commands_unified = setter
    ctrl.offboard_commander = OffboardCommander(ctrl.px4_interface, _handler())
    high = _intent(fields={'vel_body_fwd': 10., 'vel_body_right': 0., 'vel_body_down': 0., 'yawspeed_deg_s': 0.})
    assert ctrl._submit_command_intent_to_commander(high)
    pending = asyncio.create_task(ctrl.offboard_commander.publish_once())
    await asyncio.wait_for(entered.wait(), timeout=1.)
    BaseFollower.update_session_control(concrete, 'speed', requested_value, 0)
    assert concrete.session_controls()[0]['revision'] == 1
    release.set()
    assert not await pending
    assert not sent
    assert ctrl.offboard_commander.last_dispatch_refusal['reason_code'] == 'following_control_superseded'
    lower = replace(high, fields={**high.fields, 'vel_body_fwd': concrete.session_controls()[0]['value']})
    assert ctrl._submit_command_intent_to_commander(lower)
    assert await ctrl.offboard_commander.publish_once()
    assert sent[0].fields['vel_body_fwd'] == (2. if requested_value is not None else 6.)
    assert ctrl.get_target_continuity_status() == recovery


@pytest.mark.parametrize('change', ['source', 'target', 'session', 'aircraft', 'takeover'])
async def test_explicit_stop_neutral_ignores_only_target_source_controls_and_stop_flags(change):
    from classes.offboard_commander import OffboardCommander
    from tests.unit.drone_interface.test_offboard_commander import _handler, _intent
    ctrl, _ = controller()
    ctrl._freeze_following_observation_source()
    ctrl.px4_interface.get_aircraft_identity.return_value = {'autopilot_uid': 'actual-aircraft'}
    ctrl.px4_interface._offboard_start_attempt_monotonic_s = 100.
    flight = {'fresh': True, 'autopilot_uid': 'actual-aircraft', 'offboard_exit_observed_at_monotonic_s': None}
    ctrl.mavlink_data_manager = SimpleNamespace(get_flight_state=lambda: dict(flight))
    sent = []
    async def setter(*, command_intent, before_dispatch):
        validate_before_dispatch(before_dispatch)
        sent.append(command_intent)
        return True
    ctrl.px4_interface.send_commands_unified = setter
    commander = ctrl.offboard_commander = OffboardCommander(ctrl.px4_interface, _handler(),
        before_dispatch=ctrl._command_dispatch_guard(), stop_before_dispatch=ctrl._command_dispatch_guard(teardown=True))
    assert ctrl._submit_command_intent_to_commander(_intent())
    ctrl._following_stopping = True
    ctrl._operator_stop_pending_session_id = ctrl._following_session_id
    if change == 'source':
        ctrl.frame_publisher.control_source_epoch = 'restarted'
    elif change == 'target':
        ctrl._tracking_session_generation += 1
    elif change == 'session':
        ctrl._following_session_id = 'new-session'
    elif change == 'aircraft':
        ctrl.px4_interface.get_aircraft_identity.return_value = {'autopilot_uid': 'other-aircraft'}
    else:
        flight['offboard_exit_observed_at_monotonic_s'] = 101.
    assert await commander.stop(publish_final=True)
    if change in {'source', 'target'}:
        assert len(sent) == 1
        assert set(sent[0].fields.values()) == {0.}
    else:
        assert not sent
    assert commander.failed_publishes == 0


@pytest.mark.parametrize('pending', [False, True])
@pytest.mark.parametrize('sample_kind', ['old', 'missing', 'crossed'])
def test_every_definite_source_mismatch_is_terminal_evidence_even_before_retarget_returns(pending, sample_kind):
    ctrl, output = controller()
    ctrl._freeze_following_observation_source()
    ctrl.following_active = True
    ctrl._get_target_continuity_supervisor().get_status = lambda: {'target_transition_pending': pending}
    if sample_kind in {'old', 'missing'}:
        ctrl.frame_publisher.control_source_epoch = 'new-owner-epoch'
    else:
        measurement = output.image_measurement
        provenance = replace(measurement.provenance, source_id='crossed-input-source')
        output.image_measurement = replace(measurement, provenance=provenance)
    evidence = ctrl._target_evidence_snapshot(None if sample_kind == 'missing' else output)
    assert evidence.observation_source_changed
    assert evidence.state is TargetEvidenceState.UNCERTAIN
    assert evidence.reason_code == 'following_observation_source_changed'


def test_missing_sample_with_unchanged_owner_does_not_manufacture_a_source_change():
    ctrl, _ = controller()
    ctrl._freeze_following_observation_source()
    ctrl.following_active = True
    assert not ctrl._target_evidence_snapshot(None).observation_source_changed


@pytest.mark.parametrize('method', ['_execute_target_continuity_handoff', '_stop_following_after_continuity_failure'])
@pytest.mark.parametrize('queued_before_start', [False, True])
async def test_old_continuity_cleanup_cannot_stop_or_record_into_a_replacement_session(method, queued_before_start):
    ctrl, _ = controller()
    ctrl._freeze_following_observation_source()
    ctrl.following_active = True
    ctrl._follower_state_lock = asyncio.Lock()
    ctrl._disconnect_px4_internal = AsyncMock(return_value={'errors': [], 'offboard_stop_action': {'executed': True}})
    original = ctrl._get_target_continuity_supervisor()
    original.record_handoff_result = Mock()
    await ctrl._follower_state_lock.acquire()
    coroutine = getattr(ctrl, method)('following_observation_source_changed')
    if not queued_before_start:
        task = asyncio.create_task(coroutine)
        await asyncio.sleep(0)
    ctrl._following_session_id = 'new-session'
    replacement = ctrl.target_continuity = SimpleNamespace(record_handoff_result=Mock())
    if queued_before_start:
        task = asyncio.create_task(coroutine)
    ctrl._follower_state_lock.release()
    await asyncio.wait_for(task, timeout=1.)
    ctrl._disconnect_px4_internal.assert_not_called()
    original.record_handoff_result.assert_not_called()
    replacement.record_handoff_result.assert_not_called()


async def test_retarget_failure_cleanup_captures_session_before_create_task_is_scheduled(monkeypatch):
    ctrl, _ = controller()
    ctrl._freeze_following_observation_source()
    ctrl.following_active = True
    ctrl._follower_state_lock = asyncio.Lock()
    supervisor = ctrl.target_continuity = SimpleNamespace(begin_target_transition=Mock(return_value=False),
        reset_session=Mock(), record_handoff_result=Mock())
    ctrl._target_transition_previous_intent = object()
    ctrl._activate_offboard_commander_failsafe_defaults = Mock()
    ctrl._disconnect_px4_internal = AsyncMock()
    tasks, create_task = [], asyncio.create_task
    def schedule(coroutine):
        task = create_task(coroutine)
        tasks.append(task)
        return task
    monkeypatch.setattr('classes.app_controller.asyncio.create_task', schedule)
    ctrl._advance_tracking_session_generation(for_retarget=True)
    ctrl._following_session_id = 'new-session'
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=1.)
    ctrl._disconnect_px4_internal.assert_not_called()
    supervisor.record_handoff_result.assert_not_called()

"""Validated native loss observations revoke the original lifecycle before publication."""

import asyncio
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from classes.aircraft_state import AircraftStateOwner, AirframePhase
from classes.airframe_session_controls import AirframeSessionControls
from classes.command_dispatch_guard import DispatchRefusalKind, DispatchRefused
from classes.command_intent import AltitudeHoldReference
from classes.gimbal_guidance import GimbalGuidancePolicy
from classes.guidance_phase_session import PhaseSessionState
from classes.native_follow_binding import NativeFollowBinding
from classes.native_guidance import NativeGuidanceClient
from classes.offboard_commander import OffboardCommander
from classes.safety_types import AltitudeLimits
from classes.target_continuity import (
    ContinuityContext,
    ContinuityPolicy,
    TargetContinuitySupervisor,
)
from classes.vector_guidance_session import VectorGuidanceSession
from tests.fixtures.native_ownership import release_receipt
from tests.unit.core_app.test_fixed_wing_continuity import evidence
from tests.unit.core_app.test_native_connection_loss_reconciliation import (
    native_application as _native_application_fixture,
)
from tests.unit.core_app.test_native_connection_loss_reconciliation import start
from tests.unit.core_app.test_native_follow_application import app as _app_fixture
from tests.unit.core_app.test_native_follow_binding import CONFIG
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tests.unit.drone_interface.test_native_guidance import identity
from tests.unit.drone_interface.test_native_guidance import (
    native_server as _native_server_fixture,
)

app = _app_fixture
native_application = _native_application_fixture
native_server = _native_server_fixture


@pytest.fixture
async def component(native_server):
    path, requests, behavior = native_server
    now = [100.]
    original = identity()
    state = aircraft_state(binding=original.binding, is_vtol=True)
    behavior["observation"] = {"aircraft_state": asdict(state)}
    client = NativeGuidanceClient(path, request_timeout_s=.15, clock=lambda: now[0])
    capabilities = await client.connect()
    await client.bind(original.binding)
    states = AircraftStateOwner(clock=lambda: now[0])
    states.bind(original.binding)
    assert states.commit(state)
    connection = SimpleNamespace(get_aircraft_state=lambda: states.snapshot(timeout_s=.75),
                                 commit_aircraft_state=states.commit)
    guidance = VectorGuidanceSession(
        original, capabilities, profile_name="gm_velocity_vector",
        controls=AirframeSessionControls.for_fixed_wing(original, step_m_s=.5),
        supported_phases=frozenset({AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING}),
        geometry_policy=GimbalGuidancePolicy().geometry, altitude_control=False,
        altitude_limits=AltitudeLimits(5., 120., 2.), confirmation_s=0.,
        observation_timeout_s=.75, initial_phase=AirframePhase.FIXED_WING, clock=lambda: now[0],
    )
    continuity = TargetContinuitySupervisor(ContinuityPolicy.from_mapping(CONFIG), clock=lambda: now[0])
    continuity.reset_session(session_epoch=1, reason="component_start")
    base = ContinuityContext("PX4_NATIVE", AirframePhase.FIXED_WING, "fixed_wing_external", True, True, True)
    binding = NativeFollowBinding(guidance, connection, client, continuity,
        profile_name="gm_velocity_vector", continuity_config=CONFIG, target_evidence=evidence,
        context=lambda: base, circuit_breaker=lambda: False, clock=lambda: now[0])
    intent = await binding.engage()
    assert guidance.phase_owner.state is PhaseSessionState.PURSUIT
    observed, failed = [], []
    original_observer = binding.on_observation

    async def record_observation(*args):
        observed.append(args)
        return await original_observer(*args)

    binding.transport.on_observation = record_observation
    commander = OffboardCommander(None, None, command_transport=binding.transport,
        command_ttl_s=2., command_failure_threshold=3, on_failure_threshold=lambda value: failed.append(value))
    try:
        yield SimpleNamespace(now=now, original=original, initial=state, client=client, binding=binding,
            guidance=guidance, connection=connection, requests=requests, behavior=behavior,
            observer_calls=observed, failure_callbacks=failed, commander=commander, intent=intent)
    finally:
        await client.close()


@pytest.mark.parametrize("fault", ["transition_owner_false", "owner_false", "rescue_true", "raw_rescue_only", "missing_state",
                                   "stale_state", "fresh_false_valid_state", "rejected_state", "expired_snapshot"])
async def test_first_loss_publish_ends_original_session_and_invokes_terminal_owner(component, monkeypatch, fault):
    c = component
    monkeypatch.setattr("classes.offboard_commander.time", SimpleNamespace(monotonic=lambda: c.now[0]))
    assert c.commander.submit_intent(c.intent)
    incoming = replace(c.initial, sequence=2)
    original_identity = c.guidance.identity
    control = c.guidance.controls.current_control
    def target_must_not_run():
        raise AssertionError("terminal loss must not wait for target evidence")
    c.binding._target_evidence = target_must_not_run
    updates = {}
    if fault == "transition_owner_false":
        incoming = replace(incoming, phase=AirframePhase.VTOL_TRANSITION)
        updates["owner_confirmed"] = False
    elif fault == "owner_false":
        updates["owner_confirmed"] = False
    elif fault == "rescue_true":
        incoming = replace(incoming, rescue_active=True)
        updates["rescue_active"] = True
    elif fault == "raw_rescue_only":
        updates["rescue_active"] = True
    elif fault == "rejected_state":
        incoming = replace(incoming, observed_at_monotonic_s=98.)
    elif fault == "missing_state":
        incoming = None
        updates.update(fresh=False, owner_confirmed=False)
    elif fault == "stale_state":
        incoming = replace(incoming, observed_at_monotonic_s=98.)
        updates.update(fresh=False, owner_confirmed=False)
    elif fault == "fresh_false_valid_state":
        updates.update(fresh=False, owner_confirmed=False)
    else:
        c.behavior["delay_operation"] = "observe"
    updates["aircraft_state"] = None if incoming is None else asdict(incoming)
    c.behavior["observation"] = updates
    before = len(c.requests)
    if fault == "expired_snapshot":
        pending = asyncio.create_task(c.commander.publish_once())
        await c.behavior["delay_started"].wait()
        c.now[0] += .8
        c.behavior["delay_release"].set()
        assert await pending is False
    else:
        assert await c.commander.publish_once() is False
    assert not any(row["operation"] == "intent" for row in c.requests[before:])
    assert len(c.observer_calls) == 1
    assert c.guidance.phase_owner.state is PhaseSessionState.ENDED
    assert c.binding.terminal_reason is not None
    assert len(c.failure_callbacks) == 1
    assert c.commander.terminal_failure
    assert c.commander.consecutive_failures < c.commander.command_failure_threshold
    assert c.guidance.controls.current_control is None
    assert c.guidance.controls.snapshot(client_contract_version=2) is None
    with pytest.raises(ValueError, match="session_control_identity_stale"):
        c.guidance.controls.update(16., identity=original_identity, expected_revision=control.revision)
    if fault == "transition_owner_false":
        assert c.connection.get_aircraft_state().phase is AirframePhase.VTOL_TRANSITION
        assert c.binding.terminal_reason == "aircraft_transition_observed"
    if fault in {"missing_state", "rejected_state", "expired_snapshot", "stale_state"}:
        assert c.observer_calls[0][0] is None


async def test_control_owner_true_transition_already_reaches_observer(component, monkeypatch):
    c = component
    monkeypatch.setattr("classes.offboard_commander.time", SimpleNamespace(monotonic=lambda: c.now[0]))
    assert c.commander.submit_intent(c.intent)
    c.behavior["observation"] = {"aircraft_state": asdict(replace(c.initial, sequence=2,
        phase=AirframePhase.VTOL_TRANSITION))}
    before = len(c.requests)
    assert await c.commander.publish_once() is False
    assert len(c.observer_calls) == 1
    assert c.binding.terminal_reason == "aircraft_transition_observed"
    assert c.connection.get_aircraft_state().phase is AirframePhase.VTOL_TRANSITION
    assert c.guidance.controls.current_control is None
    assert not any(row["operation"] == "intent" for row in c.requests[before:])
    assert c.commander.terminal_failure
    assert len(c.failure_callbacks) == 1


async def test_original_transport_does_not_abort_replacement_acquisition(component):
    c = component
    original = c.client.acquisition_context
    c.client.abort()
    c.behavior["owner_confirmed"] = False
    c.behavior["release_receipt"] = release_receipt(original).wire_payload()
    await c.client.observe_after_release(c.original, runtime_id=original.runtime_id,
        ownership_token=original.token, mode_id=original.mode_id, acquisition=original)
    await c.client.connect()
    await c.client.bind(c.original.binding)
    reference = AltitudeHoldReference(c.initial.altitude_amsl_m, c.initial.altitude_reference_generation)
    await c.client.engage(c.original, circuit_breaker_active=False, ownership_token="e" * 32,
                         altitude_reference=reference)
    replacement = c.client.acquisition_context
    c.behavior["release_receipt"] = None
    c.behavior["owner_confirmed"] = True
    c.behavior["observation"] = {"aircraft_state": asdict(replace(c.initial, sequence=2))}
    before = len(c.requests)
    def target_must_not_run():
        raise AssertionError("replacement must be fenced before target work")
    c.binding._target_evidence = target_must_not_run
    with pytest.raises(DispatchRefused, match="native_session_replaced") as refusal:
        await c.binding.transport.publish(c.intent, reason="component", ttl_s=2.)
    assert c.client.session_identity == c.original
    assert c.client.acquisition_context == replacement
    assert c.connection.get_aircraft_state() == c.initial
    assert refusal.value.kind is DispatchRefusalKind.TERMINAL
    assert len(c.observer_calls) == 1 and c.observer_calls[0][0] is None
    assert c.guidance.phase_owner.state is PhaseSessionState.ENDED
    assert c.guidance.controls.current_control is None
    assert [row["operation"] for row in c.requests[before:]] == ["observe"]


async def test_one_actual_commander_attempt_runs_existing_app_terminal_cleanup(native_application, monkeypatch):
    native = native_application
    ctrl = native.ctrl
    prepare = ctrl._prepare_native_follow_binding.side_effect

    async def immediate_confirmation():
        binding = await prepare()
        binding.guidance.phase_owner.confirmation_s = 0.
        return binding

    ctrl._prepare_native_follow_binding.side_effect = immediate_confirmation
    binding = await start(native)
    monkeypatch.setattr("classes.offboard_commander.time", SimpleNamespace(monotonic=lambda: 100.))
    assert binding.guidance.phase_owner.state is PhaseSessionState.PURSUIT
    original_identity = binding.guidance.identity
    original_control = binding.guidance.controls.current_control
    callbacks = []

    async def existing_failure_owner(status):
        callbacks.append(status)
        await ctrl._handle_offboard_commander_failure_on_flight_loop(
            dict(status, follow_session_id=original_identity.follow_session_id))

    commander = OffboardCommander(ctrl.px4_interface, ctrl.follower.follower.setpoint_handler,
        command_transport=binding.transport, command_ttl_s=2., command_failure_threshold=3,
        on_failure_threshold=existing_failure_owner, on_publish_result=ctrl._record_offboard_publish_result)
    ctrl.offboard_commander = commander
    assert commander.submit_intent(binding.guidance.baseline())
    state = binding.connection.get_aircraft_state()
    native.behavior["observation"] = {"owner_confirmed": False,
        "aircraft_state": asdict(replace(state, sequence=state.sequence + 1))}
    native.behavior["release_receipt"] = release_receipt(native.client.acquisition_context,
        outcome="owner_already_released", nav_state=5).wire_payload()
    before = len(native.requests)
    assert await commander.publish_once() is False
    assert len(callbacks) == 1 and callbacks[0]["terminal_failure"]
    assert not ctrl.following_active
    assert ctrl._native_follow_binding is None
    assert not ctrl._following_offboard_cleanup_required
    assert binding.terminal_reason == "control_owner_lost"
    assert binding.connection.get_aircraft_state().phase is AirframePhase.FIXED_WING
    assert binding.guidance.controls.current_control is None
    with pytest.raises(ValueError, match="session_control_identity_stale"):
        binding.guidance.controls.update(16., identity=original_identity, expected_revision=original_control.revision)
    assert not any(row["operation"] in {"intent", "engage", "handoff"} for row in native.requests[before:])
    ctrl.px4_interface.stop_offboard_mode.assert_not_called()


async def test_wire_timeout_does_not_invent_an_observation_or_change_generic_retry_policy(component, monkeypatch):
    c = component
    monkeypatch.setattr("classes.offboard_commander.time", SimpleNamespace(monotonic=lambda: c.now[0]))
    assert c.commander.submit_intent(c.intent)
    c.behavior["delay_operation"] = "observe"
    assert await c.commander.publish_once() is False
    assert c.observer_calls == []
    assert c.failure_callbacks == []
    assert c.commander.consecutive_failures == 1
    assert not c.commander.terminal_failure
    assert c.guidance.phase_owner.state is PhaseSessionState.PURSUIT


async def test_already_ended_guidance_uses_terminal_owner_without_target_work(component, monkeypatch):
    c = component
    monkeypatch.setattr("classes.offboard_commander.time", SimpleNamespace(monotonic=lambda: c.now[0]))
    assert c.commander.submit_intent(c.intent)
    c.guidance.end("explicit_test_end")
    def target_must_not_run():
        raise AssertionError("ended lifecycle cannot inspect target")
    c.binding._target_evidence = target_must_not_run
    assert await c.commander.publish_once() is False
    assert c.commander.terminal_failure_reason == "explicit_test_end"
    assert len(c.failure_callbacks) == 1


async def test_inflight_speed_edit_is_refused_before_terminal_failure_callback(component, monkeypatch):
    c = component
    monkeypatch.setattr("classes.offboard_commander.time", SimpleNamespace(monotonic=lambda: c.now[0]))
    identity_before = c.guidance.identity
    revision_before = c.guidance.controls.current_control.revision
    observed_loss = asyncio.Event()
    c.behavior["observation"] = {"owner_confirmed": False,
        "aircraft_state": asdict(replace(c.initial, sequence=2, phase=AirframePhase.VTOL_TRANSITION))}
    original_observer = c.binding.transport.on_observation

    async def pending_edit():
        await observed_loss.wait()
        assert c.failure_callbacks == []
        with pytest.raises(ValueError, match="session_control_identity_stale"):
            c.guidance.controls.update(16., identity=identity_before, expected_revision=revision_before)

    edit = asyncio.create_task(pending_edit())

    async def inspect_revoked_controls(*args):
        try:
            return await original_observer(*args)
        except DispatchRefused:
            observed_loss.set()
            await edit
            raise

    c.binding.transport.on_observation = inspect_revoked_controls
    assert c.commander.submit_intent(c.intent)
    assert await c.commander.publish_once() is False
    assert edit.done()
    assert len(c.failure_callbacks) == 1


async def test_replacement_between_reply_and_binding_callback_preserves_new_client(component):
    c = component
    original = c.client.acquisition_context
    original_observer = c.binding.transport.on_observation

    def target_must_not_run():
        raise AssertionError("replacement must be fenced before target work")

    c.binding._target_evidence = target_must_not_run

    async def replace_before_observer(*args):
        c.client.abort()
        c.behavior["owner_confirmed"] = False
        c.behavior["release_receipt"] = release_receipt(original).wire_payload()
        await c.client.observe_after_release(c.original, runtime_id=original.runtime_id,
            ownership_token=original.token, mode_id=original.mode_id, acquisition=original)
        await c.client.connect()
        await c.client.bind(c.original.binding)
        reference = AltitudeHoldReference(c.initial.altitude_amsl_m, c.initial.altitude_reference_generation)
        await c.client.engage(c.original, circuit_breaker_active=False, ownership_token="e" * 32,
                             altitude_reference=reference)
        c.behavior["release_receipt"] = None
        return await original_observer(*args)

    c.binding.transport.on_observation = replace_before_observer
    with pytest.raises(DispatchRefused, match="native_session_replaced"):
        await c.binding.transport.publish(c.intent, reason="component", ttl_s=2.)
    assert c.client.acquisition_context.token == "e" * 32
    assert c.client.session_identity == c.original
    assert c.guidance.phase_owner.state is PhaseSessionState.ENDED
    assert c.guidance.controls.current_control is None

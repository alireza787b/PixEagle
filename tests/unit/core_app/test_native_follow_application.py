"""Application lifecycle chooses one publisher; native mode never uses MAVSDK Stop."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from classes.aircraft_state import AircraftKind
from tests.fixtures.native_ownership import release_receipt
from classes.app_controller import AppController
from classes.parameters import Parameters
from tests.fixtures.following_observation import bind_image_source
from classes.follower import FollowerFactory
from classes.api_v1_following_controls import session_control_snapshot
from classes.api_v1_contracts import APITargetContinuityStatus
from classes.api_v1_contracts import APIFollowingTelemetryResponse
from classes.api_v1_snapshots import get_following_telemetry_snapshot
from tests.unit.core_app.test_app_controller_offboard_safety import _follower_manager_stub
from tests.unit.core_app.test_native_follow_binding import fixture, CONFIG


@pytest.fixture
def app(monkeypatch):
    f = fixture(is_vtol=False)
    ctrl = object.__new__(AppController)
    ctrl._follower_state_lock = asyncio.Lock()
    ctrl.following_active = False
    ctrl.follower = ctrl.offboard_commander = ctrl.setpoint_sender = None
    ctrl.tracker = SimpleNamespace(normalized_center=(.5, .5))
    bind_image_source(ctrl)
    ctrl.telemetry_handler = SimpleNamespace(follower=None)
    ctrl._apply_pending_follower_config = AsyncMock(return_value={"applied_count": 0})
    ctrl._get_follow_start_readiness = Mock(return_value={"usable_for_following": True})
    ctrl._ensure_continuity_watchdog = Mock()
    ctrl._native_follow_binding = None
    ctrl.px4_interface = SimpleNamespace(
        current_yaw=0., current_altitude=50., active_mode=True,
        connect=AsyncMock(return_value={"connected": True}),
        wait_for_telemetry_ready=AsyncMock(return_value={"ready": True, "source": "fixture"}),
        get_connection_status=Mock(return_value={"connected": True}),
        get_aircraft_kind=Mock(return_value=AircraftKind.FIXED_WING),
        prepare_native_guidance=AsyncMock(return_value=f.guidance.phase_owner.capabilities),
        get_aircraft_state=Mock(return_value=f.state),
        get_telemetry_stale_timeout_s=Mock(return_value=.75),
        get_aircraft_identity=Mock(return_value={"autopilot_uid": f.state.binding.aircraft_uid,
                                                "connection_generation": f.state.binding.connection_generation}),
        native_start_context=f.start_context, native_guidance_client=f.client,
        is_command_connection_ready=Mock(return_value=True),
        start_offboard_mode=AsyncMock(), stop_offboard_mode=AsyncMock(),
    )
    manager = _follower_manager_stub()
    manager.mode = "gm_velocity_vector"
    manager.follower.profile_name = "gm_velocity_vector"
    ctrl.px4_interface.setpoint_handler = manager.follower.setpoint_handler
    factory = Mock(return_value=manager)
    factory.get_mode_info.return_value = FollowerFactory.get_follower_info("gm_velocity_vector")
    commander = SimpleNamespace(
        setpoint_handler=manager.follower.setpoint_handler,
        submit_intent=Mock(return_value=True), start=AsyncMock(return_value=True),
        stop=AsyncMock(return_value=True), get_status=Mock(return_value={"running": True}),
    )
    commander_factory = Mock(return_value=commander)

    async def prepare(start_context):
        assert start_context is f.start_context
        f.binding.continuity = ctrl.target_continuity
        f.binding._context = ctrl._build_target_continuity_context
        ctrl._following_session_id = f.guidance.identity.follow_session_id
        ctrl._native_follow_binding = f.binding
        return f.binding

    ctrl._prepare_native_follow_binding = AsyncMock(side_effect=prepare)
    monkeypatch.setattr(Parameters, "FOLLOWER_EXECUTION_MODE", "PX4")
    monkeypatch.setattr(Parameters, "FOLLOWER_CIRCUIT_BREAKER", False)
    monkeypatch.setattr(Parameters, "FOLLOWER_MODE", "gm_velocity_vector")
    monkeypatch.setattr(Parameters, "TARGET_POSITION_MODE", "initial")
    monkeypatch.setattr(Parameters, "TargetContinuity", CONFIG, raising=False)
    monkeypatch.setattr("classes.app_controller.Follower", factory)
    monkeypatch.setattr("classes.app_controller.OffboardCommander", commander_factory)
    return SimpleNamespace(ctrl=ctrl, f=f, manager=manager, commander=commander,
                           commander_factory=commander_factory, follower_factory=factory)


async def test_native_session_seeds_one_publisher_and_preserves_its_phase_controls(app):
    ctrl = app.ctrl
    result = await ctrl._connect_px4_on_flight_loop()
    assert result["errors"] == []
    assert ctrl.following_active
    ctrl.px4_interface.prepare_native_guidance.assert_awaited_once()
    ctrl.px4_interface.start_offboard_mode.assert_not_called()
    app.commander_factory.assert_called_once()
    assert app.commander_factory.call_args.kwargs["command_transport"] is app.f.binding.transport
    seed = app.commander.submit_intent.call_args.args[0]
    assert seed.control_type == "fixed_wing_external"
    assert seed.guidance_identity.follow_session_id == ctrl._following_session_id
    app.manager.follower.bind_airframe_session.assert_called_once_with(app.f.guidance)
    app.manager.follower.reset_control_session.assert_not_called()
    assert ctrl._build_target_continuity_context().guidance_identity == app.f.guidance.identity
    continuity = APITargetContinuityStatus.model_validate(ctrl.get_target_continuity_status())
    assert continuity.policy_mode == "bounded_flight"
    assert continuity.configuration_origin.startswith("phase_override:fixed_wing/")
    assert continuity.effective_policy["max_coast_time_s"] == 8.


async def test_start_does_not_refresh_away_the_original_native_phase_mismatch(app):
    from dataclasses import replace
    from classes.aircraft_state import AirframePhase
    ctrl = app.ctrl
    ctrl.px4_interface.get_aircraft_state.return_value = replace(app.f.state, phase=AirframePhase.MULTICOPTER)
    async def refresh(_socket):
        ctrl.px4_interface.get_aircraft_state.return_value = app.f.state
        return app.f.guidance.phase_owner.capabilities
    ctrl.px4_interface.prepare_native_guidance.side_effect = refresh
    result = await ctrl._connect_px4_on_flight_loop()
    assert result['precondition']['code'] == 'native_start_context_changed'
    assert not ctrl.following_active
    ctrl.px4_interface.prepare_native_guidance.assert_not_awaited()
    ctrl._prepare_native_follow_binding.assert_not_called()
    app.f.client.engage.assert_not_called()


async def test_passive_poll_queued_during_real_start_does_not_observe_active_publisher(app):
    ctrl = app.ctrl;ctrl._flight_event_loop = asyncio.get_running_loop()
    entered, release = asyncio.Event(), asyncio.Event()
    async def refresh(_socket):
        entered.set();await release.wait()
        return app.f.guidance.phase_owner.capabilities
    ctrl.px4_interface.prepare_native_guidance.side_effect = refresh
    startup = asyncio.create_task(ctrl._connect_px4_on_flight_loop())
    await entered.wait()
    poll = asyncio.create_task(ctrl.refresh_native_following_state('gm_velocity_vector'))
    await asyncio.sleep(0)
    assert not poll.done()
    release.set()
    result = await startup;await poll
    assert result['errors'] == [] and ctrl.following_active
    ctrl.px4_interface.prepare_native_guidance.assert_awaited_once()
    assert ctrl._native_follow_binding is app.f.binding


async def test_ordinary_mc_vector_retains_existing_mavsdk_owner(app):
    ctrl = app.ctrl
    ctrl.px4_interface.get_aircraft_kind.return_value = AircraftKind.MULTICOPTER
    ctrl.px4_interface.start_offboard_mode.return_value = {"executed": True, "errors": []}
    result = await ctrl._connect_px4_on_flight_loop()
    assert result["errors"] == []
    ctrl._prepare_native_follow_binding.assert_not_called()
    ctrl.px4_interface.start_offboard_mode.assert_awaited_once()
    assert app.commander_factory.call_args.kwargs["command_transport"] is None
    app.manager.follower.reset_control_session.assert_called_once()


async def test_unknown_aircraft_cannot_start_mc_commands_on_a_possible_vtol(app):
    ctrl = app.ctrl
    ctrl.px4_interface.get_aircraft_kind.return_value = AircraftKind.UNKNOWN
    result = await ctrl._connect_px4_on_flight_loop()
    assert not ctrl.following_active
    assert any("aircraft_kind_unavailable" in error for error in result["errors"])
    ctrl.px4_interface.start_offboard_mode.assert_not_called()
    ctrl.px4_interface.stop_offboard_mode.assert_not_called()
    ctrl._prepare_native_follow_binding.assert_not_called()


async def test_read_only_native_preparation_failure_cannot_send_mavsdk_hold(app):
    ctrl = app.ctrl
    ctrl._prepare_native_follow_binding.side_effect = RuntimeError("native_adapter_missing")
    result = await ctrl._connect_px4_on_flight_loop()
    assert not ctrl.following_active
    assert any("native_adapter_missing" in error for error in result["errors"])
    ctrl.px4_interface.start_offboard_mode.assert_not_called()
    ctrl.px4_interface.stop_offboard_mode.assert_not_called()
    app.f.client.engage.assert_not_called()


@pytest.mark.parametrize("phase", ["multicopter", "fixed_wing"])
@pytest.mark.parametrize("mc_supported", [False, True])
async def test_native_preparation_uses_declared_mc_capability_before_acquisition(app, monkeypatch, phase, mc_supported):
    from dataclasses import replace

    from classes.aircraft_state import AirframePhase

    ctrl = app.ctrl
    state = replace(app.f.state, phase=AirframePhase(phase), is_vtol=True, is_tailsitter=True)
    capabilities = replace(app.f.guidance.phase_owner.capabilities, multicopter_supported=mc_supported)
    ctrl.px4_interface.prepare_native_guidance = AsyncMock(return_value=capabilities)
    ctrl.px4_interface.get_aircraft_state = Mock(return_value=state)
    ctrl.px4_interface.get_telemetry_stale_timeout_s = Mock(return_value=.75)
    ctrl.px4_interface.native_guidance_client = app.f.client
    app.f.client.capabilities = capabilities
    ctrl._following_session_id = "prepared-session"
    ctrl._following_continuity_config = CONFIG
    create = Mock(return_value=app.f.guidance)
    ctrl.follower = SimpleNamespace(follower=SimpleNamespace(
        profile_name="gm_velocity_vector", create_airframe_session=create,
        setpoint_handler=SimpleNamespace(profile_config={"native_phase_contracts": {
            "multicopter": "velocity_body_offboard", "fixed_wing": "fixed_wing_external"}})))
    binding = Mock()
    construct = Mock(return_value=binding)
    monkeypatch.setattr("classes.app_controller.NativeFollowBinding", construct)
    monkeypatch.setattr(Parameters, "AIRFRAME_LAYOUT", "AUTO", raising=False)
    if mc_supported:
        from tests.fixtures.native_ownership import start_context
        original = start_context(app.f.guidance.identity, runtime_id=capabilities.runtime_id, phase=state.phase.value)
        assert await AppController._prepare_native_follow_binding(ctrl, original) is binding
        assert create.call_args.kwargs["initial_phase"] is state.phase
        construct.assert_called_once()
    else:
        with pytest.raises(RuntimeError, match="native_vtol_contract_unavailable"):
            await AppController._prepare_native_follow_binding(ctrl, app.f.start_context)
        create.assert_not_called()
        construct.assert_not_called()
    app.f.client.engage.assert_not_called()
    ctrl.px4_interface.prepare_native_guidance.assert_not_awaited()
    ctrl.px4_interface.start_offboard_mode.assert_not_called()


async def test_native_stop_joins_publisher_before_native_handoff(app):
    ctrl = app.ctrl
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    order = []

    async def publisher_stop(**_):
        order.append("publisher")
        return True

    app.commander.stop.side_effect = publisher_stop

    async def handoff(*_, **__):
        order.append("handoff")
        return release_receipt(app.f.client.acquisition_context)

    app.f.client.handoff.side_effect = handoff
    result = await ctrl._disconnect_px4_internal()
    assert result["errors"] == []
    assert order == ["publisher", "handoff"]
    assert result["offboard_stop_action"]["executed"]
    assert ctrl._native_follow_binding is None
    assert not ctrl.following_active
    app.commander.stop.assert_awaited_once_with(publish_final=False)
    ctrl.px4_interface.stop_offboard_mode.assert_not_called()


async def test_operator_stop_retains_observed_hold_after_immediate_native_abort(app):
    ctrl = app.ctrl
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    app.commander.activate_failsafe_defaults = Mock(side_effect=lambda _: app.f.client.abort())
    app.f.client.observe_after_release.return_value = release_receipt(app.f.client.acquisition_context)
    result = await ctrl.stop_native_following(ctrl._following_session_id, ctrl._following_session_aircraft_uid)
    assert not result["errors"]
    assert result["offboard_stop_action"]["executed"]
    assert ctrl._last_following_handoff["result"] == "confirmed_hold"
    app.f.client.handoff.assert_not_called()
    ctrl.px4_interface.stop_offboard_mode.assert_not_called()


async def test_native_start_cancellation_cleans_owner_without_mavsdk_stop(app):
    ctrl = app.ctrl
    app.commander.start.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await ctrl._connect_px4_on_flight_loop()
    assert not ctrl.following_active
    app.f.client.handoff.assert_awaited_once()
    ctrl.px4_interface.stop_offboard_mode.assert_not_called()
    assert ctrl._native_follow_binding is None


async def test_delayed_mavlink_offboard_exit_does_not_revoke_native_mode(app):
    ctrl = app.ctrl
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    await ctrl._handle_offboard_mode_exit_on_flight_loop(393216, 12345)
    assert ctrl.following_active
    app.commander.stop.assert_not_called()
    app.f.client.handoff.assert_not_called()


async def test_handoff_failure_retains_cleanup_owner_and_blocks_a_new_start(app):
    ctrl = app.ctrl
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    app.f.client.handoff.side_effect = RuntimeError("handoff_timeout")
    result = await ctrl._disconnect_px4_internal()
    assert result["errors"]
    assert ctrl._native_follow_binding is app.f.binding
    assert ctrl._following_offboard_cleanup_required
    next_start = await ctrl._connect_px4_on_flight_loop()
    assert next_start["precondition"]["code"] == "following_stop_pending"
    assert app.f.client.engage.await_count == 1
    ctrl.px4_interface.stop_offboard_mode.assert_not_called()


async def test_native_speed_controls_use_native_authority_instead_of_mavlink_offboard(app):
    ctrl = app.ctrl
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    ctrl.get_target_continuity_status = Mock(return_value={"authority_state": "ACTIVE"})
    ctrl.mavlink_data_manager = SimpleNamespace(get_flight_state=Mock(return_value={"flight_mode": 999}),
                                               offboard_mode_code=393216)
    app.manager.follower.session_controls.side_effect = lambda: [
        app.f.guidance.controls.snapshot(client_contract_version=2),
    ]
    app.manager.follower._submitted_command_fields = None
    app.manager.follower._vertical_limit_status = None
    principal = SimpleNamespace(scopes={"actions:execute"})
    pending = session_control_snapshot(ctrl, principal, client_contract_version=2)
    assert pending[0]["reason_code"] == "phase_confirmation_pending"
    assert not pending[0]["available"]
    for _ in range(4):
        await app.f.observation()
    active = session_control_snapshot(ctrl, principal, client_contract_version=2)
    assert active[0]["available"]
    assert active[0]["speed_basis"] == "equivalent_airspeed"
    assert active[0]["minimum"] > 0.
    ctrl.mavlink_data_manager.get_flight_state.assert_not_called()
    assert session_control_snapshot(ctrl, principal, client_contract_version=1) == []
    app.f.client.session_identity = None
    unavailable = session_control_snapshot(ctrl, principal, client_contract_version=2)
    assert not unavailable[0]["available"]


async def test_native_terminal_reason_survives_concurrent_publisher_cleanup(app):
    ctrl = app.ctrl
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    app.f.binding.abort("control_owner_lost")
    await ctrl._handle_offboard_commander_failure_on_flight_loop({"failure_policy_reason": "publish failure"})
    assert ctrl._last_following_handoff["reason_code"] == "control_owner_lost"
    app.f.client.handoff.assert_not_called()
    ctrl.px4_interface.stop_offboard_mode.assert_not_called()


async def test_pending_config_cannot_bypass_live_profile_qualification(app, monkeypatch):
    factory = app.follower_factory
    current = factory.get_mode_info.return_value
    factory.get_mode_info.side_effect = lambda mode: (FollowerFactory.get_follower_info("fw_attitude_rate")
                                                     if mode == "fw_attitude_rate" else current)

    async def apply():
        monkeypatch.setattr(Parameters, "FOLLOWER_MODE", "fw_attitude_rate")
        return {"applied_count": 1}

    app.ctrl._apply_pending_follower_config.side_effect = apply
    result = await app.ctrl._connect_px4_on_flight_loop()
    assert result["precondition"]["code"] == "continuity_profile_not_live_qualified"
    app.ctrl.px4_interface.connect.assert_not_called()
    app.ctrl.px4_interface.start_offboard_mode.assert_not_called()
    factory.assert_not_called()


async def test_native_api_reports_published_fw_contract_and_never_falls_back_to_old_mc_fields(app):
    ctrl = app.ctrl
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    intent = app.f.guidance.baseline()
    app.commander.get_published_intent = Mock(return_value=intent)
    status = app.commander.get_status.return_value
    status.update(dynamic_command_contract=True, sends_mavsdk_commands=False,
                  successful_publishes=3, observed_native_publications=None,
                  command_publication_source="px4_native_external_mode")
    app.manager.get_control_type.return_value = intent.control_type
    app.manager.get_available_fields.return_value = list(intent.fields)
    app.manager.follower.setpoint_handler.get_fields.return_value = {"vel_body_fwd": 0.}
    owner = SimpleNamespace(app_controller=ctrl, telemetry_handler=SimpleNamespace(latest_follower_data={
        "last_command_intent": {"fields": {"vel_body_fwd": 6.}}, "setpoints": {"vel_body_fwd": 6.},
    }))
    snapshot = get_following_telemetry_snapshot(owner)
    parsed = APIFollowingTelemetryResponse.model_validate(snapshot)
    assert parsed.fields == intent.fields
    assert parsed.field_source == "command_publication"
    assert parsed.last_command_intent["control_type"] == "fixed_wing_external"
    assert parsed.last_command_intent["guidance_identity"]["guidance_generation"] == intent.guidance_identity.guidance_generation
    assert not parsed.commands_sent_to_px4
    status["observed_native_publications"] = 3
    assert get_following_telemetry_snapshot(owner)["commands_sent_to_px4"] is True
    app.commander.get_published_intent.return_value = None
    retired = get_following_telemetry_snapshot(owner)
    assert retired["fields"] == {}
    assert retired["field_source"] == "unavailable"
    assert retired["last_command_intent"] is None


@pytest.mark.parametrize("kind,reason", [
    (AircraftKind.UNKNOWN, "aircraft_kind_unavailable"),
    (AircraftKind.VTOL, "vtol_transition_release_unqualified"),
])
@pytest.mark.parametrize("typed", [False, True])
async def test_live_owner_admission_is_shared_by_typed_and_legacy_start(app, kind, reason, typed):
    app.ctrl.px4_interface.get_aircraft_kind.return_value = kind
    guard = Mock() if typed else None
    result = await app.ctrl._connect_px4_on_flight_loop(native_start_guard=guard)
    assert result['precondition']['code'] == reason
    assert not app.ctrl.following_active
    app.follower_factory.assert_not_called()
    app.ctrl.px4_interface.start_offboard_mode.assert_not_called()
    app.ctrl._prepare_native_follow_binding.assert_not_called()
    app.commander_factory.assert_not_called()


async def test_aircraft_admission_is_rechecked_after_native_discovery(app):
    app.ctrl.px4_interface.get_aircraft_kind.side_effect = [
        AircraftKind.FIXED_WING, AircraftKind.FIXED_WING, AircraftKind.VTOL,
    ]
    result = await app.ctrl._connect_px4_on_flight_loop()
    assert result['precondition']['code'] == 'vtol_transition_release_unqualified'
    assert not app.ctrl.following_active
    app.f.client.engage.assert_not_called()
    app.ctrl.px4_interface.start_offboard_mode.assert_not_called()
    app.commander_factory.assert_not_called()


async def test_correlated_pilot_release_clears_cleanup_barrier_without_claiming_hold(app):
    ctrl = app.ctrl
    assert not (await ctrl._connect_px4_on_flight_loop())['errors']
    app.f.client.handoff.return_value = release_receipt(
        app.f.client.acquisition_context, outcome='owner_already_released', nav_state=5)
    outcome = await ctrl._disconnect_px4_internal()
    assert outcome['errors'] == []
    assert outcome['offboard_stop_action']['local_sender_quiesced']
    assert outcome['offboard_stop_action']['executed'] is False
    assert ctrl._native_follow_binding is None
    assert not ctrl._following_offboard_cleanup_required
    assert not ctrl.following_active
    assert (getattr(ctrl, '_last_following_handoff', None) or {}).get('result') != 'confirmed_hold'
    fresh = fixture(is_vtol=False)

    async def prepare_fresh(start_context):
        assert start_context is ctrl.px4_interface.native_start_context
        fresh.binding.continuity = ctrl.target_continuity
        fresh.binding._context = ctrl._build_target_continuity_context
        ctrl._following_session_id = fresh.guidance.identity.follow_session_id
        ctrl._native_follow_binding = fresh.binding
        return fresh.binding

    ctrl._prepare_native_follow_binding.side_effect = prepare_fresh
    result = await ctrl._connect_px4_on_flight_loop()
    assert result['errors'] == []
    assert ctrl.following_active
    assert fresh.client.engage.await_count == 1
    assert app.f.client.handoff.await_count == 1
    ctrl.px4_interface.stop_offboard_mode.assert_not_called()


@pytest.mark.parametrize("outcome", ["hold_confirmed", "owner_already_released"])
async def test_continuity_cleanup_confirms_identity_bound_release_even_without_hold(app, outcome):
    ctrl = app.ctrl
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    supervisor = ctrl.target_continuity
    supervisor.record_handoff_result = Mock()
    app.f.client.handoff.return_value = release_receipt(
        app.f.client.acquisition_context, outcome=outcome, nav_state=5 if outcome == "owner_already_released" else 4)
    await ctrl._execute_target_continuity_handoff("aircraft_transition_observed")
    supervisor.record_handoff_result.assert_called_once_with(success=True, detail="native_owner_released")
    assert ctrl._native_follow_binding is None
    assert app.f.binding.release_receipt.released
    ctrl.px4_interface.stop_offboard_mode.assert_not_called()


@pytest.mark.parametrize("invalid", ["bare_boolean", "unquiesced", "wrong_identity"])
async def test_continuity_cleanup_does_not_trust_unbound_release_flags(app, invalid):
    ctrl = app.ctrl
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    supervisor = ctrl.target_continuity
    supervisor.record_handoff_result = Mock()
    acquisition = app.f.client.acquisition_context
    if invalid != "bare_boolean":
        from dataclasses import replace
        app.f.binding._release_receipt = release_receipt(
            replace(acquisition, token="e" * 32) if invalid == "wrong_identity" else acquisition)
    if invalid != "wrong_identity":
        app.f.binding.stop = AsyncMock(return_value={"errors": [], "executed": False,
            "local_sender_quiesced": invalid != "unquiesced", "released": True})
    await ctrl._execute_target_continuity_handoff("aircraft_transition_observed")
    assert supervisor.record_handoff_result.call_args.kwargs["success"] is False


async def test_continuity_cleanup_captures_original_binding_before_await(app):
    ctrl = app.ctrl
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    supervisor = ctrl.target_continuity
    supervisor.record_handoff_result = Mock()
    cleanup = ctrl._execute_target_continuity_handoff("aircraft_phase_changed")
    # Teardown clears the App field; the original binding's validated receipt survives.
    app.f.client.handoff.return_value = release_receipt(
        app.f.client.acquisition_context, outcome="owner_already_released", nav_state=5)
    await cleanup
    assert ctrl._native_follow_binding is None
    assert supervisor.record_handoff_result.call_args.kwargs["success"] is True


async def test_smart_failed_selection_uses_the_same_native_release_completion(app):
    import threading
    ctrl = app.ctrl
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    ctrl.smart_mode_active = True
    ctrl._tracker_model_state_lock = threading.RLock()
    ctrl.smart_tracker = SimpleNamespace(get_selection_snapshot_status=lambda: {"available": True})
    ctrl._prepare_following_target_transition = Mock(return_value={
        "prepared": True, "bounded_transition_applied": True, "execution_mode": "PX4"})
    ctrl._handle_smart_click_locked = Mock(return_value={"success": False, "reason": "no_target"})
    supervisor = ctrl.target_continuity
    supervisor.record_handoff_result = Mock()
    app.f.client.handoff.return_value = release_receipt(
        app.f.client.acquisition_context, outcome="owner_already_released", nav_state=5)
    result = await ctrl._select_smart_target_on_flight_loop(1, 2)
    assert not result["success"]
    assert not result["following_stop"]["errors"]
    supervisor.record_handoff_result.assert_called_once_with(success=True, detail="native_owner_released")


@pytest.mark.parametrize("replacement", ["new_session", "new_supervisor"])
async def test_delayed_teardown_does_not_record_into_a_replacement_owner(app, replacement):
    ctrl = app.ctrl
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    original = ctrl.target_continuity
    original.record_handoff_result = Mock()
    entered, resume = asyncio.Event(), asyncio.Event()
    teardown = ctrl._disconnect_px4_teardown

    async def delayed(**kwargs):
        entered.set()
        await resume.wait()
        result = await teardown(**kwargs)
        if replacement == "new_session":
            ctrl._following_session_id = "replacement-session"
        return result

    ctrl._disconnect_px4_teardown = delayed
    task = asyncio.create_task(ctrl._execute_target_continuity_handoff("aircraft_phase_changed"))
    await entered.wait()
    if replacement == "new_session":
        ctrl._following_session_id = "replacement-session"
    else:
        ctrl.target_continuity = Mock()
    resume.set()
    await task
    original.record_handoff_result.assert_not_called()
    if replacement == "new_supervisor":
        ctrl.target_continuity.record_handoff_result.assert_not_called()


async def test_repeated_continuity_stop_records_one_original_completion(app):
    ctrl = app.ctrl
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    supervisor = ctrl.target_continuity
    supervisor.record_handoff_result = Mock()
    entered, resume = asyncio.Event(), asyncio.Event()

    async def delayed_stop(**_):
        entered.set()
        await resume.wait()
        return True

    app.commander.stop.side_effect = delayed_stop
    first = asyncio.create_task(ctrl._execute_target_continuity_handoff("aircraft_transition_observed"))
    await entered.wait()
    second = asyncio.create_task(ctrl._execute_target_continuity_handoff("aircraft_transition_observed"))
    resume.set()
    await asyncio.gather(first, second)
    supervisor.record_handoff_result.assert_called_once_with(success=True, detail="native_owner_released")
    app.f.client.handoff.assert_awaited_once()

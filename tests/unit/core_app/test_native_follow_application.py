"""Application lifecycle chooses one publisher; native mode never uses MAVSDK Stop."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from classes.aircraft_state import AircraftKind
from classes.app_controller import AppController
from classes.parameters import Parameters
from classes.api_v1_following_controls import session_control_snapshot
from classes.api_v1_contracts import APITargetContinuityStatus
from classes.api_v1_contracts import APIFollowingTelemetryResponse
from classes.api_v1_snapshots import get_following_telemetry_snapshot
from tests.unit.core_app.test_app_controller_offboard_safety import _follower_manager_stub
from tests.unit.core_app.test_native_follow_binding import fixture, CONFIG


@pytest.fixture
def app(monkeypatch):
    f = fixture()
    ctrl = object.__new__(AppController)
    ctrl._follower_state_lock = asyncio.Lock()
    ctrl.following_active = False
    ctrl.follower = ctrl.offboard_commander = ctrl.setpoint_sender = None
    ctrl.tracker = SimpleNamespace(normalized_center=(.5, .5))
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
        get_aircraft_kind=Mock(return_value=AircraftKind.VTOL),
        get_aircraft_identity=Mock(return_value={"autopilot_uid": f.state.binding.aircraft_uid,
                                                "connection_generation": f.state.binding.connection_generation}),
        is_command_connection_ready=Mock(return_value=True),
        start_offboard_mode=AsyncMock(), stop_offboard_mode=AsyncMock(),
    )
    manager = _follower_manager_stub()
    manager.mode = "gm_velocity_vector"
    manager.follower.profile_name = "gm_velocity_vector"
    ctrl.px4_interface.setpoint_handler = manager.follower.setpoint_handler
    factory = Mock(return_value=manager)
    factory.get_mode_info.return_value = {
        "airframe_phase": "multicopter",
        "native_phase_contracts": {"multicopter": "velocity_body_offboard",
                                   "fixed_wing": "fixed_wing_external", "vtol_transition": "vtol_transition_external"},
    }
    commander = SimpleNamespace(
        setpoint_handler=manager.follower.setpoint_handler,
        submit_intent=Mock(return_value=True), start=AsyncMock(return_value=True),
        stop=AsyncMock(return_value=True), get_status=Mock(return_value={"running": True}),
    )
    commander_factory = Mock(return_value=commander)

    async def prepare():
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
        return {"hold_observed": True}

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
    app.f.client.observe_after_release.return_value = {"nav_state": 4, "rescue_active": False}
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
    factory.get_mode_info.side_effect = lambda mode: ({"airframe_phase": "fixed_wing"}
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

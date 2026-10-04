"""Native follower inventory remains tied to the selected target and aircraft."""

from types import SimpleNamespace
import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Response
from fastapi.responses import JSONResponse

from classes.api_security_types import APIPrincipal
from classes.app_controller import AppController
from classes.api_v1_contracts import (APINativeFollowStartRequest, APINativeFollowStopRequest,
                                      APINativeFollowerSelectRequest)
from classes.api_v1_native_following import (following_snapshot, get_native_following,
                                             native_follow_action, native_follower_select)
from classes.parameters import Parameters
from classes.runtime_identity import INSTANCE_ID, RUNTIME_ID
from tests.unit.core_app.test_native_target_operations import owner as target_owner
from tests.unit.core_app.test_native_target_operations import execute, publish, start_request


pytestmark = pytest.mark.unit


@pytest.fixture
def owner(target_owner, monkeypatch):
    owner = target_owner
    owner.flight_test = {"fresh": True, "arm_status": "Armed",
                         "landed_state": "MAV_LANDED_STATE_IN_AIR"}
    owner.app_controller.mavlink_data_manager.get_flight_state = lambda: {
        **owner.flight_test,
        "connection_generation": owner.telemetry_test["connection_generation"],
        "autopilot_uid": owner.telemetry_test["autopilot_uid"],
    }
    monkeypatch.setattr(Parameters, "FOLLOWER_MODE", "mc_velocity_position")
    owner._get_following_status_snapshot = lambda: {
        "execution_mode": "PX4", "following_active": owner.app_controller.following_active,
        "status": "active" if owner.app_controller.following_active else "inactive",
        "profile": {"current_mode": "mc_velocity_position"},
    }
    owner._api_v1_error_response = lambda **kwargs: JSONResponse(
        status_code=kwargs["status_code"], content={"code": kwargs["code"]},
    )
    owner.app_controller.px4_interface.get_connection_status = Mock(return_value={"connected": False})
    return owner


def test_normal_modes_are_advertised_without_an_aircraft_or_start_permission(owner):
    owner.principal_test = APIPrincipal.bearer(
        subject="viewer", token_id="viewer", scopes={"status:read", "telemetry:read"},
    )
    result = following_snapshot(owner, owner.principal_test)
    assert not result["start_allowed"]
    assert "aircraft_not_verified" in result["start_reason_codes"]
    assert "following_permission_required" in result["start_reason_codes"]
    assert result["configured_mode"] == "mc_velocity_position"
    assert result["activation_pending"] is False
    assert {row["mode"] for row in result["profiles"] if row["compatible"]} == {
        "mc_velocity_chase", "mc_velocity_ground", "mc_velocity_distance",
        "mc_velocity_position", "mc_attitude_rate",
    }
    owner.app_controller.px4_interface.connect.assert_not_called()


def test_following_snapshot_reports_continuity_authority_without_claiming_handoff(owner):
    owner.app_controller.following_active = True
    owner.app_controller.get_target_continuity_status = Mock(
        return_value={"authority_state": "COASTING", "target_transition_pending": True}
    )
    result = following_snapshot(owner, owner.principal_test)
    assert result["following_active"] is True
    assert result["continuity_authority_state"] == "COASTING"
    assert result["continuity_target_transition_pending"] is True
    owner.app_controller.get_target_continuity_status.return_value = {
        "authority_state": "unrecognized"
    }
    assert following_snapshot(owner, owner.principal_test)["continuity_authority_state"] == "UNKNOWN"
    assert following_snapshot(owner, owner.principal_test)["continuity_target_transition_pending"] is False


def test_native_following_retains_identity_bound_handoff_after_session_stops(owner):
    owner.app_controller._last_following_handoff = {
        "follow_session_id": "ended-session", "aircraft_uid": "42",
        "reason_code": "maximum_coast_time_reached", "result": "confirmed_hold", "execution_mode": "PX4",
    }
    owner.app_controller.following_active = False
    snapshot = following_snapshot(owner, owner.principal_test)
    assert snapshot["last_handoff"] == owner.app_controller._last_following_handoff
    assert snapshot["following_active"] is False
    assert snapshot["continuity_authority_state"] == "UNKNOWN"


def test_failed_px4_teardown_advertises_owned_stop_retry(owner):
    app = owner.app_controller
    app._last_following_handoff = {
        "follow_session_id": "failed-session", "aircraft_uid": "42",
        "reason_code": "operator_stop", "result": "failed", "execution_mode": "PX4",
    }
    app._following_teardown_context = {
        "follow_session_id": "failed-session", "aircraft_uid": "42",
        "connection_generation": owner.telemetry_test["connection_generation"],
        "reason_code": "operator_stop", "execution_mode": "PX4",
    }
    owner.command_test.update(connected=True, autopilot_uid="42")
    owner.telemetry_test.update(connected=True, fresh=True, autopilot_uid="42", system_id=7, component_id=1)
    result = following_snapshot(owner, owner.principal_test)
    assert result["stop_allowed"] is True
    assert result["follow_session_id"] == "failed-session"
    assert result["follow_aircraft_uid"] == "42"


def test_verified_current_target_and_preflight_are_required(owner, monkeypatch):
    owner.command_test.update(connected=True, autopilot_uid="42")
    owner.telemetry_test.update(connected=True, fresh=True, autopilot_uid="42", system_id=7, component_id=1)
    owner.app_controller.tracking_started = True
    monkeypatch.setattr("classes.api_v1_native_following.get_offboard_start_preflight",
                        lambda _: {"ready": True, "issues": []})
    result = following_snapshot(owner, owner.principal_test)
    assert result["start_allowed"]
    assert result["start_reason_codes"] == []
    owner.telemetry_test["connection_generation"] = "other-vehicle"
    owner.telemetry_test["autopilot_uid"] = "99"
    result = following_snapshot(owner, owner.principal_test)
    assert not result["start_allowed"]
    assert "aircraft_not_verified" in result["start_reason_codes"]
    owner.telemetry_test["autopilot_uid"] = "42"
    owner.app_controller.tracking_started = False
    result = following_snapshot(owner, owner.principal_test)
    assert "target_not_tracking" in result["start_reason_codes"]


@pytest.mark.parametrize(("flight", "reason"), [
    ({"arm_status": "Disarmed"}, "vehicle_not_armed"),
    ({"landed_state": "MAV_LANDED_STATE_ON_GROUND"}, "vehicle_not_airborne"),
    ({"fresh": False}, "vehicle_flight_state_unavailable"),
    ({"arm_status": "Unknown"}, "vehicle_flight_state_unavailable"),
    ({"landed_state": None}, "vehicle_flight_state_unavailable"),
])
def test_native_start_requires_fresh_airborne_vehicle(owner, monkeypatch, flight, reason):
    owner.command_test.update(connected=True, autopilot_uid="42")
    owner.telemetry_test.update(connected=True, fresh=True, autopilot_uid="42", system_id=7, component_id=1)
    owner.app_controller.tracking_started = True
    owner.flight_test.update(flight)
    monkeypatch.setattr("classes.api_v1_native_following.get_offboard_start_preflight",
                        lambda _: {"ready": True, "issues": []})

    snapshot = following_snapshot(owner, owner.principal_test)
    assert not snapshot["start_allowed"]
    assert reason in snapshot["start_reason_codes"]


def test_external_tracker_offers_only_compatible_gimbal_profiles(owner, monkeypatch):
    owner.app_controller.tracker.is_external_tracker = True
    owner.app_controller.current_tracker_type = "Gimbal"
    monkeypatch.setattr("classes.api_v1_native_targets.external_selection_availability",
                        lambda _: {"available": True, "reason": None})
    monkeypatch.setattr("classes.api_v1_native_targets.get_gimbal_control_status",
                        lambda _: {"enabled": True, "available": True, "connected": True, "tracking_state": "tracking_active",
                                   "selection_mode": "classic", "capabilities": ["select", "cancel"]})
    result = following_snapshot(owner, owner.principal_test)
    assert result["target_mode"] == "external"
    assert {row["mode"] for row in result["profiles"] if row["compatible"]} == {
        "gm_velocity_chase", "gm_velocity_vector",
    }
    assert "tracker_output_incompatible" in result["start_reason_codes"]


def test_unknown_tracker_schema_does_not_assume_image_follower_support(owner):
    owner.app_controller.current_tracker_type = "unregistered_tracker"
    result = following_snapshot(owner, owner.principal_test)
    assert not any(row["compatible"] for row in result["profiles"])
    assert "tracker_output_incompatible" in result["start_reason_codes"]


def test_smart_uses_its_own_schema_not_inactive_classic_tracker(owner):
    owner.app_controller.current_tracker_type = "unregistered_tracker"
    owner.app_controller.smart_mode_active = True
    result = following_snapshot(owner, owner.principal_test)
    assert any(row["compatible"] for row in result["profiles"])
    assert not any(row["compatible"] for row in result["profiles"] if row["mode"].startswith("gm_"))


def test_manual_camera_motion_is_visible_following_interlock(owner):
    owner.app_controller.camera_runtime = SimpleNamespace(motion_active=True, provider=None)
    result = following_snapshot(owner, owner.principal_test)
    assert not result["start_allowed"]
    assert "camera_control_active" in result["start_reason_codes"]


async def test_read_requires_native_credentials_and_scopes(owner):
    request = SimpleNamespace(state=SimpleNamespace(api_principal=None))
    response = await get_native_following(owner, request)
    assert response.status_code == 401
    request.state.api_principal = APIPrincipal.bearer(
        subject="limited", token_id="limited", scopes={"status:read"},
    )
    response = await get_native_following(owner, request)
    assert response.status_code == 403
    request.state.api_principal = owner.principal_test
    response = await get_native_following(owner, request)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def ready_owner(owner, monkeypatch):
    owner.command_test.update(connected=True, autopilot_uid="42")
    owner.telemetry_test.update(connected=True, fresh=True, autopilot_uid="42", system_id=7, component_id=1)
    owner.app_controller.tracking_started = True
    monkeypatch.setattr("classes.api_v1_native_following.get_offboard_start_preflight",
                        lambda _: {"ready": True, "issues": []})
    return following_snapshot(owner, owner.principal_test)


def action_request(owner):
    return SimpleNamespace(state=SimpleNamespace(api_principal=owner.principal_test))


def start_body(snapshot):
    return APINativeFollowStartRequest(
        confirm=True, idempotency_key="start-1", start_attempt_id="b" * 32,
        profile_mode=snapshot["configured_mode"],
        profile_generation=snapshot["profile_generation"],
        native_context={"binding_mode": "vehicle", "guard": snapshot["guard"]},
    )


async def test_native_start_rechecks_context_on_flight_owner_before_commands(owner, monkeypatch):
    snapshot = ready_owner(owner, monkeypatch)
    calls = []

    async def start(native_start_guard, *, native_attempt_id, native_aircraft_uid):
        assert native_attempt_id == "b" * 32 and native_aircraft_uid == "42"
        native_start_guard("before_start")
        owner.telemetry_test["connection_generation"] = "changed"
        with pytest.raises(Exception, match="changed"):
            native_start_guard("before_offboard")
        calls.append("guarded")
        return {"steps": [], "errors": ["context changed"]}

    owner.app_controller.connect_px4 = start
    response = Response()
    record = await native_follow_action(owner, start_body(snapshot), response, action_request(owner), start=True)
    assert response.status_code == 202
    assert record["status"] == "failure"
    assert calls == ["guarded"]
    owner.app_controller.px4_interface.connect.assert_not_called()


async def test_native_start_rejects_stale_vehicle_and_replay_without_connect(owner, monkeypatch):
    snapshot = ready_owner(owner, monkeypatch)
    owner.app_controller.connect_px4 = AsyncMock()
    body = start_body(snapshot)
    owner.command_test["autopilot_uid"] = "different"
    response = await native_follow_action(owner, body, Response(), action_request(owner), start=True)
    assert response.status_code == 409
    owner.app_controller.connect_px4.assert_not_called()

    owner.command_test["autopilot_uid"] = "42"
    monkeypatch.setattr("classes.api_v1_native_following.get_offboard_start_preflight",
                        lambda _: {"ready": False, "issues": [{"code": "ACTION_OFFBOARD_REPLAY_NOT_AUTHORIZED"}]})
    response = await native_follow_action(owner, body, Response(), action_request(owner), start=True)
    assert response.status_code == 409
    owner.app_controller.connect_px4.assert_not_called()


async def test_stop_uses_captured_session_without_current_frame(owner, monkeypatch):
    ready_owner(owner, monkeypatch)
    app = owner.app_controller
    app.following_active = True
    app._following_session_id = "a" * 32
    app._following_session_aircraft_uid = "42"

    async def stop(session_id, aircraft_uid):
        assert (session_id, aircraft_uid) == ("a" * 32, "42")
        app.following_active = False
        app._following_session_id = None
        return {"steps": ["stopped"], "errors": []}

    app.stop_native_following = stop
    owner.frame_publisher.invalidate_source("disconnected-video")
    body = APINativeFollowStopRequest(
        confirm=True, idempotency_key="stop-1", instance_id=INSTANCE_ID,
        runtime_id=RUNTIME_ID, follow_session_id="a" * 32, aircraft_uid="42",
    )
    response = Response()
    record = await native_follow_action(owner, body, response, action_request(owner), start=False)
    assert response.status_code == 202 and record["status"] == "success"
    replay = await native_follow_action(owner, body, Response(), action_request(owner), start=False)
    assert replay["idempotent_replay"]


async def test_pending_start_is_advertised_and_stop_uses_its_captured_identity(owner, monkeypatch):
    ready_owner(owner, monkeypatch)
    app = owner.app_controller
    app._native_follow_start_attempt_id = "b" * 32
    app._native_follow_start_aircraft_uid = "42"
    app._follow_start_task = object()
    snapshot = following_snapshot(owner, owner.principal_test)
    assert snapshot["stop_allowed"] and snapshot["pending_start_id"] == "b" * 32

    async def stop(session_id, aircraft_uid):
        assert (session_id, aircraft_uid) == ("b" * 32, "42")
        app._native_follow_start_attempt_id = None
        return {"steps": ["startup canceled"], "errors": []}

    app.stop_native_following = stop
    body = APINativeFollowStopRequest(
        confirm=True, idempotency_key="pending-stop-1", instance_id=INSTANCE_ID,
        runtime_id=RUNTIME_ID, follow_session_id="b" * 32, aircraft_uid="42",
    )
    response = Response()
    record = await native_follow_action(owner, body, response, action_request(owner), start=False)
    assert response.status_code == 202 and record["status"] == "success"


async def test_profile_choice_checks_compatibility_and_keeps_runtime_pending(owner, monkeypatch):
    snapshot = ready_owner(owner, monkeypatch)
    configured = {"mode": "mc_velocity_position"}
    monkeypatch.setattr("classes.api_v1_native_following._get_persisted_follower_mode",
                        lambda _: configured["mode"])
    monkeypatch.setattr("classes.api_v1_native_following.update_config_parameter",
                        SimpleNamespace(__wrapped__=lambda _owner, _section, _name, body:
                                        (configured.update(mode=body.value) or
                                         JSONResponse({"saved": True, "applied": False}))))
    body = APINativeFollowerSelectRequest(
        confirm=True, idempotency_key="profile-1", profile_mode="mc_velocity_chase",
        profile_generation=snapshot["profile_generation"],
        native_context={"binding_mode": "vehicle", "guard": snapshot["guard"]},
    )
    response = Response()
    record = await native_follower_select(owner, body, response, action_request(owner))
    assert response.status_code == 202 and record["status"] == "success"
    assert record["result"]["following"]["configured_mode"] == "mc_velocity_chase"
    assert record["result"]["following"]["activation_pending"]
    assert configured["mode"] == "mc_velocity_chase"


@pytest.mark.parametrize("mode", ["mc_velocity_chase", "mc_velocity_distance", "mc_velocity_position"])
async def test_stopped_follow_session_can_change_profile_and_select_new_target(owner, monkeypatch, mode):
    app = AppController.__new__(AppController)
    app.__dict__.update(vars(owner.app_controller))
    owner.app_controller = app
    app.following_active = True
    app._following_session_id = "stopped-session"
    app.follower = None
    app.offboard_commander = None
    app.setpoint_sender = None
    app.px4_interface.stop_offboard_mode = AsyncMock(return_value={"executed": True})
    app.tracker.reset = Mock()
    app.tracker.start_tracking = Mock()
    app.tracking_started = True
    await app._disconnect_px4_internal()
    handoff = dict(app._last_following_handoff)
    # Exercise the production target executor, rather than the fixture's stub.
    del app._start_tracking_with_follower_barrier
    configured = {"mode": "mc_velocity_position"}
    monkeypatch.setattr("classes.api_v1_native_following._get_persisted_follower_mode",
                        lambda _: configured["mode"])
    monkeypatch.setattr("classes.api_v1_native_following.update_config_parameter",
                        SimpleNamespace(__wrapped__=lambda _owner, _section, _name, body:
                                        (configured.update(mode=body.value) or
                                         JSONResponse({"saved": True, "applied": False}))))
    snapshot = following_snapshot(owner, owner.principal_test)
    body = APINativeFollowerSelectRequest(
        confirm=True, idempotency_key="after-stop-profile", profile_mode=mode,
        profile_generation=snapshot["profile_generation"],
        native_context={"binding_mode": "companion_only", "guard": snapshot["guard"]},
    )
    selected = await native_follower_select(owner, body, Response(), action_request(owner))
    assert selected["status"] == "success"
    assert selected["result"]["following"]["configured_mode"] == mode
    publish(owner, 23)
    tracking, response = await execute(owner, start_request(owner))
    assert response.status_code == 202 and tracking["status"] == "success"
    assert tracking["result"]["legacy_result"]["started"]
    app.tracker.start_tracking.assert_called_once()
    assert app._last_following_handoff == handoff
    assert not app.following_active


async def test_companion_can_choose_compatible_follower_without_starting_aircraft(owner, monkeypatch):
    owner.app_controller.tracker.is_external_tracker = True
    owner.app_controller.current_tracker_type = "Gimbal"
    monkeypatch.setattr("classes.api_v1_native_targets.external_selection_availability",
                        lambda _: {"available": True, "reason": None})
    monkeypatch.setattr("classes.api_v1_native_targets.get_gimbal_control_status",
                        lambda _: {"enabled": True, "available": True, "connected": True,
                                   "tracking_state": "disabled", "selection_mode": "classic",
                                   "capabilities": ["select", "cancel"]})
    configured = {"mode": "gm_velocity_chase"}
    monkeypatch.setattr("classes.api_v1_native_following._get_persisted_follower_mode",
                        lambda _: configured["mode"])
    monkeypatch.setattr("classes.api_v1_native_following.update_config_parameter",
                        SimpleNamespace(__wrapped__=lambda _owner, _section, _name, body:
                                        (configured.update(mode=body.value) or
                                         JSONResponse({"saved": True, "applied": False}))))
    snapshot = following_snapshot(owner, owner.principal_test)
    assert not snapshot["start_allowed"]
    assert "aircraft_not_verified" in snapshot["start_reason_codes"]
    body = APINativeFollowerSelectRequest(
        confirm=True, idempotency_key="companion-profile-1", profile_mode="gm_velocity_vector",
        profile_generation=snapshot["profile_generation"],
        native_context={"binding_mode": "companion_only", "guard": snapshot["guard"]},
    )
    response = Response()
    record = await native_follower_select(owner, body, response, action_request(owner))
    assert response.status_code == 202 and record["status"] == "success"
    assert record["result"]["following"]["configured_mode"] == "gm_velocity_vector"
    assert not record["result"]["following"]["start_allowed"]
    assert configured["mode"] == "gm_velocity_vector"
    owner.app_controller.px4_interface.connect.assert_not_called()


async def test_native_stop_never_commands_a_rebound_aircraft():
    app = AppController.__new__(AppController)
    app._follower_state_lock = asyncio.Lock()
    app.following_active = True
    app._following_session_id = "a" * 32
    app._following_session_aircraft_uid = "42"
    app.px4_interface = SimpleNamespace(get_aircraft_identity=lambda: {"autopilot_uid": "99"})
    app._disconnect_px4_internal = AsyncMock(return_value={"steps": [], "errors": []})

    async def run(operation):
        return await operation()

    app._run_on_flight_event_loop = run
    stale = await app.stop_native_following("b" * 32, "42")
    assert stale["precondition"]["code"] == "native_follow_session_stale"
    app._disconnect_px4_internal.assert_not_called()
    result = await app.stop_native_following("a" * 32, "42")
    assert "identity changed" in result["errors"][0]
    app._disconnect_px4_internal.assert_awaited_once_with(
        commander_publish_final=False, attempt_offboard_stop=False,
    )


async def test_native_stop_never_commands_a_reconnected_same_uid():
    app = AppController.__new__(AppController)
    app._follower_state_lock = asyncio.Lock()
    app.following_active = True
    app._following_session_id = "a" * 32
    app._following_session_aircraft_uid = "42"
    app._following_session_connection_generation = "old"
    app.px4_interface = SimpleNamespace(get_aircraft_identity=lambda: {
        "autopilot_uid": "42", "connection_generation": "new",
    })
    app._disconnect_px4_internal = AsyncMock(return_value={"steps": [], "errors": []})

    async def run(operation):
        return await operation()

    app._run_on_flight_event_loop = run
    result = await app.stop_native_following("a" * 32, "42")
    assert "identity changed" in result["errors"][0]
    app._disconnect_px4_internal.assert_awaited_once_with(
        commander_publish_final=False, attempt_offboard_stop=False,
    )


async def test_pending_native_start_can_be_stopped_without_waiting_for_activation():
    app = AppController.__new__(AppController)
    app._follower_state_lock = asyncio.Lock()
    app._follow_start_task = None
    app.following_active = False
    app._native_follow_start_attempt_id = None
    app._native_follow_start_aircraft_uid = None
    app.px4_interface = SimpleNamespace(get_aircraft_identity=lambda: {"autopilot_uid": "42"})
    app._disconnect_px4_internal = AsyncMock(return_value={"steps": ["stopped"], "errors": []})
    entered = asyncio.Event()

    async def slow_start(_guard):
        entered.set()
        await asyncio.Event().wait()

    async def run(operation):
        return await operation()

    app._connect_px4_on_flight_loop = slow_start
    app._run_on_flight_event_loop = run
    task = asyncio.create_task(app.connect_px4(lambda _: None, native_attempt_id="b" * 32,
                                                native_aircraft_uid="42"))
    await asyncio.wait_for(entered.wait(), 1)
    stale = await app.stop_native_following("c" * 32, "42")
    assert stale["precondition"]["code"] == "native_follow_session_stale"
    assert not task.done()
    stopped = await app.stop_native_following("b" * 32, "42")
    assert stopped["errors"] == []
    assert (await task)["precondition"]["code"] == "native_follow_start_canceled"
    app._disconnect_px4_internal.assert_awaited_once_with(
        commander_publish_final=True, attempt_offboard_stop=True,
    )


async def test_native_fixed_wing_start_reports_missing_airspeed_without_offboard(owner, monkeypatch):
    ready_owner(owner, monkeypatch)
    monkeypatch.setattr(Parameters, "FOLLOWER_MODE", "fw_attitude_rate")
    monkeypatch.setattr("classes.api_v1_native_following._get_persisted_follower_mode", lambda _: "fw_attitude_rate")
    owner.app_controller.connect_px4 = AsyncMock()
    snapshot = following_snapshot(owner, owner.principal_test)
    assert "following_airspeed_unavailable" in snapshot["start_reason_codes"]
    assert "profile_not_live_qualified" in snapshot["start_reason_codes"]
    response = await native_follow_action(owner, start_body(snapshot), Response(), action_request(owner), start=True)
    assert response.status_code == 409
    owner.app_controller.connect_px4.assert_not_awaited()
    owner.app_controller.px4_interface.connect.assert_not_called()


async def test_native_fixed_wing_fallback_keeps_live_qualification_block(owner, monkeypatch):
    from tests.unit.followers.test_fixed_wing_guidance_boundary import fresh_ground_speed_controller
    ready_owner(owner, monkeypatch)
    monkeypatch.setattr(Parameters, "FOLLOWER_MODE", "fw_attitude_rate")
    monkeypatch.setattr(Parameters, "FW_ATTITUDE_RATE", {**Parameters.FW_ATTITUDE_RATE, "ALLOW_GROUND_SPEED_FALLBACK": True})
    monkeypatch.setattr("classes.api_v1_native_following._get_persisted_follower_mode", lambda _: "fw_attitude_rate")
    ground_owner = fresh_ground_speed_controller()
    owner.app_controller.px4_interface.get_telemetry_readiness = ground_owner.get_telemetry_readiness
    owner.app_controller.connect_px4 = AsyncMock()
    snapshot = following_snapshot(owner, owner.principal_test)
    assert "following_airspeed_unavailable" not in snapshot["start_reason_codes"]
    assert "following_ground_speed_stale" not in snapshot["start_reason_codes"]
    assert "profile_not_live_qualified" in snapshot["start_reason_codes"]
    response = await native_follow_action(owner, start_body(snapshot), Response(), action_request(owner), start=True)
    assert response.status_code == 409
    owner.app_controller.connect_px4.assert_not_awaited()
    owner.app_controller.px4_interface.connect.assert_not_called()

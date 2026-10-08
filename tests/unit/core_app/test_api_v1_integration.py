"""Native association/auth contracts with no aircraft, servers, or media."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from classes.aircraft_identity import TelemetryAircraftIdentity, canonical_uid
from classes.api_auth_runtime import (
    APIAuthRuntime, APIUserRecord, BearerTokenRecord, hash_bearer_token,
    hash_password_pbkdf2_sha256,
)
from classes.api_exposure_policy import resolve_api_exposure_policy
from classes.api_security_types import APIPrincipal
from classes.api_v1_integration import context_snapshot, integration_context
from classes.app_controller import AppController
from classes.fastapi_handler import FastAPIHandler
from classes.parameters import Parameters
from classes.px4_interface_manager import PX4InterfaceManager


UID = "18446744073709551614"


def mavlink_payload(counter=1, uid=UID, system=7, component=1, autopilot="MAV_AUTOPILOT_PX4"):
    return {"vehicles": {str(system): {"components": {str(component): {"messages": {
        "HEARTBEAT": {"message": {"autopilot": {"type": autopilot}},
                      "status": {"time": {"counter": counter}}},
        "AUTOPILOT_VERSION": {"message": {"uid": int(uid)}},
    }}}}}}


@pytest.mark.parametrize("value", [None, True, False, 0, -1, 2**64, 1.0, "1.0", "-1", "1e4", "١", ""])
def test_uid_rejects_unknown_or_lossy_values(value):
    assert canonical_uid(value) is None


def test_uid_preserves_full_uint64_as_decimal_string():
    assert canonical_uid(int(UID)) == UID
    assert canonical_uid("00023") == "23"


def test_heartbeat_progress_required_and_frozen_http_payload_expires():
    identity = TelemetryAircraftIdentity(7, 1, 2)
    identity.observe(mavlink_payload(), now=10)
    assert not identity.snapshot(connected=True, now=10)["fresh"]
    identity.observe(mavlink_payload(2), now=11)
    assert identity.snapshot(connected=True, now=11)["fresh"]
    identity.observe(mavlink_payload(2), now=12)
    assert not identity.snapshot(connected=True, now=14)["fresh"]
    identity.observe(mavlink_payload(2), now=15)
    assert not identity.snapshot(connected=True, now=15)["fresh"]


def test_identity_replacement_reconnect_and_counter_reset_invalidate_generation():
    identity = TelemetryAircraftIdentity(7, 1, 2)
    identity.observe(mavlink_payload(10), now=1)
    identity.observe(mavlink_payload(11), now=2)
    first = identity.snapshot(connected=True, now=2)
    identity.observe(mavlink_payload(1), now=2.1)
    reset = identity.snapshot(connected=True, now=2.1)
    assert not reset["fresh"] and reset["connection_generation"] != first["connection_generation"]
    identity.observe(mavlink_payload(2, uid="22"), now=2.2)
    replaced = identity.snapshot(connected=True, now=2.2)
    assert replaced["autopilot_uid"] == "22" and not replaced["fresh"]
    assert replaced["connection_generation"] != reset["connection_generation"]
    identity.invalidate("telemetry_disconnected")
    assert identity.snapshot(connected=False, now=3)["autopilot_uid"] is None
    identity.observe(mavlink_payload(3, uid="22"), now=3)
    assert not identity.snapshot(connected=True, now=3)["fresh"]


def test_route_configuration_is_not_observation_and_duplicates_fail_closed():
    identity = TelemetryAircraftIdentity(7, 1, 2)
    identity.observe(mavlink_payload(system=1), now=1)
    assert identity.snapshot(connected=True, now=1)["system_id"] is None
    duplicate = mavlink_payload()
    duplicate["vehicles"].update(mavlink_payload(system=8)["vehicles"])
    identity.observe(duplicate, now=1)
    assert identity.snapshot(connected=True, now=1)["reason"] == "telemetry_identity_ambiguous"
    identity.observe(mavlink_payload(autopilot="MAV_AUTOPILOT_INVALID"), now=2)
    assert identity.snapshot(connected=True, now=2)["autopilot_uid"] is None


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setattr(Parameters, "USE_MAVLINK2REST", True)
    command = dict(source="mavsdk", connected=True, connection_generation="3:1",
                   autopilot_uid=UID, hardware_uid=None, system_id=None, component_id=None)
    telemetry = dict(source="mavlink2rest", connected=True, fresh=True,
                     connection_generation="2", autopilot_uid=UID, system_id=7, component_id=1)
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.app_controller = SimpleNamespace(
        px4_interface=SimpleNamespace(get_aircraft_identity=lambda: dict(command)),
        mavlink_data_manager=SimpleNamespace(get_aircraft_identity=lambda: dict(telemetry)),
        observe_native_connection=AsyncMock(),
    )
    handler._command_test = command
    handler._telemetry_test = telemetry
    return handler


def principal():
    return APIPrincipal.bearer(subject="test-native", token_id="fixture", scopes={"status:read", "telemetry:read"})


def test_matching_observed_uid_is_read_only_and_runtime_identity_stable(owner):
    context = context_snapshot(owner, principal())
    assert context["contract_version"] == "1"
    assert context["association"]["verified"]
    assert context["command"]["autopilot_uid"] == UID
    assert context["telemetry"]["system_id"] == 7
    assert context["readiness"]["connection_ready"]
    assert context["readiness"]["following_allowed"] is False
    assert context["video"]["geometry_verified"] is False
    again = context_snapshot(owner, principal())
    assert context["instance_id"] == again["instance_id"]
    assert context["runtime_id"] == again["runtime_id"]
    owner.app_controller.observe_native_connection.assert_not_called()


@pytest.mark.parametrize("section,field,value,reason", [
    ("command", "connected", False, "command_disconnected"),
    ("command", "autopilot_uid", None, "command_identity_unknown"),
    ("telemetry", "fresh", False, "telemetry_stale"),
    ("telemetry", "connected", False, "telemetry_disconnected"),
    ("telemetry", "autopilot_uid", "22", "aircraft_identity_mismatch"),
    ("telemetry", "autopilot_uid", None, "telemetry_identity_unknown"),
    ("telemetry", "system_id", None, "telemetry_route_unobserved"),
])
def test_context_fails_closed(owner, section, field, value, reason):
    getattr(owner, f"_{section}_test")[field] = value
    context = context_snapshot(owner, principal())
    assert not context["association"]["verified"]
    assert not context["readiness"]["connection_ready"]
    assert reason in context["association"]["reason_codes"]


async def test_explicit_discovery_and_timeout_envelopes(owner):
    request = SimpleNamespace(state=SimpleNamespace(api_principal=principal()))
    response = await integration_context(owner, request, connect=True)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    owner.app_controller.observe_native_connection.assert_awaited_once()
    owner.app_controller.observe_native_connection.side_effect = TimeoutError("private endpoint")
    response = await integration_context(owner, request, connect=True)
    assert response.status_code == 504
    assert "native_discovery_timeout" in response.body.decode()
    assert "private endpoint" not in response.body.decode()


def client(owner, *, mode="machine_bearer", scopes=("status:read", "telemetry:read")):
    owner.app = FastAPI()
    owner.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1", mode="local_only", cors_allowed_origins=[],
    )
    token_hash = hash_bearer_token("native-test-fixture")
    users = {}
    if mode == "browser_session":
        user = APIUserRecord(username="native-viewer", role="viewer",
                             password_pbkdf2_sha256=hash_password_pbkdf2_sha256("fixture-only"))
        users[user.username] = user
    owner.api_auth_runtime = APIAuthRuntime(mode=mode, users_by_username=users, bearer_tokens_by_hash={
        token_hash: BearerTokenRecord(token_id="fixture", subject="native-test",
                                     token_sha256=token_hash, scopes=frozenset(scopes)),
    })
    owner._record_security_audit_event = lambda **kwargs: True
    owner.app.add_api_route("/api/v1/integration/context", owner.get_integration_context, methods=["GET"])
    owner.app.add_api_route("/api/v1/integration/connection", owner.observe_integration_connection, methods=["POST"])
    owner._setup_middleware()
    return TestClient(owner.app, base_url="http://127.0.0.1:5077", client=("127.0.0.1", 32100))


def test_route_requires_credentials_and_both_scopes(owner):
    http = client(owner)
    assert http.get("/api/v1/integration/context").status_code == 401
    headers = {"Authorization": "Bearer native-test-fixture"}
    assert http.get("/api/v1/integration/context", headers=headers).status_code == 200
    response = http.post("/api/v1/integration/connection", json={}, headers=headers)
    assert response.status_code == 200
    assert http.post("/api/v1/integration/connection", json={"arm": True}, headers=headers).status_code == 422
    http = client(owner, scopes=("status:read",))
    assert http.get("/api/v1/integration/context", headers=headers).status_code == 403
    owner.app_controller.observe_native_connection.assert_awaited_once()


def test_local_compat_does_not_grant_native_association(owner):
    http = client(owner, mode="local_compat")
    assert http.get("/api/v1/integration/context").status_code == 401
    assert http.post("/api/v1/integration/connection", json={}).status_code == 401
    owner.app_controller.observe_native_connection.assert_not_called()


def test_session_csrf_and_revocation_apply_before_discovery(owner):
    http = client(owner, mode="browser_session")
    runtime = owner.api_auth_runtime
    user = runtime.users_by_username["native-viewer"]
    session = runtime.create_session_for_user(user)
    http.cookies.set(runtime.session_cookie_name, session.session_id)
    assert http.get("/api/v1/integration/context").status_code == 200
    assert http.post("/api/v1/integration/connection", json={}).status_code == 403
    headers = {runtime.csrf_header_name: session.csrf_token}
    assert http.post("/api/v1/integration/connection", json={}, headers=headers).status_code == 200
    runtime.revoke_session_id(session.session_id)
    assert http.get("/api/v1/integration/context").status_code == 401
    owner.app_controller.observe_native_connection.assert_awaited_once()


async def test_observation_uses_stable_owner_without_following_and_blocks_shutdown():
    controller = AppController.__new__(AppController)
    controller._flight_event_loop = asyncio.get_running_loop()
    controller._follower_state_lock = asyncio.Lock()
    controller.shutdown_flag = False
    controller.px4_interface = SimpleNamespace(connect=AsyncMock(), observe_aircraft_identity=AsyncMock())
    controller.following_active = False
    await controller.observe_native_connection()
    assert controller.following_active is False
    controller.px4_interface.connect.assert_awaited_once()
    controller.px4_interface.observe_aircraft_identity.assert_awaited_once()
    controller.shutdown_flag = True
    with pytest.raises(RuntimeError, match="shutting down"):
        await controller.observe_native_connection()
    controller.px4_interface.connect.assert_awaited_once()


async def test_identity_completion_from_old_command_generation_is_discarded():
    px4 = PX4InterfaceManager.__new__(PX4InterfaceManager)
    px4._connection_generation = 4
    px4._aircraft_identity_revision = 0
    px4._aircraft_identity = None
    px4.active_mode = True
    px4.get_connection_status = lambda: {"connected": px4.active_mode}

    async def identify():
        px4._advance_connection_generation()
        return SimpleNamespace(legacy_uid=int(UID), hardware_uid="uid2-is-not-uid")

    px4.drone = SimpleNamespace(info=SimpleNamespace(get_identification=identify))
    await px4.observe_aircraft_identity()
    assert px4.get_aircraft_identity()["autopilot_uid"] is None
    px4.drone.info.get_identification = AsyncMock(return_value=SimpleNamespace(legacy_uid=int(UID), hardware_uid="uid2"))
    await px4.observe_aircraft_identity()
    observed = px4.get_aircraft_identity()
    assert observed["autopilot_uid"] == UID and observed["system_id"] is None
    px4._advance_connection_generation()
    assert px4.get_aircraft_identity()["autopilot_uid"] is None
    assert px4.get_aircraft_identity()["connection_generation"] != observed["connection_generation"]


def test_observed_autopilot_reboot_invalidates_even_with_advancing_heartbeat():
    identity = TelemetryAircraftIdentity(7, 1, 2)
    payload = mavlink_payload(1)
    messages = payload["vehicles"]["7"]["components"]["1"]["messages"]
    messages["ATTITUDE"] = {"message": {"time_boot_ms": 5000}}
    identity.observe(payload, now=1)
    messages["HEARTBEAT"]["status"]["time"]["counter"] = 2
    messages["ATTITUDE"]["message"]["time_boot_ms"] = 6000
    identity.observe(payload, now=2)
    before = identity.snapshot(connected=True, now=2)
    assert before["fresh"]
    messages["HEARTBEAT"]["status"]["time"]["counter"] = 3
    messages["ATTITUDE"]["message"]["time_boot_ms"] = 100
    identity.observe(payload, now=2.1)
    after = identity.snapshot(connected=True, now=2.1)
    assert not after["fresh"]
    assert before["connection_generation"] != after["connection_generation"]


def test_native_discovery_audit_failure_prevents_observation(owner):
    http = client(owner)
    owner._record_security_audit_event = lambda **kwargs: False
    response = http.post("/api/v1/integration/connection", json={},
                         headers={"Authorization": "Bearer native-test-fixture"})
    assert response.status_code == 503
    owner.app_controller.observe_native_connection.assert_not_called()


async def test_observation_is_serialized_and_cancellation_does_not_leave_an_owner():
    controller = AppController.__new__(AppController)
    controller._flight_event_loop = asyncio.get_running_loop()
    controller._follower_state_lock = asyncio.Lock()
    controller.shutdown_flag = False
    controller.following_active = False
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def connect():
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()

    controller.px4_interface = SimpleNamespace(connect=connect, observe_aircraft_identity=AsyncMock())
    first = asyncio.create_task(controller.observe_native_connection())
    await entered.wait()
    second = asyncio.create_task(controller.observe_native_connection())
    await asyncio.sleep(0)
    assert calls == 1
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    await second
    assert calls == 2 and not controller._follower_state_lock.locked()
    controller.px4_interface.observe_aircraft_identity.assert_awaited_once()


async def test_native_viewer_does_not_reconfigure_live_follow_telemetry():
    controller = AppController.__new__(AppController)
    controller._flight_event_loop = asyncio.get_running_loop()
    controller._follower_state_lock = asyncio.Lock()
    controller.shutdown_flag = False
    controller.following_active = True
    controller.px4_interface = SimpleNamespace(
        connect=AsyncMock(), observe_aircraft_identity=AsyncMock(),
        get_connection_status=lambda: {"connected": True},
    )
    await controller.observe_native_connection()
    controller.px4_interface.connect.assert_not_called()
    controller.px4_interface.observe_aircraft_identity.assert_awaited_once()
    controller.px4_interface.get_connection_status = lambda: {"connected": False}
    with pytest.raises(RuntimeError, match="Following owns"):
        await controller.observe_native_connection()
    controller.px4_interface.connect.assert_not_called()


async def test_native_request_does_not_steal_uninitialized_flight_loop():
    controller = AppController.__new__(AppController)
    controller._flight_event_loop = None
    with pytest.raises(RuntimeError, match="existing flight owner"):
        await controller.observe_native_connection()
    assert controller._flight_event_loop is None


async def test_configured_route_controls_aggregate_and_all_follower_reads(monkeypatch):
    from classes.mavlink_data_manager import MavlinkDataManager

    monkeypatch.setattr(Parameters, "MAVLINK_SYSTEM_ID", 7, raising=False)
    monkeypatch.setattr(Parameters, "MAVLINK_COMPONENT_ID", 42, raising=False)
    manager = MavlinkDataManager("localhost", 8088, .5, {
        "latitude": "/vehicles/1/components/1/messages/GLOBAL_POSITION_INT/message/lat",
        "arm_status": "/vehicles/1/components/191/messages/HEARTBEAT/message/base_mode",
    })
    assert all("/vehicles/7/components/42/" in path for path in manager.data_points.values())
    manager.fetch_data_from_uri = AsyncMock(return_value={"message": {}})
    await manager.fetch_attitude_data()
    await manager.fetch_altitude_data()
    await manager.fetch_ground_speed()
    await manager.fetch_throttle_percent()
    paths = [call.args[0] for call in manager.fetch_data_from_uri.await_args_list]
    assert len(paths) == 4
    assert all(path.startswith("/v1/mavlink/vehicles/7/components/42/messages/") for path in paths)


@pytest.mark.parametrize("value", [0, 256, -1, True, "7", 7.0])
def test_invalid_telemetry_route_rejected_without_defaulting(monkeypatch, value):
    from classes.mavlink_data_manager import MavlinkDataManager

    monkeypatch.setattr(Parameters, "MAVLINK_SYSTEM_ID", value, raising=False)
    with pytest.raises(ValueError, match="MAVLINK_SYSTEM_ID"):
        MavlinkDataManager("localhost", 8088, .5, {})


def test_loopback_fixture_uses_production_login_csrf_context_and_logout(tmp_path, monkeypatch):
    from tools.native_integration_fixture import create_app

    monkeypatch.setattr(Parameters, "USE_MAVLINK2REST", True)
    audit = tmp_path / "audit.jsonl"
    app = create_app(port=8091, system_id=1, uid="18446744073709551001", audit_path=audit)
    with TestClient(app, base_url="http://127.0.0.1:8091", client=("127.0.0.1", 32000)) as http:
        assert http.get("/api/v1/integration/context").status_code == 401
        login = http.post("/api/v1/auth/login", json={"username": "operator", "password": "fixture-only"})
        assert login.status_code == 200
        session = login.json()
        assert session["authenticated"]
        assert not http.get("/api/v1/integration/context").json()["association"]["verified"]
        assert http.post("/api/v1/integration/connection", json={}).status_code == 403
        headers = {session["csrf_header_name"]: session["csrf_token"]}
        context = http.post("/api/v1/integration/connection", json={}, headers=headers)
        assert context.status_code == 200 and context.json()["association"]["verified"]
        assert context.json()["command"]["autopilot_uid"] == "18446744073709551001"
        assert http.post("/api/v1/auth/logout", headers=headers).status_code == 200
        assert http.get("/api/v1/integration/context").status_code == 401
    log = audit.read_text()
    assert "api.auth.login" in log and "fixture-only" not in log
    assert session["csrf_token"] not in log

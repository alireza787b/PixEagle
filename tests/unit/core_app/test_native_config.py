"""Native config uses the real persistence owner, isolated from operator files."""

import asyncio
import json
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from fastapi import Response

from classes.api_security_types import APIPrincipal
from classes.api_v1_contracts import APINativeConfigApplyRequest, APINativeOSDSetRequest, APIActionResponse
from classes.api_v1_native_config import config_action, get_config
from classes.config_service import ConfigService
from classes.parameters import Parameters
from tests.unit.core_app.test_parameters_reload import isolated_parameters_state

pytestmark = pytest.mark.unit


@pytest.fixture
def owner(tmp_path, isolated_parameters_state):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    for name in ("config_default.yaml", "config_schema.yaml", "config_retirements.yaml"):
        shutil.copyfile(Path("configs") / name, config_dir / name)
    service = ConfigService(project_root=tmp_path)
    Parameters.publish_config_mapping(service.get_config(), source="test_native_config")
    renderer = SimpleNamespace(enabled=True)
    renderer.is_enabled = lambda: renderer.enabled
    renderer.set_enabled = lambda value: setattr(renderer, "enabled", value)
    async def run(operation):
        return await operation()
    app = SimpleNamespace(
        osd_handler=renderer, osd_pipeline=SimpleNamespace(invalidate_cache=Mock()),
        following_active=False, tracking_started=False, smart_mode_active=False,
        _follower_state_lock=asyncio.Lock(), _tracker_model_state_lock=threading.RLock(),
        _run_on_flight_event_loop=run, current_tracker_type="CSRT",
        _switch_tracker_type_with_follower_barrier=Mock(return_value={"success": True}),
    )
    result = SimpleNamespace(app_controller=app, service=service, _get_config_service=lambda: service,
                             logger=Mock(), _record_security_audit_event=Mock(return_value=True))
    from classes.api_v1_errors import build_api_v1_error_response
    result._api_v1_error_response = build_api_v1_error_response
    result.principal = APIPrincipal.bearer(subject="config-a", token_id="a", scopes={"config:read", "config:write", "control:write"})
    return result


def http(owner, scopes=None):
    principal = owner.principal if scopes is None else APIPrincipal.bearer(subject="other", token_id="b", scopes=scopes)
    return SimpleNamespace(state=SimpleNamespace(api_principal=principal))


async def snapshot(owner):
    response = await get_config(owner, http(owner))
    assert response.status_code == 200, response.body
    return json.loads(response.body)


async def request(owner, **updates):
    state = await snapshot(owner)
    payload = {key: state[key] for key in ("instance_id", "runtime_id", "config_generation")}
    payload.update(confirm=True, idempotency_key="one", enabled=False)
    payload.update(updates)
    return APINativeOSDSetRequest(**payload)


async def act(owner, payload, action="osd_set"):
    return await config_action(owner, payload, Response(), http(owner), action=action)


async def test_snapshot_is_redacted_stable_and_no_supervisor_claim(owner):
    state = await snapshot(owner)
    assert state == await snapshot(owner)
    assert not state["pending"]
    assert state["osd"]["saved_enabled"] is True
    assert state["osd"]["running_enabled"] is True
    assert state["system_restart"]["reason"] == "supervisor_not_verified"
    assert str(owner.service._project_root) not in json.dumps(state)


async def test_osd_persists_desired_state_and_retries_only_once(owner):
    payload = await request(owner)
    result = await act(owner, payload)
    APIActionResponse.model_validate(result)
    assert result["result"]["config"]["osd"]["saved_enabled"] is False
    assert result["result"]["config"]["osd"]["running_enabled"] is False
    saved = yaml.safe_load((owner.service._project_root / "configs/config.yaml").read_text())
    assert saved["OSD"]["OSD_ENABLED"] is False
    again = await act(owner, payload)
    assert again["action_id"] == result["action_id"]
    owner.app_controller.osd_pipeline.invalidate_cache.assert_called_once()


async def test_stale_generation_and_restart_never_mutate(owner):
    stale = await request(owner)
    await act(owner, await request(owner, idempotency_key="other"))
    response = await act(owner, stale)
    assert response.status_code == 409
    assert b"config_generation_stale" in response.body
    response = await act(owner, await request(owner, runtime_id="another", idempotency_key="restart"))
    assert response.status_code == 409
    assert b"config_runtime_changed" in response.body


async def test_dry_run_permissions_confirmation_and_audit_fail_closed(owner):
    payload = await request(owner, dry_run=True, confirm=False, idempotency_key=None)
    result = await act(owner, payload)
    assert not result["executed"]
    assert owner.app_controller.osd_handler.enabled
    response = await config_action(owner, payload, Response(), http(owner, {"config:read"}), action="osd_set")
    assert response.status_code == 403
    response = await act(owner, await request(owner, confirm=False))
    assert response.status_code == 422
    owner._record_security_audit_event.return_value = False
    response = await act(owner, await request(owner))
    assert response.status_code == 503
    assert owner.app_controller.osd_handler.enabled


async def test_runtime_failure_restores_saved_and_effective_osd(owner):
    renderer = owner.app_controller.osd_handler
    def setter(value):
        if value is False:
            raise RuntimeError("renderer failure")
        renderer.enabled = value
    renderer.set_enabled = setter
    result = await act(owner, await request(owner))
    assert result.status_code == 503
    state = await snapshot(owner)
    assert state["osd"]["saved_enabled"] is True
    assert state["osd"]["running_enabled"] is True
    assert Parameters.OSD_ENABLED is True


def pending(owner, section, parameter, value):
    service = owner.service
    assert service.set_parameter(section, parameter, value, audit=False).valid
    assert service.save_config(backup=False)


async def test_tracker_apply_and_follow_guard(owner):
    pending(owner, "Tracking", "DEFAULT_TRACKING_ALGORITHM", "KCF")
    state = await snapshot(owner)
    assert state["apply"]["reload_tier"] == "tracker_restart"
    payload = APINativeConfigApplyRequest(**{key:state[key] for key in ("instance_id", "runtime_id", "config_generation")},
                                         confirm=True, idempotency_key="apply", reload_tier="tracker_restart")
    owner.app_controller.following_active = True
    result = await act(owner, payload, "config_apply")
    assert result.status_code == 409
    owner.app_controller.following_active = False
    result = await act(owner, payload, "config_apply")
    assert result["result"]["config"]["pending"] is False
    owner.app_controller._switch_tracker_type_with_follower_barrier.assert_called_once_with("KCF")


async def test_dashboard_toggle_uses_same_persistent_owner(owner):
    from classes.api_legacy_osd_routes import toggle_osd
    before = await request(owner)
    response = await toggle_osd(owner)
    assert response.status_code == 200
    result = await act(owner, before)
    assert result.status_code == 409
    assert (await snapshot(owner))["osd"]["saved_enabled"] is False


@pytest.mark.parametrize("flag", ["motion_active", "busy"])
async def test_camera_operation_blocks_apply(owner, flag):
    pending(owner, "Tracking", "DEFAULT_TRACKING_ALGORITHM", "KCF")
    owner.app_controller.camera_runtime = SimpleNamespace(motion_active=False, busy=False)
    setattr(owner.app_controller.camera_runtime, flag, True)
    assert (await snapshot(owner))["apply"]["reason"] == "camera_operation_active"


async def test_osd_does_not_apply_unrelated_pending_immediate_config(owner):
    original = Parameters.OSD_PRESET
    pending(owner, "OSD", "OSD_PRESET", "minimal")
    result = await act(owner, await request(owner))
    assert result["result"]["config"]["pending"]
    assert Parameters.OSD_PRESET == original


@pytest.mark.parametrize("flight", [
    {"autopilot_uid": "fixture", "fresh": False, "arm_status": "Disarmed"},
    {"autopilot_uid": "fixture", "fresh": True, "arm_status": "Armed"},
])
async def test_observed_aircraft_must_be_freshly_disarmed(owner, flight):
    pending(owner, "Tracking", "DEFAULT_TRACKING_ALGORITHM", "KCF")
    owner.app_controller.mavlink_data_manager = SimpleNamespace(get_flight_state=lambda: flight, get_data=lambda key: "Hold")
    assert (await snapshot(owner))["apply"]["reason"] == "aircraft_not_confirmed_disarmed"
    result = await act(owner, await request(owner))
    assert result["result"]["config"]["osd"]["running_enabled"] is False


async def test_tracker_failure_restores_runtime_and_previous_tracker(owner):
    old = Parameters.DEFAULT_TRACKING_ALGORITHM
    pending(owner, "Tracking", "DEFAULT_TRACKING_ALGORITHM", "KCF")
    state = await snapshot(owner)
    owner.app_controller._switch_tracker_type_with_follower_barrier.side_effect = [{"success": False}, {"success": True}]
    payload = APINativeConfigApplyRequest(**{key: state[key] for key in ("instance_id", "runtime_id", "config_generation")},
                                         confirm=True, idempotency_key="fail", reload_tier="tracker_restart")
    result = await act(owner, payload, "config_apply")
    assert result.status_code == 503
    assert Parameters.DEFAULT_TRACKING_ALGORITHM == old
    assert (await snapshot(owner))["pending"]
    assert owner.app_controller._switch_tracker_type_with_follower_barrier.call_count == 2


async def test_provider_changes_require_system_restart(owner):
    pending(owner, "GimbalTracker", "CONTROL_ENABLED", True)
    state = await snapshot(owner)
    assert state["apply"] == {"available": False, "reason": "system_restart_required", "reload_tier": "system_restart"}
    assert state["pending_changes"][0]["reload_tier"] == "system_restart"
    publication = owner.service.apply_runtime_config_tiers(
        {"immediate", "tracker_restart"}, source="dashboard_tracker_restart_test")
    assert not publication["applied"]
    assert Parameters.GimbalTracker["CONTROL_ENABLED"] is False
    assert (await snapshot(owner))["pending"]


async def test_idempotency_conflict_does_not_change_state(owner):
    payload = await request(owner)
    assert (await act(owner, payload))["executed"]
    result = await act(owner, payload.model_copy(update={"enabled": True}))
    assert result.status_code == 409
    assert b"idempotency_conflict" in result.body
    assert not owner.app_controller.osd_handler.enabled


async def test_connected_command_route_with_missing_telemetry_blocks_apply(owner):
    pending(owner, "Tracking", "DEFAULT_TRACKING_ALGORITHM", "KCF")
    owner.app_controller.px4_interface = SimpleNamespace(get_aircraft_identity=lambda: {"connected": True})
    assert (await snapshot(owner))["apply"]["reason"] == "aircraft_not_confirmed_disarmed"


async def test_effective_renderer_drift_is_pending_and_reconciles(owner):
    owner.app_controller.osd_handler.enabled = False
    state = await snapshot(owner)
    assert state["pending"]
    assert state["osd"]["saved_enabled"] is True
    assert state["osd"]["running_enabled"] is False
    assert state["pending_changes"] == [{"path": "OSD.OSD_ENABLED", "reload_tier": "immediate"}]
    payload = APINativeConfigApplyRequest(**{key: state[key] for key in ("instance_id", "runtime_id", "config_generation")},
                                         confirm=True, idempotency_key="reconcile", reload_tier="immediate")
    result = await act(owner, payload, "config_apply")
    assert not result["result"]["config"]["pending"]
    assert result["result"]["config"]["osd"]["running_enabled"] is True


async def test_operator_can_change_only_osd_not_apply_general_config(owner):
    owner.principal = APIPrincipal.bearer(subject="operator", token_id="operator", scopes={"config:read", "control:write"})
    state = await snapshot(owner)
    assert state["osd"]["can_set"]
    assert state["apply"]["reason"] == "config_permission_required"
    result = await act(owner, await request(owner))
    assert result["executed"]
    state = await snapshot(owner)
    payload = APINativeConfigApplyRequest(**{key: state[key] for key in ("instance_id", "runtime_id", "config_generation")},
                                         confirm=True, idempotency_key="not-allowed", reload_tier="immediate")
    result = await act(owner, payload, "config_apply")
    assert result.status_code == 403


async def test_viewer_cannot_read_native_config(owner):
    result = await get_config(owner, http(owner, {"status:read", "control:read"}))
    assert result.status_code == 403


async def test_operator_session_routes_pass_real_http_middleware_and_enforce_csrf(owner):
    try:
        import httpx2 as httpx
    except ImportError:
        import httpx
    from fastapi import FastAPI
    from classes.fastapi_handler import FastAPIHandler
    from tests.unit.core_app.test_api_auth_runtime import _local_policy, _runtime_with_session_user

    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.__dict__.update(owner.__dict__)
    # Exercise the production audit method and JSONL writer, not the unit stub.
    from classes.api_security_audit import APISecurityAuditLogger
    handler.__dict__.pop("_record_security_audit_event")
    audit_path = owner.service._project_root / "security-audit.jsonl"
    handler.security_audit_logger = APISecurityAuditLogger(log_path=audit_path)
    handler.app = FastAPI()
    handler.exposure_policy = _local_policy()
    handler.api_auth_runtime = _runtime_with_session_user()
    handler._setup_middleware()
    handler.app.add_api_route("/api/v1/integration/config", handler.get_native_config, methods=["GET"])
    handler.app.add_api_route("/api/v1/actions/osd-set", handler.native_osd_set_action, methods=["POST"], status_code=202)
    handler.app.add_api_route("/api/v1/actions/config-apply", handler.native_config_apply_action, methods=["POST"], status_code=202)
    runtime = handler.api_auth_runtime
    session = runtime.create_session_for_user(runtime.users_by_username["operator"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=handler.app), base_url="http://127.0.0.1:5077") as http:
        assert (await http.get("/api/v1/integration/config")).status_code == 401
        http.cookies.set(runtime.session_cookie_name, session.session_id)
        response = await http.get("/api/v1/integration/config")
        assert response.status_code == 200, response.text
        state = response.json()
        assert state["osd"]["can_set"]
        payload = {key: state[key] for key in ("instance_id", "runtime_id", "config_generation")}
        payload.update(confirm=True, idempotency_key="http-osd", enabled=False)
        assert (await http.post("/api/v1/actions/osd-set", json=payload)).status_code == 403
        headers = {runtime.csrf_header_name: session.csrf_token}
        response = await http.post("/api/v1/actions/osd-set", json=payload, headers=headers)
        assert response.status_code == 202, response.text
        assert response.json()["status"] == "success"
        assert (await http.get("/api/v1/integration/config")).json()["osd"]["running_enabled"] is False
        del payload["enabled"]
        payload["reload_tier"] = "immediate"
        response = await http.post("/api/v1/actions/config-apply", json=payload, headers=headers)
        assert response.status_code == 403
        assert "config:write" in response.text

    audit = [json.loads(line) for line in audit_path.read_text().splitlines()]
    actions = [row for row in audit if row["event_type"] == "native_config_action"]
    assert [row["outcome"] for row in actions] == ["validated", "success"]
    assert actions[-1]["status_code"] == 202


@pytest.mark.parametrize("action", ["osd_set", "config_apply"])
def test_native_config_audit_uses_full_handler_contract(owner, action):
    from classes.fastapi_handler import FastAPIHandler
    from classes.api_security_audit import APISecurityAuditLogger
    from classes.api_v1_native_config import _audit
    handler = FastAPIHandler.__new__(FastAPIHandler)
    path = owner.service._project_root / "action-audit.jsonl"
    handler.security_audit_logger = APISecurityAuditLogger(log_path=path)
    assert _audit(handler, owner.principal, action, "validated")
    assert _audit(handler, owner.principal, action, "success")
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert events[-1]["status_code"] == 202
    assert events[-1]["reason"] == action


@pytest.mark.parametrize("flight, blocked", [
    ({"fresh": True, "arm_status": "Armed"}, True),
    ({"fresh": False, "arm_status": "Armed"}, True),
    ({"fresh": True, "arm_status": "Unknown"}, True),
    ({"fresh": True, "arm_status": "Disarmed"}, False),
    ({"fresh": False, "arm_status": None}, False),
])
def test_restart_guard_uses_flight_state_without_aircraft_uid(flight, blocked):
    from classes.api_v1_native_config import _apply_block_reason
    owner = SimpleNamespace(app_controller=SimpleNamespace(
        mavlink_data_manager=SimpleNamespace(
            connection_state="connected", get_flight_state=lambda: flight,
            get_data=lambda key: "Hold" if key == "flight_mode" else None),
    ))
    assert _apply_block_reason(owner) == (
        "aircraft_not_confirmed_disarmed" if blocked else None
    )

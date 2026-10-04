"""Shared camera ownership and native movement guards; no network or motors."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Response
from fastapi.responses import JSONResponse

from classes.api_security_types import APIPrincipal
from classes.api_v1_contracts import APIGimbalControlRequest, APIGimbalControlStatus
from classes.camera_runtime import CameraRuntime
from classes.gimbal_control import get_gimbal_control_status
from classes.gimbal_types import TrackingState
from classes import api_v1_native_camera as native


@pytest.fixture
def camera(monkeypatch):
    control = SimpleNamespace(capabilities=("pan", "tilt", "stop", "select", "cancel", "set_mode"),
                              selection_mode="classic", close=Mock())
    provider = SimpleNamespace(running=True, provider_id="test_camera", manual_control=control,
        start_listening=Mock(return_value=True), stop_listening=Mock(),
        get_current_data=lambda: SimpleNamespace(angles=object(), tracking_status=SimpleNamespace(state=TrackingState.DISABLED)),
        selection_modes=lambda: [dict(id="classic", label="Camera Classic", point=True, rectangle=True)])
    app = SimpleNamespace(_tracking_session_generation=1, following_active=False,
        tracker=SimpleNamespace(is_external_tracker=False), frame_publisher=SimpleNamespace(video_context=lambda: {"source_epoch": "source-1"}))
    async def run(operation):
        return await operation()
    app._run_on_flight_event_loop = run
    runtime = CameraRuntime(app, {"ENABLED": True, "CONTROL_ENABLED": True})
    app.camera_runtime = runtime
    monkeypatch.setattr("classes.camera_runtime.create_gimbal_provider", Mock(return_value=provider))
    runtime.start()
    owner = SimpleNamespace(app_controller=app, _record_security_audit_event=Mock(return_value=True))
    owner._api_v1_error_response = lambda **kw: JSONResponse({"code": kw["code"], "detail": kw["detail"]}, status_code=kw["status_code"])
    executor = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(native, "execute_gimbal_control", executor)
    return owner, runtime, provider, executor


def actor(session="session-1"):
    principal = APIPrincipal.session(username="operator", session_id=session, role="operator")
    return SimpleNamespace(state=SimpleNamespace(api_principal=principal))


def request(runtime, key="move", **kwargs):
    fields = dict(operation="pan", direction=1, confirm=True, idempotency_key=key,
                  camera_context={"guard": runtime.guard(), "client_id": "native-1"})
    fields.update(kwargs)
    return APIGimbalControlRequest(**fields)


def test_single_provider_survives_tracker_detach_and_local_controls(camera):
    owner, runtime, provider, _ = camera
    assert runtime.get_provider() is provider
    snapshot = APIGimbalControlStatus(**get_gimbal_control_status(owner.app_controller))
    assert snapshot.target_engine == "local"
    assert snapshot.capabilities == ["pan", "tilt", "stop"]
    assert snapshot.selection_modes[0].label == "Camera Classic"
    runtime.detach_tracker()
    provider.stop_listening.assert_not_called()
    provider.manual_control.close.assert_called_once()
    assert runtime.get_provider() is provider
    runtime.close()
    provider.stop_listening.assert_called_once()


def test_disabled_owner_creates_no_provider(monkeypatch):
    factory = Mock()
    monkeypatch.setattr("classes.camera_runtime.create_gimbal_provider", factory)
    runtime = CameraRuntime(SimpleNamespace(), {"ENABLED": False})
    with pytest.raises(ValueError, match="disabled"):
        runtime.start()
    factory.assert_not_called()


async def test_native_move_scoped_idempotency_and_guard(camera):
    owner, runtime, _, execute = camera
    payload = request(runtime)
    first = await native.camera_action(owner, payload, Response(), actor(), AsyncMock())
    second = await native.camera_action(owner, payload, Response(), actor(), AsyncMock())
    assert first["status"] == "success"
    assert second["idempotent_replay"]
    execute.assert_awaited_once()
    changed = payload.model_copy(update={"direction": -1})
    conflict = await native.camera_action(owner, changed, Response(), actor(), AsyncMock())
    assert conflict.status_code == 409


async def test_source_change_rejects_move_but_original_owner_stop_works(camera):
    owner, runtime, _, execute = camera
    payload = request(runtime)
    owner.app_controller.frame_publisher.video_context = lambda: {"source_epoch": "source-2"}
    result = await native.camera_action(owner, payload, Response(), actor(), AsyncMock())
    assert result.status_code == 409
    execute.assert_not_awaited()
    stop = payload.model_copy(update={"operation": "stop", "direction": None, "idempotency_key": "stop"})
    result = await native.camera_action(owner, stop, Response(), actor(), AsyncMock())
    assert result["status"] == "success"


async def test_stop_never_redirects_to_replacement_camera(camera):
    owner, runtime, _, execute = camera
    payload = request(runtime, operation="stop", direction=None)
    runtime.camera_id = "replacement"
    result = await native.camera_action(owner, payload, Response(), actor(), AsyncMock())
    assert result.status_code == 409
    execute.assert_not_awaited()


async def test_concurrent_client_cannot_interleave_and_stop_preempts(camera):
    owner, runtime, _, execute = camera
    entered, finish = asyncio.Event(), asyncio.Event()
    async def hold(app, payload):
        if payload.operation == "stop":
            finish.set()
        else:
            entered.set()
            await finish.wait()
        return {"success": True}
    execute.side_effect = hold
    task = asyncio.create_task(native.camera_action(owner, request(runtime), Response(), actor(), AsyncMock()))
    await entered.wait()
    other = await native.camera_action(owner, request(runtime, "other"), Response(), actor("session-2"), AsyncMock())
    assert other.status_code == 409
    stop = await native.camera_action(owner, request(runtime, "stop", operation="stop", direction=None), Response(), actor("session-2"), AsyncMock())
    assert stop["status"] == "success"
    await task
    assert not runtime.motion_active


async def test_dry_run_audits_without_lease_or_transmission(camera):
    owner, runtime, _, execute = camera
    result = await native.camera_action(owner, request(runtime, dry_run=True), Response(), actor(), AsyncMock())
    assert result["status"] == "validated"
    assert not runtime.busy and not runtime.motion_active
    execute.assert_not_awaited()
    owner._record_security_audit_event.assert_called()


async def test_following_blocks_camera_movement(camera):
    owner, runtime, _, execute = camera
    owner.app_controller.following_active = True
    result = await native.camera_action(owner, request(runtime), Response(), actor(), AsyncMock())
    assert result.status_code == 409
    execute.assert_not_awaited()


async def test_failed_audit_blocks_transmission(camera):
    owner, runtime, _, execute = camera
    owner._record_security_audit_event.return_value = False
    result = await native.camera_action(owner, request(runtime), Response(), actor(), AsyncMock())
    assert result.status_code == 503
    execute.assert_not_awaited()
    assert not runtime.motion_active


def test_hold_deadline_and_foreign_client_lease(camera, monkeypatch):
    _, runtime, _, _ = camera
    now = [100.0]
    monkeypatch.setattr("classes.camera_runtime.time.monotonic", lambda: now[0])
    runtime.acquire("a", "pan")
    runtime.release()
    with pytest.raises(ValueError, match="Another"):
        runtime.acquire("b", "tilt")
    for elapsed in range(1, 10):
        now[0] = 100.0 + elapsed
        runtime.acquire("a", "pan")
        runtime.release()
    now[0] = 110.0
    with pytest.raises(ValueError, match="hold limit"):
        runtime.acquire("a", "pan")
    runtime.acquire("a", "stop")
    runtime.acquire("b", "pan")


async def test_stop_invalidates_late_move(camera):
    owner, runtime, _, execute = camera
    late = request(runtime)
    stop = request(runtime, "stop", operation="stop", direction=None)
    result = await native.camera_action(owner, stop, Response(), actor(), AsyncMock())
    assert result["status"] == "success"
    result = await native.camera_action(owner, late, Response(), actor(), AsyncMock())
    assert result.status_code == 409
    assert execute.await_count == 1


def test_mock_camera_fixture_real_routes_have_no_hardware(tmp_path):
    from fastapi.testclient import TestClient
    from tools.native_integration_fixture import create_app
    app = create_app(port=18091, no_aircraft=True, mock_camera=True, audit_path=tmp_path / "audit.jsonl")
    with TestClient(app, base_url="http://127.0.0.1:18091", client=("127.0.0.1", 32000)) as client:
        login = client.post("/api/v1/auth/login", json={"username": "operator", "password": "fixture-only"})
        assert login.status_code == 200
        status = client.get("/api/v1/gimbal/control")
        assert status.status_code == 200
        data = status.json()
        assert data["provider_id"] == "fixture_camera"
        assert data["target_engine"] == "local"
        assert data["capabilities"] == ["pan", "tilt", "roll", "zoom", "home", "stop", "manual_begin", "manual_update"]
        assert app.state.fixture_owner.app_controller.fixture_camera_commands == []

        context = client.get("/api/v1/integration/context")
        assert context.status_code == 200, context.text
        assert "camera.control.v1" in context.json()["capabilities"]
        assert "config.operations.v1" not in context.json()["capabilities"]
        target = client.get("/api/v1/integration/target-state")
        assert target.status_code == 200, target.text
        assert target.json()["target_status"] == "idle"
        catalog = client.get("/api/v1/tracking/catalog")
        assert catalog.status_code == 200, catalog.text
        assert catalog.json()["ui_trackers"][0]["target_engine"] == "local"
        csrf = login.json()["csrf_token"]
        payload = dict(operation="pan", direction=1, confirm=True, idempotency_key="mock-step",
                       camera_context={"guard": data["guard"], "client_id": "test-client"})
        result = client.post("/api/v1/actions/gimbal-control", json=payload, headers={"x-pixeagle-csrf": csrf})
        assert result.status_code == 202, result.text
        assert result.json()["status"] == "success"
        commands = app.state.fixture_owner.app_controller.fixture_camera_commands
        assert commands == [{"operation": "pan", "mock": True}, {"operation": "stop", "mock": True}]


def test_passive_camera_reports_observed_tracking_without_enabling_controls(camera):
    owner, runtime, provider, _ = camera
    owner.app_controller.tracker.is_external_tracker = True
    provider.manual_control = None
    provider.get_current_data = lambda: SimpleNamespace(angles=object(), tracking_status=SimpleNamespace(state=TrackingState.TRACKING_ACTIVE))
    snapshot = get_gimbal_control_status(owner.app_controller)
    assert snapshot["connected"] is True
    assert snapshot["tracking_state"] == "tracking_active"
    assert snapshot["enabled"] is False and snapshot["available"] is False
    assert snapshot["capabilities"] == []

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


@pytest.mark.parametrize('operation', ['stop', 'detach', 'close'])
def test_manual_ready_wait_keeps_cancellation_bounded_and_attaches_only_idle_current_executor(monkeypatch, operation):
    import threading
    from classes.camera_manual_executor import CameraManualExecutor

    entered, finish, cancelled = threading.Event(), threading.Event(), threading.Event()
    original_run = CameraManualExecutor._run
    candidates, results = [], []

    def delayed_ready(executor):
        candidates.append(executor)
        entered.set()
        if finish.wait(.75):
            original_run(executor)

    monkeypatch.setattr(CameraManualExecutor, '_run', delayed_ready)
    control = SimpleNamespace(prepare_manual=AsyncMock(), send_manual_intent=Mock(), stop=Mock(return_value=True),
                              close=Mock(), capabilities=('pan', 'stop'))
    provider = SimpleNamespace(running=True, manual_control=control, start_listening=Mock(return_value=True))
    provider.stop_listening = Mock(side_effect=lambda: setattr(provider, 'running', False))
    runtime = CameraRuntime(SimpleNamespace(), {'ENABLED': True})
    runtime.provider = provider
    old_guard = runtime.guard()
    starting = threading.Thread(target=lambda: results.append(runtime.start()))

    def cancel():
        if operation == 'stop':
            runtime.acquire('fixture', 'stop')
        elif operation == 'detach':
            runtime.detach_tracker()
        else:
            runtime.close()
        cancelled.set()

    stopping = threading.Thread(target=cancel)
    starting.start()
    try:
        try:
            assert entered.wait(1.)
            stopping.start()
            assert cancelled.wait(.1), 'Camera cancellation blocked behind executor readiness'
        finally:
            finish.set()
            starting.join(2.)
            if stopping.ident is not None:
                stopping.join(2.)
        assert not starting.is_alive() and not stopping.is_alive()
        assert results == [operation != 'close']
        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate.snapshot()['gesture_id'] is None
        control.send_manual_intent.assert_not_called()
        if operation == 'close':
            assert runtime._manual is None and candidate._closed
            assert not candidate._thread.is_alive()
        else:
            assert runtime._manual is candidate and not candidate._closed
            with pytest.raises(ValueError, match='changed'):
                runtime.validate_guard(old_guard)
            fresh = APIGimbalControlRequest(operation='manual_begin', gesture_id='fresh-gesture', sequence=0,
                intent={'axis': 'pan', 'value': 1.}, confirm=True, idempotency_key='fresh-begin',
                camera_context={'client_id': 'fixture', 'guard': runtime.guard()})
            assert runtime.manual_action('fixture', fresh)['manual']['gesture_id'] == 'fresh-gesture'
            control.send_manual_intent.assert_not_called()
    finally:
        runtime.close()
    assert not candidates[0]._thread.is_alive()


@pytest.mark.parametrize('complete', [True, False])
def test_independent_normalized_provider_requires_accepted_lifecycle_completion(complete):
    from classes.gimbal_provider import GimbalInputProvider

    class Provider:
        provider_id, display_name, protocol_name = 'normalized_fixture', 'Fixture', 'fixture'
        running, angle_sample_sequence, manual_control = False, 0, None

        def set_lifecycle_observer(self, observer):
            self.observer = observer

        def start_listening(self):
            if self.running:
                return True
            token = self.observer('starting', None)
            if token is None:
                return False
            self.running = True
            if not complete:
                return True
            if self.observer('started', token) is False:
                self.stop_listening()
                return False
            return True

        def stop_listening(self):
            if self.running:
                self.observer('stopping', None)
            self.running = False

        def get_current_data(self):
            return None

        def get_connection_status(self):
            return 'unavailable'

        def get_statistics(self):
            return {}

        def get_health_status(self):
            return {}

        def is_tracking_active(self):
            return False

        def get_provider_metadata(self):
            return {'provider': self.provider_id}

    provider = Provider()
    assert isinstance(provider, GimbalInputProvider)
    runtime = CameraRuntime(SimpleNamespace(), {'ENABLED': True})
    runtime.provider = provider
    assert runtime.start() is complete
    if not complete:
        assert runtime.angle_observation_context() is None
        assert not provider.running
        runtime.close()
        return
    first = runtime.angle_observation_context()
    assert first is not None
    assert runtime.start() and runtime.angle_observation_context() == first
    provider.stop_listening()
    assert runtime.angle_observation_context() is None
    assert provider.start_listening()
    assert runtime.angle_observation_context() != first
    runtime.close()
    assert not provider.running


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


def test_unknown_source_accepts_initial_attachment_but_not_later_replacement(camera):
    owner, runtime, _, _ = camera
    publisher = owner.app_controller.frame_publisher
    publisher.control_source_epoch = None
    captured = runtime.guard()
    publisher.control_source_epoch = "first-source"
    runtime.validate_guard(captured)
    publisher.control_source_epoch = "replacement-source"
    with pytest.raises(ValueError, match="source or target changed"):
        runtime.validate_guard(captured)
    runtime.validate_guard(captured, stop=True)

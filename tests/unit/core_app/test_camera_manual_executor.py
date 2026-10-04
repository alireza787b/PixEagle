"""Renewable control uses no camera sockets, flight loop, or model inference."""
import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import Response

from classes.api_v1_contracts import APIGimbalControlRequest, APIGimbalControlStatus
from classes.api_v1_native_camera import camera_action
from classes.camera_runtime import CameraRuntime
from classes.gimbal_control import get_gimbal_control_status
from classes.gimbal_types import TrackingState
from classes.api_security_types import APIPrincipal


def actor():
    return SimpleNamespace(state=SimpleNamespace(api_principal=APIPrincipal.session(
        username="operator", session_id="test-session", role="operator")))


class Control:
    capabilities = ("pan", "tilt", "roll", "zoom", "stop")
    selection_mode = "classic"

    def __init__(self):
        self.allow_prepare = threading.Event()
        self.allow_prepare.set()
        self.prepares = 0
        self.writes = []
        self.stop_succeeds = True

    async def prepare_manual(self, command_guard):
        self.prepares += 1
        while not self.allow_prepare.is_set():
            await asyncio.sleep(0.005)

    def send_manual_intent(self, **intent):
        self.writes.append((time.monotonic(), intent))

    def stop(self):
        self.writes.append((time.monotonic(), {"stop": True}))
        return self.stop_succeeds

    close = stop


@pytest.fixture
def manual(monkeypatch):
    control = Control()
    provider = SimpleNamespace(running=True, manual_control=control,
        get_current_data=lambda: SimpleNamespace(angles=object(), tracking_status=SimpleNamespace(state=TrackingState.DISABLED)),
        start_listening=lambda: True, stop_listening=Mock())
    app = SimpleNamespace(following_active=False, frame_publisher=SimpleNamespace(video_context=lambda: {"source_epoch": "a"}))
    app._run_on_flight_event_loop = Mock(side_effect=AssertionError("Manual commands entered flight loop"))
    runtime = CameraRuntime(app, {"ENABLED": True, "CONTROL_ENABLED": True})
    app.camera_runtime = runtime
    monkeypatch.setattr("classes.camera_runtime.create_gimbal_provider", lambda _: provider)
    runtime.start()
    yield runtime, control
    runtime.close()


def payload(runtime, operation="manual_begin", gesture="g", sequence=0, value=1, guard=None):
    fields = dict(operation=operation, gesture_id=gesture, sequence=sequence,
                  camera_context={"client_id": "client", "guard": guard or runtime.guard()},
                  confirm=True, idempotency_key=f"{gesture}-{sequence}-{operation}")
    if operation != "stop":
        fields["intent"] = {"axis": "pan", "value": value}
    return APIGimbalControlRequest(**fields)


def wait_for(predicate, timeout=1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    assert predicate()


def moves(control):
    return [intent for _, intent in control.writes if "stop" not in intent]


def test_begin_never_moves_and_expires_without_update(manual):
    runtime, control = manual
    result = runtime.manual_action("a", payload(runtime))
    assert result["manual"]["state"] == "preparing"
    wait_for(lambda: control.prepares == 1)
    assert moves(control) == []
    wait_for(lambda: runtime.manual_snapshot()["state"] == "expired")
    assert moves(control) == []
    assert runtime.manual_snapshot()["reason"] == "lease_expired"


def test_latest_intent_replaces_pending_handshake_and_stops_under_owner_stall(manual):
    runtime, control = manual
    control.allow_prepare.clear()
    runtime.manual_action("a", payload(runtime))
    runtime.manual_action("a", payload(runtime, "manual_update", sequence=1, value=1))
    runtime.manual_action("a", payload(runtime, "manual_update", sequence=2, value=-0.5))
    control.allow_prepare.set()
    wait_for(lambda: len(moves(control)) == 1)
    assert moves(control) == [{"axis": "pan", "value": -0.5}]
    # This thread represents the blocked model/flight loop. Watchdog must run anyway.
    time.sleep(0.5)
    assert runtime.manual_snapshot()["state"] == "expired"
    assert control.writes[-1][1] == {"stop": True}
    assert control.prepares == 1


def test_release_during_prepare_never_starts_motion(manual):
    runtime, control = manual
    control.allow_prepare.clear()
    runtime.manual_action("a", payload(runtime))
    runtime.manual_action("a", payload(runtime, "manual_update", sequence=1))
    runtime.manual_action("a", payload(runtime, "stop", sequence=2))
    control.allow_prepare.set()
    wait_for(lambda: runtime.manual_snapshot()["state"] == "stopped")
    assert moves(control) == []


def test_stop_before_begin_retires_gesture_and_captured_generation(manual):
    runtime, control = manual
    guard = runtime.guard()
    runtime.manual_action("a", payload(runtime, "stop", sequence=2, guard=guard))
    with pytest.raises(ValueError):
        runtime.manual_action("a", payload(runtime, guard=guard))
    with pytest.raises(ValueError, match="already ended"):
        runtime.manual_action("a", payload(runtime))
    assert moves(control) == []


def test_scoped_old_stop_does_not_cancel_new_gesture(manual):
    runtime, control = manual
    old = runtime.guard()
    runtime.manual_action("a", payload(runtime))
    runtime.manual_action("a", payload(runtime, "stop", sequence=1))
    runtime.manual_action("a", payload(runtime, gesture="new"))
    runtime.manual_action("a", payload(runtime, "stop", sequence=2, guard=old))
    assert runtime.manual_snapshot()["gesture_id"] == "new"
    assert runtime.manual_snapshot()["state"] == "preparing"


def test_reverse_and_stale_updates(manual):
    runtime, control = manual
    runtime.manual_action("a", payload(runtime))
    runtime.manual_action("a", payload(runtime, "manual_update", sequence=1))
    wait_for(lambda: len(moves(control)) == 1)
    runtime.manual_action("a", payload(runtime, "manual_update", sequence=2, value=-1))
    wait_for(lambda: len(moves(control)) == 2)
    with pytest.raises(ValueError, match="stale"):
        runtime.manual_action("a", payload(runtime, "manual_update", sequence=1))
    assert control.prepares == 1
    assert moves(control)[-1]["value"] == -1


def test_lifecycle_excludes_manual_and_cancels_before_change(manual):
    runtime, _ = manual
    with runtime.lifecycle_reservation():
        with pytest.raises(ValueError, match="lifecycle"):
            runtime.manual_action("a", payload(runtime))
    runtime.manual_action("a", payload(runtime))
    with pytest.raises(ValueError, match="Release"):
        with runtime.lifecycle_reservation():
            pass
    with runtime.lifecycle_reservation(cancel_manual=True):
        assert runtime.manual_snapshot()["state"] == "stopped"
        with pytest.raises(ValueError):
            runtime.manual_action("a", payload(runtime, gesture="new"))


def test_source_change_stops_and_following_denies_admission(manual):
    runtime, control = manual
    runtime.manual_action("a", payload(runtime))
    runtime.app.frame_publisher.video_context = lambda: {"source_epoch": "new"}
    wait_for(lambda: runtime.manual_snapshot()["state"] == "failed")
    assert control.writes[-1][1] == {"stop": True}
    runtime.app.following_active = True
    with pytest.raises(ValueError, match="following"):
        runtime.manual_action("a", payload(runtime, gesture="next"))


def test_stop_transmission_failure_is_not_success(manual):
    runtime, control = manual
    runtime.manual_action("a", payload(runtime))
    control.stop_succeeds = False
    result = runtime.manual_action("a", payload(runtime, "stop", sequence=1))
    assert not result["success"]
    assert result["manual"]["reason"] == "stop_transmission_failed"


async def test_real_native_facade_bypasses_flight_loop_and_has_typed_snapshot(manual):
    runtime, _ = manual
    owner = SimpleNamespace(app_controller=runtime.app, _record_security_audit_event=Mock(return_value=True))
    result = await camera_action(owner, payload(runtime), Response(), actor(), None)
    assert result["status"] == "success"
    assert result["result"]["manual"]["gesture_id"] == "g"
    runtime.app._run_on_flight_event_loop.assert_not_called()
    state = APIGimbalControlStatus(**get_gimbal_control_status(runtime.app))
    assert "manual_update" in state.capabilities
    assert state.telemetry.zoom_available is False
    assert state.manual.lease_timeout_ms == 350


def test_delayed_admission_never_dispatches_old_input(manual):
    runtime, control = manual
    with pytest.raises(ValueError, match="expired before admission"):
        runtime.manual_action("a", payload(runtime), received_at=time.monotonic() - 1)
    assert moves(control) == []


def test_foreign_client_cannot_renew_and_stop_failure_requires_retry(manual):
    runtime, control = manual
    runtime.manual_action("a", payload(runtime))
    with pytest.raises(ValueError, match="not active"):
        runtime.manual_action("b", payload(runtime, "manual_update", sequence=1))
    control.stop_succeeds = False
    runtime.manual_action("a", payload(runtime, "stop", sequence=2))
    with pytest.raises(ValueError, match="Retry"):
        runtime.manual_action("a", payload(runtime, gesture="new"))
    control.stop_succeeds = True
    runtime.manual_action("a", payload(runtime, "stop", sequence=3))
    runtime.manual_action("a", payload(runtime, gesture="new"))
    assert runtime.manual_snapshot()["gesture_id"] == "new"


def test_manual_request_rejects_unbounded_and_ambiguous_inputs(manual):
    from pydantic import ValidationError
    runtime, _ = manual
    base = payload(runtime).model_dump(exclude_none=True)
    for change in ({"sequence": True}, {"sequence": 1}, {"intent": {"axis": "pan", "value": float("nan")}},
                   {"intent": {"axis": "pan", "value": 2}}, {"direction": 1}, {"camera_context": None}):
        with pytest.raises(ValidationError):
            APIGimbalControlRequest(**{**base, **change})


def test_old_scoped_stop_does_not_stop_new_discrete_operation(manual):
    runtime, control = manual
    old = runtime.guard()
    runtime.manual_action("a", payload(runtime))
    runtime.manual_action("a", payload(runtime, "stop", sequence=1))
    runtime.acquire("b", "home")
    before = len(control.writes)
    runtime.manual_action("a", payload(runtime, "stop", sequence=2, guard=old))
    assert len(control.writes) == before
    runtime.release()


def test_stop_failure_blocks_following_and_legacy_control(manual):
    runtime, control = manual
    runtime.manual_action("a", payload(runtime))
    control.stop_succeeds = False
    with pytest.raises(ValueError, match="Stop failed"):
        with runtime.lifecycle_reservation(cancel_manual=True):
            pytest.fail("Unsafe lifecycle entered")
    with pytest.raises(ValueError, match="Retry"):
        with runtime.lifecycle_reservation():
            pytest.fail("Following admitted with unresolved Stop")
    with pytest.raises(ValueError, match="Retry"):
        runtime.acquire("b", "pan")


def test_frame_transaction_cannot_block_manual_watchdog(manual):
    from classes.frame_publisher import FramePublisher
    runtime, control = manual
    publisher = FramePublisher()
    publisher.invalidate_source("a")
    runtime.app.frame_publisher = publisher
    runtime.manual_action("a", payload(runtime))
    runtime.manual_action("a", payload(runtime, "manual_update", sequence=1))
    wait_for(lambda: len(moves(control)) == 1)
    with publisher.selection_transaction():
        time.sleep(0.5)
        assert runtime.manual_snapshot()["state"] == "expired"
        assert control.writes[-1][1] == {"stop": True}


def test_renewed_hold_continues_past_old_five_second_cutoff(manual):
    runtime, control = manual
    runtime.manual_action("a", payload(runtime))
    end = time.monotonic() + 5.1
    sequence = 0
    while time.monotonic() < end:
        sequence += 1
        runtime.manual_action("a", payload(runtime, "manual_update", sequence=sequence))
        time.sleep(0.08)
    assert runtime.manual_snapshot()["state"] == "moving"
    assert control.prepares == 1
    runtime.manual_action("a", payload(runtime, "stop", sequence=sequence+1))
    assert runtime.manual_snapshot()["state"] == "stopped"


def test_real_routes_accept_manual_and_reject_late_begin_after_stop(tmp_path):
    from fastapi.testclient import TestClient
    from tools.native_integration_fixture import create_app
    app = create_app(port=18092, no_aircraft=True, mock_camera=True, audit_path=tmp_path / "audit.jsonl")
    with TestClient(app, base_url="http://127.0.0.1:18092", client=("127.0.0.1", 32000)) as client:
        login = client.post("/api/v1/auth/login", json={"username": "operator", "password": "fixture-only"})
        assert login.status_code == 200
        headers = {"x-pixeagle-csrf": login.json()["csrf_token"]}
        runtime = app.state.fixture_owner.app_controller.camera_runtime
        begin = payload(runtime)
        stop = payload(runtime, "stop", sequence=2)
        result = client.post("/api/v1/actions/gimbal-control", json=stop.model_dump(exclude_none=True), headers=headers)
        assert result.status_code == 202
        result = client.post("/api/v1/actions/gimbal-control", json=begin.model_dump(exclude_none=True), headers=headers)
        assert result.status_code == 409
        next_begin = payload(runtime, gesture="next")
        result = client.post("/api/v1/actions/gimbal-control", json=next_begin.model_dump(exclude_none=True), headers=headers)
        assert result.status_code == 202, result.text
        assert result.json()["result"]["manual"]["state"] == "preparing"
        assert app.state.fixture_owner.app_controller.fixture_camera_commands == []
        update = payload(runtime, "manual_update", gesture="next", sequence=1)
        result = client.post("/api/v1/actions/gimbal-control", json=update.model_dump(exclude_none=True), headers=headers)
        assert result.status_code == 202, result.text
        wait_for(lambda: bool(app.state.fixture_owner.app_controller.fixture_camera_commands))
        assert app.state.fixture_owner.app_controller.fixture_camera_commands[0] == {
            "operation": "pan", "value": 1, "mock": True}


def test_emergency_stop_releases_legacy_client_lease(manual):
    runtime, _ = manual
    runtime.acquire("old-client", "pan")
    runtime.release()
    stop = APIGimbalControlRequest(operation="stop", confirm=True, idempotency_key="emergency-stop",
        camera_context={"client_id": "new-client", "guard": runtime.guard()})
    runtime.manual_action("new-client", stop)
    runtime.manual_action("new-client", payload(runtime, gesture="new"))
    assert runtime.manual_snapshot()["gesture_id"] == "new"


@pytest.mark.parametrize("blocked_stage", ["capture", "inference"])
@pytest.mark.parametrize("termination", ["operator_stop", "lease_expiry"])
def test_manual_stop_deadlines_with_blocked_owner(tmp_path, blocked_stage, termination):
    """Measure public-route Stop and independent expiry; no hardware or listeners."""
    import json
    from fastapi.testclient import TestClient
    from tools.native_integration_fixture import create_app

    app = create_app(port=18093, no_aircraft=True, mock_camera=True, audit_path=tmp_path / "audit.jsonl")
    owner = app.state.fixture_owner.app_controller
    runtime = owner.camera_runtime
    stops = []
    original_stop = runtime.provider.manual_control.stop

    def timed_stop():
        stops.append(time.monotonic())
        return original_stop()

    runtime.provider.manual_control.stop = timed_stop
    loop = asyncio.new_event_loop()
    entered, release = threading.Event(), threading.Event()

    def block():
        entered.set()
        # A finite bound ensures a scheduling regression fails rather than hangs.
        release.wait(2)

    def owner_thread():
        asyncio.set_event_loop(loop)
        try:
            if blocked_stage == "capture":
                # FlowController currently captures before pumping its owner loop.
                block()
            else:
                # Smart processing currently blocks inside the owner loop.
                loop.call_soon(block)
            loop.run_forever()
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    thread = threading.Thread(target=owner_thread, name=f"blocked-{blocked_stage}", daemon=True)

    async def schedule_owner(operation):
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(operation(), loop))

    owner._run_on_flight_event_loop = schedule_owner
    try:
        with TestClient(app, base_url="http://127.0.0.1:18093", client=("127.0.0.1", 32000)) as client:
            login = client.post("/api/v1/auth/login", json={"username": "operator", "password": "fixture-only"})
            assert login.status_code == 200
            headers = {"x-pixeagle-csrf": login.json()["csrf_token"]}
            thread.start()
            assert entered.wait(1)
            path = "/api/v1/actions/gimbal-control"
            begin = client.post(path, json=payload(runtime).model_dump(exclude_none=True), headers=headers)
            assert begin.status_code == 202, begin.text
            update = client.post(path, json=payload(runtime, "manual_update", sequence=1).model_dump(exclude_none=True), headers=headers)
            assert update.status_code == 202, update.text
            accepted = update.json()["result"]["manual"]["accepted_at_monotonic"]
            wait_for(lambda: any(command.get("value") == 1 for command in owner.fixture_camera_commands))
            assert not stops
            if termination == "operator_stop":
                request_started = time.monotonic()
                result = client.post(path, json=payload(runtime, "stop", sequence=2).model_dump(exclude_none=True), headers=headers)
                response_finished = time.monotonic()
                assert result.status_code == 202, result.text
                assert result.json()["status"] == "success"
                assert stops
                measured_ms = (stops[0] - request_started) * 1000
                limit_ms = 100
                extra = {"http_round_trip_ms": (response_finished - request_started) * 1000}
            else:
                wait_for(lambda: bool(stops), timeout=1)
                measured_ms = (stops[0] - accepted) * 1000
                limit_ms = 400
                assert runtime.manual_snapshot()["state"] == "expired"
                assert measured_ms >= 350
                extra = {}
            assert not release.is_set()
            print("CAMERA_TIMING " + json.dumps(dict(
                blocked_stage=blocked_stage, termination=termination,
                measured_ms=measured_ms, limit_ms=limit_ms, **extra), sort_keys=True))
            assert 0 <= measured_ms <= limit_ms
    finally:
        release.set()
        if thread.ident is not None:
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=1)
            assert not thread.is_alive()
        else:
            loop.close()

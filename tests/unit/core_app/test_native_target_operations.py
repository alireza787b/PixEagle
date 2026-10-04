"""No-aircraft native target guards against real retained publisher pixels."""

import asyncio
from contextlib import nullcontext
import threading
import time
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from fastapi import Response

from classes.api_security_types import APIPrincipal
from classes.api_v1_contracts import (
    APIActionRequest, APIGimbalControlRequest, APITrackingStartRequest, APITrackingModeRequest,
)
from classes.api_v1_native_targets import (
    NativeTargetError, _validate_camera_selection_commit, _validate_frame,
    native_target_action, target_state, TARGET_SCOPES,
)
from classes.fastapi_handler import FastAPIHandler
from classes.frame_publisher import CaptureStamp, FramePublisher
from classes.parameters import Parameters


pytestmark = pytest.mark.unit


async def test_catalog_aliases_share_factory_request_and_unavailable_state(owner, monkeypatch):
    from classes.api_v1_read_routes import get_tracking_catalog

    catalog = {
        "ui_trackers": [
            {"name": "CSRTTracker", "factory_key": "CSRT", "available": True},
            {"name": "GimbalTracker", "factory_key": "Gimbal", "available": True},
        ],
        "tracker_types": {
            "CSRT": {"name": "CSRT", "request_tracker_type": "CSRT", "available": True},
            "Gimbal": {"name": "Gimbal", "request_tracker_type": "Gimbal", "available": True},
        },
    }
    owner._get_tracking_catalog_snapshot = lambda: catalog
    monkeypatch.setattr("classes.api_v1_native_targets.classic_tracker_availability",
                        lambda key: {"available": True, "reason": None})
    monkeypatch.setattr("classes.api_v1_native_targets.external_selection_availability",
                        lambda owner: {"available": False, "reason": "Camera controls are not configured."})
    result = await get_tracking_catalog(owner)
    for schema_row, key in zip(result["ui_trackers"], ("CSRT", "Gimbal")):
        compatibility_row = result["tracker_types"][key]
        assert schema_row["factory_key"] == compatibility_row["factory_key"] == key
        assert schema_row["request_tracker_type"] == compatibility_row["request_tracker_type"]
        assert schema_row["available"] == compatibility_row["available"] == (key == "CSRT")
        assert schema_row["unavailable_reason"] == compatibility_row["unavailable_reason"]


@pytest.mark.parametrize("factory_key", ["dlib", "VitTrack", "DaSiamRPN", "CSRT"])
def test_catalog_checks_optional_prerequisites_without_creating_tracker(monkeypatch, factory_key):
    from classes.api_v1_native_targets import classic_tracker_availability
    from classes.trackers.tracker_factory import TRACKER_REGISTRY
    from classes.tracker_artifacts import TrackerArtifactError
    import cv2

    constructor = Mock(side_effect=AssertionError("Catalog must not construct trackers"))
    monkeypatch.setattr(TRACKER_REGISTRY[factory_key], "__init__", constructor)
    if factory_key == "dlib":
        monkeypatch.setattr("classes.trackers.dlib_tracker.DLIB_AVAILABLE", False)
    elif factory_key == "CSRT":
        monkeypatch.delattr(cv2, "TrackerCSRT_create", raising=False)
    elif factory_key == "VitTrack":
        monkeypatch.setattr("classes.tracker_artifacts.resolve_tracker_artifact",
                            Mock(side_effect=TrackerArtifactError("missing")))
    else:
        monkeypatch.setattr(TRACKER_REGISTRY[factory_key], "_resolve_artifacts",
                            Mock(side_effect=TrackerArtifactError("unverified")))
    result = classic_tracker_availability(factory_key)
    assert result["available"] is False and result["reason"]
    constructor.assert_not_called()


async def test_catalog_compatibility_survives_missing_schema_manager(owner, monkeypatch):
    from classes.api_v1_native_targets import apply_catalog_availability

    monkeypatch.setattr("classes.schema_manager.get_schema_manager",
                        Mock(side_effect=RuntimeError("schema unavailable")))
    monkeypatch.setattr("classes.api_v1_native_targets.classic_tracker_availability",
                        lambda key: {"available": True, "reason": None})
    catalog = {"tracker_types": {"CSRT": {"name": "CSRT", "available": True}}}
    await apply_catalog_availability(owner, catalog)
    assert catalog["tracker_types"]["CSRT"]["factory_key"] == "CSRT"
    assert catalog["tracker_types"]["CSRT"]["available"]


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setattr(Parameters, "USE_MAVLINK2REST", True)
    monkeypatch.setattr(Parameters, "ENABLE_STREAMING", True)
    command = dict(source="mavsdk", connected=False, connection_generation="0", autopilot_uid=None)
    telemetry = dict(source="mavlink2rest", connected=False, fresh=False,
                     connection_generation="0", autopilot_uid=None, system_id=None, component_id=None)
    handler = FastAPIHandler.__new__(FastAPIHandler)
    app = SimpleNamespace(
        _tracker_model_state_lock=threading.RLock(), _follower_state_lock=asyncio.Lock(),
        _tracking_session_generation=0, current_tracker_type="CSRT", tracker=SimpleNamespace(is_external_tracker=False),
        following_active=False, tracking_started=False, smart_mode_active=False, smart_tracker=None,
        px4_interface=SimpleNamespace(get_aircraft_identity=lambda: dict(command), connect=Mock()),
        mavlink_data_manager=SimpleNamespace(get_aircraft_identity=lambda: dict(telemetry)),
        shutdown_flag=False, selected_frames=[], following_mutations=Mock(),
    )

    async def run(operation):
        return await operation()

    def start(bbox, *, frame):
        assert app._follower_state_lock.locked()
        app.selected_frames.append((frame.copy(), dict(bbox)))
        app._tracking_session_generation += 1
        app.tracking_started = True
        return {"started": True}

    def cancel():
        assert app._follower_state_lock.locked()
        app._tracking_session_generation += 1
        app.tracking_started = False

    app._run_on_flight_event_loop = run
    app._start_tracking_with_follower_barrier = start
    app._cancel_activities_locked = cancel
    handler.app_controller = app
    handler.frame_publisher = FramePublisher()
    handler._record_security_audit_event = Mock(return_value=True)
    handler.command_test, handler.telemetry_test = command, telemetry
    handler.principal_test = APIPrincipal.bearer(subject="operator-a", token_id="a", scopes=TARGET_SCOPES)
    publish(handler, 11)
    return handler


def publish(owner, value, *, age=0, candidates=()):
    owner.frame_publisher.publish(
        np.full((20, 40, 3), value+100, dtype=np.uint8), None,
        analysis_frame=np.full((80, 160, 3), value, dtype=np.uint8),
        target_revision=owner.app_controller._tracking_session_generation, candidates=candidates,
        capture=CaptureStamp("replay", str(value), time.monotonic()-age, "fresh"),
    )
    return owner.frame_publisher.get_latest()


def context(owner, *, frame=True):
    result = dict(guard=target_state(owner, owner.principal_test)["guard"], binding_mode="companion_only")
    if frame:
        stamped = owner.frame_publisher.get_latest()
        result["frame"] = {"provenance": stamped.provenance(), "selection_geometry": dict(stamped.selection_geometry)}
    return result


def start_request(owner, **kwargs):
    payload = dict(confirm=True, idempotency_key="test-key", native_context=context(owner),
                   bbox=dict(x=.25, y=.25, width=.25, height=.25, coordinate_space="normalized"))
    payload.update(kwargs)
    return APITrackingStartRequest(**payload)


async def execute(owner, request, action="tracking_start"):
    response = Response()
    result = await native_target_action(owner, request, response,
        SimpleNamespace(state=SimpleNamespace(api_principal=owner.principal_test)), action)
    return result, response


def error(result, code):
    assert result.status_code in (401, 403, 409, 422, 503)
    assert code in result.body.decode()


async def test_original_clean_displayed_pixels_survive_later_publication(owner):
    request = start_request(owner)
    publish(owner, 23)
    result, response = await execute(owner, request)
    assert response.status_code == 202 and result["status"] == "success"
    pixels, bbox = owner.app_controller.selected_frames[0]
    assert np.all(pixels == 11) and bbox == dict(x=40, y=20, width=40, height=20)
    assert result["result"]["target_state"]["target_revision"] == "1"
    assert result["audit_event"]["actor"] == dict(kind="bearer", subject="operator-a")
    owner.app_controller.px4_interface.connect.assert_not_called()
    owner.app_controller.following_mutations.assert_not_called()


@pytest.mark.parametrize("change,code", [
    (lambda o: setattr(o.app_controller, "_tracking_session_generation", 2), "target_revision_stale"),
    (lambda o: o.command_test.update(connected=True, connection_generation="1"), "native_context_stale"),
    (lambda o: o.telemetry_test.update(connected=True, connection_generation="1"), "native_context_stale"),
    (lambda o: o.command_test.update(connection_generation="2"), "native_context_stale"),
    (lambda o: o.frame_publisher.invalidate_source("another-source"), "native_context_stale"),
])
async def test_changes_reject_without_any_tracker_or_aircraft_mutation(owner, change, code):
    request = start_request(owner)
    change(owner)
    result, _ = await execute(owner, request)
    error(result, code)
    assert not owner.app_controller.selected_frames
    owner.app_controller.px4_interface.connect.assert_not_called()


async def test_classic_retarget_is_admitted_during_following_without_restarting_it(owner):
    owner.app_controller.following_active = True
    state = target_state(owner, owner.principal_test)
    assert "tracking_start" in state["allowed_actions"]
    assert "tracking_stop" not in state["allowed_actions"]
    assert "tracker_switch" not in state["allowed_actions"]

    result, response = await execute(owner, start_request(owner))
    assert response.status_code == 202 and result["status"] == "success"
    assert len(owner.app_controller.selected_frames) == 1
    assert owner.app_controller.following_active
    owner.app_controller.following_mutations.assert_not_called()


async def test_camera_action_commits_after_its_following_handshake(owner, monkeypatch):
    app = owner.app_controller
    app.tracker.is_external_tracker = True
    app.current_tracker_type = "Gimbal"
    app.following_active = True
    camera_guard = {"camera_id": "camera-a", "camera_generation": "1", "source_epoch": "replay"}
    validated_guards = []
    app.camera_runtime = SimpleNamespace(
        lifecycle_reservation=lambda **_: nullcontext(),
        guard=lambda: dict(camera_guard),
        validate_guard=lambda guard: validated_guards.append(guard),
    )
    monkeypatch.setattr("classes.api_v1_native_targets.external_selection_availability",
                        lambda _: {"available": True, "reason": None})
    monkeypatch.setattr("classes.api_v1_native_targets.get_gimbal_control_status",
                        lambda _: {"available": False, "enabled": True, "connected": True,
                                   "tracking_state": "tracking_active", "selection_mode": "classic",
                                   "selection_modes": [], "capabilities": ["select"]})
    observed = []
    prepared = object()
    monkeypatch.setattr("classes.gimbal_control.prepare_gimbal_selection", lambda *_, **__: prepared)

    async def camera_execute(_, __, *, barrier_held, selection_guard, selection_orientation, prepared_selection):
        assert barrier_held and app._follower_state_lock.locked()
        assert prepared_selection is prepared
        app._tracking_session_generation += 1
        admitted_at = time.monotonic()
        with monkeypatch.context() as patch:
            patch.setattr("classes.api_v1_native_targets.time.monotonic", lambda: admitted_at + 2.0)
            with selection_guard(str(app._tracking_session_generation)):
                observed.append(app._tracking_session_generation)
        return {"success": True}

    monkeypatch.setattr("classes.gimbal_control.execute_gimbal_control", camera_execute)
    request = APIGimbalControlRequest(
        operation="select", x=.5, y=.5, confirm=True, idempotency_key="camera-retarget",
        native_context=context(owner),
    )
    result, response = await execute(owner, request, "gimbal_control")
    assert response.status_code == 202 and result["status"] == "success"
    assert observed == [1] and app.following_active
    assert validated_guards == [camera_guard]
    assert owner._record_security_audit_event.call_args.kwargs["outcome"] == "success"


async def test_invalid_native_camera_geometry_cannot_cancel_manual_ownership(owner, monkeypatch):
    app = owner.app_controller
    app.tracker.is_external_tracker = True
    app.current_tracker_type = "Gimbal"
    app.following_active = True
    reserve = Mock(side_effect=AssertionError("Invalid selection cannot enter ownership transition"))
    app.camera_runtime = SimpleNamespace(lifecycle_reservation=reserve)
    monkeypatch.setattr("classes.api_v1_native_targets.external_selection_availability",
                        lambda _: {"available": True, "reason": None})
    monkeypatch.setattr("classes.api_v1_native_targets.get_gimbal_control_status",
                        lambda _: {"available": False, "enabled": True, "connected": True,
                                   "tracking_state": "tracking_active", "selection_mode": "classic",
                                   "selection_modes": [], "capabilities": ["select"]})

    def invalid(*_, **__):
        raise ValueError("Select slightly farther from the image edge")

    monkeypatch.setattr("classes.gimbal_control.prepare_gimbal_selection", invalid)
    request = APIGimbalControlRequest(operation="select", x=.99, y=.5, confirm=True,
                                     idempotency_key="bad-edge", native_context=context(owner))
    result, _ = await execute(owner, request, "gimbal_control")
    assert result.status_code == 422
    assert app.following_active and app._tracking_session_generation == 0
    reserve.assert_not_called()


async def test_unbound_target_selection_with_aircraft_connected_never_starts_following(owner):
    owner.command_test.update(connected=True, connection_generation="1", autopilot_uid="42")
    owner.telemetry_test.update(connected=True, connection_generation="1", autopilot_uid="42",
                                system_id=1, component_id=1)
    publish(owner, 12)
    request = start_request(owner)
    result, response = await execute(owner, request)
    assert response.status_code == 202 and result["status"] == "success"
    assert len(owner.app_controller.selected_frames) == 1
    owner.app_controller.px4_interface.connect.assert_not_called()
    owner.app_controller.following_mutations.assert_not_called()


async def test_revision_checked_after_waiting_for_owner_barrier(owner):
    request = start_request(owner)
    await owner.app_controller._follower_state_lock.acquire()
    task = asyncio.create_task(execute(owner, request))
    await asyncio.sleep(0)
    owner.app_controller._tracking_session_generation += 1
    owner.app_controller._follower_state_lock.release()
    result, _ = await task
    error(result, "target_revision_stale")
    assert not owner.app_controller.selected_frames


async def test_source_retirement_cannot_interleave_validated_tracker_commit(owner):
    request = start_request(owner)
    entered, attempted, retired = threading.Event(), threading.Event(), threading.Event()
    start = owner.app_controller._start_tracking_with_follower_barrier

    def reset():
        assert entered.wait(2)
        attempted.set()
        owner.frame_publisher.invalidate_source("replacement")
        retired.set()

    def commit(bbox, *, frame):
        entered.set()
        assert attempted.wait(2)
        assert not retired.wait(.025)
        return start(bbox, frame=frame)

    owner.app_controller._start_tracking_with_follower_barrier = commit
    worker = threading.Thread(target=reset)
    worker.start()
    result, _ = await execute(owner, request)
    worker.join(2)
    assert not worker.is_alive() and retired.is_set()
    assert result["status"] == "success" and len(owner.app_controller.selected_frames) == 1
    assert owner.frame_publisher.get_latest() is None


@pytest.mark.parametrize("field,value", [("frame_id", "33"), ("variant", "raw"),
                                         ("encoded_width", 50), ("source_epoch", "other")])
async def test_metadata_tampering_cannot_relabel_retained_pixels(owner, field, value):
    captured = context(owner)
    captured["frame"]["provenance"][field] = value
    result, _ = await execute(owner, start_request(owner, native_context=captured))
    error(result, "frame_context_invalid")
    assert not owner.app_controller.selected_frames


async def test_expired_retained_frame_does_not_fall_back_to_latest(owner, monkeypatch):
    request = start_request(owner)
    captured_at = owner.frame_publisher.get_latest().capture.captured_at
    monkeypatch.setattr("classes.api_v1_native_targets.time.monotonic", lambda: captured_at+2)
    result, _ = await execute(owner, request)
    error(result, "frame_expired")
    assert not owner.app_controller.selected_frames


async def test_slow_durable_audit_cannot_commit_an_expired_frame(owner, monkeypatch):
    request = start_request(owner)
    now = [owner.frame_publisher.get_latest().capture.captured_at+.01]
    monkeypatch.setattr("classes.api_v1_native_targets.time.monotonic", lambda: now[0])
    def delayed_audit(**kwargs):
        now[0] += 2
        return True
    owner._record_security_audit_event.side_effect = delayed_audit
    result, _ = await execute(owner, request)
    error(result, "frame_expired")
    assert not owner.app_controller.selected_frames


def test_camera_retarget_commit_accepts_its_reserved_revision_after_frame_age(owner, monkeypatch):
    request = start_request(owner)
    before = target_state(owner, owner.principal_test)
    entry = _validate_frame(owner, request, before)
    admitted_at = time.monotonic()
    owner.app_controller._tracking_session_generation = 1
    monkeypatch.setattr("classes.api_v1_native_targets.time.monotonic", lambda: admitted_at + 2.0)

    _validate_camera_selection_commit(
        owner, request, owner.principal_test, entry, "1", admitted_at,
    )

    owner.app_controller._tracking_session_generation = 2
    with pytest.raises(NativeTargetError, match="changed during selection"):
        _validate_camera_selection_commit(
            owner, request, owner.principal_test, entry, "1", admitted_at,
        )
    owner.app_controller._tracking_session_generation = 1
    owner.frame_publisher.invalidate_source("replacement")
    with pytest.raises(NativeTargetError, match="video source changed"):
        _validate_camera_selection_commit(
            owner, request, owner.principal_test, entry, "1", admitted_at,
        )


def test_admitted_camera_selection_cannot_commit_after_shutdown_begins(owner):
    request = start_request(owner)
    before = target_state(owner, owner.principal_test)
    entry = _validate_frame(owner, request, before)
    admitted_at = time.monotonic()
    owner.app_controller._tracking_session_generation = 1
    owner.app_controller.shutdown_flag = True
    with pytest.raises(NativeTargetError, match="cancelled during application shutdown") as rejected:
        _validate_camera_selection_commit(
            owner, request, owner.principal_test, entry, "1", admitted_at,
        )
    assert rejected.value.code == "application_shutting_down"


async def test_bounded_eviction_is_explicit(owner):
    request = start_request(owner)
    owner.frame_publisher.selection_max_frames = 1
    publish(owner, 23)
    result, _ = await execute(owner, request)
    error(result, "frame_evicted")
    assert not owner.app_controller.selected_frames


async def test_tracking_cancel_needs_no_video_and_never_stops_following(owner):
    owner.app_controller.tracking_started = True
    request = APIActionRequest(confirm=True, idempotency_key="cancel", native_context=context(owner, frame=False))
    result, _ = await execute(owner, request, "tracking_stop")
    assert result["status"] == "success"
    assert not owner.app_controller.tracking_started
    owner.app_controller.following_mutations.assert_not_called()


async def test_real_automatic_loss_remains_visible_until_explicit_cancel(owner):
    from classes.app_controller import AppController
    app = owner.app_controller
    for name in ("_tracking_session_is_current", "_reset_tracking_failure_state",
                 "_advance_tracking_session_generation", "_terminate_classic_tracking_loss_locked",
                 "_cancel_activities_locked"):
        setattr(app, name, MethodType(getattr(AppController, name), app))
    app.tracker.stop_tracking = Mock()
    app.tracker.clear_external_override = Mock()
    app.tracker.reset = Mock()
    app.setpoint_sender = None
    app.tracking_started = True
    app.tracking_failure_start_time = time.monotonic()-6
    assert app._terminate_classic_tracking_loss_locked("recovery_timeout", 6, expected_generation=0)
    lost = target_state(owner, owner.principal_test)
    assert not lost["tracking_active"] and lost["target_status"] == "lost"
    assert "target_lost_recovery_timeout" in lost["reason_codes"]
    assert "tracking_start" in lost["allowed_actions"] and "tracking_stop" in lost["allowed_actions"]
    request = APIActionRequest(confirm=True, idempotency_key="cancel-lost", native_context=context(owner, frame=False))
    result, _ = await execute(owner, request, "tracking_stop")
    assert result["status"] == "success"
    after = result["result"]["target_state"]
    assert after["target_status"] == "idle" and not after["tracking_active"]
    assert "target_lost_recovery_timeout" not in after["reason_codes"]
    app._last_target_loss_reason = "recovery_timeout"
    app._advance_tracking_session_generation()
    assert app._last_target_loss_reason is None


async def test_idempotency_actor_isolation_and_payload_conflict(owner):
    request = start_request(owner)
    result, _ = await execute(owner, request)
    replay, response = await execute(owner, request)
    assert replay["action_id"] == result["action_id"] and replay["idempotent_replay"]
    assert response.status_code == 200 and len(owner.app_controller.selected_frames) == 1
    changed = request.model_copy(update={"reason": "different request"})
    result, _ = await execute(owner, changed)
    error(result, "idempotency_conflict")
    owner.principal_test = APIPrincipal.bearer(subject="operator-b", token_id="b", scopes=TARGET_SCOPES)
    result, _ = await execute(owner, request)
    error(result, "target_revision_stale")


async def test_viewer_cannot_select_and_audit_failure_prevents_mutation(owner):
    request = start_request(owner)
    owner.principal_test = APIPrincipal.bearer(subject="viewer", token_id="v", scopes={"media:read", "status:read", "telemetry:read"})
    result, _ = await execute(owner, request)
    error(result, "target_permission_required")
    owner.principal_test = APIPrincipal.bearer(subject="operator-a", token_id="a", scopes=TARGET_SCOPES)
    owner._record_security_audit_event.return_value = False
    result, _ = await execute(owner, request)
    error(result, "audit_unavailable")
    assert not owner.app_controller.selected_frames


async def test_point_uses_retained_analysis_dimensions(owner):
    request = start_request(owner, bbox=None, point={"coordinate_space": "normalized", "x": .99, "y": .99})
    result, _ = await execute(owner, request)
    assert result["status"] == "success"
    assert owner.app_controller.selected_frames[0][1] == dict(x=96, y=16, width=64, height=64)


def test_native_mode_requires_desired_state_and_legacy_toggle_stays_valid(owner):
    with pytest.raises(ValueError):
        APITrackingModeRequest(native_context=context(owner, frame=False))
    assert APITrackingModeRequest().enabled is None


def test_retained_candidates_are_owned_and_memory_bounded(owner):
    candidates = [dict(box=[1, 2, 3, 4])]
    stamped = publish(owner, 23, candidates=candidates)
    candidates[0]["box"][0] = 100
    entry = owner.frame_publisher.selection_snapshot(stamped.selection_geometry["token"])
    assert entry["candidates"][0]["box"][0] == 1 and not entry["analysis"].flags.writeable
    owner.frame_publisher.selection_max_bytes = 1
    publish(owner, 24)
    assert owner.frame_publisher._selection_bytes == 0
    assert not owner.frame_publisher._selection_frames


def test_camera_selection_retains_displayed_frame_without_unused_analysis_pixels():
    encoded = np.zeros((72, 128, 3), dtype=np.uint8)
    analysis = np.zeros((108, 192, 3), dtype=np.uint8)
    camera = FramePublisher()
    local = FramePublisher()
    for publisher in (camera, local):
        publisher.selection_max_bytes = 1_300_000
    first = {}
    for number in range(40):
        capture = CaptureStamp("camera-source", str(number), time.monotonic(), "fresh")
        for publisher, retain in ((camera, False), (local, True)):
            publisher.publish(None, encoded, capture=capture, analysis_frame=analysis,
                              target_revision=0, retain_analysis_pixels=retain)
            if number == 0:
                first[publisher] = publisher.get_latest().selection_geometry["token"]
    entry = camera.selection_snapshot(first[camera])
    assert entry is not None and entry["analysis"] is None
    assert entry["stamped"].selection_geometry["analysis_width"] == analysis.shape[1]
    assert entry["stamped"].selection_geometry["analysis_height"] == analysis.shape[0]
    assert not entry["stamped"].frame.flags.writeable
    assert camera._selection_bytes == 40 * encoded.nbytes <= camera.selection_max_bytes
    assert local.selection_snapshot(first[local]) is None
    assert local._selection_bytes <= local.selection_max_bytes


def test_camera_selection_retains_only_the_streamed_variant():
    publisher = FramePublisher()
    encoded = np.zeros((72, 128, 3), dtype=np.uint8)
    analysis = np.zeros((108, 192, 3), dtype=np.uint8)
    capture = CaptureStamp("camera-source", "1", time.monotonic(), "fresh")
    publisher.publish(encoded, encoded, capture=capture, analysis_frame=analysis,
                      target_revision=0, retain_analysis_pixels=False,
                      selectable_variant="processed_osd")
    assert publisher.get_latest(prefer_osd=True).selection_geometry is not None
    assert publisher.get_latest(prefer_osd=False).selection_geometry is None
    assert publisher._selection_bytes == encoded.nbytes
    publisher.publish(None, encoded, capture=capture, analysis_frame=analysis,
                      target_revision=0, retain_analysis_pixels=False,
                      selectable_variant="processed_osd")
    assert publisher.get_latest().selection_geometry is not None


async def test_local_tracking_rejects_a_geometry_only_snapshot(owner):
    owner.frame_publisher.publish(
        np.zeros((20, 40, 3), dtype=np.uint8), None,
        analysis_frame=np.zeros((80, 160, 3), dtype=np.uint8),
        target_revision=owner.app_controller._tracking_session_generation,
        capture=CaptureStamp("replay", "12", time.monotonic(), "fresh"),
        retain_analysis_pixels=False,
    )
    result, _ = await execute(owner, start_request(owner))
    error(result, "frame_context_invalid")
    assert not owner.app_controller.selected_frames


def test_http_existing_action_route_accepts_native_context_and_observes_same_state(owner):
    from tests.unit.core_app.test_api_v1_integration import client
    http = client(owner, scopes=TARGET_SCOPES)
    owner.app.add_api_route("/api/v1/integration/target-state", owner.get_native_target_state, methods=["GET"])
    owner.app.add_api_route("/api/v1/actions/tracking-start", owner.tracking_start_action, methods=["POST"])
    headers = {"Authorization": "Bearer native-test-fixture"}
    state = http.get("/api/v1/integration/target-state", headers=headers)
    assert state.status_code == 200 and state.json()["mode_availability"]["external"]["available"] is False
    payload = start_request(owner).model_dump(mode="json")
    response = http.post("/api/v1/actions/tracking-start", json=payload, headers=headers)
    assert response.status_code == 202 and response.json()["status"] == "success"
    after = http.get("/api/v1/integration/target-state", headers=headers)
    assert after.json()["guard"] == response.json()["result"]["target_state"]["guard"]


async def test_dry_run_validates_coordinates_without_mutating(owner):
    request = start_request(owner, dry_run=True, bbox=dict(x=2, y=.2, width=.2, height=.2))
    result, _ = await execute(owner, request)
    error(result, "invalid_target_coordinates")
    assert not owner.app_controller.selected_frames


def test_smart_selection_uses_retained_candidates_and_stays_tentative(monkeypatch, tmp_path):
    from tests.unit.core_app.test_smart_tracker_runtime import DummyAppController, _configure
    from classes.detection_adapter import NormalizedDetection
    model = tmp_path / "test.pt"
    model.write_bytes(b"test")
    _configure(monkeypatch, model_path=str(model), use_gpu=False)
    from classes.smart_tracker import SmartTracker
    tracker = SmartTracker(DummyAppController())
    original = NormalizedDetection(track_id=11, class_id=0, confidence=.8,
                                   aabb_xyxy=(10, 10, 50, 50), center_xy=(30, 30))
    latest = NormalizedDetection(track_id=99, class_id=0, confidence=.8,
                                 aabb_xyxy=(10, 10, 50, 50), center_xy=(30, 30))
    tracker.last_detections = [latest]
    assert tracker.select_object_by_click(30, 30, selection_snapshot={
        "candidates": (original,), "frame_shape": (80, 160), "age_seconds": .1,
    })
    assert tracker.selected_object_id == 11
    assert tracker._last_tracking_state_result["tentative"]
    assert not tracker._last_measurement_current


@pytest.mark.parametrize("recovery", ["cancel", "selection", "mode"])
async def test_smart_exhaustion_remains_lost_until_explicit_transition(owner, monkeypatch, tmp_path, recovery):
    from classes.app_controller import AppController
    from classes.detection_adapter import NormalizedDetection
    from classes.smart_tracker import SmartTracker
    from tests.unit.core_app.test_smart_tracker_runtime import _configure

    model = tmp_path / "loss.pt"
    model.write_bytes(b"test")
    _configure(monkeypatch, model_path=str(model), use_gpu=False)
    app = owner.app_controller
    for name in ("_reset_tracking_failure_state", "_advance_tracking_session_generation",
                 "_cancel_activities_locked", "toggle_smart_mode", "_toggle_smart_mode_locked"):
        setattr(app, name, MethodType(getattr(AppController, name), app))
    app.tracker.stop_tracking = Mock()
    app.tracker.clear_external_override = Mock()
    app.tracker.reset = Mock()
    app.setpoint_sender = None
    app.smart_mode_active = True
    app.video_handler = SimpleNamespace(width=96, height=96)
    tracker = app.smart_tracker = SmartTracker(app)
    detection = NormalizedDetection(track_id=7, class_id=0, confidence=.9,
                                    aabb_xyxy=(10, 10, 36, 36), center_xy=(23, 23))
    tracker.last_detections = [detection]
    assert tracker.select_object_by_click(23, 23)
    frame = np.zeros((96, 96, 3), dtype=np.uint8)

    # The real tracking manager receives no detection for its complete bounded
    # recovery window. Only inference is fake; lifecycle and output are real.
    window = tracker.tracking_manager.max_history + tracker.config.get("EXTENDED_TOLERANCE_FRAMES", 10)
    for _ in range(window):
        tracker.track_and_draw(frame.copy())
        state = target_state(owner, owner.principal_test)
        assert state["target_status"] == "acquiring" and state["tracking_active"]
        assert not tracker.get_output().raw_data["usable_for_following"]
    tracker.track_and_draw(frame.copy())
    for _ in range(3):
        state = target_state(owner, owner.principal_test)
        assert state["target_status"] == "lost" and not state["tracking_active"]
        assert "target_lost_detector_failure" in state["reason_codes"]
        assert not tracker.get_output().raw_data["usable_for_following"]
        tracker.track_and_draw(frame.copy())

    assert not tracker.select_object_by_click(80, 80, selection_snapshot={
        "candidates": [detection], "frame_shape": frame.shape[:2], "age_seconds": .1,
    })
    assert target_state(owner, owner.principal_test)["target_status"] == "lost"

    if recovery == "cancel":
        body = APIActionRequest(confirm=True, idempotency_key="smart-cancel-lost", native_context=context(owner, frame=False))
        result, _ = await execute(owner, body, "tracking_stop")
        assert result["status"] == "success"
    elif recovery == "selection":
        assert tracker.select_object_by_click(23, 23, selection_snapshot={
            "candidates": [detection], "frame_shape": frame.shape[:2], "age_seconds": .1,
        })
        assert not tracker.get_output().raw_data["usable_for_following"]
    else:
        body = APITrackingModeRequest(enabled=False, confirm=True, idempotency_key="leave-lost-smart", native_context=context(owner, frame=False))
        result, _ = await execute(owner, body, "smart_mode_toggle")
        assert result["status"] == "success"

    after = target_state(owner, owner.principal_test)
    assert after["target_status"] == ("acquiring" if recovery == "selection" else "idle")
    assert tracker.last_loss_reason is None
    assert "target_lost_detector_failure" not in after["reason_codes"]
    assert not app.following_active

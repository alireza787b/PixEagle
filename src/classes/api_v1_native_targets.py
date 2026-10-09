"""Displayed-frame target operations on the existing tracker owner loop.

The HTTP contract adds guards to existing actions. It never connects an aircraft,
starts/stops following, or silently substitutes a newer camera observation.
"""

from __future__ import annotations

import hashlib
import json
import time
import asyncio
from urllib.parse import urlsplit
from contextlib import contextmanager, ExitStack, AsyncExitStack

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from classes.api_security_types import APIPrincipalKind, APIAuditPolicy, APISensitivity
from classes.api_v1_actions import ensure_api_action_store, new_api_action_record
from classes.api_v1_contracts import APINativeTargetState
from classes.api_v1_integration import context_snapshot
from classes.gimbal_control import get_gimbal_control_status
from classes.tracking_roi import tracking_point_to_pixels, tracking_roi_to_pixels, TrackingROIError
from classes.parameters import Parameters
from classes.camera_runtime import CameraLifecycleBusy
from classes.tracking_engine_selection import recalled_engine_selection, tracker_engine


TARGET_ACTIONS = frozenset({"tracking_start", "tracking_stop", "smart_click", "smart_mode_toggle",
                            "tracker_switch", "gimbal_control"})
TARGET_SCOPES = frozenset({"actions:execute", "status:read", "telemetry:read", "media:read"})


def classic_tracker_availability(factory_key):
    """Check runtime prerequisites without constructing or starting a tracker."""
    import cv2
    from classes.trackers.tracker_factory import TRACKER_REGISTRY
    from classes.trackers.dlib_tracker import DLIB_AVAILABLE
    from classes.tracker_artifacts import resolve_tracker_artifact, TrackerArtifactError

    reason = None
    required = {
        "CSRT": ("TrackerCSRT_create", "TrackerCSRT_Params"),
        "KCF": ("TrackerKCF_create",),
        "SparseFlow": ("calcOpticalFlowPyrLK", "goodFeaturesToTrack"),
        "VitTrack": ("TrackerVit_create", "TrackerVit_Params"),
        "DaSiamRPN": ("TrackerDaSiamRPN_create", "TrackerDaSiamRPN_Params"),
    }
    if factory_key not in TRACKER_REGISTRY:
        reason = "This tracker is not registered in the active runtime."
    elif factory_key == "dlib" and not DLIB_AVAILABLE:
        reason = "The optional dlib runtime is not installed."
    elif any(not hasattr(cv2, name) for name in required.get(factory_key, ())):
        reason = f"{factory_key} is unavailable in the active OpenCV runtime."
    elif factory_key in ("VitTrack", "DaSiamRPN"):
        tracker_type = TRACKER_REGISTRY[factory_key]
        # Artifact resolution only reads and verifies bounded owned model files.
        # It must not instantiate the tracker or download optional dependencies.
        probe = tracker_type.__new__(tracker_type)
        try:
            if factory_key == "VitTrack":
                resolve_tracker_artifact(probe._tracker_config())
            else:
                probe._resolve_artifacts()
        except (TrackerArtifactError, OSError, ValueError):
            reason = f"{factory_key} requires its verified model artifacts."
    return {"available": reason is None, "reason": reason}


async def apply_catalog_availability(owner, catalog):
    """Give schema aliases and compatibility rows one factory identity/state."""
    from classes.schema_manager import get_schema_manager

    rows = list(catalog.get("ui_trackers", [])) + list(catalog.get("tracker_types", {}).values())
    grouped = {}
    try:
        manager = get_schema_manager()
    except Exception:
        # The snapshot already reports schema-manager health; compatibility
        # rows must remain readable with their known factory identifiers.
        manager = None
    for row in rows:
        requested = row.get("factory_key") or row.get("request_tracker_type") or row["name"]
        canonical, info = None, None
        if manager is not None:
            canonical, info, _ = manager.resolve_tracker_for_ui(requested)
        factory_key = ((info or {}).get("ui_metadata", {}).get("factory_key")
                       or row.get("factory_key") or requested)
        row["factory_key"] = factory_key
        from classes.trackers.tracker_factory import TRACKER_REGISTRY
        row["target_engine"] = ("camera" if getattr(TRACKER_REGISTRY.get(factory_key), "is_external_tracker", False) else "local")
        if canonical:
            row["request_tracker_type"] = canonical
        grouped.setdefault(factory_key, []).append(row)
    for factory_key, aliases in grouped.items():
        if factory_key == "SmartTracker":
            availability = await refresh_smart_availability(owner)
        elif factory_key == "Gimbal":
            availability = external_selection_availability(owner)
        else:
            availability = await asyncio.to_thread(classic_tracker_availability, factory_key)
        declared_unavailable = next((row for row in aliases if not row.get("available", True)), None)
        if availability["available"] and declared_unavailable is not None:
            availability = {"available": False, "reason": declared_unavailable.get("unavailable_reason")
                            or "This tracker is disabled by its runtime catalog."}
        for row in aliases:
            row.update(available=availability["available"], unavailable_reason=availability["reason"])


def external_selection_availability(owner):
    runtime = getattr(owner.app_controller, "camera_runtime", None)
    if runtime is not None:
        provider = runtime.provider
        control = getattr(provider, "manual_control", None)
        video = getattr(owner.app_controller, "video_handler", None)
        matcher = getattr(provider, "matches_video_source", None)
        modes = getattr(provider, "selection_modes", None)
        reason = None
        if control is None or "select" not in control.capabilities or not callable(modes) or not modes():
            reason = "Camera target selection is not configured or advertised."
        elif not callable(matcher) or not matcher(getattr(video, "selection_source", {})):
            reason = "Camera selection requires the provider's matching full-frame video."
        return {"available": reason is None, "reason": reason}
    config = getattr(Parameters, "GimbalTracker", {})
    config = config if isinstance(config, dict) else {}
    video = getattr(owner.app_controller, "video_handler", None)
    source = getattr(video, "selection_source", {})
    reason = None
    if not config.get("ENABLED") or not config.get("CONTROL_ENABLED"):
        reason = "External camera target controls are not configured."
    elif config.get("PROVIDER", "topotek_sip_udp") != "topotek_sip_udp":
        reason = "This camera provider does not advertise native target selection."
    elif source.get("type") not in ("RTSP_OPENCV", "RTSP_STREAM") or not source.get("url"):
        reason = "External camera selection requires its matching full-frame RTSP video."
    elif urlsplit(source["url"]).hostname != config.get("UDP_HOST"):
        reason = "Video and external camera hosts do not match."
    return {"available": reason is None, "reason": reason}


async def refresh_smart_availability(owner, *, force=False):
    from classes.api_legacy_model_routes import get_smart_model_activation_error
    from classes.model_manager import AI_AVAILABLE
    app = owner.app_controller
    if getattr(app, "smart_mode_active", False) and getattr(app, "smart_tracker", None) is not None:
        result = {"available": True, "reason": None}
    elif not AI_AVAILABLE:
        result = {"available": False, "reason": "Smart requires the Full AI runtime and a compatible model."}
    else:
        now = time.monotonic()
        cache = getattr(owner, "_native_smart_availability", None)
        if not force and cache is not None and now-getattr(owner, "_native_smart_checked_at", 0) < 5:
            return cache
        reason = await get_smart_model_activation_error(owner)
        result = {"available": reason is None, "reason": reason}
    owner._native_smart_availability = result
    owner._native_smart_checked_at = time.monotonic()
    return result


class NativeTargetError(Exception):
    def __init__(self, code, message, status_code=409):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@contextmanager
def _context_transaction(owner):
    """Owner loop owns MAVSDK; synchronous observers share their own barriers."""
    with ExitStack() as stack:
        telemetry = getattr(owner.app_controller, "mavlink_data_manager", None)
        lock = getattr(telemetry, "_lock", None)
        if bool(getattr(Parameters, "USE_MAVLINK2REST", False)) and lock is not None:
            stack.enter_context(lock)
        publisher = getattr(owner, "frame_publisher", None)
        if publisher is not None:
            stack.enter_context(publisher.selection_transaction())
        yield


def target_state(owner, principal):
    app = owner.app_controller
    lock = getattr(app, "_tracker_model_state_lock", None)
    if lock is None:
        raise NativeTargetError("target_state_unavailable", "Tracker state barrier is unavailable.", 503)
    with lock:
        context = context_snapshot(owner, principal)
        tracker = getattr(app, "tracker", None)
        external = bool(getattr(tracker, "is_external_tracker", False))
        smart = bool(getattr(app, "smart_mode_active", False))
        mode = "smart" if smart else "external" if external else "classic"
        revision = str(int(getattr(app, "_tracking_session_generation", 0)))
        tracker_type = str(getattr(app, "current_tracker_type", "unknown"))
        try:
            saved_tracker = owner._get_config_service().get_parameter(
                "Tracking", "DEFAULT_TRACKING_ALGORITHM",
            )
            saved_engine = tracker_engine(saved_tracker)
        except (AttributeError, KeyError, TypeError, ValueError):
            saved_engine = None
        following = bool(getattr(app, "following_active", False))
        tracking = bool(getattr(app, "tracking_started", False) or
                        smart and getattr(getattr(app, "smart_tracker", None), "selected_bbox", None))
        camera = get_gimbal_control_status(app) if external else None
        smart_availability = getattr(owner, "_native_smart_availability", {
            "available": smart, "reason": None if smart else "Smart model readiness has not been checked."})
        external_availability = external_selection_availability(owner)
        classic_availability = {"available": True, "reason": None}
        if camera is not None:
            can_set_mode = camera["available"] and "set_mode" in camera["capabilities"] and external_availability["available"]
            smart_availability = classic_availability = {
                "available": bool(can_set_mode),
                "reason": None if can_set_mode else "Camera selection mode is unavailable. Check camera status and matching video.",
            }
        if camera is not None:
            tracking = camera["tracking_state"] in ("tracking_active", "target_lost")
        reasons = []
        if tracker is None:
            reasons.append("tracker_unavailable")
        if not TARGET_SCOPES.issubset(principal.scopes):
            reasons.append("target_permission_required")
        if (getattr(app, "shutdown_flag", False) or getattr(app, "restart_preparing", False)):
            reasons.append("application_shutting_down")
        status_value = "tracking" if tracking else "idle"
        if tracking and getattr(app, "tracking_failure_start_time", None) is not None:
            status_value = "lost"
        if tracking and smart and not getattr(app.smart_tracker, "_last_measurement_current", False):
            status_value = "acquiring"
        mutations_blocked = bool(reasons)
        loss_reason = getattr(app, "_last_target_loss_reason", None)
        if smart:
            loss_reason = getattr(app.smart_tracker, "last_loss_reason", None)
        if not tracking and not external and loss_reason:
            status_value = "lost"
            reasons.append("target_lost_" + str(loss_reason))
        if camera:
            status_value = {"tracking_active": "tracking", "target_lost": "lost",
                            "target_selection": "acquiring"}.get(camera["tracking_state"], "idle")
            if not camera["connected"]:
                reasons.append("external_camera_unavailable")
        allowed = []
        if not mutations_blocked:
            if external:
                if camera["enabled"]:
                    allowed.append("gimbal_control")
            else:
                allowed.append("smart_click" if smart else "tracking_start")
            if not following:
                allowed.append("tracker_switch")
                if not external:
                    allowed += ["tracking_stop", "smart_mode_toggle"]
        if following:
            reasons.append("target_following_active")
        command, telemetry, video = context["command"], context["telemetry"], context["video"]
        guard = dict(version="1", instance_id=context["instance_id"], runtime_id=context["runtime_id"],
                     target_revision=revision, mode=mode, tracker_type=tracker_type,
                     command_generation=command["connection_generation"],
                     telemetry_generation=telemetry["connection_generation"],
                     aircraft_uid=command.get("autopilot_uid"), system_id=telemetry.get("system_id"),
                     component_id=telemetry.get("component_id"), stream_id=video.get("stream_id"),
                     stream_epoch=video.get("stream_epoch"), source_epoch=video.get("source_epoch"))
        return APINativeTargetState(
            instance_id=context["instance_id"], runtime_id=context["runtime_id"],
            target_revision=revision, mode=mode, tracker_type=tracker_type,
            saved_engine=saved_engine,
            external_selection_mode=camera["selection_mode"] if camera else None,
            external_selection_modes=camera.get("selection_modes", []) if camera else [],
            tracking_active=tracking, following_active=following,
            target_status="unavailable" if tracker is None else status_value,
            allowed_actions=allowed, reason_codes=reasons, guard=guard,
            mode_availability={"classic": classic_availability,
                               "smart": smart_availability, "external": external_availability},
        ).model_dump(mode="json")


def _principal(request, *, mutation=False):
    principal = getattr(getattr(request, "state", None), "api_principal", None)
    if principal is None or principal.kind not in (APIPrincipalKind.SESSION, APIPrincipalKind.BEARER):
        raise NativeTargetError("native_credentials_required", "A session or scoped bearer credential is required.", 401)
    required = TARGET_SCOPES if mutation else {"status:read", "telemetry:read"}
    if not set(required).issubset(principal.scopes):
        raise NativeTargetError("target_permission_required", "The authenticated actor lacks target permissions.", 403)
    return principal


async def get_target_state(owner, http_request):
    path = "/api/v1/integration/target-state"
    try:
        principal = _principal(http_request)
        await refresh_smart_availability(owner)
        state = await run_in_threadpool(target_state, owner, principal)
        return JSONResponse(state, headers={"Cache-Control": "no-store"})
    except NativeTargetError as exc:
        return owner._api_v1_error_response(status_code=exc.status_code, code=exc.code, detail=str(exc), path=path)


def _validate_guard(owner, request, principal, action_type=None):
    state = target_state(owner, principal)
    expected = request.native_context.guard.model_dump(mode="json")
    if expected["target_revision"] != state["target_revision"]:
        raise NativeTargetError("target_revision_stale", "Target changed. Review its current state and retry.")
    if expected != state["guard"]:
        raise NativeTargetError("native_context_stale", "Runtime, vehicle, source, or tracker context changed.")
    selecting = action_type in ("tracking_start", "smart_click") or (
        action_type == "gimbal_control" and request.operation == "select"
    )
    if state["following_active"] and not selecting:
        raise NativeTargetError("target_following_active", "Stop aircraft following before changing its target.")
    context = context_snapshot(owner, principal)
    if request.native_context.binding_mode == "vehicle" and not context["association"]["verified"]:
        raise NativeTargetError("native_context_stale", "Verified aircraft association is required.")
    if (getattr(owner.app_controller, "shutdown_flag", False) or getattr(owner.app_controller, "restart_preparing", False)):
        raise NativeTargetError("target_state_unavailable", "PixEagle is shutting down.", 503)
    return state


def _validate_frame(owner, request, state):
    frame = request.native_context.frame
    if frame is None:
        raise NativeTargetError("frame_context_invalid", "Selection requires the actual displayed frame.")
    geometry = frame.selection_geometry.model_dump(mode="json")
    incoming = frame.provenance.model_dump(mode="json")
    publisher = getattr(owner, "frame_publisher", None)
    entry = publisher.selection_snapshot(geometry["token"]) if publisher else None
    if entry is None:
        raise NativeTargetError("frame_evicted", "Displayed frame is no longer retained. Select on current video.")
    stamped = entry["stamped"]
    if not publisher.is_current(stamped):
        raise NativeTargetError("frame_context_invalid", "The displayed video source changed.")
    age_ms = (time.monotonic() - stamped.capture.captured_at) * 1000
    if not 0 <= age_ms <= 1500:
        raise NativeTargetError("frame_expired", "Displayed frame is too old. Select on current video.")
    if stamped.selection_geometry != geometry or geometry["target_revision"] != state["target_revision"]:
        raise NativeTargetError("frame_context_invalid", "Selection geometry or target context changed.")
    actual = stamped.provenance()
    fixed_fields = set(actual) - {"capture_age_ms", "publication_age_ms"}
    if any(incoming[field] != actual[field] for field in fixed_fields):
        raise NativeTargetError("frame_context_invalid", "Frame metadata does not match retained pixels.")
    if incoming["capture_age_ms"] is None or incoming["capture_age_ms"] > 1500:
        raise NativeTargetError("frame_expired", "Displayed capture was stale when delivered.")
    return entry


def _validate_camera_selection_commit(owner, request, principal, entry, reserved_revision, admitted_at):
    """Recheck ownership after the camera handshake without expiring an admitted click."""
    if (getattr(owner.app_controller, "shutdown_flag", False) or getattr(owner.app_controller, "restart_preparing", False)):
        raise NativeTargetError("application_shutting_down", "Camera selection was cancelled during application shutdown.")
    elapsed = time.monotonic() - admitted_at
    if not 0 <= elapsed <= 6.0:
        raise NativeTargetError("frame_expired", "Camera selection took too long. Tap the live image again.")
    original = request.native_context.guard.model_dump(mode="json")
    try:
        original_revision = int(original["target_revision"])
        current_revision = int(reserved_revision)
    except (KeyError, TypeError, ValueError) as exc:
        raise NativeTargetError("target_revision_stale", "Target selection generation is invalid.") from exc
    if current_revision not in (original_revision, original_revision + 1):
        raise NativeTargetError("target_revision_stale", "Target changed during camera selection.")
    publisher = getattr(owner, "frame_publisher", None)
    if publisher is None or not publisher.is_current(entry["stamped"]):
        raise NativeTargetError("frame_context_invalid", "The displayed video source changed.")
    expected = dict(original, target_revision=str(current_revision))
    current = target_state(owner, principal)
    if current["guard"] != expected:
        raise NativeTargetError("native_context_stale", "Camera, aircraft, video, or target changed during selection.")
    video = getattr(owner.app_controller, "video_handler", None)
    if video is not None:
        frame_status = video.get_frame_status()
        stamp = frame_status.get("last_successful_frame_time")
        if (frame_status.get("source") != "fresh" or not isinstance(stamp, (int, float))
                or not 0 <= time.time() - stamp <= 2):
            raise NativeTargetError("frame_expired", "Camera video is no longer live. Tap again.")


def _coordinates(request, entry):
    height, width = entry["analysis"].shape[:2]
    selection = request.bbox if request.bbox is not None else request.point
    if selection.coordinate_space != "normalized":
        raise NativeTargetError("frame_context_invalid", "Native selection uses normalized encoded-image coordinates.", 422)
    if request.bbox is not None:
        return tracking_roi_to_pixels(**selection.model_dump(), frame_width=width, frame_height=height)
    x, y = tracking_point_to_pixels(**selection.model_dump(), frame_width=width, frame_height=height)
    size_x, size_y = min(64, width), min(64, height)
    return dict(x=max(0, min(width-size_x, x-size_x//2)), y=max(0, min(height-size_y, y-size_y//2)),
                width=size_x, height=size_y)


def _audit(owner, principal, path, outcome, revision, action_type):
    return owner._record_security_audit_event(
        event_type="native_target_action", outcome=outcome, reason=action_type,
        transport="http", method="POST", path=path, status_code=202 if outcome == "success" else None,
        principal=principal, audit_policy=APIAuditPolicy.MUTATION, sensitivity=APISensitivity.CONTROL,
        metadata={"target_revision": revision, "action_type": action_type},
    )


async def native_target_action(owner, request, response, http_request, action_type):
    path = "/api/v1/actions/" + action_type.replace("_", "-")
    try:
        principal = _principal(http_request, mutation=True)
        if action_type not in TARGET_ACTIONS:
            raise NativeTargetError("native_action_unavailable", "This native action is not enabled.", 403)
        if not request.dry_run and (not request.confirm or not request.idempotency_key):
            raise NativeTargetError("target_confirmation_required", "Confirm the action and supply an idempotency key.", 422)
        app = owner.app_controller
        if action_type == "smart_mode_toggle" and request.enabled:
            availability = await refresh_smart_availability(owner, force=True)
            if not availability["available"]:
                raise NativeTargetError("target_mode_unavailable", availability["reason"])
        store = ensure_api_action_store(owner)
        scope = hashlib.sha256((principal.kind.value + "\0" + principal.subject).encode()).hexdigest() + ":"
        digest = hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()

        async def execute():
            lock = getattr(app, "_follower_state_lock", None)
            if lock is None:
                raise NativeTargetError("target_state_unavailable", "Tracker lifecycle is unavailable.", 503)
            async with lock, AsyncExitStack() as lifecycle:
                if not request.dry_run:
                    replay = store.lookup_idempotent_action(action_type, request.idempotency_key, scope=scope)
                    if replay:
                        if store.request_digests.get(replay["action_id"]) != digest:
                            raise NativeTargetError("idempotency_conflict", "This key belongs to a different target request.")
                        response.status_code = 200
                        return replay
                publisher = getattr(owner, "frame_publisher", None)
                with app._tracker_model_state_lock, _context_transaction(owner):
                    before = _validate_guard(owner, request, principal, action_type)
                    if action_type not in before["allowed_actions"]:
                        raise NativeTargetError("target_mode_unavailable", "This action is unavailable for the active tracker.")
                    selecting = action_type in ("tracking_start", "smart_click") or (
                        action_type == "gimbal_control" and request.operation == "select")
                    entry = _validate_frame(owner, request, before) if selecting else None
                    if action_type in ("tracking_start", "smart_click") and entry["analysis"] is None:
                        raise NativeTargetError("frame_context_invalid", "Analysis pixels are unavailable for local tracking.")
                    if not selecting and request.native_context.frame is not None:
                        raise NativeTargetError("frame_context_invalid", "This operation does not accept frame coordinates.", 422)
                    if action_type == "gimbal_control" and request.operation not in ("select", "cancel", "set_mode"):
                        raise NativeTargetError("native_action_unavailable", "Camera movement is outside this target slice.", 403)
                    if action_type == "tracker_switch" and request.persist and "config:write" not in principal.scopes:
                        raise NativeTargetError("config_permission_required", "Saving an engine requires configuration permission.", 403)
                    if action_type == "tracker_switch":
                        from classes.schema_manager import get_schema_manager
                        manager = get_schema_manager()
                        selection = (recalled_engine_selection(app, request.tracker_type)
                                     if request.restore_engine_selection else
                                     dict(tracker_type=request.tracker_type, smart_mode=False))
                        canonical, info, _ = manager.resolve_tracker_for_ui(selection["tracker_type"])
                        if info is None:
                            raise NativeTargetError("target_mode_unavailable", "The selected tracker is unavailable.")
                        same_engine_save = (request.persist and request.restore_engine_selection and
                                            tracker_engine(canonical) == tracker_engine(before["tracker_type"]))
                        if same_engine_save:
                            canonical, info, _ = manager.resolve_tracker_for_ui(before["tracker_type"])
                            if info is None:
                                raise NativeTargetError("target_mode_unavailable", "The current tracker cannot be saved.")
                        elif not info.get("available", True):
                            raise NativeTargetError("target_mode_unavailable", "The selected tracker is unavailable.")
                        elif tracker_engine(canonical) == "camera":
                            available = external_selection_availability(owner)
                            if not available["available"]:
                                raise NativeTargetError("target_mode_unavailable", available["reason"])
                        else:
                            factory = info.get("ui_metadata", {}).get("factory_key")
                            available = classic_tracker_availability(factory)
                            if not available["available"]:
                                raise NativeTargetError("target_mode_unavailable", available["reason"])
                    bbox = _coordinates(request, entry) if action_type == "tracking_start" else None
                    point = None
                    if action_type == "smart_click":
                        if request.click.coordinate_space != "normalized":
                            raise NativeTargetError("frame_context_invalid", "Native clicks use normalized coordinates.", 422)
                        height, width = entry["analysis"].shape[:2]
                        point = tracking_point_to_pixels(**request.click.model_dump(), frame_width=width, frame_height=height)
                    pixels = entry["analysis"].copy() if action_type == "tracking_start" and not request.dry_run else None
                    if not _audit(owner, principal, path, "validated", before["target_revision"], action_type):
                        raise NativeTargetError("audit_unavailable", "Target audit is unavailable.", 503)
                    if selecting:
                        # Durable audit and pixel preparation can outlast a
                        # frame's deadline even while generations are locked.
                        _validate_frame(owner, request, before)
                    admitted_at = time.monotonic() if selecting else None
                    prepared_camera_selection = None
                    if action_type == "gimbal_control" and selecting:
                        from classes.gimbal_control import prepare_gimbal_selection

                        try:
                            prepared_camera_selection = prepare_gimbal_selection(
                                app, request, selection_orientation=entry["geometry_key"],
                            )
                        except ValueError as exc:
                            raise NativeTargetError("invalid_target_coordinates", str(exc), 422) from exc
                    runtime = getattr(app, "camera_runtime", None)
                    if runtime is not None and not request.dry_run and not (
                            action_type == "tracker_switch" and same_engine_save):
                        lifecycle.enter_context(runtime.lifecycle_reservation(cancel_manual=True))
                    camera_guard = runtime.guard() if runtime is not None and selecting else None
                    result = {}
                    if not request.dry_run:
                        if action_type == "tracking_start":
                            result = app._start_tracking_with_follower_barrier(bbox, frame=pixels)
                            result["bbox"] = bbox
                        elif action_type == "smart_click":
                            transition = None
                            if before["following_active"]:
                                transition = app._prepare_following_target_transition(
                                    "operator_smart_target_retarget"
                                )
                                if not transition["prepared"]:
                                    raise NativeTargetError(transition["reason"],
                                                            "The follower could not establish bounded target guidance.")
                            result = app._handle_smart_click_locked(*point, selection_snapshot={
                                "candidates": entry["candidates"], "frame_shape": (height, width),
                                "age_seconds": time.monotonic()-entry["stamped"].capture.captured_at,
                            })
                            if transition and transition.get("bounded_transition_applied"):
                                result["target_transition"] = transition
                        elif action_type == "tracking_stop":
                            app._cancel_activities_locked()
                            result = {"success": True, "message": "Target tracking canceled."}
                        elif action_type == "smart_mode_toggle":
                            if bool(app.smart_mode_active) == request.enabled:
                                result = {"success": True, "message": "Tracker mode is already selected."}
                            else:
                                changed = app.toggle_smart_mode()
                                result = {"success": changed is not False,
                                          "message": getattr(app, "last_smart_mode_error", None)}
                        elif action_type == "tracker_switch":
                            if same_engine_save:
                                result = {"success": True, "message": "Current tracking engine retained.",
                                          "factory_key": info.get("ui_metadata", {}).get("factory_key")}
                            else:
                                result = app._switch_tracker_type_with_follower_barrier(selection["tracker_type"])
                            if result.get("success") and selection.get("smart_mode"):
                                if app.toggle_smart_mode() is False:
                                    result.update(success=False, message=getattr(app, "last_smart_mode_error", None)
                                                  or "The previous Smart mode could not be restored. Choose a tracker.")
                if (action_type == "smart_click" and not request.dry_run
                        and before["following_active"] and not result.get("success")
                        and getattr(app, "following_execution_mode", None) == "PX4"):
                    result["following_stop"] = await app._disconnect_px4_internal(
                        commander_publish_final=False, reset_continuity=False
                    )
                if (action_type == "tracker_switch" and not request.dry_run and result.get("success")
                        and not same_engine_save and selection.get("selection_mode")):
                    from classes.api_v1_contracts import APIGimbalControlRequest
                    from classes.gimbal_control import execute_gimbal_control

                    restored = await execute_gimbal_control(
                        app, APIGimbalControlRequest(operation="set_mode", selection_mode=selection["selection_mode"]),
                        barrier_held=True,
                    )
                    if not restored.get("success"):
                        result.update(success=False, message=restored.get("message") or "Camera mode could not be restored.")
                if action_type == "tracker_switch" and not request.dry_run and result.get("success"):
                    result["runtime_applied"] = True
                    result["saved"] = False
                    if request.persist:
                        from classes.api_legacy_tracker_routes import _persist_tracker_selection

                        factory_key = result.get("factory_key") or info.get("ui_metadata", {}).get("factory_key")
                        try:
                            if not factory_key:
                                raise ValueError("Selected tracker has no factory key")
                            result["persistence"] = await run_in_threadpool(
                                _persist_tracker_selection, owner, str(factory_key),
                            )
                            result["saved"] = True
                        except Exception as persist_error:
                            if isinstance(persist_error, HTTPException):
                                detail = persist_error.detail
                                if isinstance(detail, dict):
                                    result["persistence_error_code"] = detail.get("code", "tracker_persistence_failed")
                                    result["persistence_error_message"] = detail.get("message", str(detail))
                                    result["restart_required"] = bool(detail.get("restart_required", False))
                                    if detail.get("changed_sources"):
                                        result["changed_sources"] = list(detail["changed_sources"])
                                    message = detail.get("message") or str(detail)
                                else:
                                    message = str(detail)
                            else:
                                message = (
                                    "Tracking engine changed for this session, but its startup setting could not be saved. "
                                    "Review and retry in Advanced PixEagle settings."
                                )
                            result.update(success=False, message=message)
                # Camera transitions await observed state. Never hold the sync
                # tracker/model lock across an await or re-acquire the owner lock.
                if action_type == "gimbal_control" and not request.dry_run:
                    from classes.gimbal_control import execute_gimbal_control

                    @contextmanager
                    def selection_guard(reserved_revision):
                        with app._tracker_model_state_lock, _context_transaction(owner):
                            try:
                                _validate_camera_selection_commit(
                                    owner, request, principal, entry, reserved_revision, admitted_at,
                                )
                                if runtime is not None and camera_guard is not None:
                                    runtime.validate_guard(camera_guard)
                            except NativeTargetError as exc:
                                raise ValueError(str(exc)) from exc
                            yield

                    result = await execute_gimbal_control(app, request, barrier_held=True,
                                                          selection_guard=selection_guard if selecting else None,
                                                          selection_orientation=entry["geometry_key"] if selecting else None,
                                                          prepared_selection=prepared_camera_selection)
                after = target_state(owner, principal)
                success = result.get("success", result.get("started", True)) is True
                record = new_api_action_record(
                    action_type=action_type, request=request,
                    status_value="validated" if request.dry_run else "success" if success else "failure",
                    accepted=True, executed=not request.dry_run, following_active_before=before["following_active"],
                    following_active_after=after["following_active"],
                    result={"legacy_result": result, "target_state": after,
                            "native_target_revision": after["target_revision"]},
                    error=None if success else result.get("reason", result.get("message", "Target action failed.")),
                )
                record["audit_event"]["actor"] = {"kind": principal.kind.value, "subject": principal.subject}
                store.store_action_record(record, scope=scope, digest=digest)
                _audit(owner, principal, path, "success" if success else "failure", after["target_revision"], action_type)
                response.status_code = 200 if request.dry_run else 202
                return record

        return await app._run_on_flight_event_loop(execute)
    except CameraLifecycleBusy as exc:
        return owner._api_v1_error_response(status_code=409, code="camera_control_active", detail=str(exc), path=path)
    except TrackingROIError as exc:
        return owner._api_v1_error_response(status_code=422, code="invalid_target_coordinates", detail=str(exc), path=path)
    except NativeTargetError as exc:
        return owner._api_v1_error_response(status_code=exc.status_code, code=exc.code, detail=str(exc), path=path)

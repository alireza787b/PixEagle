"""Read-only native follower choices and start readiness from backend state."""

from __future__ import annotations

import hashlib
import json

from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from classes.api_legacy_control_routes import get_offboard_start_preflight
from classes.api_legacy_config_routes import ConfigParameterUpdate, update_config_parameter
from classes.api_legacy_follower_routes import _get_persisted_follower_mode
from classes.api_security_types import APIAuditPolicy, APIPrincipalKind, APISensitivity
from classes.api_v1_actions import ensure_api_action_store, new_api_action_record
from classes.api_v1_contracts import APINativeFollowingStatus
from classes.api_v1_integration import context_snapshot
from classes.api_v1_native_targets import NativeTargetError, target_state
from classes.api_v1_paths import (API_V1_NATIVE_FOLLOWING_PATH,
                                  API_V1_ACTION_NATIVE_FOLLOW_START_PATH,
                                  API_V1_ACTION_NATIVE_FOLLOW_STOP_PATH)
from classes.api_v1_paths import API_V1_ACTION_NATIVE_FOLLOWER_SELECT_PATH
from classes.follower import FollowerFactory
from classes.airspeed_readiness import evaluate_following_start_airspeed
from classes.parameters import Parameters
from classes.runtime_identity import INSTANCE_ID, RUNTIME_ID
from classes.sih_replay import isolated_sih_replay_authorized


def _selected_tracker_schema(target):
    """Use the same canonical tracker declarations as the catalog and factory."""
    from classes.schema_manager import get_schema_manager

    manager = get_schema_manager()
    if target["mode"] == "smart":
        info = manager.get_tracker_info("SmartTracker")
    else:
        _, info, _ = manager.resolve_tracker_for_ui(target["tracker_type"])
    return (info or {}).get("data_type")


def following_snapshot(owner, principal):
    """Report choices without changing the selected backend profile or aircraft."""
    target = target_state(owner, principal)
    status = owner._get_following_status_snapshot()
    configured = _get_persisted_follower_mode(owner)
    runtime = str(Parameters.FOLLOWER_MODE)
    mode = target["mode"]
    from classes.schema_manager import get_schema_manager
    schema_manager = get_schema_manager()
    output_type = _selected_tracker_schema(target)
    execution_mode = status["execution_mode"]
    profiles = []
    for name in FollowerFactory.get_available_modes():
        info = FollowerFactory.get_follower_info(name)
        phase = str(info.get("airframe_phase") or "unknown")
        compatibility = schema_manager.check_follower_compatibility(info.get("implementation_class"), output_type)
        reason = None
        if not info.get("implementation_available"):
            reason = "follower_implementation_unavailable"
        elif compatibility not in {"required", "preferred", "compatible", "optional"}:
            reason = "tracker_output_incompatible"
        elif execution_mode == "PX4" and phase in ("fixed_wing", "vtol_transition"):
            reason = "profile_not_live_qualified"
        profiles.append(dict(
            mode=name, display_name=str(info.get("display_name") or name)[:120],
            control_type=str(info.get("control_type") or "unknown")[:80],
            airframe_phase=phase[:80], compatible=reason is None, reason_code=reason,
        ))

    reasons = []
    context = context_snapshot(owner, principal)
    if not context["association"]["verified"]:
        reasons.append("aircraft_not_verified")
    else:
        manager = getattr(owner.app_controller, "mavlink_data_manager", None)
        flight = manager.get_flight_state() if manager is not None else {}
        telemetry = context["telemetry"]
        if (not flight.get("fresh") or
            flight.get("connection_generation") != telemetry["connection_generation"] or
            flight.get("autopilot_uid") != telemetry["autopilot_uid"] or
            flight.get("arm_status") not in {"Armed", "Disarmed"} or
            flight.get("landed_state") not in {
                "MAV_LANDED_STATE_ON_GROUND", "MAV_LANDED_STATE_IN_AIR",
                "MAV_LANDED_STATE_TAKEOFF", "MAV_LANDED_STATE_LANDING",
            }):
            reasons.append("vehicle_flight_state_unavailable")
        elif flight.get("arm_status") != "Armed":
            reasons.append("vehicle_not_armed")
        elif flight.get("landed_state") != "MAV_LANDED_STATE_IN_AIR":
            reasons.append("vehicle_not_airborne")
    if target["target_status"] != "tracking":
        reasons.append("target_not_tracking")
    if "external_camera_unavailable" in target["reason_codes"]:
        reasons.append("external_camera_unavailable")
    if status["following_active"]:
        reasons.append("following_already_active")
    camera_runtime = getattr(owner.app_controller, "camera_runtime", None)
    if camera_runtime is not None and camera_runtime.motion_active:
        reasons.append("camera_control_active")
    selected = next((row for row in profiles if row["mode"] == configured), None)
    if selected is None:
        reasons.append("profile_not_advertised")
    elif not selected["compatible"]:
        reasons.append(selected["reason_code"])
    if "actions:execute" not in principal.scopes:
        reasons.append("following_permission_required")
    if execution_mode != "PX4":
        reasons.append("command_preview_not_aircraft_following")
    airspeed = evaluate_following_start_airspeed(owner.app_controller, mode=configured)
    if not airspeed["ready"]:
        reasons.append(airspeed["code"])
    if not reasons:
        try:
            preflight = get_offboard_start_preflight(owner)
            reasons.extend(issue["code"] for issue in preflight["issues"])
        except Exception:
            reasons.append("following_preflight_unavailable")

    generation_data = dict(profiles=profiles, configured_mode=configured)
    generation = hashlib.sha256(json.dumps(generation_data, sort_keys=True).encode()).hexdigest()
    continuity_getter = getattr(owner.app_controller, "get_target_continuity_status", None)
    continuity = continuity_getter() if status["following_active"] and callable(continuity_getter) else {}
    continuity_state = continuity.get("authority_state", "UNKNOWN")
    if continuity_state not in {"INACTIVE", "ACTIVE", "COASTING", "REACQUIRING", "HANDOFF_PENDING"}:
        continuity_state = "UNKNOWN"
    concrete = getattr(getattr(owner.app_controller, "follower", None), "follower", None)
    altitude_limited = getattr(concrete, "_vertical_limit_status", None)
    teardown = getattr(owner.app_controller, "_following_teardown_context", None) or {}
    failed_teardown = (
        not status["following_active"]
        and (getattr(owner.app_controller, "_last_following_handoff", None) or {}).get("result") == "failed"
        and teardown.get("execution_mode") == "PX4"
        and bool(teardown.get("follow_session_id"))
        and bool(teardown.get("aircraft_uid"))
    )
    follow_session_id = (
        getattr(owner.app_controller, "_following_session_id", None)
        if status["following_active"] else
        teardown.get("follow_session_id") if failed_teardown else None
    )
    follow_aircraft_uid = (
        getattr(owner.app_controller, "_following_session_aircraft_uid", None)
        if status["following_active"] else
        teardown.get("aircraft_uid") if failed_teardown else None
    )
    stop_identity_available = bool(follow_session_id and follow_aircraft_uid)
    return APINativeFollowingStatus(
        instance_id=INSTANCE_ID, runtime_id=RUNTIME_ID,
        profile_generation=generation, configured_mode=configured, runtime_mode=runtime,
        current_mode=status["profile"]["current_mode"] if status["following_active"] else None,
        activation_pending=configured != runtime and not status["following_active"],
        execution_mode=execution_mode, following_active=status["following_active"],
        following_status=status["status"], continuity_authority_state=continuity_state,
        sih_replay_authorized=isolated_sih_replay_authorized(owner.app_controller),
        continuity_target_transition_pending=bool(continuity.get("target_transition_pending")),
        continuity_transition_phase=continuity.get("transition_phase", "none"),
        continuity_effective_command_fields=continuity.get("effective_command_fields"),
        altitude_limited_reason=altitude_limited,
        last_handoff=getattr(owner.app_controller, "_last_following_handoff", None),
        target_mode=mode,
        target_status=target["target_status"], profiles=profiles,
        start_allowed=not reasons, start_reason_codes=list(dict.fromkeys(reasons)),
        stop_allowed=(execution_mode == "PX4" and
                      (stop_identity_available or
                       (bool(getattr(owner.app_controller, "_native_follow_start_attempt_id", None)) and
                        bool(getattr(owner.app_controller, "_native_follow_start_aircraft_uid", None)))) and
                      "actions:execute" in principal.scopes),
        follow_session_id=follow_session_id,
        follow_aircraft_uid=follow_aircraft_uid,
        pending_start_id=getattr(owner.app_controller, "_native_follow_start_attempt_id", None),
        pending_aircraft_uid=getattr(owner.app_controller, "_native_follow_start_aircraft_uid", None),
        guard=target["guard"],
    ).model_dump(mode="json")


async def get_native_following(owner, request):
    principal = getattr(getattr(request, "state", None), "api_principal", None)
    if principal is None or principal.kind not in (APIPrincipalKind.SESSION, APIPrincipalKind.BEARER):
        return owner._api_v1_error_response(
            status_code=401, code="native_credentials_required",
            detail="A session or scoped bearer credential is required.",
            path=API_V1_NATIVE_FOLLOWING_PATH,
        )
    if not {"status:read", "telemetry:read"}.issubset(principal.scopes):
        return owner._api_v1_error_response(
            status_code=403, code="following_read_permission_required",
            detail="Following status requires status and telemetry access.",
            path=API_V1_NATIVE_FOLLOWING_PATH,
        )
    try:
        payload = await run_in_threadpool(following_snapshot, owner, principal)
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})
    except Exception:
        return owner._api_v1_error_response(
            status_code=503, code="native_following_unavailable",
            detail="Follower choices or readiness are unavailable.",
            path=API_V1_NATIVE_FOLLOWING_PATH,
        )


def _actor(request, *, start):
    principal = getattr(getattr(request, "state", None), "api_principal", None)
    if principal is None or principal.kind not in (APIPrincipalKind.SESSION, APIPrincipalKind.BEARER):
        raise NativeTargetError("native_credentials_required", "Sign in to PixEagle first.", 401)
    required = {"actions:execute", "status:read", "telemetry:read"}
    if start:
        required.add("media:read")
    if not required.issubset(principal.scopes):
        raise NativeTargetError("following_permission_required", "Following permission is required.", 403)
    return principal


def _request_identity(request, principal):
    scope = hashlib.sha256((principal.kind.value + "\0" + principal.subject).encode()).hexdigest() + ":"
    digest = hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    return scope, digest


def _check_start(owner, request, principal, stage):
    if request.native_context.binding_mode != "vehicle" or request.native_context.frame is not None:
        raise NativeTargetError("native_follow_vehicle_required", "Select a verified aircraft; no frame is required.")
    snapshot = following_snapshot(owner, principal)
    if request.native_context.guard.model_dump(mode="json") != snapshot["guard"]:
        raise NativeTargetError("native_follow_context_stale", "Target, aircraft or video changed. Refresh following status.")
    if request.profile_generation != snapshot["profile_generation"] or request.profile_mode != snapshot["configured_mode"]:
        raise NativeTargetError("native_follow_profile_stale", "Follower choice changed. Refresh following status.")
    if not snapshot["start_allowed"]:
        reason = snapshot["start_reason_codes"][0]
        raise NativeTargetError(reason, f"Following is not ready ({reason}).")


def _audit(owner, principal, path, outcome, action_type):
    return owner._record_security_audit_event(
        event_type="native_follow_action", outcome=outcome, reason=action_type,
        transport="http", method="POST", path=path,
        status_code=202 if outcome == "success" else None,
        principal=principal, audit_policy=APIAuditPolicy.MUTATION,
        sensitivity=APISensitivity.CONTROL,
        metadata={"action_type": action_type},
    )


async def native_follow_action(owner, request, response, http_request, *, start):
    path = API_V1_ACTION_NATIVE_FOLLOW_START_PATH if start else API_V1_ACTION_NATIVE_FOLLOW_STOP_PATH
    action_type = "native_follow_start" if start else "native_follow_stop"
    try:
        principal = _actor(http_request, start=start)
        if not request.dry_run and (not request.confirm or not request.idempotency_key):
            raise NativeTargetError("following_confirmation_required", "Confirm following and provide an idempotency key.", 422)
        scope, digest = _request_identity(request, principal)
        store = ensure_api_action_store(owner)
        if not request.dry_run:
            replay = store.lookup_idempotent_action(action_type, request.idempotency_key, scope=scope)
            if replay:
                if store.request_digests.get(replay["action_id"]) != digest:
                    raise NativeTargetError("idempotency_conflict", "This key belongs to a different following request.")
                response.status_code = 200
                return replay

        app = owner.app_controller
        if start:
            _check_start(owner, request, principal, "before_request")
        else:
            teardown = getattr(app, "_following_teardown_context", None) or {}
            active_match = (
                getattr(app, "following_active", False)
                and request.follow_session_id == getattr(app, "_following_session_id", None)
                and request.aircraft_uid == getattr(app, "_following_session_aircraft_uid", None)
            )
            pending_match = (
                request.follow_session_id == getattr(app, "_native_follow_start_attempt_id", None)
                and request.aircraft_uid == getattr(app, "_native_follow_start_aircraft_uid", None)
                and getattr(app, "_follow_start_task", None) is not None
            )
            failed_match = (
                (getattr(app, "_last_following_handoff", None) or {}).get("result") == "failed"
                and (getattr(app, "_following_teardown_context", None) or {}).get("execution_mode") == "PX4"
                and request.follow_session_id == teardown.get("follow_session_id")
                and request.aircraft_uid == teardown.get("aircraft_uid")
            )
            if (request.instance_id != INSTANCE_ID or request.runtime_id != RUNTIME_ID
                    or not (active_match or pending_match or failed_match)):
                raise NativeTargetError("native_follow_session_stale", "Follow session changed. Refresh status.")
        if not _audit(owner, principal, path, "validated", action_type):
            raise NativeTargetError("audit_unavailable", "Following audit is unavailable.", 503)

        before = bool(getattr(app, "following_active", False))
        result = {"steps": [], "errors": []}
        if not request.dry_run:
            if start:
                result = await app.connect_px4(
                    native_start_guard=lambda stage: _check_start(owner, request, principal, stage),
                    native_attempt_id=request.start_attempt_id,
                    native_aircraft_uid=request.native_context.guard.aircraft_uid,
                )
            else:
                result = await app.stop_native_following(request.follow_session_id, request.aircraft_uid)
        after = bool(getattr(app, "following_active", False))
        success = not result.get("errors") and (after if start else not after)
        record = new_api_action_record(
            action_type=action_type, request=request,
            status_value="validated" if request.dry_run else "success" if success else "failure",
            accepted=True, executed=not request.dry_run,
            following_active_before=before, following_active_after=after,
            result={"outcome": result, "follow_session_id": getattr(app, "_following_session_id", None)},
            error=None if success or request.dry_run else "Following action failed; review current status.",
        )
        record["audit_event"]["actor"] = {"kind": principal.kind.value, "subject": principal.subject}
        store.store_action_record(record, scope=scope, digest=digest)
        _audit(owner, principal, path, "success" if success else "failure", action_type)
        response.status_code = 200 if request.dry_run else 202
        return record
    except NativeTargetError as exc:
        return owner._api_v1_error_response(status_code=exc.status_code, code=exc.code,
                                            detail=str(exc), path=path)
    except Exception:
        return owner._api_v1_error_response(
            status_code=503, code="native_follow_action_unavailable",
            detail="Following action failed; refresh status before another command.", path=path,
        )


async def native_follower_select(owner, request, response, http_request):
    path = API_V1_ACTION_NATIVE_FOLLOWER_SELECT_PATH
    action_type = "native_follower_select"
    try:
        principal = _actor(http_request, start=True)
        if not request.dry_run and (not request.confirm or not request.idempotency_key):
            raise NativeTargetError("following_confirmation_required", "Confirm the follower choice and provide an idempotency key.", 422)
        scope, digest = _request_identity(request, principal)
        store = ensure_api_action_store(owner)
        app = owner.app_controller

        async def execute():
            async with app._follower_state_lock:
                if not request.dry_run:
                    replay = store.lookup_idempotent_action(action_type, request.idempotency_key, scope=scope)
                    if replay:
                        if store.request_digests.get(replay["action_id"]) != digest:
                            raise NativeTargetError("idempotency_conflict", "This key belongs to a different follower choice.")
                        response.status_code = 200
                        return replay
                snapshot = following_snapshot(owner, principal)
                if (request.native_context.frame is not None or
                    request.native_context.guard.model_dump(mode="json") != snapshot["guard"] or
                    (request.native_context.binding_mode == "vehicle" and
                     not context_snapshot(owner, principal)["association"]["verified"])):
                    raise NativeTargetError("native_follow_context_stale", "Refresh the target and following status.")
                if request.profile_generation != snapshot["profile_generation"]:
                    raise NativeTargetError("native_follow_profile_stale", "Follower choices changed. Refresh status.")
                if snapshot["following_active"]:
                    raise NativeTargetError("following_active", "Stop following before changing profile.")
                row = next((item for item in snapshot["profiles"] if item["mode"] == request.profile_mode), None)
                if row is None or not row["compatible"]:
                    raise NativeTargetError("follower_profile_incompatible", "This follower is not compatible with the selected tracker.")
                if not _audit(owner, principal, path, "validated", action_type):
                    raise NativeTargetError("audit_unavailable", "Following audit is unavailable.", 503)
                result = {"saved": False, "applied": False}
                if not request.dry_run:
                    # The config writer's synchronous body runs beneath the flight-owner
                    # lock, so a concurrent start cannot apply a half-changed profile.
                    written = await run_in_threadpool(
                        update_config_parameter.__wrapped__, owner, "Follower", "FOLLOWER_MODE",
                        ConfigParameterUpdate(value=request.profile_mode),
                    )
                    if written.status_code >= 400:
                        raise NativeTargetError("follower_profile_save_failed", "The follower choice was not saved.")
                    result = json.loads(written.body)
                after = following_snapshot(owner, principal)
                record = new_api_action_record(
                    action_type=action_type, request=request,
                    status_value="validated" if request.dry_run else "success",
                    accepted=True, executed=not request.dry_run,
                    following_active_before=False, following_active_after=False,
                    result={"profile_mode": request.profile_mode, "save": result, "following": after},
                )
                record["audit_event"]["actor"] = {"kind": principal.kind.value, "subject": principal.subject}
                store.store_action_record(record, scope=scope, digest=digest)
                _audit(owner, principal, path, "success", action_type)
                response.status_code = 200 if request.dry_run else 202
                return record

        return await app._run_on_flight_event_loop(execute)
    except NativeTargetError as exc:
        return owner._api_v1_error_response(status_code=exc.status_code, code=exc.code,
                                            detail=str(exc), path=path)
    except Exception:
        return owner._api_v1_error_response(
            status_code=503, code="native_follower_select_unavailable",
            detail="Follower choice could not be saved; refresh status.", path=path,
        )

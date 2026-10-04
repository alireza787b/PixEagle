"""Captured camera ownership for native controls and shared dashboard arbitration."""

from __future__ import annotations

import hashlib
import json
import time

from classes.api_security_types import APIAuditPolicy, APIPrincipalKind, APISensitivity
from classes.api_v1_actions import ensure_api_action_store, new_api_action_record
from classes.api_v1_native_targets import NativeTargetError
from classes.api_v1_paths import API_V1_ACTION_GIMBAL_CONTROL_PATH
from classes.gimbal_control import execute_gimbal_control, get_gimbal_control_status


def _audit(owner, principal, outcome, operation):
    return owner._record_security_audit_event(
        event_type="native_camera_action", outcome=outcome, reason=operation,
        transport="http", method="POST", path=API_V1_ACTION_GIMBAL_CONTROL_PATH,
        status_code=202 if outcome == "success" else None,
        principal=principal, audit_policy=APIAuditPolicy.MUTATION,
        sensitivity=APISensitivity.CONTROL, metadata={"operation": operation},
    )


async def camera_action(owner, request, response, http_request, dispatch):
    """Arbitrate all clients before entering the existing owner-loop executor."""
    received_at = time.monotonic()
    runtime = owner.app_controller.camera_runtime
    principal = getattr(getattr(http_request, "state", None), "api_principal", None)
    native = request.camera_context is not None
    if native and (principal is None or principal.kind not in (APIPrincipalKind.SESSION, APIPrincipalKind.BEARER)):
        return owner._api_v1_error_response(status_code=401, code="native_credentials_required",
            detail="A session or scoped bearer credential is required.", path=API_V1_ACTION_GIMBAL_CONTROL_PATH)
    identity = (str(getattr(principal, "credential_id", None) or getattr(principal, "subject", "local"))
                + ":" + (request.camera_context.client_id if native else "dashboard"))
    actor = hashlib.sha256(identity.encode()).hexdigest()

    manual = native and runtime.manual_supported and request.operation in {"manual_begin", "manual_update", "stop"}

    async def run():
        acquired = False
        failed = True
        try:
            if request.operation != "stop" and (getattr(owner, "_restart_pending", False) or getattr(owner.app_controller, "shutdown_flag", False)):
                raise NativeTargetError("backend_restarting", "PixEagle is restarting. Camera Stop remains available.")
            if native:
                if "actions:execute" not in principal.scopes:
                    raise NativeTargetError("camera_permission_required", "Camera action permission is required.", 403)
                if not request.dry_run and (not request.confirm or not request.idempotency_key):
                    raise NativeTargetError("camera_confirmation_required", "Confirm this camera action and provide an idempotency key.", 400)
                store = ensure_api_action_store(owner)
                digest = hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
                replay = store.lookup_idempotent_action("gimbal_control", request.idempotency_key, scope=actor)
                if replay:
                    if store.request_digests.get(replay["action_id"]) != digest:
                        raise NativeTargetError("idempotency_conflict", "This key belongs to a different camera action.")
                    response.status_code = 200
                    return replay
                runtime.validate_guard(request.camera_context.guard.model_dump(), stop=request.operation == "stop")
            if not manual and not request.dry_run and request.confirm:
                runtime.acquire(actor, request.operation)
                acquired = request.operation != "stop"
            if not native:
                result = await dispatch()
                failed = (getattr(result, "status_code", 200) >= 400
                          or isinstance(result, dict) and result.get("status") == "failure")
                return result
            camera = get_gimbal_control_status(owner.app_controller)
            if request.operation not in camera["capabilities"]:
                raise NativeTargetError("camera_operation_unavailable", "Camera does not advertise this operation.")
            if request.operation != "stop" and not camera["available"]:
                raise NativeTargetError("camera_unavailable", camera["reason"] or "Camera is unavailable.")
            if request.operation in {"manual_begin", "manual_update"} and request.intent.axis not in camera["capabilities"]:
                raise NativeTargetError("camera_operation_unavailable", "Camera does not advertise this manual axis.")
            if request.speed_deg_s is not None or request.duration_ms is not None:
                from classes.gimbal_motion import resolve_motion
                resolve_motion(camera.get("motion_settings"), request.speed_deg_s, request.duration_ms)
            if not _audit(owner, principal, "validated", request.operation):
                raise NativeTargetError("audit_unavailable", "Camera action audit is unavailable.", 503)
            result = {"success": True, "message": "Dry-run validated; no camera command was sent."}
            if not request.dry_run:
                result = (runtime.manual_action(actor, request, received_at=received_at) if manual else
                          await execute_gimbal_control(owner.app_controller, request))
            result["timing"] = dict(received_at_monotonic=received_at, completed_at_monotonic=time.monotonic())
            after = get_gimbal_control_status(owner.app_controller)
            failed = result.get("success") is not True
            outcome = "validated" if request.dry_run else "failure" if failed else "success"
            record = new_api_action_record(action_type="gimbal_control", request=request,
                status_value=outcome, accepted=True, executed=not request.dry_run,
                following_active_before=camera["following_active"], following_active_after=after["following_active"],
                result={**result, "camera_status": after}, error=result.get("message") if failed else None)
            store.store_action_record(record, scope=actor, digest=digest)
            _audit(owner, principal, outcome, request.operation)
            response.status_code = 200 if request.dry_run else 202
            return record
        except (NativeTargetError, ValueError) as exc:
            return owner._api_v1_error_response(status_code=getattr(exc, "status_code", 409),
                code=getattr(exc, "code", "camera_context_conflict"), detail=str(exc), path=API_V1_ACTION_GIMBAL_CONTROL_PATH)
        finally:
            if acquired:
                runtime.release(failed=failed)

    independent = runtime.manual_supported and request.operation in {
        "manual_begin", "manual_update", "stop", "pan", "tilt", "roll", "zoom", "home"}
    return await run() if independent else await owner.app_controller._run_on_flight_event_loop(run)

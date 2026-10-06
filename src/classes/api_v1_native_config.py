"""Native configuration views and bounded actions on the shared ConfigService."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets

from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from classes.api_legacy_config_routes import (
    _config_mutation_transaction, _persist_config, _log_config_audit,
)
from classes.api_security_types import APIAuditPolicy, APIPrincipalKind, APISensitivity
from classes.api_v1_actions import ensure_api_action_store, get_control_activity_state, get_system_restart_availability, new_api_action_record
from classes.api_v1_contracts import APINativeConfigSnapshot
from classes.api_v1_native_targets import NativeTargetError
from classes.parameters import Parameters
from classes.runtime_identity import INSTANCE_ID, RUNTIME_ID

_GENERATION_KEY = secrets.token_bytes(32)
_TIERS = ("immediate", "follower_restart", "tracker_restart", "system_restart")


def _principal(request, action=None):
    principal = getattr(getattr(request, "state", None), "api_principal", None)
    if principal is None or principal.kind not in (APIPrincipalKind.SESSION, APIPrincipalKind.BEARER):
        raise NativeTargetError("native_credentials_required", "Sign in to configure PixEagle.", 401)
    scopes = {"config:read"}
    if action is not None:
        scopes.add("control:write" if action == "osd_set" else "config:write")
    if not scopes.issubset(principal.scopes):
        raise NativeTargetError("config_permission_required", "Configuration permission is required.", 403)
    return principal


def _apply_block_reason(owner):
    app = owner.app_controller
    if getattr(app, "shutdown_flag", False):
        return "shutdown_pending"
    if get_control_activity_state(owner)["control_active"]:
        return "following_or_offboard_active"
    camera = getattr(app, "camera_runtime", None)
    if camera is not None and (camera.motion_active or camera.busy):
        return "camera_operation_active"
    manager = getattr(app, "mavlink_data_manager", None)
    px4 = getattr(app, "px4_interface", None)
    command = px4.get_aircraft_identity() if px4 is not None else {}
    flight = manager.get_flight_state() if manager is not None else {}
    # A MAVLink transport can remain connected to a router while no PX4
    # aircraft has been discovered. That companion-only state must not block
    # backend settings or restart; use an aircraft identity as evidence.
    observed = bool(command.get("connected") or command.get("autopilot_uid") or flight.get("autopilot_uid"))
    if observed and (not flight.get("fresh") or flight.get("arm_status") != "Disarmed"):
        return "aircraft_not_confirmed_disarmed"
    if getattr(app, "tracking_started", False):
        return "target_active"
    if getattr(app, "smart_mode_active", False):
        return "leave_smart_before_apply"
    return None


def _snapshot_locked(owner, principal, service, http_request=None):
    pending = service.get_pending_runtime_config_status()
    source = service.get_runtime_config_status()["source_generation"]
    changes = [dict(path=row["path"], reload_tier=(
        "system_restart" if ((row["section"] == "OSD" and row["parameter"] != "OSD_ENABLED") or
                             (row["reload_tier"] == "immediate" and row["path"] != "OSD.OSD_ENABLED"))
        else row["reload_tier"]
    )) for row in pending["pending_changes"]]
    if len(changes) > 256:
        raise NativeTargetError("config_inventory_limit", "Review this configuration in the dashboard.", 503)
    persisted, _, _ = service._read_persisted_effective_config_locked()
    saved = persisted.get("OSD", {}).get("OSD_ENABLED")
    renderer = getattr(owner.app_controller, "osd_handler", None)
    running = renderer.is_enabled() if renderer is not None else None
    available = isinstance(saved, bool) and isinstance(running, bool)
    if available and saved != running and not any(row["path"] == "OSD.OSD_ENABLED" for row in changes):
        changes.append(dict(path="OSD.OSD_ENABLED", reload_tier="immediate"))
        if len(changes) > 256:
            raise NativeTargetError("config_inventory_limit", "Review this configuration in the dashboard.", 503)
    reason = None if available else "osd_unavailable"
    if source["state"] != "current":
        reason = "configuration_definitions_changed"
    writable = "config:write" in principal.scopes
    osd_writable = "control:write" in principal.scopes
    tier = max((row["reload_tier"] for row in changes), key=_TIERS.index, default=None)
    apply_reason = "no_pending_changes" if tier is None else None
    if not writable:
        apply_reason = "config_permission_required"
    elif tier == "system_restart" or source["state"] != "current":
        tier, apply_reason = "system_restart", "system_restart_required"
    elif tier == "follower_restart":
        apply_reason = "follower_apply_not_supported"
    elif tier is not None:
        try:
            apply_reason = _apply_block_reason(owner)
        except Exception:
            apply_reason = "control_state_unavailable"
    if getattr(owner, "_restart_pending", False):
        apply_reason = reason = "restart_pending"
    generation = hmac.new(_GENERATION_KEY, json.dumps(dict(
        instance_id=INSTANCE_ID, runtime_id=RUNTIME_ID,
        persisted=pending["persisted_config_digest"], runtime=pending["runtime_generation"],
        source=source, running_osd=running,
    ), sort_keys=True, default=str).encode(), hashlib.sha256).hexdigest()
    return APINativeConfigSnapshot(
        instance_id=INSTANCE_ID, runtime_id=RUNTIME_ID, config_generation=generation,
        pending=bool(changes) or source["state"] != "current", pending_changes=changes,
        osd=dict(available=available, can_set=available and osd_writable and reason is None,
                 saved_enabled=saved if isinstance(saved, bool) else None,
                 running_enabled=running if isinstance(running, bool) else None,
                 unavailable_reason=reason if osd_writable else "control_permission_required"),
        apply=dict(available=apply_reason is None, reason=apply_reason, reload_tier=tier),
        system_restart=dict(available=False, reason="supervisor_not_verified", reload_tier="system_restart") if http_request is None else
            {key: value for key, value in get_system_restart_availability(owner, http_request).items() if key in ("available", "reason")} | {"reload_tier": "system_restart"},
    ).model_dump(mode="json")


def _snapshot(owner, principal, http_request=None):
    service = owner._get_config_service()
    with service._mutation_lock:
        return _snapshot_locked(owner, principal, service, http_request)


def _error(owner, exc, path):
    if isinstance(exc, NativeTargetError):
        code, detail, status = exc.code, str(exc), exc.status_code
    else:
        owner.logger.error("Native configuration operation failed: %s", exc)
        code, detail, status = "config_operation_failed", "Configuration could not be applied. Refresh its state before retrying.", 503
    return owner._api_v1_error_response(status_code=status, code=code, detail=detail, path=path)


async def get_config(owner, http_request):
    try:
        principal = _principal(http_request)
        payload = await run_in_threadpool(_snapshot, owner, principal, http_request)
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})
    except Exception as exc:
        return _error(owner, exc, "/api/v1/integration/config")


def _audit(owner, principal, action, outcome):
    return owner._record_security_audit_event(
        event_type="native_config_action", outcome=outcome, reason=action,
        transport="http", method="POST", path="/api/v1/actions/" + action.replace("_", "-"),
        status_code=202 if outcome == "success" else None,
        principal=principal, audit_policy=APIAuditPolicy.MUTATION, sensitivity=APISensitivity.CONFIG,
        metadata={"action_type": action},
    )


def set_osd_locked(owner, service, transaction, enabled):
    """One desired-state owner, also used by the dashboard compatibility route."""
    renderer = owner.app_controller.osd_handler
    before = renderer.is_enabled()
    old = service.get_parameter("OSD", "OSD_ENABLED")
    try:
        validation = service.set_parameter("OSD", "OSD_ENABLED", enabled, audit=False)
        if not validation.valid:
            raise NativeTargetError("osd_value_invalid", "OSD enablement is not valid for this configuration.", 422)
        _persist_config(service, transaction)
        _log_config_audit(service, transaction, action="update", section="OSD", parameter="OSD_ENABLED",
                          old_value=old, new_value=enabled, source="native_osd")
        # Publish only this path, so unrelated saved immediate changes are not
        # silently included by an OSD checkbox.
        runtime = service.get_applied_runtime_config()
        runtime.setdefault("OSD", {})["OSD_ENABLED"] = enabled
        service.publish_runtime_config_snapshot(runtime, source="native_osd")
        renderer.set_enabled(enabled)
        if renderer.is_enabled() is not enabled:
            raise RuntimeError("OSD renderer did not apply requested state")
        pipeline = getattr(owner.app_controller, "osd_pipeline", None)
        if pipeline is not None:
            pipeline.invalidate_cache("osd_set")
    except Exception:
        renderer.set_enabled(before)
        raise


def _execute_locked(owner, principal, request, action):
    app = owner.app_controller
    tracker_lock = getattr(app, "_tracker_model_state_lock", None)
    if tracker_lock is None:
        raise NativeTargetError("state_barrier_unavailable", "Configuration state barrier is unavailable.", 503)
    with tracker_lock:
        with _config_mutation_transaction(owner) as (service, transaction):
            before = _snapshot_locked(owner, principal, service)
            if request.instance_id != INSTANCE_ID or request.runtime_id != RUNTIME_ID:
                return NativeTargetError("config_runtime_changed", "PixEagle restarted. Refresh configuration before retrying.")
            if request.config_generation != before["config_generation"]:
                return NativeTargetError("config_generation_stale", "Configuration changed. Refresh before applying.")
            if action == "osd_set":
                if not before["osd"]["can_set"]:
                    return NativeTargetError("osd_unavailable", "OSD control is currently unavailable.")
            elif not before["apply"]["available"] or request.reload_tier != before["apply"]["reload_tier"]:
                return NativeTargetError("config_apply_unavailable", before["apply"]["reason"] or "Refresh the pending reload tier.")
            if not _audit(owner, principal, action, "validated"):
                return NativeTargetError("audit_unavailable", "Configuration audit is unavailable.", 503)
            if not request.dry_run:
                if action == "osd_set":
                    set_osd_locked(owner, service, transaction, request.enabled)
                else:
                    old_tracker = getattr(app, "current_tracker_type", None)
                    renderer = getattr(app, "osd_handler", None)
                    old_osd = renderer.is_enabled() if renderer is not None else None
                    try:
                        tiers = {"immediate", "tracker_restart"} if request.reload_tier == "tracker_restart" else {"immediate"}
                        service.apply_runtime_config_tiers(tiers, source="native_config_apply")
                        if request.reload_tier == "tracker_restart":
                            result = app._switch_tracker_type_with_follower_barrier(Parameters.DEFAULT_TRACKING_ALGORITHM)
                            if not result.get("success"):
                                raise RuntimeError("Tracker apply failed")
                        if renderer is not None:
                            renderer.set_enabled(Parameters.OSD_ENABLED)
                            pipeline = getattr(app, "osd_pipeline", None)
                            if pipeline is not None:
                                pipeline.invalidate_cache("config_apply")
                    except Exception:
                        service.publish_runtime_config_snapshot(transaction.applied_runtime_snapshot, source="native_apply_rollback")
                        if renderer is not None:
                            renderer.set_enabled(old_osd)
                        if request.reload_tier == "tracker_restart" and old_tracker:
                            recovery = app._switch_tracker_type_with_follower_barrier(old_tracker)
                            if not recovery.get("success"):
                                raise RuntimeError("Tracker apply rollback needs operator recovery")
                        raise
            after = _snapshot_locked(owner, principal, service)
            record = new_api_action_record(
                action_type=action, request=request, status_value="validated" if request.dry_run else "success",
                accepted=True, executed=not request.dry_run,
                following_active_before=bool(app.following_active), following_active_after=bool(app.following_active),
                result={"config": after},
            )
            record["audit_event"]["actor"] = {"kind": principal.kind.value, "subject": principal.subject}
            _audit(owner, principal, action, "success")
            return record


async def config_action(owner, request, response, http_request, *, action):
    try:
        principal = _principal(http_request, action=action)
        if not request.dry_run and (not request.confirm or not request.idempotency_key):
            raise NativeTargetError("config_confirmation_required", "Confirm the action and supply an idempotency key.", 422)
        app = owner.app_controller
        store = ensure_api_action_store(owner)
        scope = hashlib.sha256((principal.kind.value + "\0" + principal.subject).encode()).hexdigest() + ":"
        digest = hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()

        async def execute():
            lock = getattr(app, "_follower_state_lock", None)
            if lock is None:
                raise NativeTargetError("state_barrier_unavailable", "Configuration state barrier is unavailable.", 503)
            async with lock:
                if not request.dry_run:
                    replay = store.lookup_idempotent_action(action, request.idempotency_key, scope=scope)
                    if replay:
                        if store.request_digests.get(replay["action_id"]) != digest:
                            raise NativeTargetError("idempotency_conflict", "This key belongs to another configuration request.")
                        response.status_code = 200
                        return replay
                record = await run_in_threadpool(_execute_locked, owner, principal, request, action)
                if isinstance(record, NativeTargetError):
                    raise record
                store.store_action_record(record, scope=scope, digest=digest)
                response.status_code = 200 if request.dry_run else 202
                return record

        return await app._run_on_flight_event_loop(execute)
    except Exception as exc:
        return _error(owner, exc, "/api/v1/actions/" + action.replace("_", "-"))

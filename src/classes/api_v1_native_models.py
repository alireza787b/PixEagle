"""Installed Smart models for native clients, using the dashboard model owner."""

from __future__ import annotations

import hashlib
import json
import re

from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from classes.api_legacy_model_routes import (
    _model_manager_capability,
    _smart_tracker_has_target_selection,
    _switch_model_under_follower_guard,
    get_configured_yolo_models,
    get_smart_tracker_runtime_context,
    resolve_model_entry,
)
from classes.api_security_types import APIAuditPolicy, APIPrincipalKind, APISensitivity
from classes.api_v1_actions import ensure_api_action_store, new_api_action_record
from classes.api_v1_contracts import APINativeModelInventory, APINativeModelLabels
from classes.api_v1_native_targets import (
    NativeTargetError,
    _context_transaction,
    _validate_guard,
    target_state,
)
from classes.api_v1_paths import API_V1_ACTION_MODEL_SELECT_PATH, API_V1_NATIVE_MODELS_PATH
from classes.model_artifact_policy import ModelStoreBusyError
from classes.parameters import Parameters
from classes.runtime_identity import INSTANCE_ID, RUNTIME_ID

MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
MODEL_SELECT_SCOPES = frozenset({"models:read", "models:select", "status:read", "telemetry:read"})


def _principal(http_request, *, mutation=False):
    principal = getattr(getattr(http_request, "state", None), "api_principal", None)
    if principal is None or principal.kind not in (APIPrincipalKind.SESSION, APIPrincipalKind.BEARER):
        raise NativeTargetError("native_credentials_required", "A session or scoped bearer credential is required.", 401)
    required = MODEL_SELECT_SCOPES if mutation else {"models:read"}
    if not required.issubset(principal.scopes):
        raise NativeTargetError("model_permission_required", "The authenticated actor lacks model permissions.", 403)
    return principal


def _inventory_locked(owner, principal):
    """Read trust metadata only; inventory never executes or downloads checkpoints."""
    from classes.model_manager import AI_AVAILABLE

    capability = _model_manager_capability(owner)
    models = owner.model_manager.discover_models(False) if capability["available"] else {}
    if len(models) > 256:
        raise NativeTargetError("model_inventory_limit", "The model inventory exceeds the native limit of 256 models.", 503)
    if any(not MODEL_ID.fullmatch(model_id) for model_id in models):
        raise NativeTargetError("model_inventory_invalid", "A registered model has an unsupported identifier.", 503)
    available = capability["available"] and AI_AVAILABLE
    reason = None if available else "Smart requires the Full AI runtime and a compatible installed model."
    configured, _, _ = get_configured_yolo_models(owner)
    current, runtime = get_smart_tracker_runtime_context(owner)
    configured_id, _ = resolve_model_entry(owner.model_manager, models, configured) if models else (None, None)
    active_id, _ = resolve_model_entry(owner.model_manager, models, current) if models else (None, None)
    if not getattr(owner.app_controller, "smart_mode_active", False):
        active_id, runtime = None, None
    runtime = runtime or {}
    summary = dict(backend=runtime.get("backend"), device=runtime.get("effective_device"),
                   fallback_occurred=bool(runtime.get("fallback_occurred", False)),
                   # Backend failure strings can contain local checkpoint paths.
                   fallback_reason=("The preferred device was unavailable; the reported device is in use."
                                    if runtime.get("fallback_occurred") else None))
    rows = []
    for model_id, info in sorted(models.items()):
        labels = [str(label)[:240] for label in info.get("class_names", [])]
        supported = info.get("smarttracker_supported") is True and info.get("task") in ("detect", "obb")
        row_reason = reason
        if available and not supported:
            row_reason = "Smart supports verified detect or OBB models; review this model in the dashboard."
        rows.append(dict(model_id=model_id,
                         display_name=str(info.get("display_name") or info.get("name") or model_id)[:240],
                         task=str(info.get("task") or "unknown")[:40],
                         available=available and supported,
                         unavailable_reason=row_reason, labels=labels[:32], total_labels=len(labels),
                         has_more_labels=len(labels) > 32, size_mb=info.get("size_mb")))
    config = getattr(Parameters, "SmartTracker", {})
    generation_state = dict(instance_id=INSTANCE_ID, runtime_id=RUNTIME_ID,
                            models=models, configured=config, active_model_id=active_id, runtime=summary)
    generation = hashlib.sha256(json.dumps(generation_state, sort_keys=True, default=str).encode()).hexdigest()
    state = target_state(owner, principal) if {"status:read", "telemetry:read"}.issubset(principal.scopes) else None
    payload = APINativeModelInventory(
        instance_id=INSTANCE_ID, runtime_id=RUNTIME_ID, model_generation=generation,
        available=available, unavailable_reason=reason, configured_model_id=configured_id,
        active_model_id=active_id, runtime=summary, models=rows, target_state=state,
    ).model_dump(mode="json")
    return payload, models


def _inventory(owner, principal):
    lock = getattr(owner.app_controller, "_tracker_model_state_lock", None)
    if lock is None:
        raise NativeTargetError("target_state_unavailable", "Tracker/model state barrier is unavailable.", 503)
    with lock:
        return _inventory_locked(owner, principal)


def _error(owner, exc, path):
    if isinstance(exc, NativeTargetError):
        code, detail, status = exc.code, str(exc), exc.status_code
    elif isinstance(exc, ModelStoreBusyError):
        code, detail, status = "model_store_busy", "The model store is busy. Retry after the current operation finishes.", 409
    else:
        logger = getattr(owner, "logger", None)
        if logger:
            logger.error("Native model operation failed: %s", exc)
        code, detail, status = "model_operation_failed", "Model operation failed. Review model status and retry; Classic remains available.", 503
    return owner._api_v1_error_response(status_code=status, code=code, detail=detail, path=path)


async def get_models(owner, http_request):
    try:
        principal = _principal(http_request)
        payload, _ = await run_in_threadpool(_inventory, owner, principal)
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})
    except Exception as exc:
        return _error(owner, exc, API_V1_NATIVE_MODELS_PATH)


async def get_labels(owner, http_request, model_id, *, offset=0, limit=200):
    path = API_V1_NATIVE_MODELS_PATH + "/" + model_id + "/labels"
    try:
        principal = _principal(http_request)
        if not 0 <= offset or not 1 <= limit <= 200:
            raise NativeTargetError("model_labels_invalid_page", "Use a nonnegative offset and a limit from 1 to 200.", 422)
        inventory, models = await run_in_threadpool(_inventory, owner, principal)
        if model_id not in models:
            raise NativeTargetError("model_not_advertised", "The model is no longer in the installed inventory.", 404)
        labels = [str(label)[:240] for label in models[model_id].get("class_names", [])]
        payload = APINativeModelLabels(
            instance_id=INSTANCE_ID, runtime_id=RUNTIME_ID,
            model_generation=inventory["model_generation"], model_id=model_id,
            labels=[dict(class_id=index, label=label) for index, label in enumerate(labels[offset:offset+limit], offset)],
            total_labels=len(labels), offset=offset, limit=limit, has_more=offset+limit < len(labels),
        ).model_dump(mode="json")
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})
    except Exception as exc:
        return _error(owner, exc, path)


def _audit(owner, principal, outcome, revision):
    return owner._record_security_audit_event(
        event_type="native_model_action", outcome=outcome, reason="model_select",
        transport="http", method="POST", path=API_V1_ACTION_MODEL_SELECT_PATH,
        status_code=202 if outcome == "success" else None,
        principal=principal, audit_policy=APIAuditPolicy.MUTATION, sensitivity=APISensitivity.MODELS,
        metadata={"target_revision": revision, "action_type": "model_select"},
    )


def _select_locked(owner, principal, request):
    app = owner.app_controller
    with app._tracker_model_state_lock:
        with _context_transaction(owner):
            before = _validate_guard(owner, request, principal)
        if request.native_context.frame is not None:
            raise NativeTargetError("frame_context_invalid", "Model selection does not accept frame coordinates.", 422)
        inventory, models = _inventory_locked(owner, principal)
        if request.model_generation != inventory["model_generation"]:
            raise NativeTargetError("model_generation_stale", "Installed models or their selection changed. Refresh before choosing a model.")
        if request.model_id not in models:
            raise NativeTargetError("model_not_advertised", "Choose a model from the current installed inventory.")
        row = next(row for row in inventory["models"] if row["model_id"] == request.model_id)
        if not row["available"]:
            raise NativeTargetError("model_unavailable", row["unavailable_reason"])
        smart = getattr(app, "smart_tracker", None)
        if smart is not None and (_smart_tracker_has_target_selection(smart) or getattr(smart, "selected_bbox", None) is not None):
            raise NativeTargetError("model_target_active", "Cancel the Smart target before selecting another model.")
        if not _audit(owner, principal, "validated", before["target_revision"]):
            raise NativeTargetError("audit_unavailable", "Model action audit is unavailable.", 503)
        success, selection_status = True, "configured"
        if not request.dry_run:

            def before_commit():
                # Checkpoint validation can be slow. Keep source locks short so
                # video publication and aircraft observations remain live.
                with _context_transaction(owner):
                    _validate_guard(owner, request, principal)
                current_inventory, _ = _inventory_locked(owner, principal)
                if request.model_generation != current_inventory["model_generation"]:
                    raise NativeTargetError("model_generation_stale", "Installed models or their selection changed. Refresh before choosing a model.")

            from contextlib import nullcontext
            runtime = getattr(app, "camera_runtime", None)
            with runtime.lifecycle_reservation(cancel_manual=True) if runtime is not None else nullcontext():
                result = _switch_model_under_follower_guard(owner, models[request.model_id]["path"], "auto", target_lock_acquired=True,
                                                           before_commit=before_commit)
            body = json.loads(result.body)
            success = result.status_code < 400 and body.get("status") == "success"
            selection_status = "active" if body.get("action") == "model_switched" else "configured"
            if success and str(app._tracking_session_generation) == before["target_revision"]:
                app._advance_tracking_session_generation()
            owner._native_smart_checked_at = 0
        after, _ = _inventory_locked(owner, principal)
        state = after["target_state"]
        record = new_api_action_record(
            action_type="model_select", request=request,
            status_value="validated" if request.dry_run else "success" if success else "failure",
            accepted=True, executed=not request.dry_run,
            following_active_before=False, following_active_after=state["following_active"],
            result={"model_id": request.model_id, "selection_status": selection_status,
                    "model_inventory": after, "target_state": state,
                    "native_target_revision": state["target_revision"]},
            error=None if success else "Model selection failed. Review model status; the prior selection was retained when possible.",
        )
        record["audit_event"]["actor"] = {"kind": principal.kind.value, "subject": principal.subject}
        _audit(owner, principal, "success" if success else "failure", state["target_revision"])
        return record


async def select_model(owner, request, response, http_request):
    try:
        principal = _principal(http_request, mutation=True)
        if not request.dry_run and (not request.confirm or not request.idempotency_key):
            raise NativeTargetError("model_confirmation_required", "Confirm model selection and supply an idempotency key.", 422)
        app = owner.app_controller
        store = ensure_api_action_store(owner)
        scope = hashlib.sha256((principal.kind.value + "\0" + principal.subject).encode()).hexdigest() + ":"
        digest = hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()

        async def execute():
            lock = getattr(app, "_follower_state_lock", None)
            if lock is None or getattr(app, "_tracker_model_state_lock", None) is None:
                raise NativeTargetError("target_state_unavailable", "Tracker/model lifecycle is unavailable.", 503)
            async with lock:
                if not request.dry_run:
                    replay = store.lookup_idempotent_action("model_select", request.idempotency_key, scope=scope)
                    if replay:
                        if store.request_digests.get(replay["action_id"]) != digest:
                            raise NativeTargetError("idempotency_conflict", "This key belongs to a different model request.")
                        response.status_code = 200
                        return replay
                record = await run_in_threadpool(_select_locked, owner, principal, request)
                store.store_action_record(record, scope=scope, digest=digest)
                response.status_code = 200 if request.dry_run else 202
                return record

        return await app._run_on_flight_event_loop(execute)
    except Exception as exc:
        from classes.camera_runtime import CameraLifecycleBusy
        if isinstance(exc, CameraLifecycleBusy):
            exc = NativeTargetError("camera_control_active", str(exc))
        return _error(owner, exc, API_V1_ACTION_MODEL_SELECT_PATH)

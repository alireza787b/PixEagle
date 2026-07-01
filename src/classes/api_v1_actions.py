"""In-process action-resource helpers for typed /api/v1 control actions."""

from __future__ import annotations

import asyncio
from collections import deque
import threading
import time
from typing import Any, Dict, Literal, Optional
import uuid

from fastapi import status
from fastapi.responses import JSONResponse

from classes.api_v1_contracts import (
    APIActionRequest,
    APITrackerSwitchRequest,
    APITrackingSmartClickRequest,
    APITrackingStartRequest,
)
from classes.api_v1_errors import build_api_v1_error_response
from classes.api_v1_paths import (
    API_V1_ACTION_OFFBOARD_START_PATH,
    API_V1_ACTION_OFFBOARD_STOP_PATH,
    API_V1_ACTION_OPERATOR_ABORT_PATH,
    API_V1_ACTION_RESOURCE_PREFIX,
    API_V1_ACTION_SEGMENTATION_TOGGLE_PATH,
    API_V1_ACTION_SMART_CLICK_PATH,
    API_V1_ACTION_SMART_MODE_TOGGLE_PATH,
    API_V1_ACTION_TRACKER_SWITCH_PATH,
    API_V1_ACTION_TRACKING_REDETECT_PATH,
    API_V1_ACTION_TRACKING_START_PATH,
    API_V1_ACTION_TRACKING_STOP_PATH,
)

API_ACTION_CLAIM_BOUNDARY = (
    "This action resource records a PixEagle API/control-path request only; "
    "PX4-observed mode, setpoint cadence, SITL, HIL, or field success require "
    "separate evidence artifacts."
)

ActionType = Literal[
    "offboard_start",
    "offboard_stop",
    "operator_abort",
    "segmentation_toggle",
    "smart_click",
    "smart_mode_toggle",
    "tracker_switch",
    "tracking_redetect",
    "tracking_start",
    "tracking_stop",
]
ActionStatus = Literal["validated", "success", "failure"]


class ApiActionStore:
    """Process-local action resource store with idempotency replay support."""

    def __init__(self, max_history: int = 1000) -> None:
        self.max_history = max_history
        self.records: Dict[str, Dict[str, Any]] = {}
        self.idempotency_index: Dict[tuple[str, str], str] = {}
        self.history_order: deque[str] = deque()
        self.lock = threading.Lock()
        self.key_locks: Dict[tuple[str, str], asyncio.Lock] = {}

    def action_lock_for_key(
        self,
        action_type: str,
        idempotency_key: Optional[str],
    ) -> Optional[asyncio.Lock]:
        """Return a per-idempotency-key async lock for confirmed mutations."""
        if not idempotency_key:
            return None
        key = (action_type, idempotency_key)
        with self.lock:
            lock = self.key_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self.key_locks[key] = lock
            return lock

    def lookup_idempotent_action(
        self,
        action_type: str,
        idempotency_key: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Return a replay copy for an already executed idempotent action."""
        if not idempotency_key:
            return None
        with self.lock:
            action_id = self.idempotency_index.get((action_type, idempotency_key))
            if not action_id:
                return None
            record = self.records.get(action_id)
            if not record:
                return None
            replay = dict(record)
            replay["idempotent_replay"] = True
            return replay

    def store_action_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Store an action resource and update replay indexes when applicable."""
        with self.lock:
            action_id = record["action_id"]
            self.records[action_id] = dict(record)
            self.history_order.append(action_id)
            idempotency_key = record.get("idempotency_key")
            if idempotency_key and record.get("executed") is True:
                self.idempotency_index[(record["action_type"], idempotency_key)] = (
                    action_id
                )

            while len(self.history_order) > self.max_history:
                old_action_id = self.history_order.popleft()
                old_record = self.records.pop(old_action_id, None)
                if (
                    old_record
                    and old_record.get("idempotency_key")
                    and old_record.get("executed") is True
                ):
                    lock_key = (
                        old_record["action_type"],
                        old_record["idempotency_key"],
                    )
                    self.idempotency_index.pop(lock_key, None)
                    self.key_locks.pop(lock_key, None)
        return record

    def get_action_record(self, action_id: str) -> Optional[Dict[str, Any]]:
        """Return the stored action resource, if present."""
        with self.lock:
            return self.records.get(action_id)


def ensure_api_action_store(owner: Any) -> ApiActionStore:
    """Initialize action storage for tests that construct handlers via __new__."""
    store = getattr(owner, "_api_action_store", None)
    if isinstance(store, ApiActionStore):
        return store
    store = ApiActionStore()
    setattr(owner, "_api_action_store", store)
    return store


def new_api_action_record(
    *,
    action_type: ActionType,
    request: APIActionRequest,
    status_value: ActionStatus,
    accepted: bool,
    executed: bool,
    following_active_before: Optional[bool],
    following_active_after: Optional[bool],
    result: Dict[str, Any],
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a process-local typed action resource."""
    timestamp = time.time()
    event = {
        "event_id": f"pixeagle-action-event-{uuid.uuid4()}",
        "event_type": f"{action_type}.{status_value}",
        "timestamp": timestamp,
        "source": request.source,
        "reason": request.reason,
    }
    return {
        "action_id": f"pixeagle-action-{uuid.uuid4()}",
        "action_type": action_type,
        "status": status_value,
        "accepted": accepted,
        "executed": executed,
        "dry_run": request.dry_run,
        "confirmed": request.confirm,
        "idempotency_key": request.idempotency_key,
        "idempotent_replay": False,
        "source": request.source,
        "reason": request.reason,
        "following_active_before": following_active_before,
        "following_active_after": following_active_after,
        "result": result,
        "error": error,
        "claim_boundary": API_ACTION_CLAIM_BOUNDARY,
        "audit_event": event,
        "timestamp": timestamp,
    }


def attach_legacy_action_audit(
    payload: Dict[str, Any],
    *,
    store: ApiActionStore,
    action_type: ActionType,
    internal_handler: str,
    following_active_before: Optional[bool],
    following_active_after: Optional[bool],
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Attach an audit record for an internal compatibility executor."""
    legacy_payload = dict(payload)
    legacy_payload.pop("action_audit", None)
    canonical_routes = {
        "offboard_start": API_V1_ACTION_OFFBOARD_START_PATH,
        "offboard_stop": API_V1_ACTION_OFFBOARD_STOP_PATH,
        "operator_abort": API_V1_ACTION_OPERATOR_ABORT_PATH,
        "segmentation_toggle": API_V1_ACTION_SEGMENTATION_TOGGLE_PATH,
        "smart_click": API_V1_ACTION_SMART_CLICK_PATH,
        "smart_mode_toggle": API_V1_ACTION_SMART_MODE_TOGGLE_PATH,
        "tracker_switch": API_V1_ACTION_TRACKER_SWITCH_PATH,
        "tracking_redetect": API_V1_ACTION_TRACKING_REDETECT_PATH,
        "tracking_start": API_V1_ACTION_TRACKING_START_PATH,
        "tracking_stop": API_V1_ACTION_TRACKING_STOP_PATH,
    }
    request = APIActionRequest(
        source="internal_compatibility",
        reason=internal_handler,
        confirm=True,
        metadata={
            "internal_handler": internal_handler,
            "canonical_route": canonical_routes[action_type],
        },
    )
    status_value: ActionStatus = (
        "success" if payload.get("status") == "success" and not error else "failure"
    )
    record = store.store_action_record(
        new_api_action_record(
            action_type=action_type,
            request=request,
            status_value=status_value,
            accepted=True,
            executed=True,
            following_active_before=following_active_before,
            following_active_after=following_active_after,
            result={
                "internal_compatibility_handler": internal_handler,
                "legacy_result": legacy_payload,
            },
            error=error,
        )
    )
    payload["action_audit"] = {
        "action_id": record["action_id"],
        "action_type": record["action_type"],
        "status": record["status"],
        "canonical_route": request.metadata["canonical_route"],
        "claim_boundary": record["claim_boundary"],
    }
    return payload


def build_action_precondition_failed_response(
    *,
    store: ApiActionStore,
    action_type: ActionType,
    request: APIActionRequest,
    path: str,
    code: str,
    message: str,
    following_active: bool,
) -> JSONResponse:
    """Record and return a typed precondition failure for control actions."""
    record = store.store_action_record(
        new_api_action_record(
            action_type=action_type,
            request=request,
            status_value="failure",
            accepted=False,
            executed=False,
            following_active_before=following_active,
            following_active_after=following_active,
            result={
                "precondition": code,
                "metadata": dict(request.metadata or {}),
            },
            error=message,
        )
    )
    return build_api_v1_error_response(
        status_code=status.HTTP_409_CONFLICT,
        code=code,
        detail={
            "message": message,
            "action_type": action_type,
            "action_id": record["action_id"],
        },
        path=path,
    )


async def start_offboard_action(
    owner: Any,
    request: APIActionRequest,
    response: Any,
) -> Any:
    """
    Execute the typed /api/v1 action resource for Offboard path startup.

    The action delegates to the existing compatibility handler only after
    explicit confirmation and idempotency validation. Its response records local
    PixEagle control-path state; it does not claim PX4-observed Offboard mode.
    """
    if not request.dry_run and request.confirm and not request.idempotency_key:
        return owner._idempotency_key_required_response(
            action_type="offboard_start",
            request=request,
            path=API_V1_ACTION_OFFBOARD_START_PATH,
        )
    lock = (
        None
        if request.dry_run or not request.confirm
        else owner._action_lock_for_key("offboard_start", request.idempotency_key)
    )
    if lock is None:
        return await start_offboard_action_unlocked(owner, request, response)
    async with lock:
        return await start_offboard_action_unlocked(owner, request, response)


async def start_offboard_action_unlocked(
    owner: Any,
    request: APIActionRequest,
    response: Any,
) -> Any:
    app_controller = owner.app_controller
    following_before = bool(getattr(app_controller, "following_active", False))

    if request.dry_run:
        response.status_code = status.HTTP_200_OK
        record = owner._new_api_action_record(
            action_type="offboard_start",
            request=request,
            status_value="validated",
            accepted=True,
            executed=False,
            following_active_before=following_before,
            following_active_after=following_before,
            result={
                "would_execute": "api_legacy_control_routes.start_offboard_mode",
                "message": "Dry-run validated; no Offboard command was executed.",
                "metadata": dict(request.metadata or {}),
            },
        )
        return owner._store_action_record(record)

    if not request.confirm:
        return owner._confirmation_required_response(
            action_type="offboard_start",
            request=request,
            path=API_V1_ACTION_OFFBOARD_START_PATH,
        )

    replay = owner._lookup_idempotent_action(
        "offboard_start",
        request.idempotency_key,
    )
    if replay:
        response.status_code = status.HTTP_200_OK
        return replay

    try:
        legacy_result = await owner._execute_offboard_start_action()
    except Exception as exc:
        following_after = bool(getattr(app_controller, "following_active", False))
        response.status_code = status.HTTP_202_ACCEPTED
        record = owner._new_api_action_record(
            action_type="offboard_start",
            request=request,
            status_value="failure",
            accepted=True,
            executed=True,
            following_active_before=following_before,
            following_active_after=following_after,
            result={
                "internal_compatibility_handler": "api_legacy_control_routes.start_offboard_mode",
                "metadata": dict(request.metadata or {}),
            },
            error=f"{type(exc).__name__}: {exc}",
        )
        return owner._store_action_record(record)

    following_after = bool(getattr(app_controller, "following_active", False))
    status_value = (
        "success"
        if legacy_result.get("status") == "success" and following_after
        else "failure"
    )
    error = None
    if status_value == "failure":
        error = (
            legacy_result.get("error")
            or "; ".join(legacy_result.get("details", {}).get("errors", []))
            or "Offboard action did not reach active local state."
        )

    response.status_code = status.HTTP_202_ACCEPTED
    record = owner._new_api_action_record(
        action_type="offboard_start",
        request=request,
        status_value=status_value,
        accepted=True,
        executed=True,
        following_active_before=following_before,
        following_active_after=following_after,
        result={
            "internal_compatibility_handler": "api_legacy_control_routes.start_offboard_mode",
            "legacy_result": legacy_result,
            "metadata": dict(request.metadata or {}),
        },
        error=error,
    )
    logger = getattr(owner, "logger", None)
    if logger is not None:
        logger.info(
            "Typed action %s completed with status=%s executed=%s",
            record["action_id"],
            record["status"],
            record["executed"],
        )
    return owner._store_action_record(record)


async def stop_offboard_action(
    owner: Any,
    request: APIActionRequest,
    response: Any,
) -> Any:
    """Execute the typed /api/v1 action resource for Offboard path shutdown."""
    if not request.dry_run and request.confirm and not request.idempotency_key:
        return owner._idempotency_key_required_response(
            action_type="offboard_stop",
            request=request,
            path=API_V1_ACTION_OFFBOARD_STOP_PATH,
        )
    lock = (
        None
        if request.dry_run or not request.confirm
        else owner._action_lock_for_key("offboard_stop", request.idempotency_key)
    )
    if lock is None:
        return await stop_offboard_action_unlocked(owner, request, response)
    async with lock:
        return await stop_offboard_action_unlocked(owner, request, response)


async def stop_offboard_action_unlocked(
    owner: Any,
    request: APIActionRequest,
    response: Any,
) -> Any:
    app_controller = owner.app_controller
    following_before = bool(getattr(app_controller, "following_active", False))

    if request.dry_run:
        response.status_code = status.HTTP_200_OK
        record = owner._new_api_action_record(
            action_type="offboard_stop",
            request=request,
            status_value="validated",
            accepted=True,
            executed=False,
            following_active_before=following_before,
            following_active_after=following_before,
            result={
                "would_execute": "api_legacy_control_routes.stop_offboard_mode",
                "message": "Dry-run validated; no Offboard stop was executed.",
                "metadata": dict(request.metadata or {}),
            },
        )
        return owner._store_action_record(record)

    if not request.confirm:
        return owner._confirmation_required_response(
            action_type="offboard_stop",
            request=request,
            path=API_V1_ACTION_OFFBOARD_STOP_PATH,
        )

    replay = owner._lookup_idempotent_action(
        "offboard_stop",
        request.idempotency_key,
    )
    if replay:
        response.status_code = status.HTTP_200_OK
        return replay

    try:
        legacy_result = await owner._execute_offboard_stop_action()
    except Exception as exc:
        following_after = bool(getattr(app_controller, "following_active", False))
        response.status_code = status.HTTP_202_ACCEPTED
        record = owner._new_api_action_record(
            action_type="offboard_stop",
            request=request,
            status_value="failure",
            accepted=True,
            executed=True,
            following_active_before=following_before,
            following_active_after=following_after,
            result={
                "internal_compatibility_handler": "api_legacy_control_routes.stop_offboard_mode",
                "metadata": dict(request.metadata or {}),
            },
            error=f"{type(exc).__name__}: {exc}",
        )
        return owner._store_action_record(record)

    following_after = bool(getattr(app_controller, "following_active", False))
    details = legacy_result.get("details", {})
    errors = details.get("errors", []) if isinstance(details, dict) else []
    status_value = (
        "success"
        if legacy_result.get("status") == "success" and not errors and not following_after
        else "failure"
    )
    error = "; ".join(errors) if errors else legacy_result.get("error")
    if status_value == "failure" and not error and following_after:
        error = "Offboard stop action did not leave local following inactive."

    response.status_code = status.HTTP_202_ACCEPTED
    record = owner._new_api_action_record(
        action_type="offboard_stop",
        request=request,
        status_value=status_value,
        accepted=True,
        executed=True,
        following_active_before=following_before,
        following_active_after=following_after,
        result={
            "internal_compatibility_handler": "api_legacy_control_routes.stop_offboard_mode",
            "legacy_result": legacy_result,
            "metadata": dict(request.metadata or {}),
        },
        error=error,
    )
    logger = getattr(owner, "logger", None)
    if logger is not None:
        logger.info(
            "Typed action %s completed with status=%s executed=%s",
            record["action_id"],
            record["status"],
            record["executed"],
        )
    return owner._store_action_record(record)


async def operator_abort_action(
    owner: Any,
    request: APIActionRequest,
    response: Any,
) -> Any:
    """Execute the typed /api/v1 action resource for operator abort/cancel."""
    if not request.dry_run and request.confirm and not request.idempotency_key:
        return owner._idempotency_key_required_response(
            action_type="operator_abort",
            request=request,
            path=API_V1_ACTION_OPERATOR_ABORT_PATH,
        )
    lock = (
        None
        if request.dry_run or not request.confirm
        else owner._action_lock_for_key("operator_abort", request.idempotency_key)
    )
    if lock is None:
        return await operator_abort_action_unlocked(owner, request, response)
    async with lock:
        return await operator_abort_action_unlocked(owner, request, response)


async def operator_abort_action_unlocked(
    owner: Any,
    request: APIActionRequest,
    response: Any,
) -> Any:
    app_controller = owner.app_controller
    following_before = bool(getattr(app_controller, "following_active", False))

    if request.dry_run:
        response.status_code = status.HTTP_200_OK
        record = owner._new_api_action_record(
            action_type="operator_abort",
            request=request,
            status_value="validated",
            accepted=True,
            executed=False,
            following_active_before=following_before,
            following_active_after=following_before,
            result={
                "would_execute": "api_legacy_control_routes.cancel_activities",
                "message": "Dry-run validated; no operator abort was executed.",
                "metadata": dict(request.metadata or {}),
            },
        )
        return owner._store_action_record(record)

    if not request.confirm:
        return owner._confirmation_required_response(
            action_type="operator_abort",
            request=request,
            path=API_V1_ACTION_OPERATOR_ABORT_PATH,
        )

    replay = owner._lookup_idempotent_action(
        "operator_abort",
        request.idempotency_key,
    )
    if replay:
        response.status_code = status.HTTP_200_OK
        return replay

    try:
        legacy_result = await owner._execute_operator_abort_action()
    except Exception as exc:
        following_after = bool(getattr(app_controller, "following_active", False))
        response.status_code = status.HTTP_202_ACCEPTED
        record = owner._new_api_action_record(
            action_type="operator_abort",
            request=request,
            status_value="failure",
            accepted=True,
            executed=True,
            following_active_before=following_before,
            following_active_after=following_after,
            result={
                "internal_compatibility_handler": "api_legacy_control_routes.cancel_activities",
                "metadata": dict(request.metadata or {}),
            },
            error=f"{type(exc).__name__}: {exc}",
        )
        return owner._store_action_record(record)

    following_after = bool(getattr(app_controller, "following_active", False))
    result_details = legacy_result.get("result", {})
    errors = result_details.get("errors", []) if isinstance(result_details, dict) else []
    status_value = (
        "success"
        if legacy_result.get("status") == "success" and not errors and not following_after
        else "failure"
    )
    error = "; ".join(errors) if errors else legacy_result.get("error")
    if status_value == "failure" and not error and following_after:
        error = "Operator abort action did not leave local following inactive."

    response.status_code = status.HTTP_202_ACCEPTED
    record = owner._new_api_action_record(
        action_type="operator_abort",
        request=request,
        status_value=status_value,
        accepted=True,
        executed=True,
        following_active_before=following_before,
        following_active_after=following_after,
        result={
            "internal_compatibility_handler": "api_legacy_control_routes.cancel_activities",
            "legacy_result": legacy_result,
            "metadata": dict(request.metadata or {}),
        },
        error=error,
    )
    logger = getattr(owner, "logger", None)
    if logger is not None:
        logger.info(
            "Typed action %s completed with status=%s executed=%s",
            record["action_id"],
            record["status"],
            record["executed"],
        )
    return owner._store_action_record(record)


def _tracking_bbox_payload(request: APITrackingStartRequest) -> Dict[str, Any]:
    bbox = request.bbox
    if hasattr(bbox, "model_dump"):
        return bbox.model_dump()
    return bbox.dict()


async def tracking_start_action(
    owner: Any,
    request: APITrackingStartRequest,
    response: Any,
) -> Any:
    """Execute the typed /api/v1 action resource for manual tracking start."""
    if not request.dry_run and request.confirm and not request.idempotency_key:
        return owner._idempotency_key_required_response(
            action_type="tracking_start",
            request=request,
            path=API_V1_ACTION_TRACKING_START_PATH,
        )
    lock = (
        None
        if request.dry_run or not request.confirm
        else owner._action_lock_for_key("tracking_start", request.idempotency_key)
    )
    if lock is None:
        return await tracking_start_action_unlocked(owner, request, response)
    async with lock:
        return await tracking_start_action_unlocked(owner, request, response)


async def tracking_start_action_unlocked(
    owner: Any,
    request: APITrackingStartRequest,
    response: Any,
) -> Any:
    app_controller = owner.app_controller
    following_before = bool(getattr(app_controller, "following_active", False))
    tracking_before = bool(getattr(app_controller, "tracking_started", False))
    bbox_payload = _tracking_bbox_payload(request)

    if request.dry_run:
        response.status_code = status.HTTP_200_OK
        record = owner._new_api_action_record(
            action_type="tracking_start",
            request=request,
            status_value="validated",
            accepted=True,
            executed=False,
            following_active_before=following_before,
            following_active_after=following_before,
            result={
                "would_execute": "FastAPIHandler._execute_tracking_start_action",
                "bbox": bbox_payload,
                "tracking_active_before": tracking_before,
                "tracking_active_after": tracking_before,
                "message": "Dry-run validated; no tracking start was executed.",
                "metadata": dict(request.metadata or {}),
            },
        )
        return owner._store_action_record(record)

    if not request.confirm:
        return owner._confirmation_required_response(
            action_type="tracking_start",
            request=request,
            path=API_V1_ACTION_TRACKING_START_PATH,
        )

    replay = owner._lookup_idempotent_action(
        "tracking_start",
        request.idempotency_key,
    )
    if replay:
        response.status_code = status.HTTP_200_OK
        return replay

    try:
        legacy_result = await owner._execute_tracking_start_action(request.bbox)
    except Exception as exc:
        following_after = bool(getattr(app_controller, "following_active", False))
        tracking_after = bool(getattr(app_controller, "tracking_started", False))
        response.status_code = status.HTTP_202_ACCEPTED
        record = owner._new_api_action_record(
            action_type="tracking_start",
            request=request,
            status_value="failure",
            accepted=True,
            executed=True,
            following_active_before=following_before,
            following_active_after=following_after,
            result={
                "internal_handler": "FastAPIHandler._execute_tracking_start_action",
                "bbox": bbox_payload,
                "tracking_active_before": tracking_before,
                "tracking_active_after": tracking_after,
                "metadata": dict(request.metadata or {}),
            },
            error=f"{type(exc).__name__}: {exc}",
        )
        return owner._store_action_record(record)

    following_after = bool(getattr(app_controller, "following_active", False))
    tracking_after = bool(getattr(app_controller, "tracking_started", False))
    status_value = "success" if legacy_result.get("status") == "Tracking started" else "failure"
    error = None if status_value == "success" else legacy_result.get("error")

    response.status_code = status.HTTP_202_ACCEPTED
    record = owner._new_api_action_record(
        action_type="tracking_start",
        request=request,
        status_value=status_value,
        accepted=True,
        executed=True,
        following_active_before=following_before,
        following_active_after=following_after,
        result={
            "internal_handler": "FastAPIHandler._execute_tracking_start_action",
            "legacy_result": legacy_result,
            "bbox": legacy_result.get("bbox", bbox_payload),
            "tracking_active_before": tracking_before,
            "tracking_active_after": tracking_after,
            "metadata": dict(request.metadata or {}),
        },
        error=error,
    )
    return owner._store_action_record(record)


async def tracking_stop_action(
    owner: Any,
    request: APIActionRequest,
    response: Any,
) -> Any:
    """Execute the typed /api/v1 action resource for manual tracking stop."""
    if not request.dry_run and request.confirm and not request.idempotency_key:
        return owner._idempotency_key_required_response(
            action_type="tracking_stop",
            request=request,
            path=API_V1_ACTION_TRACKING_STOP_PATH,
        )
    lock = (
        None
        if request.dry_run or not request.confirm
        else owner._action_lock_for_key("tracking_stop", request.idempotency_key)
    )
    if lock is None:
        return await tracking_stop_action_unlocked(owner, request, response)
    async with lock:
        return await tracking_stop_action_unlocked(owner, request, response)


async def tracking_stop_action_unlocked(
    owner: Any,
    request: APIActionRequest,
    response: Any,
) -> Any:
    app_controller = owner.app_controller
    following_before = bool(getattr(app_controller, "following_active", False))
    tracking_before = bool(getattr(app_controller, "tracking_started", False))

    if request.dry_run:
        response.status_code = status.HTTP_200_OK
        record = owner._new_api_action_record(
            action_type="tracking_stop",
            request=request,
            status_value="validated",
            accepted=True,
            executed=False,
            following_active_before=following_before,
            following_active_after=following_before,
            result={
                "would_execute": "FastAPIHandler._execute_tracking_stop_action",
                "tracking_active_before": tracking_before,
                "tracking_active_after": tracking_before,
                "message": "Dry-run validated; no tracking stop was executed.",
                "metadata": dict(request.metadata or {}),
            },
        )
        return owner._store_action_record(record)

    if not request.confirm:
        return owner._confirmation_required_response(
            action_type="tracking_stop",
            request=request,
            path=API_V1_ACTION_TRACKING_STOP_PATH,
        )

    replay = owner._lookup_idempotent_action(
        "tracking_stop",
        request.idempotency_key,
    )
    if replay:
        response.status_code = status.HTTP_200_OK
        return replay

    try:
        legacy_result = await owner._execute_tracking_stop_action()
    except Exception as exc:
        following_after = bool(getattr(app_controller, "following_active", False))
        tracking_after = bool(getattr(app_controller, "tracking_started", False))
        response.status_code = status.HTTP_202_ACCEPTED
        record = owner._new_api_action_record(
            action_type="tracking_stop",
            request=request,
            status_value="failure",
            accepted=True,
            executed=True,
            following_active_before=following_before,
            following_active_after=following_after,
            result={
                "internal_handler": "FastAPIHandler._execute_tracking_stop_action",
                "tracking_active_before": tracking_before,
                "tracking_active_after": tracking_after,
                "metadata": dict(request.metadata or {}),
            },
            error=f"{type(exc).__name__}: {exc}",
        )
        return owner._store_action_record(record)

    following_after = bool(getattr(app_controller, "following_active", False))
    tracking_after = bool(getattr(app_controller, "tracking_started", False))
    result_details = legacy_result.get("result", {})
    errors = result_details.get("errors", []) if isinstance(result_details, dict) else []
    status_value = (
        "success"
        if legacy_result.get("status") == "Tracking stopped" and not errors
        else "failure"
    )
    error = "; ".join(errors) if errors else legacy_result.get("error")

    response.status_code = status.HTTP_202_ACCEPTED
    record = owner._new_api_action_record(
        action_type="tracking_stop",
        request=request,
        status_value=status_value,
        accepted=True,
        executed=True,
        following_active_before=following_before,
        following_active_after=following_after,
        result={
            "internal_handler": "FastAPIHandler._execute_tracking_stop_action",
            "legacy_result": legacy_result,
            "tracking_active_before": tracking_before,
            "tracking_active_after": tracking_after,
            "metadata": dict(request.metadata or {}),
        },
        error=error,
    )
    return owner._store_action_record(record)


def _tracking_click_payload(request: APITrackingSmartClickRequest) -> Dict[str, Any]:
    click = request.click
    if hasattr(click, "model_dump"):
        return click.model_dump()
    return click.dict()


def _runtime_action_state(owner: Any) -> Dict[str, Any]:
    app_controller = owner.app_controller
    tracker = getattr(app_controller, "tracker", None)
    return {
        "following_active": bool(getattr(app_controller, "following_active", False)),
        "tracking_active": bool(getattr(app_controller, "tracking_started", False)),
        "segmentation_active": bool(
            getattr(app_controller, "segmentation_active", False)
        ),
        "smart_mode_active": bool(getattr(app_controller, "smart_mode_active", False)),
        "configured_tracker": getattr(app_controller, "current_tracker_type", None),
        "active_tracker_class": tracker.__class__.__name__ if tracker else None,
    }


async def _guarded_runtime_action(
    owner: Any,
    request: APIActionRequest,
    response: Any,
    *,
    action_type: ActionType,
    path: str,
    unlocked,
) -> Any:
    if not request.dry_run and request.confirm and not request.idempotency_key:
        return owner._idempotency_key_required_response(
            action_type=action_type,
            request=request,
            path=path,
        )
    lock = (
        None
        if request.dry_run or not request.confirm
        else owner._action_lock_for_key(action_type, request.idempotency_key)
    )
    if lock is None:
        return await unlocked(owner, request, response)
    async with lock:
        return await unlocked(owner, request, response)


async def _runtime_action_unlocked(
    owner: Any,
    request: APIActionRequest,
    response: Any,
    *,
    action_type: ActionType,
    path: str,
    internal_handler: str,
    dry_run_message: str,
    execute,
    classify_result,
    extra_result: Optional[Dict[str, Any]] = None,
) -> Any:
    before = _runtime_action_state(owner)
    extra_result = dict(extra_result or {})

    if request.dry_run:
        response.status_code = status.HTTP_200_OK
        record = owner._new_api_action_record(
            action_type=action_type,
            request=request,
            status_value="validated",
            accepted=True,
            executed=False,
            following_active_before=before["following_active"],
            following_active_after=before["following_active"],
            result={
                "would_execute": internal_handler,
                "message": dry_run_message,
                "state_before": before,
                "state_after": before,
                "metadata": dict(request.metadata or {}),
                **extra_result,
            },
        )
        return owner._store_action_record(record)

    if not request.confirm:
        return owner._confirmation_required_response(
            action_type=action_type,
            request=request,
            path=path,
        )

    replay = owner._lookup_idempotent_action(action_type, request.idempotency_key)
    if replay:
        response.status_code = status.HTTP_200_OK
        return replay

    try:
        legacy_result = await execute()
    except Exception as exc:
        after = _runtime_action_state(owner)
        response.status_code = status.HTTP_202_ACCEPTED
        record = owner._new_api_action_record(
            action_type=action_type,
            request=request,
            status_value="failure",
            accepted=True,
            executed=True,
            following_active_before=before["following_active"],
            following_active_after=after["following_active"],
            result={
                "internal_handler": internal_handler,
                "state_before": before,
                "state_after": after,
                "metadata": dict(request.metadata or {}),
                **extra_result,
            },
            error=f"{type(exc).__name__}: {exc}",
        )
        return owner._store_action_record(record)

    after = _runtime_action_state(owner)
    status_value, error = classify_result(legacy_result, before, after)
    response.status_code = status.HTTP_202_ACCEPTED
    record = owner._new_api_action_record(
        action_type=action_type,
        request=request,
        status_value=status_value,
        accepted=True,
        executed=True,
        following_active_before=before["following_active"],
        following_active_after=after["following_active"],
        result={
            "internal_handler": internal_handler,
            "legacy_result": legacy_result,
            "state_before": before,
            "state_after": after,
            "metadata": dict(request.metadata or {}),
            **extra_result,
        },
        error=error,
    )
    return owner._store_action_record(record)


def _tracking_redetect_result(
    legacy_result: Dict[str, Any],
    _before: Dict[str, bool],
    _after: Dict[str, bool],
) -> tuple[ActionStatus, Optional[str]]:
    detection = legacy_result.get("detection_result", {})
    success = bool(isinstance(detection, dict) and detection.get("success") is True)
    if legacy_result.get("status") == "success" and success:
        return "success", None
    error = (
        detection.get("message")
        if isinstance(detection, dict)
        else legacy_result.get("error")
    )
    return "failure", error or "Re-detection did not reacquire a target."


def _segmentation_toggle_result(
    legacy_result: Dict[str, Any],
    _before: Dict[str, bool],
    _after: Dict[str, bool],
) -> tuple[ActionStatus, Optional[str]]:
    if legacy_result.get("status") == "success" and "segmentation_active" in legacy_result:
        return "success", None
    return "failure", legacy_result.get("error") or "Segmentation toggle failed."


def _smart_mode_toggle_result(
    legacy_result: Dict[str, Any],
    before: Dict[str, bool],
    after: Dict[str, bool],
) -> tuple[ActionStatus, Optional[str]]:
    changed = before["smart_mode_active"] != after["smart_mode_active"]
    if str(legacy_result.get("status", "")).startswith("Smart mode") and changed:
        return "success", None
    return (
        "failure",
        legacy_result.get("error") or "Smart mode state did not change.",
    )


def _smart_click_result(
    legacy_result: Dict[str, Any],
    _before: Dict[str, bool],
    _after: Dict[str, bool],
) -> tuple[ActionStatus, Optional[str]]:
    if (
        legacy_result.get("status") == "Click processed"
        and legacy_result.get("applied") is True
    ):
        return "success", None
    return (
        "failure",
        legacy_result.get("message")
        or legacy_result.get("error")
        or "Smart click was not applied.",
    )


def _tracker_switch_validation_error(tracker_type: str) -> Optional[str]:
    try:
        from classes.schema_manager import get_schema_manager

        is_valid, error_msg = get_schema_manager().validate_tracker_for_ui(
            tracker_type
        )
    except Exception as exc:
        return f"Tracker catalog validation unavailable: {type(exc).__name__}: {exc}"

    if is_valid:
        return None
    return error_msg or f"Tracker type {tracker_type!r} is not selectable."


def _tracker_switch_validation_failed_response(
    owner: Any,
    request: APITrackerSwitchRequest,
    *,
    message: str,
) -> JSONResponse:
    following_current = bool(getattr(owner.app_controller, "following_active", False))
    record = owner._store_action_record(
        owner._new_api_action_record(
            action_type="tracker_switch",
            request=request,
            status_value="failure",
            accepted=False,
            executed=False,
            following_active_before=following_current,
            following_active_after=following_current,
            result={
                "precondition": "ACTION_TRACKER_SWITCH_INVALID",
                "requested_tracker": request.tracker_type,
                "metadata": dict(request.metadata or {}),
            },
            error=message,
        )
    )
    return build_api_v1_error_response(
        status_code=status.HTTP_409_CONFLICT,
        code="ACTION_TRACKER_SWITCH_INVALID",
        detail={
            "message": message,
            "action_type": "tracker_switch",
            "action_id": record["action_id"],
            "requested_tracker": request.tracker_type,
        },
        path=API_V1_ACTION_TRACKER_SWITCH_PATH,
    )


def _tracker_switch_result(
    legacy_result: Dict[str, Any],
    _before: Dict[str, Any],
    after: Dict[str, Any],
) -> tuple[ActionStatus, Optional[str]]:
    requested_tracker = legacy_result.get("new_tracker") or legacy_result.get(
        "requested_tracker"
    )
    configured_tracker = after.get("configured_tracker")
    success_payload = (
        legacy_result.get("status") == "success"
        and legacy_result.get("action") == "tracker_switched"
    )
    if success_payload and (
        not requested_tracker or configured_tracker == requested_tracker
    ):
        return "success", None

    if success_payload:
        return (
            "failure",
            (
                "Tracker switch reported success but configured tracker is "
                f"{configured_tracker!r}, not {requested_tracker!r}."
            ),
        )
    return (
        "failure",
        legacy_result.get("error")
        or legacy_result.get("message")
        or "Tracker switch failed.",
    )


async def tracker_switch_action(
    owner: Any,
    request: APITrackerSwitchRequest,
    response: Any,
) -> Any:
    """Execute the typed /api/v1 action resource for tracker switching."""
    return await _guarded_runtime_action(
        owner,
        request,
        response,
        action_type="tracker_switch",
        path=API_V1_ACTION_TRACKER_SWITCH_PATH,
        unlocked=tracker_switch_action_unlocked,
    )


async def tracker_switch_action_unlocked(
    owner: Any,
    request: APITrackerSwitchRequest,
    response: Any,
) -> Any:
    if not request.dry_run and not request.confirm:
        return owner._confirmation_required_response(
            action_type="tracker_switch",
            request=request,
            path=API_V1_ACTION_TRACKER_SWITCH_PATH,
        )

    validation_error = _tracker_switch_validation_error(request.tracker_type)
    if validation_error:
        return _tracker_switch_validation_failed_response(
            owner,
            request,
            message=validation_error,
        )

    async def execute():
        return await owner._execute_tracker_switch_action(request.tracker_type)

    return await _runtime_action_unlocked(
        owner,
        request,
        response,
        action_type="tracker_switch",
        path=API_V1_ACTION_TRACKER_SWITCH_PATH,
        internal_handler="api_legacy_tracker_routes.switch_tracker_to_type",
        dry_run_message="Dry-run validated; tracker type was not switched.",
        execute=execute,
        classify_result=_tracker_switch_result,
        extra_result={"requested_tracker": request.tracker_type},
    )


async def tracking_redetect_action(
    owner: Any,
    request: APIActionRequest,
    response: Any,
) -> Any:
    """Execute the typed /api/v1 action resource for classic re-detection."""
    return await _guarded_runtime_action(
        owner,
        request,
        response,
        action_type="tracking_redetect",
        path=API_V1_ACTION_TRACKING_REDETECT_PATH,
        unlocked=tracking_redetect_action_unlocked,
    )


async def tracking_redetect_action_unlocked(
    owner: Any,
    request: APIActionRequest,
    response: Any,
) -> Any:
    return await _runtime_action_unlocked(
        owner,
        request,
        response,
        action_type="tracking_redetect",
        path=API_V1_ACTION_TRACKING_REDETECT_PATH,
        internal_handler="FastAPIHandler._execute_tracking_redetect_action",
        dry_run_message="Dry-run validated; no re-detection was executed.",
        execute=owner._execute_tracking_redetect_action,
        classify_result=_tracking_redetect_result,
    )


async def segmentation_toggle_action(
    owner: Any,
    request: APIActionRequest,
    response: Any,
) -> Any:
    """Execute the typed /api/v1 action resource for segmentation toggle."""
    return await _guarded_runtime_action(
        owner,
        request,
        response,
        action_type="segmentation_toggle",
        path=API_V1_ACTION_SEGMENTATION_TOGGLE_PATH,
        unlocked=segmentation_toggle_action_unlocked,
    )


async def segmentation_toggle_action_unlocked(
    owner: Any,
    request: APIActionRequest,
    response: Any,
) -> Any:
    return await _runtime_action_unlocked(
        owner,
        request,
        response,
        action_type="segmentation_toggle",
        path=API_V1_ACTION_SEGMENTATION_TOGGLE_PATH,
        internal_handler="FastAPIHandler._execute_segmentation_toggle_action",
        dry_run_message="Dry-run validated; segmentation was not toggled.",
        execute=owner._execute_segmentation_toggle_action,
        classify_result=_segmentation_toggle_result,
    )


async def smart_mode_toggle_action(
    owner: Any,
    request: APIActionRequest,
    response: Any,
) -> Any:
    """Execute the typed /api/v1 action resource for smart-mode toggle."""
    return await _guarded_runtime_action(
        owner,
        request,
        response,
        action_type="smart_mode_toggle",
        path=API_V1_ACTION_SMART_MODE_TOGGLE_PATH,
        unlocked=smart_mode_toggle_action_unlocked,
    )


async def smart_mode_toggle_action_unlocked(
    owner: Any,
    request: APIActionRequest,
    response: Any,
) -> Any:
    return await _runtime_action_unlocked(
        owner,
        request,
        response,
        action_type="smart_mode_toggle",
        path=API_V1_ACTION_SMART_MODE_TOGGLE_PATH,
        internal_handler="FastAPIHandler._execute_smart_mode_toggle_action",
        dry_run_message="Dry-run validated; smart mode was not toggled.",
        execute=owner._execute_smart_mode_toggle_action,
        classify_result=_smart_mode_toggle_result,
    )


async def smart_click_action(
    owner: Any,
    request: APITrackingSmartClickRequest,
    response: Any,
) -> Any:
    """Execute the typed /api/v1 action resource for smart-tracker click."""
    return await _guarded_runtime_action(
        owner,
        request,
        response,
        action_type="smart_click",
        path=API_V1_ACTION_SMART_CLICK_PATH,
        unlocked=smart_click_action_unlocked,
    )


async def smart_click_action_unlocked(
    owner: Any,
    request: APITrackingSmartClickRequest,
    response: Any,
) -> Any:
    click_payload = _tracking_click_payload(request)

    async def execute():
        return await owner._execute_smart_click_action(request.click)

    return await _runtime_action_unlocked(
        owner,
        request,
        response,
        action_type="smart_click",
        path=API_V1_ACTION_SMART_CLICK_PATH,
        internal_handler="FastAPIHandler._execute_smart_click_action",
        dry_run_message="Dry-run validated; no smart click was executed.",
        execute=execute,
        classify_result=_smart_click_result,
        extra_result={"click": click_payload},
    )


async def get_action_resource(owner: Any, action_id: str) -> Any:
    """Return a tracked in-process /api/v1 action resource."""
    record = owner._ensure_action_store().get_action_record(action_id)

    if record is None:
        return owner._api_v1_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ACTION_NOT_FOUND",
            detail={"action_id": action_id},
            path=f"{API_V1_ACTION_RESOURCE_PREFIX}/{action_id}",
        )
    return record


__all__ = [
    "API_ACTION_CLAIM_BOUNDARY",
    "ActionStatus",
    "ActionType",
    "ApiActionStore",
    "attach_legacy_action_audit",
    "build_action_precondition_failed_response",
    "ensure_api_action_store",
    "get_action_resource",
    "new_api_action_record",
    "operator_abort_action",
    "operator_abort_action_unlocked",
    "segmentation_toggle_action",
    "segmentation_toggle_action_unlocked",
    "smart_click_action",
    "smart_click_action_unlocked",
    "smart_mode_toggle_action",
    "smart_mode_toggle_action_unlocked",
    "start_offboard_action",
    "start_offboard_action_unlocked",
    "stop_offboard_action",
    "stop_offboard_action_unlocked",
    "tracker_switch_action",
    "tracker_switch_action_unlocked",
    "tracking_redetect_action",
    "tracking_redetect_action_unlocked",
    "tracking_start_action",
    "tracking_start_action_unlocked",
    "tracking_stop_action",
    "tracking_stop_action_unlocked",
]

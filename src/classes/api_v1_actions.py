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

from classes.api_v1_contracts import APIActionRequest
from classes.api_v1_errors import build_api_v1_error_response
from classes.api_v1_paths import (
    API_V1_ACTION_OFFBOARD_START_PATH,
    API_V1_ACTION_OPERATOR_ABORT_PATH,
)

API_ACTION_CLAIM_BOUNDARY = (
    "This action resource records a PixEagle API/control-path request only; "
    "PX4-observed mode, setpoint cadence, SITL, HIL, or field success require "
    "separate evidence artifacts."
)

ActionType = Literal["offboard_start", "operator_abort"]
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
    route: str,
    following_active_before: Optional[bool],
    following_active_after: Optional[bool],
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Attach a process-local action audit record to legacy command routes."""
    legacy_payload = dict(payload)
    legacy_payload.pop("action_audit", None)
    request = APIActionRequest(
        source="legacy_compatibility",
        reason=route,
        confirm=True,
        metadata={
            "legacy_route": route,
            "canonical_route": (
                API_V1_ACTION_OFFBOARD_START_PATH
                if action_type == "offboard_start"
                else API_V1_ACTION_OPERATOR_ABORT_PATH
            ),
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
                "legacy_compatibility_route": route,
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


__all__ = [
    "API_ACTION_CLAIM_BOUNDARY",
    "ActionStatus",
    "ActionType",
    "ApiActionStore",
    "attach_legacy_action_audit",
    "build_action_precondition_failed_response",
    "ensure_api_action_store",
    "new_api_action_record",
]

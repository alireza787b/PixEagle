"""Authenticated, generation-guarded circuit-breaker state for native clients."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets

from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from classes.api_security_types import APIPrincipalKind
from classes.api_v1_contracts import APINativeSafetySnapshot
from classes.circuit_breaker import FollowerCircuitBreaker
from classes.parameters import Parameters
from classes.runtime_identity import INSTANCE_ID, RUNTIME_ID


_GENERATION_KEY = secrets.token_bytes(32)


def safety_snapshot(owner, principal):
    activation = FollowerCircuitBreaker.get_activation_state()
    persisted = owner._get_config_service().get_path_value(
        ["FOLLOWER_CIRCUIT_BREAKER"], default=None,
    )
    active = activation["active"] if activation["available"] else None
    persisted_active = persisted if type(persisted) is bool else None
    following = bool(getattr(owner.app_controller, "following_active", False))
    preview = str(getattr(Parameters, "FOLLOWER_EXECUTION_MODE", "PX4")).upper() == "COMMAND_PREVIEW"
    consistent = active is not None and active == persisted_active
    writable = principal is None or "safety:write" in principal.scopes
    reason = None
    if not consistent:
        reason = "circuit_breaker_state_unavailable"
    elif following:
        reason = "following_active"
    elif not writable:
        reason = "safety_permission_required"
    fields = dict(instance_id=INSTANCE_ID, runtime_id=RUNTIME_ID, active=active,
                  persisted_active=persisted_active, follower_test=preview, following_active=following)
    generation = hmac.new(_GENERATION_KEY, json.dumps(fields, sort_keys=True).encode(), hashlib.sha256).hexdigest()
    return APINativeSafetySnapshot(
        **fields, state_generation=generation, available=consistent,
        can_set=reason is None, reason_code=reason,
    ).model_dump(mode="json")


def native_safety_context_matches(owner, context):
    current = safety_snapshot(owner, None)
    return (current["can_set"] and context.instance_id == current["instance_id"]
            and context.runtime_id == current["runtime_id"]
            and context.state_generation == current["state_generation"]
            and context.expected_active is current["active"])


async def get_native_safety(owner, request):
    principal = getattr(getattr(request, "state", None), "api_principal", None)
    if principal is None or principal.kind not in (APIPrincipalKind.SESSION, APIPrincipalKind.BEARER):
        return owner._api_v1_error_response(
            status_code=401, code="native_credentials_required",
            detail="Sign in to read PixEagle safety status.", path="/api/v1/integration/safety",
        )
    if "safety:read" not in principal.scopes:
        return owner._api_v1_error_response(
            status_code=403, code="safety_permission_required",
            detail="Safety status permission is required.", path="/api/v1/integration/safety",
        )
    try:
        payload = await run_in_threadpool(safety_snapshot, owner, principal)
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})
    except Exception:
        return owner._api_v1_error_response(
            status_code=503, code="native_safety_unavailable",
            detail="PixEagle safety status is unavailable.", path="/api/v1/integration/safety",
        )

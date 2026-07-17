"""Typed /api/v1 browser-session auth routes."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Request, Response, status
from starlette.concurrency import run_in_threadpool

from classes.api_auth_runtime import APISessionRecord, APIUserRecord
from classes.browser_user_store import (
    BrowserUserConflictError,
    BrowserUserInvariantError,
    BrowserUserNotFoundError,
    BrowserUserPersistenceError,
    BrowserUserPublicRecord,
    BrowserUserStoreError,
    BrowserUserValidationError,
    normalize_username,
)
from classes.api_security_types import (
    APIAuditPolicy,
    APIPrincipal,
    APIPrincipalKind,
    APISensitivity,
)
from classes.api_v1_contracts import (
    APIAuthLoginRequest,
    APIAuthLoginResponse,
    APIAuthLogoutResponse,
    APIAuthPasswordChangeRequest,
    APIAuthPasswordChangeResponse,
    APIAuthPrincipal,
    APIAuthSessionResponse,
    APIAuthUserCreateRequest,
    APIAuthUserDeleteRequest,
    APIAuthUserDeleteResponse,
    APIAuthUserMutationResponse,
    APIAuthUserSummary,
    APIAuthUsersResponse,
    APIAuthUserUpdateRequest,
)
from classes.api_v1_paths import (
    API_V1_AUTH_LOGIN_PATH,
    API_V1_AUTH_LOGOUT_PATH,
    API_V1_AUTH_PASSWORD_PATH,
    API_V1_AUTH_USER_PATH,
    API_V1_AUTH_USERS_PATH,
)


def _session_principal_payload(principal: APIPrincipal) -> APIAuthPrincipal:
    if principal.kind == APIPrincipalKind.SESSION:
        return APIAuthPrincipal(
            kind="session",
            subject=principal.subject,
            role=principal.role,
            scopes=sorted(principal.scopes),
            session_id=None,
        )
    return APIAuthPrincipal(
        kind="anonymous",
        subject="anonymous",
        role=None,
        scopes=[],
        session_id=None,
    )


def _principal_from_request(request: Request) -> APIPrincipal:
    return getattr(request.state, "api_principal", APIPrincipal.anonymous())


def _set_session_cookie(
    owner: Any,
    response: Response,
    session: APISessionRecord,
) -> None:
    runtime = owner.api_auth_runtime
    response.set_cookie(
        key=runtime.session_cookie_name,
        value=session.session_id,
        max_age=runtime.session_ttl_seconds,
        expires=runtime.session_ttl_seconds,
        path="/",
        secure=runtime.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _clear_session_cookie(owner: Any, response: Response) -> None:
    response.delete_cookie(
        key=owner.api_auth_runtime.session_cookie_name,
        path="/",
        samesite="lax",
    )


def _login_attempt_key(request: Request, username: str) -> str:
    client_host = getattr(getattr(request, "client", None), "host", "") or "unknown"
    return f"{client_host}:{str(username or '').strip().lower()}"


def _public_user_payload(record: BrowserUserPublicRecord) -> APIAuthUserSummary:
    return APIAuthUserSummary(
        username=record.username,
        role=record.role,
        enabled=record.enabled,
    )


def _account_error_response(owner: Any, *, path: str, exc: BrowserUserStoreError):
    if isinstance(exc, BrowserUserNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (BrowserUserConflictError, BrowserUserInvariantError)):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, BrowserUserValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif isinstance(exc, BrowserUserPersistenceError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return owner._api_v1_error_response(
        status_code=status_code,
        code=getattr(exc, "code", "browser_user_store_error"),
        detail=str(exc),
        path=path,
    )


def _session_is_self(principal: APIPrincipal, username: str) -> bool:
    return (
        principal.kind == APIPrincipalKind.SESSION
        and principal.subject.strip().lower() == normalize_username(username)
    )


def _account_runtime_is_configured(owner: Any) -> bool:
    runtime = owner.api_auth_runtime
    return runtime.browser_sessions_enabled and runtime.user_store is not None


def _account_runtime_unavailable(owner: Any, path: str):
    return owner._api_v1_error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="browser_user_store_not_configured",
        detail=(
            "Browser-user management requires API_AUTH_MODE=browser_session "
            "with an external API_SESSION_USER_FILE."
        ),
        path=path,
    )


def _password_hash_capacity_response(
    owner: Any,
    *,
    request: Request,
    path: str,
    event_type: str,
    principal: APIPrincipal,
    metadata: Optional[dict[str, Any]] = None,
):
    _record_auth_route_audit(
        owner,
        request=request,
        event_type=event_type,
        outcome="denied",
        reason="password_hash_capacity_limited",
        path=path,
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        principal=principal,
        metadata=metadata,
    )
    capacity_response = owner._api_v1_error_response(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code="password_hash_capacity_limited",
        detail="Password hashing or verification is busy. Retry shortly.",
        path=path,
    )
    capacity_response.headers["Retry-After"] = "1"
    return capacity_response


def _record_auth_route_audit(
    owner: Any,
    *,
    request: Request,
    event_type: str,
    outcome: str,
    reason: str,
    path: str,
    status_code: int,
    principal: APIPrincipal,
    metadata: Optional[dict[str, Any]] = None,
) -> bool:
    recorder = getattr(owner, "_record_security_audit_event", None)
    if recorder is None:
        return True
    return recorder(
        event_type=event_type,
        outcome=outcome,
        reason=reason,
        transport="http",
        method=getattr(request, "method", None),
        path=path,
        status_code=status_code,
        principal=principal,
        audit_policy=APIAuditPolicy.SECURITY_CRITICAL,
        sensitivity=APISensitivity.SYSTEM,
        client_host=getattr(getattr(request, "client", None), "host", None),
        host_header=request.headers.get("host"),
        origin=request.headers.get("origin"),
        sec_fetch_site=request.headers.get("sec-fetch-site"),
        request_id=request.headers.get("x-request-id"),
        metadata=metadata,
    )


async def get_auth_session(owner: Any, request: Request) -> APIAuthSessionResponse:
    """Return current browser session state without exposing cookie secrets."""
    runtime = owner.api_auth_runtime
    principal = _principal_from_request(request)
    session: Optional[APISessionRecord] = runtime.session_record_for_principal(principal)
    session_principal = principal if session is not None else APIPrincipal.anonymous()
    return APIAuthSessionResponse(
        authenticated=session is not None,
        auth_mode=runtime.mode,
        principal=_session_principal_payload(session_principal),
        csrf_required=runtime.browser_sessions_enabled,
        csrf_header_name=runtime.csrf_header_name,
        csrf_token=session.csrf_token if session is not None else None,
        expires_at=session.expires_at if session is not None else None,
    )


async def login_auth_session(
    owner: Any,
    http_request: Request,
    request: APIAuthLoginRequest,
    response: Response,
) -> Any:
    """Create an HttpOnly browser/operator session from a verified user record."""
    runtime = owner.api_auth_runtime
    if not runtime.browser_sessions_enabled:
        return owner._api_v1_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="browser_session_auth_not_configured",
            detail=(
                "Set API_AUTH_MODE=browser_session and provide an external "
                "API_SESSION_USER_FILE to use browser sessions."
            ),
            path=API_V1_AUTH_LOGIN_PATH,
        )

    attempt_key = _login_attempt_key(http_request, request.username)
    allowed, retry_after = runtime.login_attempt_allowed(attempt_key)
    if not allowed:
        _record_auth_route_audit(
            owner,
            request=http_request,
            event_type="api.auth.login",
            outcome="denied",
            reason="login_rate_limited",
            path=API_V1_AUTH_LOGIN_PATH,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            principal=APIPrincipal.anonymous(),
            metadata={"username": str(request.username or "").strip().lower()},
        )
        throttle_response = owner._api_v1_error_response(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="login_rate_limited",
            detail="Too many failed login attempts. Retry after the throttle window.",
            path=API_V1_AUTH_LOGIN_PATH,
        )
        if retry_after is not None:
            throttle_response.headers["Retry-After"] = str(retry_after)
        return throttle_response

    if not runtime.try_acquire_password_hash_slot():
        _record_auth_route_audit(
            owner,
            request=http_request,
            event_type="api.auth.login",
            outcome="denied",
            reason="login_capacity_limited",
            path=API_V1_AUTH_LOGIN_PATH,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            principal=APIPrincipal.anonymous(),
            metadata={"username": str(request.username or "").strip().lower()},
        )
        capacity_response = owner._api_v1_error_response(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="login_capacity_limited",
            detail="Password verification is busy. Retry shortly.",
            path=API_V1_AUTH_LOGIN_PATH,
        )
        capacity_response.headers["Retry-After"] = "1"
        return capacity_response

    try:
        authenticated = await run_in_threadpool(
            runtime.authenticate_and_create_session,
            username=request.username,
            password=request.password,
        )
    finally:
        runtime.release_password_hash_slot()
    if authenticated is None:
        runtime.record_login_failure(attempt_key)
        _record_auth_route_audit(
            owner,
            request=http_request,
            event_type="api.auth.login",
            outcome="denied",
            reason="invalid_credentials",
            path=API_V1_AUTH_LOGIN_PATH,
            status_code=status.HTTP_401_UNAUTHORIZED,
            principal=APIPrincipal.anonymous(),
            metadata={"username": str(request.username or "").strip().lower()},
        )
        return owner._api_v1_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_credentials",
            detail="Username or password is invalid.",
            path=API_V1_AUTH_LOGIN_PATH,
        )

    _user, session = authenticated
    runtime.clear_login_failures(attempt_key)
    _set_session_cookie(owner, response, session)
    principal = APIPrincipal.session(
        username=session.username,
        role=session.role,
        session_id=session.session_id,
    )
    audit_ok = _record_auth_route_audit(
        owner,
        request=http_request,
        event_type="api.auth.login",
        outcome="allowed",
        reason="login_success",
        path=API_V1_AUTH_LOGIN_PATH,
        status_code=status.HTTP_200_OK,
        principal=principal,
        metadata={"role": session.role},
    )
    if not audit_ok:
        runtime.revoke_session_id(session.session_id)
        _clear_session_cookie(owner, response)
        error_response = owner._api_v1_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="security_audit_unavailable",
            detail="API security audit event could not be recorded.",
            path=API_V1_AUTH_LOGIN_PATH,
        )
        _clear_session_cookie(owner, error_response)
        return error_response
    return APIAuthLoginResponse(
        auth_mode=runtime.mode,
        principal=_session_principal_payload(principal),
        csrf_header_name=runtime.csrf_header_name,
        csrf_token=session.csrf_token,
        expires_at=session.expires_at,
    )


async def logout_auth_session(
    owner: Any,
    request: Request,
    response: Response,
) -> Any:
    """Revoke the current browser/operator session."""
    runtime = owner.api_auth_runtime
    principal = _principal_from_request(request)
    session = runtime.session_record_for_principal(principal)
    if session is None:
        _clear_session_cookie(owner, response)
        _record_auth_route_audit(
            owner,
            request=request,
            event_type="api.auth.logout",
            outcome="denied",
            reason="session_required",
            path=API_V1_AUTH_LOGOUT_PATH,
            status_code=status.HTTP_401_UNAUTHORIZED,
            principal=principal,
        )
        error_response = owner._api_v1_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="session_required",
            detail="A browser session is required to log out.",
            path=API_V1_AUTH_LOGOUT_PATH,
        )
        _clear_session_cookie(owner, error_response)
        return error_response

    audit_ok = _record_auth_route_audit(
        owner,
        request=request,
        event_type="api.auth.logout",
        outcome="allowed",
        reason="logout_success",
        path=API_V1_AUTH_LOGOUT_PATH,
        status_code=status.HTTP_200_OK,
        principal=principal,
    )
    revoked = runtime.revoke_session_id(session.session_id)
    _clear_session_cookie(owner, response)
    if not audit_ok:
        error_response = owner._api_v1_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="security_audit_unavailable",
            detail="API security audit event could not be recorded.",
            path=API_V1_AUTH_LOGOUT_PATH,
        )
        _clear_session_cookie(owner, error_response)
        return error_response

    return APIAuthLogoutResponse(revoked=revoked, auth_mode=runtime.mode)


async def get_auth_users(owner: Any, request: Request) -> Any:
    """Return admin-only credential-free browser-user metadata."""
    if not _account_runtime_is_configured(owner):
        return _account_runtime_unavailable(owner, API_V1_AUTH_USERS_PATH)
    return APIAuthUsersResponse(
        users=[
            _public_user_payload(record)
            for record in owner.api_auth_runtime.browser_user_public_snapshot()
        ]
    )


async def create_auth_user(
    owner: Any,
    http_request: Request,
    request: APIAuthUserCreateRequest,
) -> Any:
    """Create one browser user and publish the committed runtime snapshot."""
    if not _account_runtime_is_configured(owner):
        return _account_runtime_unavailable(owner, API_V1_AUTH_USERS_PATH)
    runtime = owner.api_auth_runtime
    principal = _principal_from_request(http_request)
    target = str(request.username or "").strip().lower()
    audit_metadata = {
        "target_username": target,
        "role": request.role,
        "enabled": request.enabled,
    }
    if not runtime.try_acquire_password_hash_slot():
        return _password_hash_capacity_response(
            owner,
            request=http_request,
            path=API_V1_AUTH_USERS_PATH,
            event_type="api.auth.user.create",
            principal=principal,
            metadata=audit_metadata,
        )
    try:
        if not _record_auth_route_audit(
            owner,
            request=http_request,
            event_type="api.auth.user.create",
            outcome="allowed",
            reason="browser_user_create_authorized",
            path=API_V1_AUTH_USERS_PATH,
            status_code=status.HTTP_201_CREATED,
            principal=principal,
            metadata=audit_metadata,
        ):
            return owner._api_v1_error_response(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="security_audit_unavailable",
                detail="API security audit event could not be recorded.",
                path=API_V1_AUTH_USERS_PATH,
            )
        try:
            result = await run_in_threadpool(
                runtime.create_browser_user,
                username=request.username,
                password=request.password,
                role=request.role,
                enabled=request.enabled,
            )
        except BrowserUserStoreError as exc:
            return _account_error_response(owner, path=API_V1_AUTH_USERS_PATH, exc=exc)
    finally:
        runtime.release_password_hash_slot()
    assert result.record is not None
    return APIAuthUserMutationResponse(
        user=_public_user_payload(result.record),
        sessions_revoked=0,
    )


async def update_auth_user(
    owner: Any,
    username: str,
    http_request: Request,
    request: APIAuthUserUpdateRequest,
) -> Any:
    """Update role, enablement, or password for one browser user."""
    if not _account_runtime_is_configured(owner):
        return _account_runtime_unavailable(owner, API_V1_AUTH_USER_PATH)
    principal = _principal_from_request(http_request)
    fields = request.model_fields_set
    if not fields:
        return owner._api_v1_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="browser_user_update_empty",
            detail="Set at least one of role, enabled, or password.",
            path=API_V1_AUTH_USER_PATH,
        )
    null_fields = sorted(
        field_name
        for field_name in fields
        if getattr(request, field_name, None) is None
    )
    if null_fields:
        return owner._api_v1_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="browser_user_update_null",
            detail=(
                "Account update fields cannot be null: "
                + ", ".join(null_fields)
            ),
            path=API_V1_AUTH_USER_PATH,
        )
    try:
        is_self = _session_is_self(principal, username)
    except BrowserUserValidationError as exc:
        return _account_error_response(owner, path=API_V1_AUTH_USER_PATH, exc=exc)
    if is_self and (
        request.password is not None
        or request.enabled is False
        or (request.role is not None and request.role != "admin")
    ):
        return owner._api_v1_error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="browser_user_self_admin_update_rejected",
            detail=(
                "Administrators cannot disable, demote, or reset their own account "
                "through the admin route. Use /api/v1/auth/password for a self password change."
            ),
            path=API_V1_AUTH_USER_PATH,
        )
    runtime = owner.api_auth_runtime
    audit_metadata = {
        "target_username": str(username or "").strip().lower(),
        "fields": sorted(fields),
    }
    hash_slot_acquired = False
    if request.password is not None:
        hash_slot_acquired = runtime.try_acquire_password_hash_slot()
        if not hash_slot_acquired:
            return _password_hash_capacity_response(
                owner,
                request=http_request,
                path=API_V1_AUTH_USER_PATH,
                event_type="api.auth.user.update",
                principal=principal,
                metadata=audit_metadata,
            )
    try:
        if not _record_auth_route_audit(
            owner,
            request=http_request,
            event_type="api.auth.user.update",
            outcome="allowed",
            reason="browser_user_update_authorized",
            path=API_V1_AUTH_USER_PATH,
            status_code=status.HTTP_200_OK,
            principal=principal,
            metadata=audit_metadata,
        ):
            return owner._api_v1_error_response(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="security_audit_unavailable",
                detail="API security audit event could not be recorded.",
                path=API_V1_AUTH_USER_PATH,
            )
        try:
            result, revoked = await run_in_threadpool(
                runtime.update_browser_user,
                username,
                role=request.role,
                enabled=request.enabled,
                password=request.password,
            )
        except BrowserUserStoreError as exc:
            return _account_error_response(owner, path=API_V1_AUTH_USER_PATH, exc=exc)
    finally:
        if hash_slot_acquired:
            runtime.release_password_hash_slot()
    assert result.record is not None
    return APIAuthUserMutationResponse(
        user=_public_user_payload(result.record),
        sessions_revoked=revoked,
    )


async def delete_auth_user(
    owner: Any,
    username: str,
    http_request: Request,
    request: APIAuthUserDeleteRequest,
) -> Any:
    """Delete one non-self browser user after explicit username confirmation."""
    if not _account_runtime_is_configured(owner):
        return _account_runtime_unavailable(owner, API_V1_AUTH_USER_PATH)
    principal = _principal_from_request(http_request)
    try:
        normalized_username = normalize_username(username)
        confirmation = normalize_username(request.confirm_username)
    except BrowserUserValidationError as exc:
        return _account_error_response(owner, path=API_V1_AUTH_USER_PATH, exc=exc)
    if confirmation != normalized_username:
        return owner._api_v1_error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="browser_user_delete_confirmation_mismatch",
            detail="confirm_username must exactly identify the user being deleted.",
            path=API_V1_AUTH_USER_PATH,
        )
    if _session_is_self(principal, normalized_username):
        return owner._api_v1_error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="browser_user_self_delete_rejected",
            detail="Administrators cannot delete their own active account.",
            path=API_V1_AUTH_USER_PATH,
        )
    if not _record_auth_route_audit(
        owner,
        request=http_request,
        event_type="api.auth.user.delete",
        outcome="allowed",
        reason="browser_user_delete_authorized",
        path=API_V1_AUTH_USER_PATH,
        status_code=status.HTTP_200_OK,
        principal=principal,
        metadata={"target_username": normalized_username},
    ):
        return owner._api_v1_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="security_audit_unavailable",
            detail="API security audit event could not be recorded.",
            path=API_V1_AUTH_USER_PATH,
        )
    try:
        _result, revoked = await run_in_threadpool(
            owner.api_auth_runtime.delete_browser_user,
            normalized_username,
        )
    except BrowserUserStoreError as exc:
        return _account_error_response(owner, path=API_V1_AUTH_USER_PATH, exc=exc)
    return APIAuthUserDeleteResponse(
        username=normalized_username,
        sessions_revoked=revoked,
    )


async def change_auth_password(
    owner: Any,
    http_request: Request,
    request: APIAuthPasswordChangeRequest,
    response: Response,
) -> Any:
    """Change the current browser user's password and replace all old sessions."""
    if not _account_runtime_is_configured(owner):
        return _account_runtime_unavailable(owner, API_V1_AUTH_PASSWORD_PATH)
    runtime = owner.api_auth_runtime
    principal = _principal_from_request(http_request)
    if (
        principal.kind != APIPrincipalKind.SESSION
        or runtime.session_record_for_principal(principal) is None
    ):
        return owner._api_v1_error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            code="browser_session_required",
            detail="A current browser session is required to change its password.",
            path=API_V1_AUTH_PASSWORD_PATH,
        )
    attempt_key = _login_attempt_key(http_request, principal.subject)
    allowed, retry_after = runtime.login_attempt_allowed(attempt_key)
    if not allowed:
        _record_auth_route_audit(
            owner,
            request=http_request,
            event_type="api.auth.password.change",
            outcome="denied",
            reason="password_change_rate_limited",
            path=API_V1_AUTH_PASSWORD_PATH,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            principal=principal,
        )
        throttle_response = owner._api_v1_error_response(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="password_change_rate_limited",
            detail="Too many failed current-password attempts. Retry after the throttle window.",
            path=API_V1_AUTH_PASSWORD_PATH,
        )
        if retry_after is not None:
            throttle_response.headers["Retry-After"] = str(retry_after)
        return throttle_response
    if not runtime.try_acquire_password_hash_slot():
        return _password_hash_capacity_response(
            owner,
            request=http_request,
            path=API_V1_AUTH_PASSWORD_PATH,
            event_type="api.auth.password.change",
            principal=principal,
        )
    try:
        if not _record_auth_route_audit(
            owner,
            request=http_request,
            event_type="api.auth.password.change",
            outcome="allowed",
            reason="browser_password_change_authorized",
            path=API_V1_AUTH_PASSWORD_PATH,
            status_code=status.HTTP_200_OK,
            principal=principal,
        ):
            return owner._api_v1_error_response(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="security_audit_unavailable",
                detail="API security audit event could not be recorded.",
                path=API_V1_AUTH_PASSWORD_PATH,
            )
        try:
            changed = await run_in_threadpool(
                runtime.change_browser_user_password,
                username=principal.subject,
                current_password=request.current_password,
                new_password=request.new_password,
            )
        except BrowserUserStoreError as exc:
            return _account_error_response(owner, path=API_V1_AUTH_PASSWORD_PATH, exc=exc)
    finally:
        runtime.release_password_hash_slot()
    if changed is None:
        runtime.record_login_failure(attempt_key)
        _record_auth_route_audit(
            owner,
            request=http_request,
            event_type="api.auth.password.change",
            outcome="denied",
            reason="current_password_invalid",
            path=API_V1_AUTH_PASSWORD_PATH,
            status_code=status.HTTP_401_UNAUTHORIZED,
            principal=principal,
        )
        return owner._api_v1_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="current_password_invalid",
            detail="The current password is invalid.",
            path=API_V1_AUTH_PASSWORD_PATH,
        )
    runtime.clear_login_failures(attempt_key)
    _result, replacement, revoked = changed
    _set_session_cookie(owner, response, replacement)
    replacement_principal = APIPrincipal.session(
        username=replacement.username,
        role=replacement.role,
        session_id=replacement.session_id,
    )
    return APIAuthPasswordChangeResponse(
        auth_mode=runtime.mode,
        principal=_session_principal_payload(replacement_principal),
        csrf_header_name=runtime.csrf_header_name,
        csrf_token=replacement.csrf_token,
        expires_at=replacement.expires_at,
        sessions_revoked=revoked,
    )


__all__ = [
    "change_auth_password",
    "create_auth_user",
    "delete_auth_user",
    "get_auth_session",
    "get_auth_users",
    "login_auth_session",
    "logout_auth_session",
    "update_auth_user",
]

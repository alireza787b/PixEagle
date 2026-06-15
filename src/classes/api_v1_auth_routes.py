"""Typed /api/v1 browser-session auth routes."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Request, Response, status

from classes.api_auth_runtime import APISessionRecord, APIUserRecord
from classes.api_security_types import APIPrincipal, APIPrincipalKind
from classes.api_v1_contracts import (
    APIAuthLoginRequest,
    APIAuthLoginResponse,
    APIAuthLogoutResponse,
    APIAuthPrincipal,
    APIAuthSessionResponse,
)
from classes.api_v1_paths import (
    API_V1_AUTH_LOGIN_PATH,
    API_V1_AUTH_LOGOUT_PATH,
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
        throttle_response = owner._api_v1_error_response(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="login_rate_limited",
            detail="Too many failed login attempts. Retry after the throttle window.",
            path=API_V1_AUTH_LOGIN_PATH,
        )
        if retry_after is not None:
            throttle_response.headers["Retry-After"] = str(retry_after)
        return throttle_response

    user: Optional[APIUserRecord] = runtime.authenticate_user(
        username=request.username,
        password=request.password,
    )
    if user is None:
        runtime.record_login_failure(attempt_key)
        return owner._api_v1_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_credentials",
            detail="Username or password is invalid.",
            path=API_V1_AUTH_LOGIN_PATH,
        )

    session = runtime.create_session_for_user(user)
    runtime.clear_login_failures(attempt_key)
    _set_session_cookie(owner, response, session)
    principal = APIPrincipal.session(
        username=session.username,
        role=session.role,
        session_id=session.session_id,
    )
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
        return owner._api_v1_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="session_required",
            detail="A browser session is required to log out.",
            path=API_V1_AUTH_LOGOUT_PATH,
        )

    revoked = runtime.revoke_session_id(session.session_id)
    _clear_session_cookie(owner, response)
    return APIAuthLogoutResponse(revoked=revoked, auth_mode=runtime.mode)


__all__ = [
    "get_auth_session",
    "login_auth_session",
    "logout_auth_session",
]

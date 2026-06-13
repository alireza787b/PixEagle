"""Runtime authentication and route authorization helpers for PixEagle APIs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import parse_qs

from classes.api_exposure_policy import APIExposurePolicy, is_loopback_host
from classes.api_security_policy import resolve_route_security_policy
from classes.api_security_types import (
    APIAuthorizationDecision,
    APIPrincipal,
    APIPrincipalKind,
    authorize_api_request,
)


API_AUTH_MODE_LOCAL_COMPAT = "local_compat"
API_AUTH_MODE_MACHINE_BEARER = "machine_bearer"
SUPPORTED_API_AUTH_MODES = frozenset(
    {
        API_AUTH_MODE_LOCAL_COMPAT,
        API_AUTH_MODE_MACHINE_BEARER,
    }
)
TOKEN_QUERY_KEYS = frozenset({"access_token", "api_key", "token"})
FORWARDED_CLIENT_HEADER_NAMES = frozenset(
    {
        "forwarded",
        "x-forwarded-for",
        "x-real-ip",
        "x-client-ip",
        "cf-connecting-ip",
        "true-client-ip",
    }
)


class APIAuthConfigurationError(ValueError):
    """Raised when API authentication configuration is unsafe or invalid."""


@dataclass(frozen=True)
class BearerTokenRecord:
    """One hashed, revocable machine-token record."""

    token_id: str
    subject: str
    token_sha256: str
    scopes: frozenset[str]
    enabled: bool = True
    expires_at: Optional[datetime] = None

    def is_active(self, *, now: Optional[datetime] = None) -> bool:
        if not self.enabled:
            return False
        if self.expires_at is None:
            return True
        current = now or datetime.now(timezone.utc)
        return current < self.expires_at


@dataclass(frozen=True)
class APIAuthRuntime:
    """Authentication runtime used by HTTP and WebSocket route guards."""

    mode: str
    bearer_tokens_by_hash: Mapping[str, BearerTokenRecord] = MappingProxyType({})
    token_file: Optional[Path] = None

    def __post_init__(self) -> None:
        normalized_mode = str(self.mode or "").strip().lower()
        if normalized_mode not in SUPPORTED_API_AUTH_MODES:
            supported = ", ".join(sorted(SUPPORTED_API_AUTH_MODES))
            raise APIAuthConfigurationError(
                f"Unsupported API auth mode {self.mode!r}; supported modes: {supported}"
            )
        object.__setattr__(self, "mode", normalized_mode)
        object.__setattr__(
            self,
            "bearer_tokens_by_hash",
            MappingProxyType(dict(self.bearer_tokens_by_hash or {})),
        )
        if normalized_mode == API_AUTH_MODE_MACHINE_BEARER and not any(
            record.enabled for record in self.bearer_tokens_by_hash.values()
        ):
            raise APIAuthConfigurationError(
                "API_AUTH_MODE=machine_bearer requires at least one enabled "
                "bearer token record"
            )

    @property
    def local_compat_enabled(self) -> bool:
        return self.mode == API_AUTH_MODE_LOCAL_COMPAT

    def principal_from_authorization_header(
        self,
        authorization_header: Optional[str],
    ) -> tuple[APIPrincipal, Optional[str]]:
        """Return a principal plus an authentication failure reason when present."""
        scheme, credential = _parse_authorization_header(authorization_header)
        if scheme is None and credential is None:
            return APIPrincipal.anonymous(), None
        if scheme != "bearer" or not credential:
            return APIPrincipal.anonymous(), "unsupported_authorization_scheme"

        token_hash = hash_bearer_token(credential)
        record = self.bearer_tokens_by_hash.get(token_hash)
        if record is None:
            return APIPrincipal.anonymous(), "invalid_bearer_token"
        if not record.is_active():
            return APIPrincipal.anonymous(), "inactive_bearer_token"

        return (
            APIPrincipal.bearer(
                token_id=record.token_id,
                subject=record.subject,
                scopes=record.scopes,
            ),
            None,
        )


@dataclass(frozen=True)
class APITransportAuthorizationResult:
    """HTTP/WebSocket authorization result with no credential material."""

    allowed: bool
    status_code: int
    reason: str
    principal: APIPrincipal
    decision: APIAuthorizationDecision
    missing_scopes: tuple[str, ...] = ()

    @property
    def is_authentication_failure(self) -> bool:
        return self.status_code == 401


def hash_bearer_token(token: str) -> str:
    """Hash a high-entropy bearer token for storage and lookup."""
    raw = str(token or "").strip()
    if not raw:
        raise APIAuthConfigurationError("Bearer token must not be empty")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_bearer_token_records(path: Path) -> tuple[BearerTokenRecord, ...]:
    """Load machine bearer token records from JSON outside checked-in config."""
    token_path = Path(path).expanduser()
    if not token_path.exists():
        raise APIAuthConfigurationError(f"API bearer token file does not exist: {token_path}")

    try:
        payload = json.loads(token_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise APIAuthConfigurationError(f"Invalid API bearer token JSON: {token_path}") from exc

    raw_records = payload.get("tokens") if isinstance(payload, dict) else payload
    if not isinstance(raw_records, list):
        raise APIAuthConfigurationError("API bearer token file must contain a tokens list")

    records = tuple(
        _parse_bearer_token_record(item, index)
        for index, item in enumerate(raw_records)
    )
    hashes = [record.token_sha256 for record in records]
    if len(hashes) != len(set(hashes)):
        raise APIAuthConfigurationError("Duplicate API bearer token hashes are not allowed")
    return records


def resolve_api_auth_runtime_from_parameters(parameters) -> APIAuthRuntime:
    """Build the API auth runtime from flattened Parameters without secrets."""
    raw_config = getattr(parameters, "_raw_config", {})
    raw_streaming = raw_config.get("Streaming", {}) if isinstance(raw_config, dict) else {}
    if not isinstance(raw_streaming, dict):
        raw_streaming = {}

    mode = raw_streaming.get(
        "API_AUTH_MODE",
        getattr(parameters, "API_AUTH_MODE", API_AUTH_MODE_LOCAL_COMPAT),
    )
    token_file_value = raw_streaming.get(
        "API_BEARER_TOKEN_FILE",
        getattr(parameters, "API_BEARER_TOKEN_FILE", ""),
    )
    token_path = _normalize_optional_token_path(token_file_value)
    records = load_bearer_token_records(token_path) if token_path is not None else ()
    return APIAuthRuntime(
        mode=mode,
        bearer_tokens_by_hash={record.token_sha256: record for record in records},
        token_file=token_path,
    )


def authorize_http_request(
    *,
    runtime: APIAuthRuntime,
    method: str,
    path: str,
    headers: Mapping[str, str],
    client_host: Optional[str],
    host_header: Optional[str],
    exposure_policy: APIExposurePolicy,
    query_params: Optional[Mapping[str, Any]] = None,
) -> APITransportAuthorizationResult:
    """Authorize one HTTP route after exposure Host/Origin checks pass."""
    return _authorize_transport(
        runtime=runtime,
        method=method,
        path=path,
        headers=headers,
        client_host=client_host,
        host_header=host_header,
        exposure_policy=exposure_policy,
        query_params=query_params,
    )


def authorize_websocket_request(
    *,
    runtime: APIAuthRuntime,
    path: str,
    headers: Mapping[str, str],
    client_host: Optional[str],
    host_header: Optional[str],
    exposure_policy: APIExposurePolicy,
    query_string: str = "",
) -> APITransportAuthorizationResult:
    """Authorize one WebSocket route before accept()."""
    return _authorize_transport(
        runtime=runtime,
        method="WEBSOCKET",
        path=path,
        headers=headers,
        client_host=client_host,
        host_header=host_header,
        exposure_policy=exposure_policy,
        query_params=parse_qs(query_string, keep_blank_values=True),
    )


def is_loopback_transport_client(
    *,
    client_host: Optional[str],
    host_header: Optional[str],
    exposure_policy: APIExposurePolicy,
    headers: Optional[Mapping[str, str]] = None,
) -> bool:
    """Identify local-compat clients from the socket peer, not HTTP Host."""
    _ = host_header, exposure_policy
    if has_proxy_forwarded_client_headers(headers):
        return False
    return is_loopback_host(client_host or "")


def has_proxy_forwarded_client_headers(
    headers: Optional[Mapping[str, str]],
) -> bool:
    """Return true when a proxy/client-forwarding identity header is present."""
    if not headers:
        return False
    return any(
        bool(str(_header_get(headers, header_name) or "").strip())
        for header_name in FORWARDED_CLIENT_HEADER_NAMES
    )


def make_token_record(
    *,
    token_id: str,
    plaintext_token: str,
    scopes: Iterable[str],
    subject: str = "machine-client",
    enabled: bool = True,
) -> dict[str, Any]:
    """Build a token-file record for tests/tools without logging secrets."""
    return {
        "token_id": token_id,
        "subject": subject,
        "token_sha256": hash_bearer_token(plaintext_token),
        "scopes": list(scopes),
        "enabled": enabled,
    }


def _authorize_transport(
    *,
    runtime: APIAuthRuntime,
    method: str,
    path: str,
    headers: Mapping[str, str],
    client_host: Optional[str],
    host_header: Optional[str],
    exposure_policy: APIExposurePolicy,
    query_params: Optional[Mapping[str, Any]],
) -> APITransportAuthorizationResult:
    anonymous = APIPrincipal.anonymous()
    policy = resolve_route_security_policy(method, path)
    if _contains_query_token(query_params):
        return _result(False, 401, "query_token_not_supported", anonymous)

    is_loopback_client = is_loopback_transport_client(
        client_host=client_host,
        host_header=host_header,
        exposure_policy=exposure_policy,
        headers=headers,
    )
    forwarded_loopback_peer = (
        is_loopback_host(client_host or "")
        and has_proxy_forwarded_client_headers(headers)
    )
    principal, auth_error = runtime.principal_from_authorization_header(
        _header_get(headers, "authorization")
    )
    if auth_error is not None:
        return _result(False, 401, auth_error, anonymous)

    if principal.kind == APIPrincipalKind.ANONYMOUS:
        if runtime.local_compat_enabled and is_loopback_client:
            principal = APIPrincipal.local_compat()
        elif runtime.local_compat_enabled and forwarded_loopback_peer:
            return _result(
                False,
                401,
                "proxy_forwarded_local_compat_not_allowed",
                anonymous,
            )

    decision = authorize_api_request(
        policy=policy,
        principal=principal,
        is_loopback_client=is_loopback_client,
        csrf_valid=False,
    )
    if decision.allowed:
        return APITransportAuthorizationResult(
            allowed=True,
            status_code=200,
            reason="allowed",
            principal=principal,
            decision=decision,
        )

    status_code = 401 if decision.reason == "authentication_required" else 403
    return APITransportAuthorizationResult(
        allowed=False,
        status_code=status_code,
        reason=decision.reason,
        principal=principal,
        decision=decision,
        missing_scopes=decision.missing_scopes,
    )


def _parse_bearer_token_record(raw: Any, index: int) -> BearerTokenRecord:
    if not isinstance(raw, dict):
        raise APIAuthConfigurationError(f"Token record {index} must be an object")

    token_id = str(raw.get("token_id") or "").strip()
    subject = str(raw.get("subject") or token_id).strip()
    token_sha256 = str(raw.get("token_sha256") or "").strip().lower()
    scopes = raw.get("scopes")
    enabled = bool(raw.get("enabled", True))
    expires_at = _parse_optional_datetime(raw.get("expires_at"), index)

    if not token_id:
        raise APIAuthConfigurationError(f"Token record {index} missing token_id")
    if not subject:
        raise APIAuthConfigurationError(f"Token record {index} missing subject")
    if len(token_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in token_sha256
    ):
        raise APIAuthConfigurationError(
            f"Token record {token_id!r} has invalid token_sha256"
        )
    if not isinstance(scopes, list) or not scopes:
        raise APIAuthConfigurationError(f"Token record {token_id!r} must declare scopes")

    try:
        principal = APIPrincipal.bearer(
            token_id=token_id,
            subject=subject,
            scopes=scopes,
        )
    except ValueError as exc:
        raise APIAuthConfigurationError(str(exc)) from exc

    return BearerTokenRecord(
        token_id=token_id,
        subject=subject,
        token_sha256=token_sha256,
        scopes=principal.scopes,
        enabled=enabled,
        expires_at=expires_at,
    )


def _parse_authorization_header(header: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    raw = str(header or "").strip()
    if not raw:
        return None, None
    parts = raw.split(None, 1)
    if len(parts) != 2:
        return raw.lower(), None
    return parts[0].lower(), parts[1].strip()


def _parse_optional_datetime(value: Any, index: int) -> Optional[datetime]:
    if value in {None, ""}:
        return None
    if not isinstance(value, str):
        raise APIAuthConfigurationError(
            f"Token record {index} expires_at must be a string"
        )
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise APIAuthConfigurationError(
            f"Token record {index} has invalid expires_at"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_optional_token_path(value: Any) -> Optional[Path]:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def _contains_query_token(query_params: Optional[Mapping[str, Any]]) -> bool:
    if not query_params:
        return False
    return any(str(key).lower() in TOKEN_QUERY_KEYS for key in query_params.keys())


def _header_get(headers: Mapping[str, str], name: str) -> Optional[str]:
    if not hasattr(headers, "get"):
        return None
    target = name.lower()
    if hasattr(headers, "items"):
        for key, value in headers.items():
            if str(key).lower() == target:
                return value
    return headers.get(name) or headers.get(name.title())


def _result(
    allowed: bool,
    status_code: int,
    reason: str,
    principal: APIPrincipal,
) -> APITransportAuthorizationResult:
    return APITransportAuthorizationResult(
        allowed=allowed,
        status_code=status_code,
        reason=reason,
        principal=principal,
        decision=APIAuthorizationDecision(allowed, reason),
    )


__all__ = [
    "API_AUTH_MODE_LOCAL_COMPAT",
    "API_AUTH_MODE_MACHINE_BEARER",
    "APIAuthConfigurationError",
    "APIAuthRuntime",
    "APITransportAuthorizationResult",
    "BearerTokenRecord",
    "FORWARDED_CLIENT_HEADER_NAMES",
    "SUPPORTED_API_AUTH_MODES",
    "authorize_http_request",
    "authorize_websocket_request",
    "hash_bearer_token",
    "has_proxy_forwarded_client_headers",
    "is_loopback_transport_client",
    "load_bearer_token_records",
    "make_token_record",
    "resolve_api_auth_runtime_from_parameters",
]
